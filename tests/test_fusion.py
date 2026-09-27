import unittest
from bot.audio.fusion import fuse_anger, FusedAngerResult, has_frustration_cues
from bot.audio.loudness import UtteranceAudioFeatures


class TestFusion(unittest.TestCase):

    def test_a_text_none_was_loud_active_dispute_fused_mild(self):
        """
        Acceptance (a): text none + was_loud + active dispute -> fused mild (boost works).
        p_text = 0.0, peak_z = 5.0 -> boost = 0.60
        p_fused = 1.0 - (1.0 - 0.0)*(1.0 - 0.60) = 0.60 >= 0.45 -> 'mild'
        """
        features = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=68.0,
            peak_robust_z=5.0,
            sustained_spike_count=5,
            clip_ratio=0.01,
            calibrated=True,
            was_loud=True
        )

        result = fuse_anger(
            raw_anger="none",
            audio_features=features,
            has_active_dispute=True,
            text="لا هي أستراليا"
        )

        self.assertEqual(result.raw_anger, "none")
        self.assertEqual(result.p_text, 0.0)
        self.assertAlmostEqual(result.acoustic_boost, 0.60, places=2)
        self.assertAlmostEqual(result.p_fused, 0.60, places=2)
        self.assertEqual(result.final_anger, "mild")
        self.assertEqual(result.gate_reason, "boost_applied")

    def test_b_text_none_was_loud_no_dispute_excitement_guard_stays_none(self):
        """
        Acceptance (b): text none + was_loud + no dispute -> stays none (excitement guard).
        Without frustration text or an active dispute, acoustic arousal is treated as excitement.
        """
        features = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=70.0,
            peak_robust_z=5.5,
            sustained_spike_count=6,
            clip_ratio=0.00,
            calibrated=True,
            was_loud=True
        )

        result = fuse_anger(
            raw_anger="none",
            audio_features=features,
            has_active_dispute=False,
            text="عاش يا رجالة جون عالمي ههههه"
        )

        self.assertEqual(result.raw_anger, "none")
        self.assertEqual(result.p_text, 0.0)
        self.assertEqual(result.acoustic_boost, 0.0)
        self.assertEqual(result.p_fused, 0.0)
        self.assertEqual(result.final_anger, "none")
        self.assertEqual(result.gate_reason, "excitement_guard")

    def test_c_text_high_not_loud_stays_high(self):
        """
        Acceptance (c): text high + not loud -> stays high.
        p_text = 0.9, boost = 0.0 -> p_fused = 0.9 >= 0.8 -> 'high'.
        """
        features = UtteranceAudioFeatures(
            frame_count=15,
            voiced_frames=14,
            p95_log_rms_db=52.0,
            peak_robust_z=0.8,
            sustained_spike_count=0,
            clip_ratio=0.00,
            calibrated=True,
            was_loud=False
        )

        result = fuse_anger(
            raw_anger="high",
            audio_features=features,
            has_active_dispute=False,
            text="انت غبي أوي وحمار"
        )

        self.assertEqual(result.raw_anger, "high")
        self.assertEqual(result.p_text, 0.9)
        self.assertEqual(result.acoustic_boost, 0.0)
        self.assertEqual(result.p_fused, 0.9)
        self.assertEqual(result.final_anger, "high")
        self.assertEqual(result.gate_reason, "not_loud")

    def test_d_uncalibrated_speaker_no_fusion(self):
        """
        Acceptance (d): uncalibrated speaker -> no fusion (p_effective = p_text).
        """
        features = UtteranceAudioFeatures(
            frame_count=10,
            voiced_frames=9,
            p95_log_rms_db=75.0,
            peak_robust_z=4.8,
            sustained_spike_count=5,
            clip_ratio=0.00,
            calibrated=False,
            was_loud=False
        )

        result = fuse_anger(
            raw_anger="none",
            audio_features=features,
            has_active_dispute=True,
            text="كلام فارغ"
        )

        self.assertEqual(result.p_text, 0.0)
        self.assertEqual(result.acoustic_boost, 0.0)
        self.assertEqual(result.p_fused, 0.0)
        self.assertEqual(result.final_anger, "none")
        self.assertEqual(result.gate_reason, "uncalibrated")

    def test_clipping_guard_suppresses_boost(self):
        """clip_ratio >= 0.05 suppresses boost regardless of peak_z."""
        features = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=72.0,
            peak_robust_z=6.0,
            sustained_spike_count=8,
            clip_ratio=0.06,  # Exceeds 0.05 limit
            calibrated=True,
            was_loud=True
        )

        result = fuse_anger(
            raw_anger="none",
            audio_features=features,
            has_active_dispute=True,
            text="غلط خالص"
        )

        self.assertEqual(result.acoustic_boost, 0.0)
        self.assertEqual(result.final_anger, "none")
        self.assertEqual(result.gate_reason, "clipping_exceeded")

    def test_text_mild_escalates_to_high_with_shout(self):
        """
        p_text = 0.5 (mild) + peak_z = 5.0 (boost = 0.6)
        p_fused = 1.0 - (1.0 - 0.5)*(1.0 - 0.6) = 1.0 - 0.20 = 0.80 >= 0.8 -> 'high'.
        """
        features = UtteranceAudioFeatures(
            frame_count=20,
            voiced_frames=18,
            p95_log_rms_db=70.0,
            peak_robust_z=5.0,
            sustained_spike_count=5,
            clip_ratio=0.01,
            calibrated=True,
            was_loud=True
        )

        result = fuse_anger(
            raw_anger="mild",
            audio_features=features,
            has_active_dispute=False,
            text="زهقت من الكلام ده"
        )

        self.assertEqual(result.raw_anger, "mild")
        self.assertEqual(result.p_text, 0.5)
        self.assertAlmostEqual(result.acoustic_boost, 0.60, places=2)
        self.assertAlmostEqual(result.p_fused, 0.80, places=2)
        self.assertEqual(result.final_anger, "high")
        self.assertEqual(result.gate_reason, "boost_applied")

    def test_dict_and_none_audio_features_tolerance(self):
        """Defensive handling when audio_features is a dict or None."""
        res_none = fuse_anger("none", None)
        self.assertEqual(res_none.final_anger, "none")
        self.assertEqual(res_none.gate_reason, "uncalibrated")

        feat_dict = {
            "calibrated": True,
            "was_loud": True,
            "peak_robust_z": 5.0,
            "clip_ratio": 0.01
        }
        res_dict = fuse_anger("none", feat_dict, has_active_dispute=True)
        self.assertEqual(res_dict.final_anger, "mild")
        self.assertEqual(res_dict.gate_reason, "boost_applied")


if __name__ == "__main__":
    unittest.main()
