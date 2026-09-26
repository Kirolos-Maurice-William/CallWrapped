import os
import re
import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List, Set
import httpx
from bot.config import config

logger = logging.getLogger("GroqClient")


def parse_reset_duration(header_val: Optional[str]) -> float:
    """
    Parses rate limit reset duration from headers (e.g. '134ms', '250ms', '27m21.6s', '2m30s', '45s', '42').
    Checks 'ms' FIRST and returns early. Accumulates compound formats (hours, minutes, seconds).
    """
    if not header_val:
        return 2.0
    val = str(header_val).strip()

    # 1. Check 'ms' FIRST and return early (e.g. '250ms' -> 0.25, '134ms' -> 0.134)
    m_ms = re.search(r"(\d+(?:\.\d+)?)\s*ms", val)
    if m_ms:
        return float(m_ms.group(1)) / 1000.0

    # 2. Raw numeric value in seconds
    try:
        return max(0.001, float(val))
    except ValueError:
        pass

    # 3. Accumulate compound formats: 'h' hours, 'm(?!s)' minutes, 's' seconds
    total_sec = 0.0

    m_h = re.search(r"(\d+(?:\.\d+)?)\s*h", val)
    if m_h:
        total_sec += float(m_h.group(1)) * 3600.0

    m_min = re.search(r"(\d+(?:\.\d+)?)\s*m(?!s)", val)
    if m_min:
        total_sec += float(m_min.group(1)) * 60.0

    m_sec = re.search(r"(\d+(?:\.\d+)?)\s*s(?:ec)?", val)
    if m_sec:
        total_sec += float(m_sec.group(1))

    return round(total_sec, 4) if total_sec > 0 else 2.0


class KeyPool:
    """Manages a pool of Groq API keys with token-budget tracking and 429 rotation."""

    def __init__(self):
        self.keys: List[Dict[str, Any]] = []
        self._init_pool()

    def _init_pool(self):
        candidates = [
            ("key#1", getattr(config, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")),
        ]
        # Dynamically discover all secondary keys: GROQ_API_KEY_2, GROQ_API_KEY_3, ...
        i = 2
        while True:
            extra_key = getattr(config, f"GROQ_API_KEY_{i}", "") or os.getenv(f"GROQ_API_KEY_{i}", "")
            if not extra_key or not extra_key.strip():
                break
            candidates.append((f"key#{i}", extra_key))
            i += 1

        for key_id, raw_key in candidates:
            if raw_key and raw_key.strip():
                self.keys.append({
                    "id": key_id,
                    "key": raw_key.strip(),
                    "remaining_tokens": 100000,
                    "reset_time": 0.0
                })

    def remove_key(self, key_id: str, reason: str = "invalid (401)"):
        """Permanently removes an invalid key from the pool for the remainder of the session."""
        before_count = len(self.keys)
        self.keys = [k for k in self.keys if k["id"] != key_id]
        if len(self.keys) < before_count:
            logger.warning(f"⚠️ [GroqClient] {key_id} {reason} — removed from pool ({len(self.keys)} keys remaining)")

    def select_key(self) -> Optional[Dict[str, Any]]:
        """Selects the key with MORE remaining tokens, respecting cool-down."""
        if not self.keys:
            return None
        if len(self.keys) == 1:
            return self.keys[0]

        now = time.time()
        available = [k for k in self.keys if now >= k["reset_time"]]
        if not available:
            # All in 429 cool-down; pick the one that resets sooner
            return min(self.keys, key=lambda k: k["reset_time"])

        # Pick key with more remaining tokens (key#1 on tie)
        best = max(available, key=lambda k: k["remaining_tokens"])
        return best

    def get_other_key(self, current_key: Dict[str, Any], excluded_ids: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
        """Returns the alternate key if available, prioritizing available keys with most remaining tokens."""
        if excluded_ids is None:
            excluded = {current_key["id"]}
        else:
            excluded = set(excluded_ids) | {current_key["id"]}

        others = [k for k in self.keys if k["id"] not in excluded]
        if not others:
            return None

        now = time.time()
        available = [k for k in others if now >= k["reset_time"]]
        if available:
            return max(available, key=lambda k: k["remaining_tokens"])
        return min(others, key=lambda k: k["reset_time"])

    def update_headers(self, key_entry: Dict[str, Any], headers: httpx.Headers, status_code: int = 200):
        """Updates remaining tokens and reset time from response headers, or removes invalid keys."""
        if status_code in (401, 403):
            self.remove_key(key_entry["id"], reason=f"invalid ({status_code})")
            return
        if status_code == 429:
            key_entry["remaining_tokens"] = 0
            return
        rem = headers.get("x-ratelimit-remaining-tokens")
        if rem is not None:
            try:
                key_entry["remaining_tokens"] = int(rem)
            except ValueError:
                pass


class GroqClient:
    """High-speed Groq LPU client with multi-key rotation and token-budget balancing (~150ms)."""

    def __init__(self):
        self.pool = KeyPool()
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.default_model = config.GROQ_MODEL
        self.last_used_key_id: Optional[str] = None
        self.last_used_key_remaining: Optional[int] = None

    async def complete_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.0
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, int], int]:
        """
        Executes a chat completion against Groq LPU with multi-key rotation.
        Returns (parsed_dict, tokens_dict, latency_ms).
        """
        k = self.pool.select_key()
        if not k:
            logger.warning("[GroqClient] No valid Groq API keys available")
            return None, {}, 0

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        elif response_format:
            payload["response_format"] = response_format

        t0 = time.perf_counter()
        resp = None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {k['key']}",
                    "Content-Type": "application/json"
                }
                resp = await client.post(self.url, headers=headers, json=payload)
                self.pool.update_headers(k, resp.headers, resp.status_code)

                # HTTP 429 / 401 / 403: Immediately retry with other keys in pool
                attempted_ids = {k["id"]}
                while resp.status_code in (401, 403, 429):
                    if resp.status_code == 429:
                        wait_sec = parse_reset_duration(
                            resp.headers.get("retry-after") or
                            resp.headers.get("x-ratelimit-reset-tokens")
                        )
                        k["remaining_tokens"] = 0
                        k["reset_time"] = time.time() + wait_sec

                    k_next = self.pool.get_other_key(k, excluded_ids=attempted_ids)
                    if k_next:
                        prev_id = k["id"]
                        prev_status = resp.status_code
                        attempted_ids.add(k_next["id"])
                        headers_next = {
                            "Authorization": f"Bearer {k_next['key']}",
                            "Content-Type": "application/json"
                        }
                        resp_next = await client.post(self.url, headers=headers_next, json=payload)
                        self.pool.update_headers(k_next, resp_next.headers, resp_next.status_code)

                        if resp_next.status_code == 200:
                            logger.info(f"🔄 [{prev_id} {prev_status} → {k_next['id']} retry ok]")
                            resp = resp_next
                            k = k_next
                            break
                        else:
                            resp = resp_next
                            k = k_next
                    else:
                        # All keys in pool exhausted
                        break

                if resp.status_code == 429:
                    sleep_wait = min(
                        max(0.0, key_entry["reset_time"] - time.time())
                        for key_entry in self.pool.keys
                    ) if self.pool.keys else 0.0

                    keys_count = len(self.pool.keys)
                    keys_label = "Both keys" if keys_count == 2 else f"All {keys_count} keys"
                    if sleep_wait > 2.0:
                        logger.warning(
                            f"⚠️ [GroqClient] {keys_label} hit 429 with long resets ({sleep_wait:.1f}s > 2.0s). Skipping request."
                        )
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        return None, {}, latency_ms
                    elif sleep_wait > 0 and self.pool.keys:
                        logger.warning(f"⚠️ [GroqClient] {keys_label} hit 429. Waiting {sleep_wait:.2f}s reset...")
                        await asyncio.sleep(sleep_wait)
                        k_best = min(self.pool.keys, key=lambda x: x["reset_time"])
                        h_best = {"Authorization": f"Bearer {k_best['key']}", "Content-Type": "application/json"}
                        resp = await client.post(self.url, headers=h_best, json=payload)
                        self.pool.update_headers(k_best, resp.headers, resp.status_code)
                        k = k_best

        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(f"⚠️ [GroqClient] Network exception via {k['id']}: {e}")
            return None, {}, latency_ms

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if not resp or resp.status_code != 200:
            err_msg = resp.text[:200] if resp else "No response"
            logger.warning(f"⚠️ [GroqClient] {k['id']} returned HTTP {resp.status_code if resp else 'N/A'}: {err_msg}")
            return None, {}, latency_ms

        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        tokens_dict = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "key_id": k["id"],
            "remaining_tokens": k["remaining_tokens"]
        }
        self.last_used_key_id = k["id"]
        self.last_used_key_remaining = k["remaining_tokens"]

        logger.info(
            f"⚡ [GroqClient] {k['id']} completed in {latency_ms}ms "
            f"(prompt_tokens={prompt_tokens}, remaining_tokens={k['remaining_tokens']})"
        )

        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed, tokens_dict, latency_ms
        except Exception as e:
            logger.warning(f"⚠️ [GroqClient] Failed to parse JSON from {k['id']}: {e}")
            return None, tokens_dict, latency_ms

    def complete_chat_sync(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.0
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, int], int]:
        """Synchronous version for recap flushes."""
        k = self.pool.select_key()
        if not k:
            return None, {}, 0

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        elif response_format:
            payload["response_format"] = response_format

        t0 = time.perf_counter()
        resp = None

        try:
            with httpx.Client(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {k['key']}",
                    "Content-Type": "application/json"
                }
                resp = client.post(self.url, headers=headers, json=payload)
                self.pool.update_headers(k, resp.headers, resp.status_code)

                # HTTP 429 / 401 / 403: Immediately retry with other keys in pool
                attempted_ids = {k["id"]}
                while resp.status_code in (401, 403, 429):
                    if resp.status_code == 429:
                        wait_sec = parse_reset_duration(
                            resp.headers.get("retry-after") or
                            resp.headers.get("x-ratelimit-reset-tokens")
                        )
                        k["remaining_tokens"] = 0
                        k["reset_time"] = time.time() + wait_sec

                    k_next = self.pool.get_other_key(k, excluded_ids=attempted_ids)
                    if k_next:
                        prev_id = k["id"]
                        prev_status = resp.status_code
                        attempted_ids.add(k_next["id"])
                        headers_next = {
                            "Authorization": f"Bearer {k_next['key']}",
                            "Content-Type": "application/json"
                        }
                        resp_next = client.post(self.url, headers=headers_next, json=payload)
                        self.pool.update_headers(k_next, resp_next.headers, resp_next.status_code)
                        if resp_next.status_code == 200:
                            logger.info(f"🔄 [{prev_id} {prev_status} → {k_next['id']} retry ok]")
                            resp = resp_next
                            k = k_next
                            break
                        else:
                            resp = resp_next
                            k = k_next
                    else:
                        # All keys in pool exhausted
                        break

                if resp.status_code == 429:
                    sleep_wait = min(
                        max(0.1, key_entry["reset_time"] - time.time())
                        for key_entry in self.pool.keys
                    ) if self.pool.keys else 0.0

                    keys_count = len(self.pool.keys)
                    keys_label = "Both keys" if keys_count == 2 else f"All {keys_count} keys"
                    if sleep_wait > 2.0:
                        logger.warning(
                            f"⚠️ [GroqClient] Sync rate limit reset too long ({sleep_wait:.1f}s > 2.0s). Skipping request."
                        )
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        return None, {}, latency_ms
                    elif sleep_wait > 0 and self.pool.keys:
                        time.sleep(sleep_wait)
                        k_best = min(self.pool.keys, key=lambda x: x["reset_time"])
                        h_best = {"Authorization": f"Bearer {k_best['key']}", "Content-Type": "application/json"}
                        resp = client.post(self.url, headers=h_best, json=payload)
                        self.pool.update_headers(k_best, resp.headers, resp.status_code)
                        k = k_best

        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return None, {}, latency_ms

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if not resp or resp.status_code != 200:
            return None, {}, latency_ms

        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        tokens_dict = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "key_id": k["id"],
            "remaining_tokens": k["remaining_tokens"]
        }
        self.last_used_key_id = k["id"]
        self.last_used_key_remaining = k["remaining_tokens"]

        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed, tokens_dict, latency_ms
        except Exception:
            return None, tokens_dict, latency_ms

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Runs JSON-mode completion and returns (parsed_json, latency_ms). Backwards-compatible."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        parsed, tokens, latency_ms = await self.complete_chat(
            messages=messages,
            model=model,
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return parsed, latency_ms


groq_client = GroqClient()
