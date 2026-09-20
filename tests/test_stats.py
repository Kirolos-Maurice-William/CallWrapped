"""
Unit tests for real-time per-speaker talk statistics and streak calculation.
Enforces non-negotiable rules:
- Timestamps from RMS speech windows only (no WAV byte counting).
- Exact validation of all six fields:
  speaker_id, total_speak_seconds, utterance_count,
  longest_streak_seconds, current_streak, last_utterance_end.
"""

import unittest
from bot.arbitration.stats import SpeakerStats, SessionStatsTracker


class TestSpeakerTalkStatistics(unittest.TestCase):

    def test_synthetic_five_utterances_two_speakers(self):
        """
        Synthetic utterance sequence with known times across two speakers:
        Utterance 1: Alice (0.0 -> 10.0, dur 10.0s) -> streak 10.0s
        Utterance 2: Alice (12.0 -> 20.0, dur 8.0s, gap 2.0s < 5s) -> streak accumulates to 18.0s
        Utterance 3: Bob   (22.0 -> 26.0, dur 4.0s) -> Bob streak 4.0s, Alice streak broken to 0.0s
        Utterance 4: Alice (28.0 -> 33.0, dur 5.0s) -> Alice new streak 5.0s, Bob streak broken
        Utterance 5: Alice (40.0 -> 45.0, dur 5.0s, gap 7.0s >= 5s) -> Alice new streak 5.0s (gap >= 5s)
        """
        tracker = SessionStatsTracker(session_id="test_session")

        # --- Utterance 1: Alice speaks 10 seconds ---
        s1 = tracker.record_utterance(
            speaker_id="alice",
            speech_start=0.0,
            speech_end=10.0,
            speaker_name="Alice"
        )
        self.assertEqual(s1.speaker_id, "alice")
        self.assertAlmostEqual(s1.total_speak_seconds, 10.0, places=3)
        self.assertEqual(s1.utterance_count, 1)
        self.assertAlmostEqual(s1.longest_streak_seconds, 10.0, places=3)
        self.assertAlmostEqual(s1.current_streak, 10.0, places=3)
        self.assertAlmostEqual(s1.last_utterance_end, 10.0, places=3)

        # --- Utterance 2: Alice speaks 8 seconds after a 2.0s gap (< 5s, no other user) ---
        s2 = tracker.record_utterance(
            speaker_id="alice",
            speech_start=12.0,
            speech_end=20.0,
            speaker_name="Alice"
        )
        self.assertEqual(s2.speaker_id, "alice")
        self.assertAlmostEqual(s2.total_speak_seconds, 18.0, places=3)
        self.assertEqual(s2.utterance_count, 2)
        self.assertAlmostEqual(s2.longest_streak_seconds, 18.0, places=3)
        self.assertAlmostEqual(s2.current_streak, 18.0, places=3)
        self.assertAlmostEqual(s2.last_utterance_end, 20.0, places=3)

        # --- Utterance 3: Bob speaks 4 seconds (breaks Alice's streak) ---
        s3 = tracker.record_utterance(
            speaker_id="bob",
            speech_start=22.0,
            speech_end=26.0,
            speaker_name="Bob"
        )
        # Check Bob's 6 fields
        self.assertEqual(s3.speaker_id, "bob")
        self.assertAlmostEqual(s3.total_speak_seconds, 4.0, places=3)
        self.assertEqual(s3.utterance_count, 1)
        self.assertAlmostEqual(s3.longest_streak_seconds, 4.0, places=3)
        self.assertAlmostEqual(s3.current_streak, 4.0, places=3)
        self.assertAlmostEqual(s3.last_utterance_end, 26.0, places=3)

        # Check Alice's 6 fields after Bob spoke (streak broken)
        alice_after_bob = tracker.get_speaker("alice")
        self.assertEqual(alice_after_bob.speaker_id, "alice")
        self.assertAlmostEqual(alice_after_bob.total_speak_seconds, 18.0, places=3)
        self.assertEqual(alice_after_bob.utterance_count, 2)
        self.assertAlmostEqual(alice_after_bob.longest_streak_seconds, 18.0, places=3)
        self.assertAlmostEqual(alice_after_bob.current_streak, 0.0, places=3)
        self.assertAlmostEqual(alice_after_bob.last_utterance_end, 20.0, places=3)

        # --- Utterance 4: Alice speaks 5 seconds (new streak started, breaks Bob's streak) ---
        s4 = tracker.record_utterance(
            speaker_id="alice",
            speech_start=28.0,
            speech_end=33.0,
            speaker_name="Alice"
        )
        self.assertEqual(s4.speaker_id, "alice")
        self.assertAlmostEqual(s4.total_speak_seconds, 23.0, places=3)
        self.assertEqual(s4.utterance_count, 3)
        self.assertAlmostEqual(s4.longest_streak_seconds, 18.0, places=3)
        self.assertAlmostEqual(s4.current_streak, 5.0, places=3)
        self.assertAlmostEqual(s4.last_utterance_end, 33.0, places=3)

        # Check Bob's streak is broken
        bob_after_alice = tracker.get_speaker("bob")
        self.assertAlmostEqual(bob_after_alice.current_streak, 0.0, places=3)

        # --- Utterance 5: Alice speaks 5 seconds after 7.0s gap (>= 5s, new streak) ---
        s5 = tracker.record_utterance(
            speaker_id="alice",
            speech_start=40.0,
            speech_end=45.0,
            speaker_name="Alice"
        )
        # Final assertion on Alice's all six fields:
        self.assertEqual(s5.speaker_id, "alice")
        self.assertAlmostEqual(s5.total_speak_seconds, 28.0, places=3)
        self.assertEqual(s5.utterance_count, 4)
        self.assertAlmostEqual(s5.longest_streak_seconds, 18.0, places=3)
        self.assertAlmostEqual(s5.current_streak, 5.0, places=3)
        self.assertAlmostEqual(s5.last_utterance_end, 45.0, places=3)

        # Final assertion on Bob's all six fields:
        bob_final = tracker.get_speaker("bob")
        self.assertEqual(bob_final.speaker_id, "bob")
        self.assertAlmostEqual(bob_final.total_speak_seconds, 4.0, places=3)
        self.assertEqual(bob_final.utterance_count, 1)
        self.assertAlmostEqual(bob_final.longest_streak_seconds, 4.0, places=3)
        self.assertAlmostEqual(bob_final.current_streak, 0.0, places=3)
        self.assertAlmostEqual(bob_final.last_utterance_end, 26.0, places=3)

    def test_force_split_fifteen_seconds_continuation(self):
        """
        Verify that 15s VAD force-split buffers chained together form one continuous streak.
        Utterance 1: 0.0 -> 15.0 (15.0s)
        Utterance 2: 15.0 -> 25.0 (10.0s, gap=0.0s)
        Total streak must be 25.0s.
        """
        tracker = SessionStatsTracker()
        tracker.record_utterance("charlie", 0.0, 15.0, "Charlie")
        s = tracker.record_utterance("charlie", 15.0, 25.0, "Charlie")

        self.assertEqual(s.speaker_id, "charlie")
        self.assertAlmostEqual(s.total_speak_seconds, 25.0, places=3)
        self.assertEqual(s.utterance_count, 2)
        self.assertAlmostEqual(s.longest_streak_seconds, 25.0, places=3)
        self.assertAlmostEqual(s.current_streak, 25.0, places=3)
        self.assertAlmostEqual(s.last_utterance_end, 25.0, places=3)


if __name__ == "__main__":
    unittest.main()
