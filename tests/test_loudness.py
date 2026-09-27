import array
import json
import os
from pathlib import Path
import tempfile
import unittest

from bot.audio.loudness import (
    CalibrationState,
    PCM16Adapter,
    SpeakerLoudnessBaseline,
    UtteranceAudioFeatures,
    UtteranceLoudnessAccumulator,
    log_loudness_shadow,
    rms_to_db,
)


class TestLoudness(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.shadow_path = Path(self.tmp_dir.name) / "test_loudness_shadow.jsonl"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_calibration_progression(self):
        """29 frames -> not ready (LEARNING); 30 frames -> ready (READY)."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        self.assertEqual(baseline.state, CalibrationState.COLD)
        self.assertFalse(baseline.baseline_ready)
        self.assertFalse(baseline.calibrated)

        # Feed 29 frames
        for i in range(29):
            appended = baseline.observe_eligible_frame(50.0 + (i % 3), clipped=False)
            self.assertTrue(appended)

        self.assertEqual(len(baseline.history), 29)
        self.assertEqual(baseline.state, CalibrationState.LEARNING)
        self.assertFalse(baseline.baseline_ready)
        self.assertFalse(baseline.calibrated)
        self.assertIsNone(baseline.score(50.0))

        # 30th frame crosses calibration threshold
        appended = baseline.observe_eligible_frame(50.0, clipped=False)
        self.assertTrue(appended)
        self.assertEqual(len(baseline.history), 30)
        self.assertEqual(baseline.state, CalibrationState.READY)
        self.assertTrue(baseline.baseline_ready)
        self.assertTrue(baseline.calibrated)
        self.assertIsNotNone(baseline.score(50.0))

    def test_flat_baseline_z_score(self):
        """Flat baseline -> z ≈ 0 for median values."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for _ in range(35):
            baseline.observe_eligible_frame(50.0, clipped=False)

        self.assertTrue(baseline.baseline_ready)
        self.assertEqual(baseline.median, 50.0)
        self.assertEqual(baseline.mad, 0.0)

        # Scoring median on flat baseline yields exactly 0.0
        z = baseline.score(50.0)
        self.assertIsNotNone(z)
        self.assertAlmostEqual(z, 0.0, places=4)

    def test_synthetic_spike_under_four_frames_was_loud_false(self):
        """Synthetic spike >= 2.5 for < 4 frames -> was_loud False."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        # Establish baseline: values between 48.0 and 52.0 dB (median 50.0, MAD ~ 1.0)
        for i in range(35):
            baseline.observe_eligible_frame(50.0 + ((i % 5) - 2) * 0.8, clipped=False)

        acc = UtteranceLoudnessAccumulator()
        acc.begin("utt_1", "speaker_1")

        # 3 spike frames (65.0 dB -> z >> 2.5) + 7 normal frames (50.0 dB)
        for _ in range(3):
            acc.observe_frame(rms=-1.0, log_rms_db=65.0)  # spike
        for _ in range(7):
            acc.observe_frame(rms=-1.0, log_rms_db=50.0)  # normal

        features = acc.finalize(baseline)
        self.assertEqual(features.frame_count, 10)
        self.assertTrue(features.calibrated)
        self.assertGreaterEqual(features.peak_robust_z, 2.5)
        self.assertEqual(features.sustained_spike_count, 3)
        self.assertFalse(features.was_loud, "Expected was_loud=False when spike count < 4")

    def test_four_of_ten_elevated_frames_was_loud_true(self):
        """4/10 elevated frames -> was_loud True."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for i in range(35):
            baseline.observe_eligible_frame(50.0 + ((i % 5) - 2) * 0.8, clipped=False)

        acc = UtteranceLoudnessAccumulator()
        acc.begin("utt_2", "speaker_1")

        # 4 spike frames (65.0 dB -> z >> 2.5) + 6 normal frames (50.0 dB)
        for _ in range(4):
            acc.observe_frame(rms=-1.0, log_rms_db=65.0)  # spike
        for _ in range(6):
            acc.observe_frame(rms=-1.0, log_rms_db=50.0)  # normal

        features = acc.finalize(baseline)
        self.assertEqual(features.frame_count, 10)
        self.assertTrue(features.calibrated)
        self.assertGreaterEqual(features.peak_robust_z, 2.5)
        self.assertEqual(features.sustained_spike_count, 4)
        self.assertLess(features.clip_ratio, 0.05)
        self.assertTrue(features.was_loud, "Expected was_loud=True with 4 spike frames and calibrated baseline")

    def test_loud_frames_excluded_from_baseline(self):
        """Loud frames excluded from baseline (baseline unchanged after shout)."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for i in range(35):
            baseline.observe_eligible_frame(50.0 + ((i % 5) - 2) * 0.8, clipped=False)

        initial_len = len(baseline.history)
        initial_median = baseline.median
        initial_mad = baseline.mad

        # Attempt to insert a loud frame (80 dB, z >> 2.5)
        appended = baseline.observe_eligible_frame(80.0, clipped=False)
        self.assertFalse(appended, "Update gate must reject loud frame")

        self.assertEqual(len(baseline.history), initial_len)
        self.assertEqual(baseline.median, initial_median)
        self.assertEqual(baseline.mad, initial_mad)

    def test_clipping_detection_and_rejection(self):
        """Clipping: clipped spike -> was_loud False, clip_ratio reported."""
        # 1. Direct PCM16Adapter check
        # Create 100 samples with 10 clipped samples (10% clipped >= 0.01 frame threshold)
        samples = [1000] * 90 + [32735] * 10
        self.assertTrue(PCM16Adapter.is_frame_clipped(samples))
        self.assertAlmostEqual(PCM16Adapter.compute_clip_ratio(samples), 0.10)

        # 2. Utterance clipping guard
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for i in range(35):
            baseline.observe_eligible_frame(50.0 + ((i % 5) - 2) * 0.8, clipped=False)

        acc = UtteranceLoudnessAccumulator()
        acc.begin("utt_clipped", "speaker_1")

        # 5 spike frames, but with 6% clipping (above 0.05 utterance threshold)
        for _ in range(5):
            acc.observe_frame(rms=-1.0, samples=0.06, log_rms_db=68.0)
        for _ in range(5):
            acc.observe_frame(rms=-1.0, samples=0.06, log_rms_db=50.0)

        features = acc.finalize(baseline)
        self.assertEqual(features.frame_count, 10)
        self.assertEqual(features.sustained_spike_count, 5)
        self.assertGreaterEqual(features.peak_robust_z, 2.5)
        self.assertGreaterEqual(features.clip_ratio, 0.05)
        self.assertFalse(features.was_loud, "Expected was_loud=False when clip_ratio >= 0.05")

    def test_cold_start_spike_before_calibration(self):
        """Cold start: spike before calibration -> was_loud False, baseline_ready False."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for i in range(10):  # Only 10 frames, not ready
            baseline.observe_eligible_frame(50.0 + (i % 3), clipped=False)

        self.assertFalse(baseline.baseline_ready)

        acc = UtteranceLoudnessAccumulator()
        acc.begin("utt_cold", "speaker_1")
        for _ in range(5):
            acc.observe_frame(rms=-1.0, log_rms_db=75.0)

        features = acc.finalize(baseline)
        self.assertFalse(features.calibrated)
        self.assertFalse(features.baseline_ready)
        self.assertFalse(features.was_loud)

    def test_per_speaker_independence(self):
        """Two baselines don't cross-contaminate."""
        baseline_a = SpeakerLoudnessBaseline(min_calibration_frames=30)
        baseline_b = SpeakerLoudnessBaseline(min_calibration_frames=30)

        for _ in range(35):
            baseline_a.observe_eligible_frame(45.0, clipped=False)
            baseline_b.observe_eligible_frame(70.0, clipped=False)

        self.assertEqual(baseline_a.median, 45.0)
        self.assertEqual(baseline_b.median, 70.0)

        # Speaker A frame scored against both baselines
        z_in_a = baseline_a.score(45.0)
        z_in_b = baseline_b.score(45.0)
        self.assertAlmostEqual(z_in_a, 0.0)
        self.assertLess(z_in_b, 0.0)

    def test_force_split_finalize_resets_accumulator_keeps_baseline(self):
        """Force-split finalize resets accumulator, keeps baseline."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        for _ in range(35):
            baseline.observe_eligible_frame(50.0, clipped=False)

        acc = UtteranceLoudnessAccumulator()
        acc.begin("utt_part1", "speaker_1")
        for _ in range(15):
            acc.observe_frame(rms=-1.0, log_rms_db=52.0)

        features_1 = acc.finalize(baseline)
        self.assertEqual(features_1.frame_count, 15)

        # Accumulator should be empty/inactive
        self.assertEqual(len(acc.frames_log_rms_db), 0)
        self.assertFalse(acc.is_active)

        # Baseline must still be intact
        self.assertEqual(len(baseline.history), 35)
        self.assertTrue(baseline.baseline_ready)

        # Second part of speech after force-split
        acc.begin("utt_part2", "speaker_1")
        for _ in range(8):
            acc.observe_frame(rms=-1.0, log_rms_db=53.0)

        features_2 = acc.finalize(baseline)
        self.assertEqual(features_2.frame_count, 8)
        self.assertEqual(len(baseline.history), 35)

    def test_empty_session_stop_no_crash(self):
        """Empty session stop -> valid empty features, no crash."""
        acc = UtteranceLoudnessAccumulator()
        features = acc.finalize(baseline=None)
        self.assertEqual(features.frame_count, 0)
        self.assertEqual(features.voiced_frames, 0)
        self.assertEqual(features.peak_robust_z, 0.0)
        self.assertEqual(features.sustained_spike_count, 0)
        self.assertEqual(features.clip_ratio, 0.0)
        self.assertFalse(features.calibrated)
        self.assertFalse(features.was_loud)

    def test_shadow_logger_records_was_loud(self):
        """Shadow logger records was_loud events to JSONL."""
        features_loud = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=68.5,
            peak_robust_z=3.42,
            sustained_spike_count=6,
            clip_ratio=0.001,
            calibrated=True,
            was_loud=True
        )

        rec = log_loudness_shadow("2xDanger", features_loud, shadow_path=self.shadow_path, timestamp=1727464000.0)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["speaker"], "2xDanger")
        self.assertEqual(rec["z_peak"], 3.42)
        self.assertEqual(rec["sustain_ms"], 120.0)
        self.assertTrue(self.shadow_path.exists())

        # Features with was_loud=False should not be logged
        features_quiet = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=52.0,
            peak_robust_z=0.8,
            sustained_spike_count=0,
            clip_ratio=0.0,
            calibrated=True,
            was_loud=False
        )
        rec_none = log_loudness_shadow("Mostafa", features_quiet, shadow_path=self.shadow_path)
        self.assertIsNone(rec_none)

        # Verify only 1 line written
        lines = self.shadow_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data["speaker"], "2xDanger")
        self.assertEqual(data["z_peak"], 3.42)


if __name__ == "__main__":
    unittest.main()
