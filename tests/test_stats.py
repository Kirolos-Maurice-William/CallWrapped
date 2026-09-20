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

    def test_acceptance_five_angry_utterances_within_sixty_seconds_is_one_episode(self):
        """
        ACCEPTANCE (a): 5 angry utterances within 60s = exactly 1 episode.
        Timestamps: 0.0s, 12.0s, 25.0s, 42.0s, 58.0s (all within 60s).
        """
        tracker = SessionStatsTracker(session_id="anger_test_1")
        timestamps = [0.0, 12.0, 25.0, 42.0, 58.0]
        quotes = [
            "للسط مرتين علطول",
            "يا خسارة الدبيل ده",
            "زهقت خلاص",
            "الرانك بيعصب أوي",
            "سيرفر زبالة"
        ]

        for idx, (t, q) in enumerate(zip(timestamps, quotes), 1):
            s = tracker.record_anger(
                speaker_id="alice",
                timestamp=t,
                anger="mild",
                anger_quote=q,
                speaker_name="Alice"
            )
            self.assertEqual(s.angry_episodes, 1, f"Utterance {idx} at t={t}s should maintain 1 episode, got {s.angry_episodes}")

        alice = tracker.get_speaker("alice")
        self.assertEqual(alice.angry_episodes, 1)
        self.assertAlmostEqual(alice.last_anger_time, 58.0, places=3)
        self.assertEqual(alice.first_anger_quote, "للسط مرتين علطول")

        # Verify to_dict includes anger tracking fields
        d = alice.to_dict()
        self.assertEqual(d["angry_episodes"], 1)
        self.assertEqual(d["last_anger_time"], 58.0)
        self.assertEqual(d["first_anger_quote"], "للسط مرتين علطول")

    def test_acceptance_two_angry_utterances_three_minutes_apart_is_two_episodes(self):
        """
        ACCEPTANCE (b): 2 angry utterances 3 minutes apart = exactly 2 episodes.
        Utterance 1 at 0.0s (Episode 1)
        Utterance 2 at 180.0s (3 min later > 90s window -> Episode 2)
        """
        tracker = SessionStatsTracker(session_id="anger_test_2")

        # Utterance 1 at t = 0.0s
        s1 = tracker.record_anger(
            speaker_id="bob",
            timestamp=0.0,
            anger="mild",
            anger_quote="الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            speaker_name="Bob"
        )
        self.assertEqual(s1.angry_episodes, 1)
        self.assertAlmostEqual(s1.last_anger_time, 0.0, places=3)
        self.assertEqual(s1.first_anger_quote, "الكول أوف ديوتي زبالة والرانك بيعصب أوي")

        # Utterance 2 at t = 180.0s (3 minutes later)
        s2 = tracker.record_anger(
            speaker_id="bob",
            timestamp=180.0,
            anger="mild",
            anger_quote="زهقت من السيرفر ده بجد",
            speaker_name="Bob"
        )
        self.assertEqual(s2.angry_episodes, 2)
        self.assertAlmostEqual(s2.last_anger_time, 180.0, places=3)
        # first_anger_quote retains the initial anger quote
        self.assertEqual(s2.first_anger_quote, "الكول أوف ديوتي زبالة والرانك بيعصب أوي")

    def test_anger_with_classifier_output_and_neutral_utterance(self):
        """
        Verifies interaction with classifier dict format and confirms neutral
        utterances (anger='none') do NOT increment angry_episodes or touch last_anger_time.
        """
        tracker = SessionStatsTracker(session_id="anger_test_3")

        # 1. Angry classification via dict
        c1 = {"anger": "mild", "anger_evidence": "زهقت خلاص", "topic": "gaming", "is_factual_claim": False}
        s = tracker.record_classification("player1", timestamp=10.0, classification=c1)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 10.0, places=3)
        self.assertEqual(s.first_anger_quote, "زهقت خلاص")

        # 2. Neutral utterance at t=30.0s (anger='none')
        c2 = {"anger": "none", "anger_evidence": None, "topic": "other", "is_factual_claim": False}
        s = tracker.record_classification("player1", timestamp=30.0, classification=c2)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 10.0, places=3)  # last_anger_time untouched

        # 3. Second angry utterance at t=50.0s (within 90s of t=10.0s -> continues episode 1)
        c3 = {"anger": "high", "anger_evidence": "حرام كدة بجد", "topic": "gaming", "is_factual_claim": False}
        s = tracker.record_classification("player1", timestamp=50.0, classification=c3)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 50.0, places=3)


if __name__ == "__main__":
    unittest.main()

