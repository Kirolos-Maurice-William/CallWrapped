"""
Unit tests for Continuous Topic Interval State Tracking and Anaphora Inheritance.
Verifies that discourse intervals correctly span elliptical / pronoun turns and
measure true elapsed continuous discussion duration rather than discrete utterance tallying.
"""

import sys
import unittest
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.arbitration.engine import SessionState, TopicInterval, arbitration_engine


class TestTopicIntervalTracker(unittest.TestCase):

    def test_initial_topic_interval_creation(self):
        session = SessionState(guild_id=123)
        self.assertIsNone(session.active_interval)
        self.assertEqual(len(session.completed_intervals), 0)
        self.assertEqual(session.get_topic_durations(), {})

        # null_topic initially does not start a discourse interval
        session.record_topic_turn(
            macro_topic="null_topic",
            canonical_tag="",
            speaker_name="Mostafa",
            timestamp=100.0,
            duration=2.0
        )
        self.assertIsNone(session.active_interval)

        # First meaningful topic turn starts an active interval
        session.record_topic_turn(
            macro_topic="gaming",
            canonical_tag="League of Legends",
            speaker_name="Mostafa",
            timestamp=105.0,
            duration=4.0
        )
        self.assertIsNotNone(session.active_interval)
        self.assertEqual(session.active_interval.macro_topic, "gaming")
        self.assertEqual(session.active_interval.canonical_tag, "League of Legends")
        self.assertEqual(session.active_interval.start_time, 105.0)
        self.assertEqual(session.active_interval.last_activity_time, 109.0)
        self.assertEqual(session.active_interval.turn_count, 1)
        self.assertIn("Mostafa", session.active_interval.participating_speakers)
        self.assertEqual(session.active_interval.duration_seconds, 4.0)

    def test_anaphora_and_ellipsis_topic_continuation(self):
        """
        Direct verification of user's core insight:
        Line 1: 'league of legends is a good game' (gaming)
        Line 2: 'not is not a good game' (elliptical, gaming)
        Line 3: 'guys not all gaming is about league of legends' (gaming)
        Line 4: 'no it is all about it' (anaphoric, no gaming keywords -> tagged other/null)
        All 4 lines must sustain the single continuous 'gaming' discourse interval.
        """
        session = SessionState(guild_id=456)

        # Line 1: t=10.0 to 14.0
        session.record_topic_turn(
            macro_topic="gaming",
            canonical_tag="League of Legends",
            speaker_name="Speaker A",
            timestamp=10.0,
            duration=4.0,
            evidence="league of legends is a good game"
        )

        # Line 2: t=15.0 to 18.0 (1s gap)
        session.record_topic_turn(
            macro_topic="gaming",
            canonical_tag="League of Legends",
            speaker_name="Speaker B",
            timestamp=15.0,
            duration=3.0,
            evidence="not is not a good game"
        )

        # Line 3: t=19.0 to 24.0 (1s gap)
        session.record_topic_turn(
            macro_topic="gaming",
            canonical_tag="League of Legends",
            speaker_name="Speaker C",
            timestamp=19.0,
            duration=5.0,
            evidence="guys not all gaming is about league of legends"
        )

        # Line 4: t=25.0 to 28.0 (1s gap) - Elliptical/anaphoric turn classified as 'other' or 'null_topic'
        session.record_topic_turn(
            macro_topic="other",
            canonical_tag="",
            speaker_name="Speaker D",
            timestamp=25.0,
            duration=3.0,
            evidence="no it is all about it"
        )

        interval = session.active_interval
        self.assertIsNotNone(interval)
        self.assertEqual(interval.macro_topic, "gaming")
        self.assertEqual(interval.canonical_tag, "League of Legends")
        self.assertEqual(interval.turn_count, 4)
        self.assertEqual(len(interval.participating_speakers), 4)
        self.assertEqual({"Speaker A", "Speaker B", "Speaker C", "Speaker D"}, interval.participating_speakers)

        # True continuous duration = 28.0 - 10.0 = 18.0 seconds
        self.assertEqual(interval.duration_seconds, 18.0)
        durations = session.get_topic_durations()
        self.assertEqual(durations["gaming"], 18.0)

    def test_topic_shift_closes_old_interval_and_accrues_duration(self):
        session = SessionState(guild_id=789)

        # Gaming discussion for 18.0 seconds
        session.record_topic_turn("gaming", "League of Legends", "A", 10.0, 4.0)
        session.record_topic_turn("gaming", "League of Legends", "B", 15.0, 3.0)
        session.record_topic_turn("gaming", "League of Legends", "C", 20.0, 8.0)  # ends at 28.0

        # Topic shift to Football at t=30.0 (ends at 35.0)
        session.record_topic_turn(
            macro_topic="football",
            canonical_tag="الأهلي",
            speaker_name="A",
            timestamp=30.0,
            duration=5.0,
            evidence="شفت ماتش الأهلي امبارح"
        )

        # Gaming interval should now be completed and accrued
        self.assertEqual(len(session.completed_intervals), 1)
        completed = session.completed_intervals[0]
        self.assertEqual(completed.macro_topic, "gaming")
        self.assertEqual(completed.duration_seconds, 18.0)

        # Active interval should be football
        self.assertIsNotNone(session.active_interval)
        self.assertEqual(session.active_interval.macro_topic, "football")
        self.assertEqual(session.active_interval.canonical_tag, "الأهلي")
        self.assertEqual(session.active_interval.duration_seconds, 5.0)

        # Topic durations dict should report both
        durs = session.get_topic_durations()
        self.assertEqual(durs["gaming"], 18.0)
        self.assertEqual(durs["football"], 5.0)

        # Explicit close_active_interval (e.g. at end of session)
        session.close_active_interval()
        self.assertIsNone(session.active_interval)
        self.assertEqual(len(session.completed_intervals), 2)
        durs_after = session.get_topic_durations()
        self.assertEqual(durs_after["gaming"], 18.0)
        self.assertEqual(durs_after["football"], 5.0)

    def test_silence_boundary_closes_interval(self):
        session = SessionState(guild_id=999)

        # Gaming block 1: t=0.0 to 5.0
        session.record_topic_turn("gaming", "GTA", "User1", 0.0, 5.0)

        # Gap of 50 seconds (> 45s threshold)
        session.record_topic_turn("gaming", "GTA", "User1", 55.0, 5.0)

        # First block should have closed due to silence boundary
        self.assertEqual(len(session.completed_intervals), 1)
        self.assertEqual(session.completed_intervals[0].duration_seconds, 5.0)
        self.assertEqual(session.active_interval.start_time, 55.0)
        self.assertEqual(session.active_interval.duration_seconds, 5.0)

        # Total gaming duration: 5.0 + 5.0 = 10.0 (silence is NOT accrued as topic duration!)
        self.assertEqual(session.get_topic_durations()["gaming"], 10.0)

    def test_session_reset_clears_all_intervals_and_durations(self):
        session = SessionState(guild_id=111)
        session.add_discovered_entity("Scout Master", ["وستيسكات ماستر"])
        session.record_topic_turn("gaming", "Scout Master", "Mostafa", 10.0, 10.0)
        session.record_topic_turn("tech", "RTX 5070", "Ahmed", 25.0, 10.0)

        self.assertEqual(len(session.completed_intervals), 1)
        self.assertIsNotNone(session.active_interval)
        self.assertEqual(len(session.discovered_entities), 1)
        self.assertEqual(len(session.entity_aliases), 1)

        session.reset()

        self.assertIsNone(session.active_interval)
        self.assertEqual(len(session.completed_intervals), 0)
        self.assertEqual(len(session.topic_durations), 0)
        self.assertEqual(len(session.discovered_entities), 0)
        self.assertEqual(len(session.entity_aliases), 0)
        self.assertEqual(session.get_topic_durations(), {})

    def test_apply_batch_results_entity_upgrade_and_intervals(self):
        """
        Tests that _apply_batch_results correctly:
        1. Resolves phonetic variants against session entities.
        2. Upgrades empty/generic tags to canonical entity.
        3. Auto-registers new entities into session discovered_entities.
        4. Accrues continuous topic intervals.
        """
        session = arbitration_engine.get_session(555)
        session.reset()
        session.add_discovered_entity("Scout Master")

        buffer_to_process = [
            {
                "timestamp": 15.0,
                "speaker_name": "Mostafa",
                "user_id": 1,
                "text": "وستيسكات ماستر هينزل بكرا",
                "talk_delta_seconds": 5.0,
                "streak_seconds": 5.0,
                "correlation_id": "c1",
                "audio_features": None
            },
            {
                "timestamp": 22.0,
                "speaker_name": "Ali",
                "user_id": 2,
                "text": "لا مش نازل بكرا",
                "talk_delta_seconds": 4.0,
                "streak_seconds": 4.0,
                "correlation_id": "c2",
                "audio_features": None
            }
        ]

        # Groq batch results: line 1 missed specific tag, line 2 labeled as other/ellipsis
        mock_results = [
            {"line_number": 1, "topic": "gaming", "tag": "", "anger": "none", "anger_evidence": ""},
            {"line_number": 2, "topic": "other", "tag": "", "anger": "none", "anger_evidence": ""}
        ]

        arbitration_engine._apply_batch_results(
            session=session,
            guild_id=555,
            buffer_to_process=buffer_to_process,
            results=mock_results,
            tokens={"total_tokens": 150},
            reason="test_flush"
        )

        # 1. Phonetic variant 'وستيسكات ماستر' should have been registered as alias for 'Scout Master'
        self.assertIn("وستيسكات ماستر", session.entity_aliases)
        self.assertEqual(session.entity_aliases["وستيسكات ماستر"], "Scout Master")

        # 2. Both turns should be part of the active gaming interval
        interval = session.active_interval
        self.assertIsNotNone(interval)
        self.assertEqual(interval.macro_topic, "gaming")
        self.assertEqual(interval.canonical_tag, "Scout Master")
        self.assertEqual(interval.turn_count, 2)
        self.assertIn("Mostafa", interval.participating_speakers)
        self.assertIn("Ali", interval.participating_speakers)

        # 3. Continuous duration from line 1 start (15.0 - 5.0 = 10.0) to line 2 end (22.0) = 12.0s
        self.assertEqual(interval.duration_seconds, 12.0)
        self.assertEqual(session.get_topic_durations()["gaming"], 12.0)


if __name__ == "__main__":
    unittest.main()
