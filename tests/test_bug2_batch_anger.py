"""
BUG 2 Acceptance Test:
Verifies that anger episodes are NOT counted on anger=none lines in the batch analytics path.
Scenario A: Batch of 5 lines all anger=none -> 0 episodes.
Scenario B: Batch of 5 lines with 1 mild line -> exactly 1 episode.
"""
import tests._setup
import time
import unittest
from bot.arbitration.engine import arbitration_engine, SessionState


class TestBatchAngerFiltering(unittest.TestCase):

    def test_five_lines_all_none_produces_zero_episodes(self):
        """Scenario A: Batch of 5 lines all anger=none -> 0 episodes."""
        guild_id = 888111
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        now = time.time()
        buffer_items = [
            {
                "timestamp": now + i,
                "speaker_id": "1001",
                "speaker_name": "Mostafa",
                "user_id": 1001,
                "text": f"Regular conversation line {i+1}",
                "talk_delta_seconds": 2.0,
                "streak_seconds": 2.0 * (i + 1),
                "correlation_id": f"corr_none_{i+1}"
            }
            for i in range(5)
        ]

        batch_results = [
            {
                "line_number": i + 1,
                "topic": "gaming",
                "anger": "none",
                "anger_evidence": None
            }
            for i in range(5)
        ]

        print("\n" + "=" * 65)
        print("=== BUG 2 ACCEPTANCE: SCENARIO A (5 LINES ALL ANGER=NONE) ===")
        print("=" * 65)

        with self.assertLogs("ArbitrationEngine", level="INFO") as cm:
            arbitration_engine._apply_batch_results(
                session=session,
                guild_id=guild_id,
                buffer_to_process=buffer_items,
                results=batch_results,
                tokens={},
                reason="test_batch_none"
            )

        for log in cm.output:
            if "[Batched Analytics Line]" in log:
                print(f"  {log}")

        speaker_stats = session._stats_tracker.get_speaker("1001")
        self.assertIsNotNone(speaker_stats)
        self.assertEqual(
            speaker_stats.angry_episodes, 0,
            f"Expected 0 angry episodes for 5 anger=none lines, got {speaker_stats.angry_episodes}"
        )
        self.assertIsNone(speaker_stats.first_anger_quote)
        print(f"\n[VERIFIED] Mostafa angry_episodes = {speaker_stats.angry_episodes} (Expected: 0)")
        print("=" * 65 + "\n")

    def test_five_lines_one_mild_produces_exactly_one_episode(self):
        """Scenario B: Batch of 5 lines with 1 mild line among them -> exactly 1 episode."""
        guild_id = 888222
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        now = time.time()
        buffer_items = [
            {
                "timestamp": now + i,
                "speaker_id": "1002",
                "speaker_name": "Karim",
                "user_id": 1002,
                "text": f"Karim utterance {i+1}",
                "talk_delta_seconds": 2.0,
                "streak_seconds": 2.0 * (i + 1),
                "correlation_id": f"corr_mild_{i+1}"
            }
            for i in range(5)
        ]

        # 4 lines none, line 3 is mild
        batch_results = [
            {"line_number": 1, "topic": "tech", "anger": "none", "anger_evidence": None},
            {"line_number": 2, "topic": "gaming", "anger": "none", "anger_evidence": None},
            {"line_number": 3, "topic": "gaming", "anger": "mild", "anger_evidence": "زهقت خلاص من السيرفر ده"},
            {"line_number": 4, "topic": "football", "anger": "none", "anger_evidence": None},
            {"line_number": 5, "topic": "movies", "anger": "none", "anger_evidence": None},
        ]

        print("\n" + "=" * 65)
        print("=== BUG 2 ACCEPTANCE: SCENARIO B (4 NONE + 1 MILD LINE) ===")
        print("=" * 65)

        with self.assertLogs("ArbitrationEngine", level="INFO") as cm:
            arbitration_engine._apply_batch_results(
                session=session,
                guild_id=guild_id,
                buffer_to_process=buffer_items,
                results=batch_results,
                tokens={},
                reason="test_batch_one_mild"
            )

        for log in cm.output:
            if "[Batched Analytics Line]" in log:
                print(f"  {log}")

        speaker_stats = session._stats_tracker.get_speaker("1002")
        self.assertIsNotNone(speaker_stats)
        self.assertEqual(
            speaker_stats.angry_episodes, 1,
            f"Expected exactly 1 angry episode for 1 mild line, got {speaker_stats.angry_episodes}"
        )
        self.assertEqual(speaker_stats.first_anger_quote, "زهقت خلاص من السيرفر ده")
        print(f"\n[VERIFIED] Karim angry_episodes = {speaker_stats.angry_episodes} (Expected: 1)")
        print(f"[VERIFIED] Karim first_anger_quote = '{speaker_stats.first_anger_quote}'")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
