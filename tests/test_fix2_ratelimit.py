import sys
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from bot.ai.groq import parse_reset_duration, GroqClient, KeyPool


class TestRateLimitParserAndRotation(unittest.TestCase):
    def test_parse_reset_duration_acceptance(self):
        """
        Acceptance test:
        Asserts '250ms'->0.25, '134ms'->0.134, '27m21.6s'->1641.6, '2m30s'->150, '45s'->45.
        """
        test_cases = [
            ("250ms", 0.25),
            ("134ms", 0.134),
            ("27m21.6s", 1641.6),
            ("2m30s", 150),
            ("45s", 45),
        ]

        print("\n" + "=" * 60)
        print("=== RATE-LIMIT RESET DURATION PARSER ACCEPTANCE ===")
        print("=" * 60)
        for header, expected in test_cases:
            actual = parse_reset_duration(header)
            print(f"Header: '{header:<10}' -> Parsed: {actual:<10} (Expected: {expected})")
            self.assertEqual(actual, expected, f"Failed for header: {header}")

        # Compound hours test
        self.assertEqual(parse_reset_duration("1h2m3s"), 3723.0)
        print(f"Header: '1h2m3s'    -> Parsed: {parse_reset_duration('1h2m3s')} (Expected: 3723.0)")
        print("=" * 60)

    def test_rotation_never_sleeps_more_than_two_seconds(self):
        """
        Verify that 429 responses with long resets (> 2s) mark the key unavailable
        and never block/sleep the request path.
        """
        client = GroqClient()
        # Mock pool with two keys
        client.pool.keys = [
            {"id": "key#1", "key": "gsk_test1", "remaining_tokens": 1000, "reset_time": 0.0},
            {"id": "key#2", "key": "gsk_test2", "remaining_tokens": 1000, "reset_time": 0.0},
        ]

        async def run_test():
            # Mock httpx client post to return 429 with 60s reset on both keys
            mock_resp_429 = MagicMock()
            mock_resp_429.status_code = 429
            mock_resp_429.headers = {"retry-after": "60s"}
            mock_resp_429.text = "Rate limit exceeded"

            with patch("httpx.AsyncClient.post", return_value=mock_resp_429):
                t_start = time.perf_counter()
                parsed, tokens, latency = await client.complete_chat(
                    messages=[{"role": "user", "content": "hi"}]
                )
                elapsed = time.perf_counter() - t_start

                # Must return almost immediately (< 0.5s), NEVER sleeping 60 seconds
                print(f"\n[Rotation Hardening Test] Elapsed: {elapsed*1000:.2f}ms for 60s rate limit reset")
                self.assertLess(elapsed, 2.0, "Request path slept more than 2.0 seconds!")
                self.assertIsNone(parsed)
                self.assertGreater(client.pool.keys[0]["reset_time"], time.time() + 50)
                self.assertGreater(client.pool.keys[1]["reset_time"], time.time() + 50)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
