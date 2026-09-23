import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.arbitration.engine import arbitration_engine
from bot.arbitration.claim_memory import StoredClaim

# Configure root/test logging so we capture engine log lines
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class TestFix4FastGate(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for Fix 4:
    - Banter text skips arbitration with log line '⚡ [FastGate Skip]'
    - Analytics talk-time is unaffected and still recorded
    - Factual text proceeds to conflict detection
    """

    async def test_banter_skips_arbitration_with_log(self):
        guild_id = 900401
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        banter_text = "يا عم تمام ههههه"

        with self.assertLogs("ArbitrationEngine", level="INFO") as cm, \
             patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock) as mock_claim, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):

            await arbitration_engine.process_utterance(
                guild_id=guild_id,
                user_id=101,
                speaker_name="Karim",
                raw_text=banter_text,
                stt_ms=120,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=0.0,
                speech_end=2.5
            )

            # FastGate must skip arbitration before Groq claim detector
            mock_claim.assert_not_called()

            # Verify log line
            skip_logs = [line for line in cm.output if "⚡ [FastGate Skip]" in line]
            self.assertTrue(len(skip_logs) > 0, "Must log FastGate Skip")
            print("\n--- BANTER LOG OUTPUT ---")
            for log_line in skip_logs:
                print(log_line)

            # Verify analytics path was unaffected: talk-time recorded
            speaker_stats = session._stats_tracker.get_speaker("101")
            self.assertIsNotNone(speaker_stats)
            self.assertGreater(speaker_stats.total_speak_seconds, 0)
            self.assertEqual(speaker_stats.utterance_count, 1)
            print(f"Banter talk-time verified: {speaker_stats.total_speak_seconds}s (utterances: {speaker_stats.utterance_count})")

    async def test_factual_text_proceeds_to_conflict_detection(self):
        guild_id = 900402
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        # Seed memory with prior claim to trigger conflict detection check
        session.claim_memory.add_claim(
            claim_id="prior_5070",
            speaker_name="Omar",
            speaker_id="102",
            raw_text="كارت 5070 نازل بـ 16 جيجا",
            claim_text="كارت 5070 نازل بـ 16 جيجا",
            entity="RTX 5070",
            topic="tech",
            metric="16 جيجا"
        )

        factual_text = "كارت الـ RTX 5070 نازل بـ 12 جيجا"

        mock_claim_result = (
            True,
            {"claim": factual_text, "entity": "RTX 5070", "topic": "tech", "metric": "12 جيجا"},
            45
        )

        with self.assertLogs("ArbitrationEngine", level="INFO") as cm, \
             patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim_result) as mock_claim, \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock) as mock_conflict, \
             patch("bot.arbitration.engine.arbitration_verifier.verify_dispute", new_callable=AsyncMock) as mock_verify, \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock), \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):

            mock_conflict.return_value = (True, {"has_conflict": True, "search_query": "RTX 5070 VRAM specs"}, 40)
            mock_verify.return_value = ({
                "status": "CONTRADICTED",
                "correct_fact": "RTX 5070 comes with 12GB VRAM",
                "confidence": 98,
                "spoken_intervention": "تصحيح: كارت 5070 بيجي بـ 12 جيجا بايت VRAM مش 16."
            }, 60, 200, [])

            await arbitration_engine.process_utterance(
                guild_id=guild_id,
                user_id=103,
                speaker_name="Tarek",
                raw_text=factual_text,
                stt_ms=130,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=3.0,
                speech_end=6.5
            )

            # Groq claim detector must have been called
            mock_claim.assert_called_once_with(factual_text)

            # Conflict detector must have been invoked
            mock_conflict.assert_called_once()
            print("\n--- FACTUAL LOG OUTPUT ---")
            for log_line in cm.output:
                if "Conflict" in log_line or "FastGate" in log_line or "Batched" in log_line or "Session" in log_line:
                    print(log_line)

            print(f"Conflict detection called successfully with args: {mock_conflict.call_args}")


if __name__ == "__main__":
    unittest.main()
