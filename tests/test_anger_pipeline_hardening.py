import unittest
from bot.audio.loudness import SpeakerLoudnessBaseline, UtteranceLoudnessAccumulator
from bot.audio.fusion import fuse_anger, has_frustration_cues
from bot.arbitration.stats import SessionStatsTracker


class TestAngerPipelineHardening(unittest.TestCase):
    """
    Regression and hardening test suite targeting the 5 root causes found in the deep audit:
    1. Digital silence cannot calibrate or corrupt baseline.
    2. Zero-MAD flat baseline uses 2.5 dB spread floor (no division by near-zero).
    3. Z-scores are bounded in [-20.0, 10.0].
    4. Stuck baseline self-healing resets after 100 consecutive loud rejections.
    5. Excitement guard dampens loud non-frustrated speech ("I love League of Legends") to 'none'.
    6. Anger episodes strictly require verbal quotes (null/empty/placeholder rejected).
    """

    def test_silence_frames_cannot_calibrate_baseline(self):
        """Digital silence frames (RMS=0, dB=-180) must be rejected by voiced-energy gate."""
        b = SpeakerLoudnessBaseline(min_calibration_frames=30)
        # Feed 60 packets of digital silence
        for _ in range(60):
            accepted = b.observe_eligible_frame(-180.0)
            self.assertFalse(accepted, "Digital silence frames must not be accepted into baseline")

        self.assertFalse(b.baseline_ready)
        self.assertEqual(len(b.history), 0)
        self.assertIsNone(b.score(70.0))

    def test_zero_mad_spread_floor_prevents_astronomical_z(self):
        """When MAD=0 (identical speech frames), spread floor of 2.5 dB prevents infinite z-scores."""
        b = SpeakerLoudnessBaseline(min_calibration_frames=30)
        # Feed 35 speech frames at exactly 50.0 dB
        for _ in range(35):
            b.observe_eligible_frame(50.0)

        self.assertTrue(b.baseline_ready)
        self.assertEqual(b.median, 50.0)
        self.assertEqual(b.mad, 0.0)

        # Exact match yields 0.0
        self.assertEqual(b.score(50.0), 0.0)

        # 5 dB louder (55.0 dB) with floor of 2.5 dB -> z = 5.0 / 2.5 = 2.0 (NOT 50,000!)
        z = b.score(55.0)
        self.assertAlmostEqual(z, 2.0, places=2)

    def test_z_score_clamped_to_ten(self):
        """Even extreme loudness differences are clamped to maximum 10.0 sigma."""
        b = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for _ in range(35):
            b.observe_eligible_frame(50.0)

        # 100 dB difference: 150.0 - 50.0 = 100.0 / 2.5 = 40.0 -> clamped to 10.0
        z = b.score(150.0)
        self.assertEqual(z, 10.0)

    def test_self_healing_resets_stuck_baseline(self):
        """If 100 consecutive frames are rejected as loud, baseline resets to uncalibrated."""
        b = SpeakerLoudnessBaseline(min_calibration_frames=30)
        # Calibrate at 45.0 dB
        for _ in range(35):
            b.observe_eligible_frame(45.0)
        self.assertTrue(b.baseline_ready)

        # Send 99 loud frames (80.0 dB)
        for _ in range(99):
            b.observe_eligible_frame(80.0)
        self.assertTrue(b.baseline_ready, "Should not reset before 100 consecutive loud frames")

        # 100th consecutive loud frame triggers self-healing reset
        b.observe_eligible_frame(80.0)
        self.assertFalse(b.baseline_ready, "Baseline must self-heal and reset after 100 stuck loud frames")
        self.assertEqual(len(b.history), 0)

    def test_excitement_guard_dampens_loud_positive_speech(self):
        """
        User case: Shouting 'I love League of Legends!' with was_loud=True,
        no dispute, no frustration keywords -> excitement guard dampens to 'none'.
        """
        # Scenario A: LLM says 'none'
        res_none = fuse_anger(
            raw_anger="none",
            audio_features={"calibrated": True, "was_loud": True, "peak_robust_z": 3.5, "clip_ratio": 0.0},
            has_active_dispute=False,
            in_active_argument=False,
            text="I love League of Legends!"
        )
        self.assertEqual(res_none.final_anger, "none")
        self.assertEqual(res_none.gate_reason, "excitement_guard")

        # Scenario B: LLM hallucinated 'mild' due to acoustic arousal, but text is non-frustrated
        res_mild = fuse_anger(
            raw_anger="mild",
            audio_features={"calibrated": True, "was_loud": True, "peak_robust_z": 3.5, "clip_ratio": 0.0},
            has_active_dispute=False,
            in_active_argument=False,
            text="I love League of Legends!"
        )
        # Excitement guard damps p_text (0.5 * 0.4 = 0.20 < 0.45) -> none
        self.assertEqual(res_mild.final_anger, "none")
        self.assertEqual(res_mild.gate_reason, "excitement_guard")

    def test_dispute_context_elevates_loud_frustration(self):
        """In an active dispute, shouting frustration text elevates to mild/high anger."""
        res = fuse_anger(
            raw_anger="mild",
            audio_features={"calibrated": True, "was_loud": True, "peak_robust_z": 4.0, "clip_ratio": 0.0},
            has_active_dispute=True,
            in_active_argument=True,
            text="i fucking hate this"
        )
        self.assertEqual(res.gate_reason, "boost_applied")
        self.assertIn(res.final_anger, ("mild", "high"))

    def test_record_anger_requires_valid_verbal_evidence(self):
        """Strict dual-evidence requirement: empty, whitespace, or placeholder quote is rejected."""
        tracker = SessionStatsTracker(session_id="evidence_guard_test")

        # 1. Null quote -> rejected
        r1 = tracker.record_anger("u1", timestamp=10.0, anger="mild", anger_quote=None)
        self.assertEqual(r1.angry_episodes, 0)
        self.assertIsNone(r1.first_anger_quote)

        # 2. Empty string -> rejected
        r2 = tracker.record_anger("u1", timestamp=20.0, anger="mild", anger_quote="   ")
        self.assertEqual(r2.angry_episodes, 0)

        # 3. Placeholder string -> rejected
        r3 = tracker.record_anger("u1", timestamp=30.0, anger="mild", anger_quote="(no verbal evidence captured)")
        self.assertEqual(r3.angry_episodes, 0)

        # 4. Valid quote -> accepted and incremented
        r4 = tracker.record_anger("u1", timestamp=40.0, anger="mild", anger_quote="زهقت من كدة بجد")
        self.assertEqual(r4.angry_episodes, 1)
        self.assertEqual(r4.first_anger_quote, "زهقت من كدة بجد")


if __name__ == "__main__":
    unittest.main()
