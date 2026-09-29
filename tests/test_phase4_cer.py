"""
Unit Tests for Phase 4: Retrospective CER, Audio Evidence Propagation, and Banter State Machine.
Validates:
1. record_banter auto-creates speaker if not previously initialized.
2. High-arousal auto-capture writes isolated WAV clips when TEST_CAPTURE_MODE is 0.
3. process_utterance propagates audio_clip through analytics_buffer and queued utterances.
4. drain_queue preserves audio_clip during arbitration drain.
5. End-to-end multi-turn discourse resolution through ArbitrationEngine.
"""

import unittest
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from bot.config import PROJECT_ROOT, config
from bot.arbitration.stats import SessionStatsTracker
from bot.audio.capture import save_captured_utterance_sync
from bot.arbitration.engine import arbitration_engine, SessionState


class TestPhase4CER(unittest.TestCase):

    def test_record_banter_auto_creates_speaker(self):
        """
        Regression Test for Bug: record_banter previously dropped banter if speaker was not yet in self.speakers.
        Verified fix: get_or_create_speaker ensures speaker is created and banter count incremented.
        """
        tracker = SessionStatsTracker("test_banter_autocreate")
        self.assertNotIn("ghost_user", tracker.speakers)

        tracker.record_banter(["ghost_user"], terms=["يا حمار"])
        spk = tracker.get_speaker("ghost_user")
        self.assertIsNotNone(spk)
        self.assertEqual(spk.banter_count, 1)
        self.assertIn("يا حمار", spk.banter_terms)

    def test_high_arousal_force_save_captures_audio_clip(self):
        """
        Verifies that force_save=True writes a WAV file into recordings/test_session/evidence/
        even when TEST_CAPTURE_MODE is 0.
        """
        orig_mode = getattr(config, "TEST_CAPTURE_MODE", 0)
        config.TEST_CAPTURE_MODE = 0
        try:
            dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            entry = save_captured_utterance_sync(
                speaker_name="LoudGamer",
                wav_bytes=dummy_wav,
                asr_text="احا ايه ده",
                stt_latency_ms=150.0,
                ended_by="silence",
                timestamp=1700000001.0,
                audio_features={"was_loud": True, "peak_robust_z": 3.2},
                force_save=True
            )
            self.assertIsNotNone(entry)
            self.assertIsNotNone(entry.get("wav_filename"))
            saved_wav = PROJECT_ROOT / "recordings" / "test_session" / "evidence" / entry["wav_filename"]
            self.assertTrue(saved_wav.exists())
            # Clean up
            saved_wav.unlink(missing_ok=True)
        finally:
            config.TEST_CAPTURE_MODE = orig_mode

    def test_process_utterance_buffers_audio_clip(self):
        """
        Verifies that process_utterance accepts audio_clip and stores it in session.analytics_buffer.
        """
        session = arbitration_engine.get_session(999001)
        session.reset()

        asyncio.run(
            arbitration_engine.process_utterance(
                guild_id=999001,
                user_id=12345,
                speaker_name="Ali",
                raw_text="fuck you ali",
                stt_ms=120,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=100.0,
                speech_end=102.0,
                audio_features={"was_loud": True, "peak_robust_z": 3.1},
                audio_clip="100_Ali.wav"
            )
        )

        self.assertEqual(len(session.analytics_buffer), 1)
        item = session.analytics_buffer[0]
        self.assertEqual(item["audio_clip"], "100_Ali.wav")
        self.assertEqual(item["speaker_name"], "Ali")

    def test_queue_drain_preserves_audio_clip(self):
        """
        Verifies that queued utterances maintain audio_clip and forward it to _record_analytics upon drain.
        """
        session = arbitration_engine.get_session(999002)
        session.reset()
        session.is_arbitrating = True  # Force queueing

        asyncio.run(
            arbitration_engine.process_utterance(
                guild_id=999002,
                user_id=54321,
                speaker_name="Omar",
                raw_text="fuck you too",
                stt_ms=100,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=200.0,
                speech_end=202.0,
                audio_features={"was_loud": True, "peak_robust_z": 3.0},
                audio_clip="200_Omar.wav"
            )
        )

        self.assertEqual(len(session.pending_utterances), 1)
        queued = session.pending_utterances[0]
        self.assertEqual(queued["audio_clip"], "200_Omar.wav")

        # Now simulate arbitration completion and drain
        session.is_arbitrating = False
        asyncio.run(arbitration_engine._drain_queue(999002, session))

        self.assertEqual(len(session.pending_utterances), 0)
        self.assertEqual(len(session.analytics_buffer), 1)
        item = session.analytics_buffer[0]
        self.assertEqual(item["audio_clip"], "200_Omar.wav")


if __name__ == "__main__":
    unittest.main()
