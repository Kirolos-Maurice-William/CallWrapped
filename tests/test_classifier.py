"""
Acceptance Test for Every-Utterance Classifier (bot/arbitration/claim_detector.py).
Sends 10 real transcripts (2 football, 2 movies, 1 politics, 2 gaming, 1 music, 2 banter)
through the REAL Groq API using strict json_schema.

Verifies:
1. All 10 raw JSON outputs returned.
2. Token usage reported per utterance (prompt, completion, total).
3. Banter must NOT be labeled angry (anger == 'none').
4. Opinions must have is_factual_claim == False.
5. ANALYTICS_ENABLED=0 skips classification entirely.
"""

import os
import sys
import io
import json
import time
import asyncio
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from bot.arbitration.claim_detector import claim_detector
from bot.config import config


class TestEveryUtteranceClassifier(unittest.IsolatedAsyncioTestCase):

    TEST_UTTERANCES = [
        ("Football 1 (Claim)", "الأهلي كسب كأس السوبر بعد ما غلب الزمالك 2-0"),
        ("Football 2 (Opinion)", "صلاح أحسن وأمهر وينج في العالم ومفيش حد زيه"),
        ("Movies 1 (Claim)", "فيلم ولاد رزق 3 نزل في السينما في موسم عيد الأضحى"),
        ("Movies 2 (Opinion)", "الفيلم الجديد ده دمه تقيل وممل وميستاهلش تدفع فيه فلوس"),
        ("Politics (Claim)", "مجلس النواب وافق رسمي على قانون الإيجار القديم الجديد"),
        ("Gaming 1 (Claim)", "لعبة GTA 6 هتنزل رسمياً في خريف 2025 على الكونسول"),
        ("Gaming 2 (Opinion)", "لعبة كول أوف ديوتي الجديدة زبالة والرانك فيها بيعصب أوي"),
        ("Music (Claim)", "عمرو دياب نزل ألبوم مكانك وفيه 12 تراك جديد"),
        ("Banter 1", "يا عم انت نوب وبتضيع علينا الجيم كل مرة ههههه"),
        ("Banter 2", "يا اسطى بطل هبد بقى وروح نام انت مش فاهم حاجة"),
        ("Gaming Frustration (Mild)", "للسط مرتين علطول يا خسارة الدبيل ده زهقت خلاص"),
        ("Laughter Teasing (None)", "انت وخد الجيم ده ههههه مبيدكش")
    ]

    async def test_twelve_transcripts_real_groq_api(self):
        print("\n" + "=" * 70)
        print("=== RUNNING ACCEPTANCE TEST: 12 TRANSCRIPTS ON REAL GROQ API ===")
        print("=" * 70 + "\n")

        self.assertTrue(config.GROQ_API_KEY, "GROQ_API_KEY must be present")

        for idx, (label, text) in enumerate(self.TEST_UTTERANCES, 1):
            await asyncio.sleep(0.5)  # Pace calls to respect rate limit

            is_claim, data, latency_ms = await claim_detector.check_claim(text)

            tokens = data.get("_tokens", {})
            print(f"[{idx}/12] {label}")
            print(f"  Input Utterance: \"{text}\"")
            print(f"  Latency: {latency_ms}ms | is_factual_claim: {is_claim}")
            print(f"  Tokens Used: prompt_tokens={tokens.get('prompt_tokens')}, completion_tokens={tokens.get('completion_tokens')}, total_tokens={tokens.get('total_tokens')}")
            print(f"  Raw JSON Output: {json.dumps({k: v for k, v in data.items() if k != '_tokens'}, ensure_ascii=False)}")

            # Assertions per task requirements:
            self.assertIsNotNone(data, f"Output data should not be None for: {text}")
            self.assertIn("topic", data)
            self.assertIn("anger", data)
            self.assertIn("is_factual_claim", data)

            # 1. Banter and laughter must NOT be labeled angry (anger == 'none')
            if "Banter" in label or "Laughter" in label:
                self.assertEqual(data.get("anger"), "none", f"Banter/Laughter must have anger='none', got: {data.get('anger')}")
                self.assertFalse(data.get("is_factual_claim"), f"Banter must have is_factual_claim=False, got: {data}")

            # 2. Opinions must have is_factual_claim=False
            if "Opinion" in label:
                self.assertFalse(data.get("is_factual_claim"), f"Opinion must have is_factual_claim=False, got: {data}")

            # 3. Factual Claims must have is_factual_claim=True
            if "Claim" in label:
                self.assertTrue(data.get("is_factual_claim"), f"Claim must have is_factual_claim=True, got: {data}")

            # 4. Specific anger assertions:
            # Sentence #7 (Gaming 2 Opinion) and Sentence #11 (Gaming Frustration) must be mild
            if "Gaming 2 (Opinion)" in label or "Frustration" in label:
                self.assertEqual(data.get("anger"), "mild", f"{label} must have anger='mild', got: {data.get('anger')}")

            # Sentence #6 (Gaming 1 Claim) must have claim in Arabic
            if "Gaming 1 (Claim)" in label:
                claim_val = data.get("claim", "")
                self.assertTrue(any('\u0600' <= c <= '\u06FF' for c in (claim_val or "")), f"Claim for GTA 6 must be in Arabic, got: {claim_val}")

            print("  Verdict: PASS\n")

    async def test_analytics_disabled_skips_classification(self):
        print("--- Testing ANALYTICS_ENABLED=0 flag ---")
        original_flag = config.ANALYTICS_ENABLED
        try:
            config.ANALYTICS_ENABLED = 0
            is_claim, data, latency_ms = await claim_detector.check_claim("الأهلي كسب 2-1")
            self.assertFalse(is_claim)
            self.assertIsNone(data)
            self.assertEqual(latency_ms, 0)
            print("  [SUCCESS] Classification successfully skipped when ANALYTICS_ENABLED=0\n")
        finally:
            config.ANALYTICS_ENABLED = original_flag


if __name__ == "__main__":
    unittest.main()
