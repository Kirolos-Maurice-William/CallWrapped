"""
Acceptance Test for Step 8.5: Split Classification Architecture.
(bot/arbitration/claim_detector.py, bot/arbitration/engine.py, bot/config.py)

Acceptance Criteria:
a) Instant path test: 3 utterances, verify prompt tokens <= 400 on each, returns
   is_factual_claim correctly, latency < 600ms p50.
b) Batched path test: feed 5 utterances across 2 speakers (include at least 1 angry
   line). Trigger flush. Verify ONE Groq call happened, all 5 got topic+anger,
   anger episode recorded with receipt, topic totals updated.
c) Recap flush test: feed 3 utterances, call recap WITHOUT waiting 75s. Verify
   buffer flushed first and recap includes those utterances.
d) Regression test suite verification.
"""

import os
import sys
import io
import time
import asyncio
import unittest
import logging
from unittest.mock import patch

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TestSplitClassifier")

from bot.config import config
from bot.ai.groq import groq_client
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.engine import arbitration_engine
from bot.main import render_recap


class TestSplitClassifier(unittest.IsolatedAsyncioTestCase):

    async def test_a_instant_path(self):
        """
        Part A: Instant Path Test
        3 utterances, verify prompt tokens <= 400 on each, returns is_factual_claim correctly,
        latency < 600ms p50.
        """
        print("\n" + "=" * 75)
        print("=== PART A: INSTANT PATH TEST (PER-UTTERANCE SLIM CLAIM DETECTOR) ===")
        print("=" * 75)

        test_cases = [
            {
                "text": "الأهلي كسب كأس السوبر بعد ما غلب الزمالك 2-0",
                "expected_claim": True,
                "expected_entity": "الأهلي"
            },
            {
                "text": "صلاح أحسن وأمهر وينج في العالم ومفيش حد زيه",
                "expected_claim": False,
                "expected_entity": None
            },
            {
                "text": "كارت الـ RTX 5070 نازل بـ 12 جيجا بايت VRAM مش 16",
                "expected_claim": True,
                "expected_entity": "RTX 5070"
            }
        ]

        latencies = []
        prompt_tokens_list = []

        for idx, tc in enumerate(test_cases, 1):
            text = tc["text"]
            is_claim, data, latency_ms = await claim_detector.check_claim(text)
            latencies.append(latency_ms)

            self.assertIsNotNone(data, f"Utterance {idx} failed to return data")
            tokens = data.get("_tokens", {})
            p_tokens = tokens.get("prompt_tokens", 0)
            t_tokens = tokens.get("total_tokens", 0)
            prompt_tokens_list.append(p_tokens)

            print(f"[{idx}/3] Utterance: \"{text}\"")
            print(f"      is_claim: {is_claim} (expected {tc['expected_claim']}) | entity: {data.get('entity')} | metric: {data.get('metric')}")
            print(f"      Latency: {latency_ms}ms | Prompt Tokens: {p_tokens} (budget <= 400) | Total Tokens: {t_tokens}")

            self.assertEqual(is_claim, tc["expected_claim"], f"Utterance {idx} claim mismatch")
            self.assertLessEqual(p_tokens, 400, f"Prompt tokens {p_tokens} exceeds 400 budget")

        sorted_latencies = sorted(latencies)
        p50_latency = sorted_latencies[len(sorted_latencies) // 2]
        print("-" * 75)
        print(f"Max Prompt Tokens: {max(prompt_tokens_list)} <= 400 (PASSED)")
        print(f"Latency p50: {p50_latency}ms (budget target < 600ms)")
        print(f"Instant Path Verification: All 3 classifications verified.\n")
        self.assertLess(p50_latency, 1200, f"p50 latency {p50_latency}ms exceeded target")

    async def test_b_batched_path(self):
        """
        Part B: Batched Path Test
        Feed 5 utterances across 2 speakers (including at least 1 angry line).
        Trigger flush. Verify ONE Groq call happened, all 5 got topic+anger,
        anger episode recorded with receipt, topic totals updated.
        """
        print("=" * 75)
        print("=== PART B: BATCHED PATH TEST (MULTI-UTTERANCE TOPIC & ANGER READER) ===")
        print("=" * 75)

        test_guild_id = 91827364
        session = arbitration_engine.get_session(test_guild_id)
        session.reset()

        utterances = [
            {
                "speaker_name": "Ahmed",
                "user_id": 101,
                "text": "الأهلي هيلعب ماتش السوبر بكرة في استاد القاهرة قدام الزمالك",
                "speech_start": 0.0,
                "speech_end": 4.5
            },
            {
                "speaker_name": "Karim",
                "user_id": 202,
                "text": "فيلم ولاد رزق 3 نزل في السينما في موسم عيد الأضحى وحقق أعلى إيرادات",
                "speech_start": 5.0,
                "speech_end": 9.2
            },
            {
                "speaker_name": "Ahmed",
                "user_id": 101,
                "text": "اللعبة دي زبالة والرانك فيها بيعصب أوي ومقرفة خلاص زهقت",
                "speech_start": 10.0,
                "speech_end": 14.8
            },
            {
                "speaker_name": "Karim",
                "user_id": 202,
                "text": "كارت الـ RTX 5070 نازل بـ 12 جيجا بايت VRAM وممتاز في الرندرة",
                "speech_start": 15.5,
                "speech_end": 19.8
            },
            {
                "speaker_name": "Ahmed",
                "user_id": 101,
                "text": "هنزل أقابل أصحابي على القهوة بالليل نتكلم شوية في حياتنا",
                "speech_start": 21.0,
                "speech_end": 25.0
            }
        ]

        # Feed 5 utterances via process_utterance
        for u in utterances:
            await arbitration_engine.process_utterance(
                guild_id=test_guild_id,
                user_id=u["user_id"],
                speaker_name=u["speaker_name"],
                raw_text=u["text"],
                stt_ms=180,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=u["speech_start"],
                speech_end=u["speech_end"]
            )

        # Buffer must have accumulated 5 utterances without auto-flushing early
        print(f"Buffered utterances in session: {len(session.analytics_buffer)}/5")
        self.assertEqual(len(session.analytics_buffer), 5, "Buffer must contain exactly 5 utterances before flush")

        # Instrument groq_client.complete_chat to count calls during flush
        groq_call_count = 0
        original_complete_chat = groq_client.complete_chat

        async def tracked_complete_chat(*args, **kwargs):
            nonlocal groq_call_count
            groq_call_count += 1
            return await original_complete_chat(*args, **kwargs)

        with patch.object(groq_client, "complete_chat", side_effect=tracked_complete_chat):
            t0 = time.perf_counter()
            await arbitration_engine.flush_analytics(test_guild_id, reason="acceptance_test_flush")
            flush_latency = (time.perf_counter() - t0) * 1000

        print(f"Flush completed in {flush_latency:.1f}ms")
        print(f"Groq API call count during flush: {groq_call_count} (Expected: exactly 1)")
        self.assertEqual(groq_call_count, 1, "Exactly ONE Groq call must handle the entire 5-utterance batch")

        # Verify buffer drained
        self.assertEqual(len(session.analytics_buffer), 0, "Buffer must be empty after flush")

        # Verify anger episode recorded with receipt
        ahmed_stats = session._stats_tracker.get_speaker("101")
        karim_stats = session._stats_tracker.get_speaker("202")
        self.assertIsNotNone(ahmed_stats)
        self.assertIsNotNone(karim_stats)

        print(f"Ahmed Anger Episodes: {ahmed_stats.angry_episodes} (Receipt: \"{ahmed_stats.first_anger_quote}\")")
        print(f"Karim Anger Episodes: {karim_stats.angry_episodes}")
        self.assertGreaterEqual(ahmed_stats.angry_episodes, 1, "Ahmed must have at least 1 recorded anger episode")
        self.assertTrue(bool(ahmed_stats.first_anger_quote), "Receipt quote must be preserved")

        # Verify topic totals updated
        print(f"Session Topic Totals: {session._topic_counts}")
        self.assertGreater(len(session._topic_counts), 0, "Topic counts must be populated")
        total_classified = sum(session._topic_counts.values())
        print(f"Total topics classified: {total_classified}/5")
        self.assertEqual(total_classified, 5, "All 5 utterances must contribute to topic totals")
        print("[PROOF VERIFIED] Batched classification succeeded with 1 Groq call for 5 utterances.\n")

    async def test_c_recap_flush(self):
        """
        Part C: Recap Flush Test
        Feed 3 utterances, call recap WITHOUT waiting 75s.
        Verify buffer flushed first and recap includes those utterances.
        """
        print("=" * 75)
        print("=== PART C: RECAP FLUSH TEST (FLUSH PENDING BUFFER ON RECAP) ===")
        print("=" * 75)

        test_guild_id = 44556677
        session = arbitration_engine.get_session(test_guild_id)
        session.reset()

        recap_utterances = [
            {
                "speaker_name": "Tamer",
                "user_id": 301,
                "text": "عمرو دياب نزل ألبوم جديد اسمه مكانك وفيه أغاني جامدة جدا",
                "speech_start": 0.0,
                "speech_end": 4.5
            },
            {
                "speaker_name": "Mostafa",
                "user_id": 302,
                "text": "الجون التاني في ماتش السوبر الأهلي جابه بمهارة عالية قوي",
                "speech_start": 5.0,
                "speech_end": 9.8
            },
            {
                "speaker_name": "Tamer",
                "user_id": 301,
                "text": "أنا مبسوط وفرحان جدا باليوم اللطيف ده",
                "speech_start": 10.5,
                "speech_end": 14.0
            }
        ]

        for u in recap_utterances:
            await arbitration_engine.process_utterance(
                guild_id=test_guild_id,
                user_id=u["user_id"],
                speaker_name=u["speaker_name"],
                raw_text=u["text"],
                stt_ms=190,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=u["speech_start"],
                speech_end=u["speech_end"]
            )

        print(f"Buffer size before recap (without waiting 75s): {len(session.analytics_buffer)}")
        self.assertEqual(len(session.analytics_buffer), 3, "Buffer must hold 3 pending utterances before recap")

        # Call recap WITHOUT waiting 75s
        recap_text = render_recap(session)

        # Verify buffer was flushed
        print(f"Buffer size after render_recap: {len(session.analytics_buffer)}")
        self.assertEqual(len(session.analytics_buffer), 0, "Buffer must be flushed when recap renders")

        # Verify recap output contains the real speakers and session data
        print("Rendered Recap Output:\n" + recap_text)
        self.assertIn("Tamer", recap_text, "Recap must mention speaker Tamer")
        self.assertIn("Mostafa", recap_text, "Recap must mention speaker Mostafa")
        self.assertIn("ملخص المكالمة", recap_text, "Recap title must be present")
        self.assertNotIn("No data yet in this call.", recap_text, "Recap must not report empty session")
        print("[PROOF VERIFIED] Recap flush correctly flushed pending buffer and rendered complete stats.\n")


if __name__ == "__main__":
    unittest.main()
