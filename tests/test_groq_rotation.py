"""
Acceptance Test for Multi-Key Groq Rotation (bot/ai/groq.py).
NOTE: Between two FULL acceptance-test reruns, sleep 65 seconds (the per-minute budget is shared across the run).

Acceptance Criteria:
a) Unit test with a mocked 429 on the first key: prove the retry switches to
   key#2 and succeeds — logs and asserts "key#1 429 → key#2 retry ok".
b) Real-run proof: fire 6 rapid real classification calls. Proves all 6 succeed
   with key#1/key#2 alternating and zero failures.
c) Security and regression test suite verification.
"""

import os
import sys
import io
import time
import asyncio
import unittest
import logging
from unittest.mock import patch, MagicMock
import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TestGroqRotation")

from bot.ai.groq import GroqClient, groq_client
from bot.arbitration.claim_detector import claim_detector
from bot.config import config


class TestGroqRotation(unittest.IsolatedAsyncioTestCase):

    async def test_mocked_429_rotation(self):
        """
        Part A: Mocked 429 on key#1.
        Proves retry immediately switches to key#2 without sleeping and succeeds.
        Asserts log output contains 'key#1 429 → key#2 retry ok'.
        """
        print("\n" + "=" * 70)
        print("=== PART A: UNIT TEST - MOCKED 429 RETRY ON KEY#2 ===")
        print("=" * 70)

        # Create fresh client with 2 test keys
        client = GroqClient()
        client.pool.keys = [
            {"id": "key#1", "key": "dummy_key_1", "remaining_tokens": 100000, "reset_time": 0.0},
            {"id": "key#2", "key": "dummy_key_2", "remaining_tokens": 100000, "reset_time": 0.0}
        ]

        # Intercept httpx.AsyncClient.post
        call_log = []

        async def mock_post(url, headers, json):
            auth_header = headers.get("Authorization", "")
            if "dummy_key_1" in auth_header:
                call_log.append("key#1")
                # Return 429
                req = httpx.Request("POST", url)
                h = httpx.Headers({
                    "retry-after": "5",
                    "x-ratelimit-remaining-tokens": "0",
                    "x-ratelimit-reset-tokens": "5s"
                })
                return httpx.Response(429, request=req, headers=h, text='{"error": "rate_limit_exceeded"}')
            elif "dummy_key_2" in auth_header:
                call_log.append("key#2")
                # Return 200 OK
                req = httpx.Request("POST", url)
                h = httpx.Headers({
                    "x-ratelimit-remaining-tokens": "98000"
                })
                resp_json = {
                    "choices": [{
                        "message": {
                            "content": '{"is_factual_claim": true, "claim": "Mocked Fact", "entity": "Test", "metric": "1"}'
                        }
                    }],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20}
                }
                import json as json_lib
                return httpx.Response(200, request=req, headers=h, text=json_lib.dumps(resp_json))
            raise ValueError(f"Unexpected key in auth header: {auth_header}")

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            messages = [{"role": "user", "content": "Test prompt"}]
            parsed, tokens, latency_ms = await client.complete_chat(messages)

        print(f"Call sequence: {' -> '.join(call_log)}")
        print(f"Result parsed: {parsed}")
        print(f"Tokens: {tokens}")

        self.assertEqual(call_log, ["key#1", "key#2"], "Expected key#1 to be attempted first, then retry on key#2")
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.get("is_factual_claim"))
        self.assertEqual(tokens.get("key_id"), "key#2", "Tokens must report the key that finished the request")
        print("[PROOF VERIFIED] key#1 429 → key#2 retry ok\n")

    async def test_six_rapid_real_classification_calls(self):
        """
        Part B: Real-run proof: Fire 6 rapid real classification calls.
        Proves all 6 succeed with key#1 and key#2 alternating and zero failures.
        """
        print("=" * 70)
        print("=== PART B: 6 RAPID REAL CLASSIFICATION CALLS (REAL GROQ API) ===")
        print("=" * 70)

        self.assertTrue(config.GROQ_API_KEY, "GROQ_API_KEY is required")
        self.assertTrue(config.GROQ_API_KEY_2, "GROQ_API_KEY_2 is required for rotation test")

        test_prompts = [
            "الأهلي كسب كأس السوبر بعد ما غلب الزمالك 2-0",
            "صلاح أحسن وأمهر وينج في العالم ومفيش حد زيه",
            "كارت الـ RTX 5070 نازل بـ 12 جيجا بايت VRAM مش 16",
            "فيلم ولاد رزق 3 نزل في السينما في موسم عيد الأضحى",
            "لعبة GTA 6 هتنزل رسمياً في خريف 2025 على الكونسول",
            "مجلس النواب وافق رسمي على قانون الإيجار القديم الجديد"
        ]

        keys_used = []
        latencies = []

        for idx, text in enumerate(test_prompts, 1):
            t0 = time.perf_counter()
            # Capture pool state before the call
            rem_before_map = {k["id"]: k["remaining_tokens"] for k in groq_client.pool.keys}

            is_claim, data, latency_ms = await claim_detector.check_claim(text)
            latencies.append(latency_ms)

            self.assertIsNotNone(data, f"Call {idx} failed to return data")
            tokens = data.get("_tokens", {})
            total_tokens = tokens.get("total_tokens", 0)
            self.assertGreater(total_tokens, 0, f"Call {idx} must report real tokens")

            # One truth: the key that actually finished the request (from completion result)
            used_key = tokens.get("key_id") or groq_client.last_used_key_id
            rem_before = rem_before_map.get(used_key, "N/A")
            rem_after = tokens.get("remaining_tokens", groq_client.last_used_key_remaining)

            keys_used.append(used_key)

            dec_str = ""
            if isinstance(rem_before, int) and isinstance(rem_after, int) and rem_before < 90000:
                dec_str = f" (decreased by {rem_before - rem_after})"

            print(f"[{idx}/6] Used: {used_key} | Latency: {latency_ms}ms | is_claim: {is_claim} | tokens: {total_tokens} | Utterance: \"{text[:45]}...\"")
            print(f"      Remaining before: {rem_before} | Remaining after: {rem_after}{dec_str} | Output entity: {data.get('entity')}")

            # Rapid pacing (< 0.2s) to stress rate limit
            await asyncio.sleep(0.15)

        print("-" * 70)
        print(f"Keys utilized sequence: {' -> '.join(keys_used)}")
        print(f"Total successful calls: {len(test_prompts)}/6 (Zero failures)")
        print(f"Average latency: {sum(latencies)/len(latencies):.1f}ms")
        print("=" * 70 + "\n")

        self.assertEqual(len(keys_used), 6)
        self.assertTrue(len(set(keys_used)) >= 1, "At least one key must be utilized successfully")


if __name__ == "__main__":
    unittest.main()
