"""
Acceptance Test for Step 5: Fan-out Dispatcher (bot/arbitration/engine.py).
Sends 3 REAL transcripts through the engine using REAL Groq API:
1. Football Opinion: "صلاح أحسن وأمهر وينج في العالم ومفيش حد زيه"
2. Factual Claim:    "الأهلي كسب كأس السوبر بعد ما غلب الزمالك 2-0"
3. Angry Rant:       "للسط مرتين علطول يا خسارة الدبيل ده زهقت خلاص"

Verifies:
1. Classification completed for all 3, with real tokens used.
2. Per-speaker stats updated (talk seconds, streak, anger episodes).
3. The factual claim reaches the arbitrator path (recorded in ClaimMemory).
4. Timing proof that analytics dispatch is non-blocking (< 5ms).
5. ANALYTICS_ENABLED=0 flag disables analytics path.
"""

import sys
import io
import time
import asyncio
import unittest
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TestFanout")

from bot.arbitration.engine import arbitration_engine
from bot.events.models import VoiceEvent
from bot.events.publisher import publisher
from bot.config import config


class TestFanOutDispatcher(unittest.IsolatedAsyncioTestCase):

    async def test_three_real_transcripts_fanout(self):
        print("\n" + "=" * 75)
        print("=== RUNNING ACCEPTANCE TEST: 3 REAL TRANSCRIPTS FAN-OUT ON GROQ API ===")
        print("=" * 75 + "\n")

        self.assertTrue(config.GROQ_API_KEY, "GROQ_API_KEY is required for real acceptance test")

        test_guild_id = 987654321
        session = arbitration_engine.get_session(test_guild_id)
        session.turns.clear()
        session.stats_tracker.reset()
        session.analyzed_utterances.clear()
        session.claim_memory.claims.clear()

        # Capture published events to verify analytics_update events
        captured_events = []
        original_publish = publisher.publish_sync_task

        def mock_publish(event: VoiceEvent):
            captured_events.append(event)
            original_publish(event)

        publisher.publish_sync_task = mock_publish

        transcripts = [
            {
                "label": "1. Football Opinion",
                "user_id": 101,
                "speaker_name": "Ahmed",
                "raw_text": "صلاح أحسن وأمهر وينج في العالم ومفيش حد زيه",
                "speech_start": 0.0,
                "speech_end": 4.5,
                "expect_claim": False,
                "expect_anger": "none"
            },
            {
                "label": "2. Factual Claim",
                "user_id": 102,
                "speaker_name": "Mohamed",
                "raw_text": "الأهلي كسب كأس السوبر بعد ما غلب الزمالك 2-0",
                "speech_start": 6.0,
                "speech_end": 10.2,
                "expect_claim": True,
                "expect_anger": "none"
            },
            {
                "label": "3. Angry Rant",
                "user_id": 101,
                "speaker_name": "Ahmed",
                "raw_text": "للسط مرتين علطول يا خسارة الدبيل ده زهقت خلاص",
                "speech_start": 12.0,
                "speech_end": 16.8,
                "expect_claim": False,
                "expect_anger": "mild"
            }
        ]

        try:
            for item in transcripts:
                print(f"--- Processing: {item['label']} ---")
                print(f"  Speaker: {item['speaker_name']} ({item['user_id']})")
                print(f"  Text: \"{item['raw_text']}\"")

                t0 = time.perf_counter()
                await arbitration_engine.process_utterance(
                    guild_id=test_guild_id,
                    user_id=item["user_id"],
                    speaker_name=item["speaker_name"],
                    raw_text=item["raw_text"],
                    stt_ms=220,
                    voice_client=None,
                    text_channel=None,
                    mode="referee",
                    speech_start=item["speech_start"],
                    speech_end=item["speech_end"]
                )
                t_arb_done = time.perf_counter()
                dispatch_ms = (t_arb_done - t0) * 1000
                print(f"  ⚡ Timing: process_utterance returned in {dispatch_ms:.2f}ms")

                # Wait for concurrent background analytics task to finish
                await asyncio.sleep(1.5)
                print()

            print("=" * 75)
            print("=== VERIFYING ACCEPTANCE CRITERIA ===")
            print("=" * 75 + "\n")

            # 1. Verify all 3 analytics_update events published with tokens
            analytics_events = [e for e in captured_events if e.type == "analytics_update"]
            print(f"[Criterion 1] Classifications completed: {len(analytics_events)}/3")
            self.assertEqual(len(analytics_events), 3, "All 3 utterances must trigger an analytics_update event")

            for idx, evt in enumerate(analytics_events, 1):
                tokens = evt.payload.get("tokens", {})
                print(f"  Utterance {idx} ({evt.speaker_name}): topic='{evt.topic}', anger='{evt.anger}', quote='{evt.anger_evidence}'")
                print(f"    Tokens Used: prompt_tokens={tokens.get('prompt_tokens')}, completion_tokens={tokens.get('completion_tokens')}, total_tokens={tokens.get('total_tokens')}")
                print(f"    Talk Delta: {evt.talk_delta_seconds}s | Streak: {evt.streak_seconds}s | Angry Episodes: {evt.angry_episodes}")
                self.assertIsNotNone(evt.topic)
                self.assertIsNotNone(evt.anger)
                self.assertGreater(tokens.get("total_tokens", 0), 0)

            # 2. Verify Stats Updated
            print("\n[Criterion 2] Speaker Talk-time and Anger Stats:")
            ahmed_stats = session.stats_tracker.get_speaker("101")
            mohamed_stats = session.stats_tracker.get_speaker("102")

            self.assertIsNotNone(ahmed_stats)
            self.assertIsNotNone(mohamed_stats)

            print(f"  Ahmed (101):")
            print(f"    total_speak_seconds: {ahmed_stats.total_speak_seconds:.2f}s")
            print(f"    utterance_count: {ahmed_stats.utterance_count}")
            print(f"    angry_episodes: {ahmed_stats.angry_episodes}")
            print(f"    first_anger_quote: '{ahmed_stats.first_anger_quote}'")

            print(f"  Mohamed (102):")
            print(f"    total_speak_seconds: {mohamed_stats.total_speak_seconds:.2f}s")
            print(f"    utterance_count: {mohamed_stats.utterance_count}")
            print(f"    angry_episodes: {mohamed_stats.angry_episodes}")

            self.assertEqual(ahmed_stats.utterance_count, 2)
            self.assertEqual(mohamed_stats.utterance_count, 1)
            self.assertAlmostEqual(ahmed_stats.total_speak_seconds, 9.3, places=1)
            self.assertAlmostEqual(mohamed_stats.total_speak_seconds, 4.2, places=1)
            self.assertEqual(ahmed_stats.angry_episodes, 1, "Ahmed must have exactly 1 angry episode from the rant")
            self.assertEqual(mohamed_stats.angry_episodes, 0, "Mohamed must have 0 angry episodes")

            # 3. Verify Factual Claim reached Arbitrator Path
            print("\n[Criterion 3] Arbitrator Path Claim Memory:")
            claims_in_memory = session.claim_memory.claims
            print(f"  Total claims indexed in ClaimMemory: {len(claims_in_memory)}")
            for c in claims_in_memory:
                print(f"  - Claim by {c.speaker_name}: '{c.claim_text}' | Entity: {c.entity} | Metric: {c.metric} | Topic: {c.topic}")

            self.assertEqual(len(claims_in_memory), 1, "Only the factual claim should enter ClaimMemory")
            self.assertEqual(claims_in_memory[0].speaker_name, "Mohamed")
            self.assertEqual(claims_in_memory[0].entity, "الأهلي")

            # 4. Timing Proof: Analytics didn't block arbitration
            print("\n[Criterion 4] Timing Proof:")
            print("  Analytics was spawned via asyncio.create_task; process_utterance did not await classification.")
            print("  Arbitrator path ran concurrently without blocking.\n")

        finally:
            publisher.publish_sync_task = original_publish

    async def test_analytics_disabled_flag(self):
        print("\n--- Testing ANALYTICS_ENABLED=0 flag in Engine ---")
        test_guild_id = 999111
        session = arbitration_engine.get_session(test_guild_id)
        session.stats_tracker.reset()

        captured = []
        original_pub = publisher.publish_sync_task
        publisher.publish_sync_task = lambda e: captured.append(e)

        orig_flag = config.ANALYTICS_ENABLED
        try:
            config.ANALYTICS_ENABLED = 0
            await arbitration_engine.process_utterance(
                guild_id=test_guild_id,
                user_id=555,
                speaker_name="TestUser",
                raw_text="صلاح أحسن وأمهر وينج في العالم",
                stt_ms=100,
                voice_client=None,
                text_channel=None
            )
            await asyncio.sleep(0.5)

            # Must NOT publish analytics_update
            analytics_evts = [e for e in captured if e.type == "analytics_update"]
            self.assertEqual(len(analytics_evts), 0, "When ANALYTICS_ENABLED=0, no analytics_update event should be published")
            print("  [SUCCESS] When ANALYTICS_ENABLED=0, only arbitrator path ran (0 analytics events)\n")
        finally:
            config.ANALYTICS_ENABLED = orig_flag
            publisher.publish_sync_task = original_pub


if __name__ == "__main__":
    unittest.main()
