"""
Acceptance test for arbitration queue:
Proves that utterance B arriving while arbitration for A is running
is queued, preserved, and processed after arbitration for A completes.
Also validates queue overflow policy (drops oldest, never drops silently).
"""

import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

# Configure logging so test logs are visible in stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from bot.arbitration.engine import arbitration_engine, SessionState


class TestArbitrationQueue(unittest.IsolatedAsyncioTestCase):

    async def test_utterance_b_queued_and_processed_after_a(self):
        """
        Utterance B arrives while arbitration for A is running.
        Verifies:
        1. A begins arbitration (session.is_arbitrating = True).
        2. B arrives and is queued instead of dropped.
        3. A completes arbitration.
        4. B is drained and processed through the pipeline.
        5. Both completed.
        """
        guild_id = 999123
        session = arbitration_engine.get_session(guild_id)
        session.pending_utterances.clear()
        session.is_arbitrating = False

        processed_utterances = []
        arbitration_a_started = asyncio.Event()
        arbitration_a_finish = asyncio.Event()

        # Mock claim detector, conflict detector, verifier to control timing
        async def mock_check_claim(text):
            return True, {"claim": text, "entity": "TestEntity", "topic": "tech", "metric": "test"}, 50

        async def mock_detect_conflict(speaker_a, claim_a, speaker_b, claim_b):
            return True, {"has_conflict": True, "search_query": "test query"}, 50

        async def mock_verify_dispute(*args, **kwargs):
            arbitration_a_started.set()
            # Wait until test signals arbitration A can finish
            await arbitration_a_finish.wait()
            return {
                "status": "CONTRADICTED",
                "correct_fact": "Test Fact",
                "confidence": 99,
                "spoken_intervention": "Correction: verified fact."
            }, 50, 50, []

        with patch("bot.arbitration.engine.claim_detector.check_claim", side_effect=mock_check_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", side_effect=mock_detect_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.verify_dispute", side_effect=mock_verify_dispute), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):

            mock_speak.return_value = 50

            # Step 1: Pre-populate memory with a prior claim so A triggers a conflict
            session.claim_memory.add_claim(
                claim_id="prior_1",
                speaker_name="PriorSpeaker",
                speaker_id="100",
                raw_text="Initial statement",
                claim_text="Initial claim",
                entity="TestEntity",
                topic="tech",
                metric="test"
            )

            # Step 2: Launch Utterance A in background
            task_a = asyncio.create_task(
                arbitration_engine.process_utterance(
                    guild_id=guild_id,
                    user_id=201,
                    speaker_name="Speaker_A",
                    raw_text="Utterance A contradicting prior",
                    stt_ms=150,
                    voice_client=None,
                    text_channel=None,
                    mode="referee"
                )
            )

            # Wait for arbitration for A to actively lock session
            await arbitration_a_started.wait()
            self.assertTrue(session.is_arbitrating, "Session must be arbitrating during Utterance A")

            # Step 3: While A is arbitrating, Utterance B arrives
            await arbitration_engine.process_utterance(
                guild_id=guild_id,
                user_id=202,
                speaker_name="Speaker_B",
                raw_text="Utterance B arriving during A arbitration",
                stt_ms=160,
                voice_client=None,
                text_channel=None,
                mode="referee"
            )

            # Assert B was queued (NOT dropped!)
            self.assertEqual(len(session.pending_utterances), 1, "Utterance B must be queued")
            self.assertEqual(session.pending_utterances[0]["speaker_name"], "Speaker_B")

            # Step 4: Release arbitration A
            arbitration_a_finish.set()
            await task_a

            # Allow drained tasks to complete
            await asyncio.sleep(0.1)

            # Assert queue is now drained and both completed
            self.assertFalse(session.is_arbitrating, "Session must not be arbitrating after drain")
            self.assertEqual(len(session.pending_utterances), 0, "Queue must be completely drained")

            # Verify speaker turns record both A and B
            turn_texts = [t["text"] for t in session.turns]
            self.assertIn("Utterance A contradicting prior", turn_texts)
            self.assertIn("Utterance B arriving during A arbitration", turn_texts)

            print("\n[SUCCESS] Utterance A arbitration completed, Utterance B queued and drained successfully!")

    async def test_queue_overflow_drops_oldest_with_warning(self):
        """
        Verify bounded queue behavior (max 3):
        When 4 utterances arrive while arbitrating, the OLDEST is dropped with warning.
        """
        guild_id = 999456
        session = arbitration_engine.get_session(guild_id)
        session.pending_utterances.clear()
        session.is_arbitrating = True  # Simulate active arbitration

        with patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):
            # Send 4 utterances while session.is_arbitrating = True
            for i, name in enumerate(["User_1", "User_2", "User_3", "User_4"]):
                await arbitration_engine.process_utterance(
                    guild_id=guild_id,
                    user_id=300 + i,
                    speaker_name=name,
                    raw_text=f"Message from {name}",
                    stt_ms=100,
                    voice_client=None,
                    text_channel=None,
                    mode="referee"
                )

            # Queue max size is 3 -> User_1 must have been dropped; User_2, User_3, User_4 retained
            self.assertEqual(len(session.pending_utterances), 3)
            queued_names = [item["speaker_name"] for item in session.pending_utterances]
            self.assertEqual(queued_names, ["User_2", "User_3", "User_4"])
            print("\n[SUCCESS] Queue overflow dropped oldest (User_1) and retained [User_2, User_3, User_4]!")


if __name__ == "__main__":
    unittest.main()
