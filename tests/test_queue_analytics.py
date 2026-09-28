"""
Acceptance test for queued utterance analytics drain (DATA-02).
Verifies that utterances arriving during active arbitration are queued,
and upon drain, route through analytics (talk-time tracking, streak, analytics buffer)
as well as the arbitration pipeline.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.arbitration.engine import arbitration_engine
from bot.arbitration.stats import SessionStatsTracker


class TestQueueAnalytics(unittest.IsolatedAsyncioTestCase):

    async def test_queued_utterances_record_analytics_on_drain(self):
        """
        FIX 1 (DATA-02):
        3 utterances arrive during active arbitration.
        Before drain: utterances are queued in pending_utterances, not yet in stats_tracker or analytics_buffer.
        After _drain_queue(): all 3 appear in stats_tracker with talk_seconds > 0 AND in analytics_buffer.
        """
        guild_id = 999789
        session = arbitration_engine.get_session(guild_id)
        session.pending_utterances.clear()
        session.analytics_buffer.clear()
        session.analyzed_utterances.clear()
        session._stats_tracker = SessionStatsTracker(session_id=str(guild_id))
        session.is_arbitrating = True

        with patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):
            # Send 3 utterances while arbitrating
            for i, name in enumerate(["Alice", "Bob", "Charlie"]):
                await arbitration_engine.process_utterance(
                    guild_id=guild_id,
                    user_id=400 + i,
                    speaker_name=name,
                    raw_text=f"Statement from {name} while arbitrating",
                    stt_ms=100,
                    voice_client=None,
                    text_channel=None,
                    mode="referee",
                    speech_start=10.0 * (i + 1),
                    speech_end=10.0 * (i + 1) + 4.0
                )

            # Assert they were queued
            self.assertEqual(len(session.pending_utterances), 3)
            # Before drain: stats_tracker has 0 talk seconds for each
            for i in range(3):
                spk = session._stats_tracker.get_speaker(str(400 + i))
                self.assertIsNone(spk)
            self.assertEqual(len(session.analytics_buffer), 0)

            # Now arbitration ends and queue is drained
            session.is_arbitrating = False
            with patch.object(arbitration_engine, "_run_pipeline", new_callable=AsyncMock):
                await arbitration_engine._drain_queue(guild_id, session)

            # After drain: all 3 must appear in stats_tracker with talk_seconds > 0 AND in analytics_buffer
            self.assertEqual(len(session.analytics_buffer), 3)
            for i, name in enumerate(["Alice", "Bob", "Charlie"]):
                spk = session._stats_tracker.get_speaker(str(400 + i))
                self.assertIsNotNone(spk)
                self.assertGreater(spk.total_speak_seconds, 0)
                print(f"[Stats Output] {name} (ID: {400+i}): total_speak_seconds={spk.total_speak_seconds:.2f}s, utterance_count={spk.utterance_count}, streak={spk.current_streak:.2f}s")

            buffered_names = [item["speaker_name"] for item in session.analytics_buffer]
            self.assertEqual(buffered_names, ["Alice", "Bob", "Charlie"])


if __name__ == "__main__":
    unittest.main()
