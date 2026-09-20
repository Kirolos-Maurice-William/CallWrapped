import os
import re
import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List
import httpx
from bot.config import config

logger = logging.getLogger("GroqClient")


def parse_reset_duration(header_val: Optional[str]) -> float:
    """Parses rate limit reset duration from headers (e.g. '6s', '250ms', '1m12s', '42')."""
    if not header_val:
        return 2.0
    val = str(header_val).strip()
    try:
        return max(0.1, float(val))
    except ValueError:
        pass

    total_sec = 0.0
    m_min = re.search(r"(\d+(?:\.\d+)?)\s*m(?:in)?", val)
    if m_min:
        total_sec += float(m_min.group(1)) * 60.0
    m_sec = re.search(r"(\d+(?:\.\d+)?)\s*s(?:ec)?", val)
    if m_sec:
        total_sec += float(m_sec.group(1))
    m_ms = re.search(r"(\d+(?:\.\d+)?)\s*ms", val)
    if m_ms:
        total_sec += float(m_ms.group(1)) / 1000.0

    return max(0.1, total_sec) if total_sec > 0 else 2.0


class KeyPool:
    """Manages a pool of Groq API keys with token-budget tracking and 429 rotation."""

    def __init__(self):
        self.keys: List[Dict[str, Any]] = []
        self._init_pool()

    def _init_pool(self):
        candidates = [
            ("key#1", config.GROQ_API_KEY),
            ("key#2", getattr(config, "GROQ_API_KEY_2", ""))
        ]
        for key_id, raw_key in candidates:
            if raw_key and raw_key.strip():
                self.keys.append({
                    "id": key_id,
                    "key": raw_key.strip(),
                    "remaining_tokens": 100000,
                    "reset_time": 0.0
                })

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

    def get_other_key(self, current_key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Returns the alternate key if available."""
        others = [k for k in self.keys if k["id"] != current_key["id"]]
        return others[0] if others else None

    def update_headers(self, key_entry: Dict[str, Any], headers: httpx.Headers):
        """Updates remaining tokens and reset time from response headers."""
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
                self.pool.update_headers(k, resp.headers)

                # HTTP 429: Immediately retry ONCE with OTHER key
                if resp.status_code == 429:
                    wait_sec = parse_reset_duration(
                        resp.headers.get("retry-after") or
                        resp.headers.get("x-ratelimit-reset-tokens") or
                        resp.headers.get("x-ratelimit-reset-requests")
                    )
                    k["remaining_tokens"] = 0
                    k["reset_time"] = time.time() + wait_sec

                    k2 = self.pool.get_other_key(k)
                    if k2 and time.time() >= k2["reset_time"]:
                        headers2 = {
                            "Authorization": f"Bearer {k2['key']}",
                            "Content-Type": "application/json"
                        }
                        resp2 = await client.post(self.url, headers=headers2, json=payload)
                        self.pool.update_headers(k2, resp2.headers)

                        if resp2.status_code == 200:
                            logger.info(f"🔄 [{k['id']} 429 → {k2['id']} retry ok]")
                            resp = resp2
                            k = k2
                        elif resp2.status_code == 429:
                            # Both keys exhausted
                            wait_sec2 = parse_reset_duration(
                                resp2.headers.get("retry-after") or
                                resp2.headers.get("x-ratelimit-reset-tokens")
                            )
                            k2["remaining_tokens"] = 0
                            k2["reset_time"] = time.time() + wait_sec2
                            sleep_wait = min(
                                max(0.1, k["reset_time"] - time.time()),
                                max(0.1, k2["reset_time"] - time.time())
                            )
                            logger.warning(f"⚠️ [GroqClient] Both keys hit 429. Waiting {sleep_wait:.2f}s reset...")
                            await asyncio.sleep(sleep_wait)
                            k_best = min(self.pool.keys, key=lambda x: x["reset_time"])
                            h_best = {"Authorization": f"Bearer {k_best['key']}", "Content-Type": "application/json"}
                            resp = await client.post(self.url, headers=h_best, json=payload)
                            self.pool.update_headers(k_best, resp.headers)
                            k = k_best
                    else:
                        # Single key or both exhausted, wait and retry once
                        logger.warning(f"⚠️ [{k['id']} 429] Rate limit hit. Waiting {wait_sec:.2f}s...")
                        await asyncio.sleep(wait_sec)
                        resp = await client.post(self.url, headers=headers, json=payload)
                        self.pool.update_headers(k, resp.headers)

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
                self.pool.update_headers(k, resp.headers)

                if resp.status_code == 429:
                    wait_sec = parse_reset_duration(
                        resp.headers.get("retry-after") or
                        resp.headers.get("x-ratelimit-reset-tokens")
                    )
                    k["remaining_tokens"] = 0
                    k["reset_time"] = time.time() + wait_sec

                    k2 = self.pool.get_other_key(k)
                    if k2 and time.time() >= k2["reset_time"]:
                        headers2 = {
                            "Authorization": f"Bearer {k2['key']}",
                            "Content-Type": "application/json"
                        }
                        resp2 = client.post(self.url, headers=headers2, json=payload)
                        self.pool.update_headers(k2, resp2.headers)
                        if resp2.status_code == 200:
                            logger.info(f"🔄 [{k['id']} 429 → {k2['id']} retry ok]")
                            resp = resp2
                            k = k2
                        elif resp2.status_code == 429:
                            wait_sec2 = parse_reset_duration(
                                resp2.headers.get("retry-after") or
                                resp2.headers.get("x-ratelimit-reset-tokens")
                            )
                            k2["remaining_tokens"] = 0
                            k2["reset_time"] = time.time() + wait_sec2
                            sleep_wait = min(
                                max(0.1, k["reset_time"] - time.time()),
                                max(0.1, k2["reset_time"] - time.time())
                            )
                            time.sleep(sleep_wait)
                            k_best = min(self.pool.keys, key=lambda x: x["reset_time"])
                            h_best = {"Authorization": f"Bearer {k_best['key']}", "Content-Type": "application/json"}
                            resp = client.post(self.url, headers=h_best, json=payload)
                            self.pool.update_headers(k_best, resp.headers)
                            k = k_best
                    else:
                        time.sleep(wait_sec)
                        resp = client.post(self.url, headers=headers, json=payload)
                        self.pool.update_headers(k, resp.headers)

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
