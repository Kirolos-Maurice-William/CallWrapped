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
        s = tracker.record_anger("player1", timestamp=10.0, anger=c1)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 10.0, places=3)
        self.assertEqual(s.first_anger_quote, "زهقت خلاص")

        # 2. Neutral utterance at t=30.0s (anger='none')
        c2 = {"anger": "none", "anger_evidence": None, "topic": "other", "is_factual_claim": False}
        s = tracker.record_anger("player1", timestamp=30.0, anger=c2)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 10.0, places=3)  # last_anger_time untouched

        # 3. Second angry utterance at t=50.0s (within 90s of t=10.0s -> continues episode 1)
        c3 = {"anger": "high", "anger_evidence": "حرام كدة بجد", "topic": "gaming", "is_factual_claim": False}
        s = tracker.record_anger("player1", timestamp=50.0, anger=c3)
        self.assertEqual(s.angry_episodes, 1)
        self.assertAlmostEqual(s.last_anger_time, 50.0, places=3)

    def test_anger_episode_with_null_evidence_rejected_without_increment(self):
        """
        ACCEPTANCE (Strict Dual-Evidence Guard):
        Anger episode with null or empty evidence is rejected (angry_episodes remains 0).
        Verifiable anger requires actual verbal evidence.
        """
        tracker = SessionStatsTracker(session_id="anger_null_evidence")
        c1 = {"anger": "mild", "anger_evidence": None, "topic": "gaming", "is_factual_claim": False}
        s = tracker.record_anger("player1", timestamp=10.0, anger=c1)
        self.assertEqual(s.angry_episodes, 0)
        self.assertIsNone(s.first_anger_quote)

        # Verify direct call with null evidence also does not increment
        s2 = tracker.record_anger("player2", timestamp=15.0, anger="mild", anger_quote=None)
        self.assertEqual(s2.angry_episodes, 0)
        self.assertIsNone(s2.first_anger_quote)

        # Verify call with actual quote DOES increment
        s3 = tracker.record_anger("player3", timestamp=20.0, anger="mild", anger_quote="زهقت من اللعبة دي")
        self.assertEqual(s3.angry_episodes, 1)
        self.assertEqual(s3.first_anger_quote, "زهقت من اللعبة دي")


    def test_phase2_topic_share_excludes_null_topic_and_computes_coverage(self):
        """
        Phase 2 Acceptance:
        - topic share percentage denominator EXCLUDES null_topic
        - topic share = (topical time in class k) / (total topical time)
        - Topical coverage = topical_time / total_talk_time
        - All-null edge case yields empty share and 0.0 coverage
        """
        tracker = SessionStatsTracker(session_id="topic_share_test")

        # 60s football, 40s tech, 20s null_topic (total 120s talk, 100s topical)
        tracker.record_utterance("alice", 0.0, 60.0, "Alice", topic="football")
        tracker.record_utterance("bob", 60.0, 100.0, "Bob", topic="tech")
        tracker.record_utterance("alice", 100.0, 120.0, "Alice", topic="null_topic")

        shares = tracker.get_topic_share()
        self.assertIn("football", shares)
        self.assertIn("tech", shares)
        self.assertNotIn("null_topic", shares)
        self.assertAlmostEqual(shares["football"], 60.0, places=1)
        self.assertAlmostEqual(shares["tech"], 40.0, places=1)

        coverage = tracker.get_topical_coverage()
        self.assertAlmostEqual(coverage, 100.0 / 120.0, places=3)

        # All-null edge case
        empty_tracker = SessionStatsTracker(session_id="empty_share_test")
        empty_tracker.record_utterance("alice", 0.0, 10.0, "Alice", topic="null_topic")
        self.assertEqual(empty_tracker.get_topic_share(), {})
        self.assertAlmostEqual(empty_tracker.get_topical_coverage(), 0.0)

    def test_phase3_topic_streak_bridging_with_null_topic(self):
        """
        Phase 3 Acceptance (a):
        - A speaker's null_topic utterance does NOT break their active topic streak if gap < 5s.
        - Null duration is EXCLUDED from topic streak seconds, acting as a bridge.
        - streak length += both topical utterances.
        """
        tracker = SessionStatsTracker(session_id="streak_bridge_test")

        # Utterance 1: Alice speaks football 10s (0.0 -> 10.0)
        s1 = tracker.record_utterance("alice", 0.0, 10.0, "Alice", topic="football")
        self.assertEqual(s1.current_topic, "football")
        self.assertAlmostEqual(s1.current_topic_streak, 10.0, places=3)
        self.assertEqual(s1.topic_streak_count, 1)

        # Utterance 2: Alice utters 'تمام' (null_topic, 1.2s: 11.0 -> 12.2, gap 1.0s < 5s)
        s2 = tracker.record_utterance("alice", 11.0, 12.2, "Alice", topic="null_topic")
        self.assertEqual(s2.current_topic, "football", "null_topic bridges topic streak")
        self.assertAlmostEqual(s2.current_topic_streak, 10.0, places=3, msg="null duration is excluded from topic streak")
        self.assertEqual(s2.topic_streak_count, 1)

        # Utterance 3: Alice continues on football 8s (13.0 -> 21.0, gap 0.8s < 5s)
        s3 = tracker.record_utterance("alice", 13.0, 21.0, "Alice", topic="football")
        self.assertEqual(s3.current_topic, "football")
        self.assertAlmostEqual(s3.current_topic_streak, 18.0, places=3, msg="10s + 8s topical speech")
        self.assertAlmostEqual(s3.longest_topic_streak_seconds, 18.0, places=3)
        self.assertEqual(s3.topic_streak_count, 1, "Must remain 1 continuous streak")

    def test_phase3_listener_backchannel_does_not_break_floor_or_topic_streak(self):
        """
        Phase 3 Acceptance (b):
        - Schegloff (1982) listener backchannel rule:
          A listener's null_topic utterance (< 2.0s duration) does NOT break
          the primary speaker's active monologue or topic streak.
        """
        tracker = SessionStatsTracker(session_id="listener_backchannel_test")

        # 1. Alice speaks football 10s (0.0 -> 10.0)
        tracker.record_utterance("alice", 0.0, 10.0, "Alice", topic="football")

        # 2. Bob utters listener backchannel 'أيوة' (null_topic, 1.0s < 2.0s: 11.0 -> 12.0)
        tracker.record_utterance("bob", 11.0, 12.0, "Bob", topic="null_topic")

        # Alice's active streak should NOT be broken by listener's backchannel
        alice_mid = tracker.get_speaker("alice")
        self.assertEqual(alice_mid.current_topic, "football")
        self.assertAlmostEqual(alice_mid.current_topic_streak, 10.0, places=3)
        self.assertAlmostEqual(alice_mid.current_streak, 10.0, places=3)

        # 3. Alice continues on football 6s (13.0 -> 19.0, gap 3.0s < 5s from Alice's 10.0s end)
        s_alice_final = tracker.record_utterance("alice", 13.0, 19.0, "Alice", topic="football")
        self.assertEqual(s_alice_final.current_topic, "football")
        self.assertAlmostEqual(s_alice_final.current_streak, 16.0, places=3, msg="Monologue streak continues")
        self.assertAlmostEqual(s_alice_final.current_topic_streak, 16.0, places=3, msg="Topic streak continues")
        self.assertEqual(s_alice_final.topic_streak_count, 1)

    def test_phase3_listener_substantive_speech_breaks_floor_and_topic_streak(self):
        """
        Phase 3 Acceptance (c):
        - If listener B speaks a substantive line (non-null), the streak ends normally.
        """
        tracker = SessionStatsTracker(session_id="substantive_interruption_test")

        # Alice speaks football 10s
        tracker.record_utterance("alice", 0.0, 10.0, "Alice", topic="football")

        # Bob takes floor with substantive speech (gaming, 4.0s)
        tracker.record_utterance("bob", 11.0, 15.0, "Bob", topic="gaming")

        alice = tracker.get_speaker("alice")
        self.assertEqual(alice.current_streak, 0.0)
        self.assertIsNone(alice.current_topic)
        self.assertEqual(alice.current_topic_streak, 0.0)

    def test_phase3_topic_switch_ends_topic_streak(self):
        """
        Phase 3 Acceptance (d):
        - If speaker A switches to another topical class ('politics'), the streak ends normally.
        """
        tracker = SessionStatsTracker(session_id="topic_switch_test")

        # Alice speaks football 10s
        tracker.record_utterance("alice", 0.0, 10.0, "Alice", topic="football")

        # Alice switches to politics 5s
        tracker.record_utterance("alice", 11.0, 16.0, "Alice", topic="politics")

        alice = tracker.get_speaker("alice")
        self.assertEqual(alice.current_topic, "politics")
        self.assertAlmostEqual(alice.current_topic_streak, 5.0, places=3)
        self.assertEqual(alice.topic_streak_count, 2)
        self.assertAlmostEqual(alice.longest_topic_streak_seconds, 10.0, places=3)
        self.assertEqual(alice.longest_topic, "football")

    def test_anger_episodes_history_recorded_with_metadata(self):
        """Verifies anger episode history preserves all episode receipts, timestamps, and loudness."""
        tracker = SessionStatsTracker(session_id="anger_history_test")
        
        # Episode 1 at t=10.0s
        tracker.record_anger(
            speaker_id="alice",
            timestamp=10.0,
            anger="mild",
            anger_quote="الكول أوف ديوتي زبالة",
            speaker_name="Alice",
            was_loud=True,
            peak_z=3.8,
            context="boost_applied"
        )
        
        # Rant continuation within 90s (debounce) at t=30.0s -> does not create new episode
        tracker.record_anger(
            speaker_id="alice",
            timestamp=30.0,
            anger="mild",
            anger_quote="مش عارف ألعب",
            speaker_name="Alice"
        )

        # Episode 2 after > 90s at t=125.0s (125 - 30 = 95 > 90)
        tracker.record_anger(
            speaker_id="alice",
            timestamp=125.0,
            anger="high",
            anger_quote="أنا زهقت خلاص كفاية",
            speaker_name="Alice",
            was_loud=True,
            peak_z=4.5,
            context="boost_applied"
        )

        alice = tracker.get_speaker("alice")
        self.assertEqual(alice.angry_episodes, 2)
        self.assertEqual(alice.first_anger_quote, "الكول أوف ديوتي زبالة")
        self.assertEqual(len(alice.anger_episodes_history), 2)
        self.assertEqual(alice.anger_episodes_history[0]["episode_number"], 1)
        self.assertEqual(alice.anger_episodes_history[0]["quote"], "الكول أوف ديوتي زبالة")
        self.assertTrue(alice.anger_episodes_history[0]["was_loud"])
        self.assertEqual(alice.anger_episodes_history[1]["episode_number"], 2)
        self.assertEqual(alice.anger_episodes_history[1]["quote"], "أنا زهقت خلاص كفاية")
        self.assertEqual(alice.anger_episodes_history[1]["anger"], "high")

        # to_dict contains anger_episodes_history
        d = alice.to_dict()
        self.assertIn("anger_episodes_history", d)
        self.assertEqual(len(d["anger_episodes_history"]), 2)


class TestPhase1DurationAndSilentObserver(unittest.TestCase):
    """
    Hostile unit tests for Phase 1:
    - Deterministic duration formatting (format_duration_human).
    - Zero-safe normalized talk share calculation.
    - Honest 'The Silent Observer' detection & tie guards.
    """

    def test_format_duration_human_transitions(self):
        from bot.arbitration.stats import format_duration_human

        # Zero / negative / None edge cases
        self.assertEqual(format_duration_human(0.0), "0s")
        self.assertEqual(format_duration_human(-5.0), "0s")
        self.assertEqual(format_duration_human(None), "0s")
        self.assertEqual(format_duration_human(0.0, lang="ar"), "0ث")
        self.assertEqual(format_duration_human(-1.0, lang="ar"), "0ث")

        # Sub-minute values
        self.assertEqual(format_duration_human(12.0), "12s")
        self.assertEqual(format_duration_human(12.0, lang="ar"), "12ث")
        self.assertEqual(format_duration_human(45.4), "45s")

        # Rounding at 60s boundary
        self.assertEqual(format_duration_human(59.4), "59s")
        self.assertEqual(format_duration_human(59.6), "1m")
        self.assertEqual(format_duration_human(59.6, lang="ar"), "1د")
        self.assertEqual(format_duration_human(60.0), "1m")

        # Minutes and seconds
        self.assertEqual(format_duration_human(75.0), "1m 15s")
        self.assertEqual(format_duration_human(75.0, lang="ar"), "1د 15ث")
        self.assertEqual(format_duration_human(120.0), "2m")
        self.assertEqual(format_duration_human(120.0, lang="ar"), "2د")

        # Hour boundary transitions
        self.assertEqual(format_duration_human(3599.6), "1h")
        self.assertEqual(format_duration_human(3599.6, lang="ar"), "1س")
        self.assertEqual(format_duration_human(3660.0), "1h 1m")
        self.assertEqual(format_duration_human(3660.0, lang="ar"), "1س 1د")
        self.assertEqual(format_duration_human(7200.0), "2h")
        self.assertEqual(format_duration_human(7200.0, lang="ar"), "2س")

    def test_speaker_talk_shares_zero_safe(self):
        tracker = SessionStatsTracker("test_shares")

        # Empty session
        self.assertEqual(tracker.get_speaker_talk_shares(), {})

        # Zero speech recorded
        tracker.get_or_create_speaker("alice", "Alice")
        tracker.get_or_create_speaker("bob", "Bob")
        shares = tracker.get_speaker_talk_shares()
        self.assertEqual(shares["alice"], 0.0)
        self.assertEqual(shares["bob"], 0.0)

        # Alice 60s, Bob 40s -> Alice 60%, Bob 40%
        tracker.record_utterance("alice", 0.0, 60.0, "Alice")
        tracker.record_utterance("bob", 60.0, 100.0, "Bob")
        shares = tracker.get_speaker_talk_shares()
        self.assertEqual(shares["alice"], 60.0)
        self.assertEqual(shares["bob"], 40.0)
        self.assertAlmostEqual(sum(shares.values()), 100.0, places=1)

    def test_silent_observer_badge_logic(self):
        tracker = SessionStatsTracker("test_observer")

        # Case 1: Empty or 1 speaker -> None (solo caller cannot be silent observer)
        self.assertIsNone(tracker.get_silent_observer())
        tracker.record_utterance("alice", 0.0, 60.0, "Alice")
        self.assertIsNone(tracker.get_silent_observer())

        # Case 2: 2 speakers with clear disparity (Alice 90s, Bob 10s)
        tracker.record_utterance("alice", 60.0, 90.0, "Alice")  # Alice total: 90s
        tracker.record_utterance("bob", 95.0, 105.0, "Bob")     # Bob total: 10s
        observer = tracker.get_silent_observer()
        self.assertIsNotNone(observer)
        spk_id, dur, pct = observer
        self.assertEqual(spk_id, "bob")
        self.assertAlmostEqual(dur, 10.0, places=1)
        self.assertAlmostEqual(pct, 10.0, places=1)  # 10s / 100s = 10%

        # Case 3: Honest tie guard (both spoke within 1.0s) -> None
        tracker_tie = SessionStatsTracker("test_tie")
        tracker_tie.record_utterance("alice", 0.0, 50.0, "Alice")
        tracker_tie.record_utterance("bob", 50.0, 99.5, "Bob")  # Alice=50.0s, Bob=49.5s -> diff 0.5s < 1.0s
        self.assertIsNone(tracker_tie.get_silent_observer())

        # Case 4: 3 speakers (Mostafa 120s, Ali 50s, Tamer 10s) -> Tamer is Silent Observer
        tracker_3 = SessionStatsTracker("test_3spk")
        tracker_3.record_utterance("mostafa", 0.0, 120.0, "Mostafa")
        tracker_3.record_utterance("ali", 120.0, 170.0, "Ali")
        tracker_3.record_utterance("tamer", 170.0, 180.0, "Tamer")
        obs_3 = tracker_3.get_silent_observer()
        self.assertIsNotNone(obs_3)
        self.assertEqual(obs_3[0], "tamer")
        self.assertAlmostEqual(obs_3[1], 10.0, places=1)
        self.assertAlmostEqual(obs_3[2], 5.6, places=1)  # 10 / 180 = 5.55% -> 5.6%

        # Case 5: 3 speakers where the two quietest are tied (Alice 100s, Bob 10s, Charlie 10.3s) -> None
        tracker_multi_tie = SessionStatsTracker("test_multi_tie")
        tracker_multi_tie.record_utterance("alice", 0.0, 100.0, "Alice")
        tracker_multi_tie.record_utterance("bob", 100.0, 110.0, "Bob")        # 10.0s
        tracker_multi_tie.record_utterance("charlie", 110.0, 120.3, "Charlie") # 10.3s -> diff 0.3s < 1.0s
        self.assertIsNone(tracker_multi_tie.get_silent_observer())

        # Case 6: 3 speakers where two quietest spoke 0s (Alice 100s, Bob 0s, Charlie 0s) -> None
        tracker_zero_tie = SessionStatsTracker("test_zero_tie")
        tracker_zero_tie.record_utterance("alice", 0.0, 100.0, "Alice")
        tracker_zero_tie.get_or_create_speaker("bob", "Bob")
        tracker_zero_tie.get_or_create_speaker("charlie", "Charlie")
        self.assertIsNone(tracker_zero_tie.get_silent_observer())


if __name__ == "__main__":
    unittest.main()


