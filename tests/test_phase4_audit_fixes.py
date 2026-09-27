import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bot.arbitration.engine import FifoSet, SessionState
from bot.arbitration.dispute_replay import load_session_events
from bot.audio.capture import generate_labels_draft_csv
from bot.audio.loudness import SpeakerLoudnessBaseline
from bot.ai.groq import GroqClient
from backend.app.config import settings
from bot.config import config, PROJECT_ROOT


class TestPhase4AuditFixes(unittest.TestCase):
    """
    Acceptance tests for Phase 4:
    a) .env.example TTS_TIMEOUT_SEC matches config.py default (10.0).
    b) engine.py FifoSet: capped at 500 entries, evicts oldest, logs warning/debug.
    c) dispute_replay.py: clamps clock jumps > 60s between consecutive rows to +1.0s.
    d) groq.py: logs JSON decode errors at WARNING with response excerpt.
    e) backend config: PROJECT_NAME is CallWrapped, DATABASE_URL aligns with .env.example.
    f) capture.py: atomic write of labels_DRAFT.csv via os.replace.
    g) loudness.py: lazy median/MAD recompute every 50 frames.
    """

    def test_a_env_example_tts_timeout_sec_matches_config(self):
        """Phase 4 (a): Verify .env.example specifies TTS_TIMEOUT_SEC=10.0 matching config default."""
        env_example_path = PROJECT_ROOT / ".env.example"
        self.assertTrue(env_example_path.exists(), ".env.example must exist")
        
        found = False
        with open(env_example_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TTS_TIMEOUT_SEC="):
                    val = float(line.split("=", 1)[1].strip().strip('"').strip("'"))
                    self.assertEqual(val, 10.0, "TTS_TIMEOUT_SEC in .env.example must be 10.0")
                    found = True
                    break
        self.assertTrue(found, "TTS_TIMEOUT_SEC setting not found in .env.example")
        self.assertEqual(getattr(config, "TTS_TIMEOUT_SEC", 10.0), 10.0)

    def test_b_fifoset_capacity_eviction_and_logging(self):
        """Phase 4 (b): Verify FifoSet caps at maxlen, evicts oldest entry, and logs the eviction."""
        fifo = FifoSet(maxlen=500)
        self.assertEqual(len(fifo), 0)

        # Fill with 500 items
        for i in range(500):
            fifo.add(f"utterance_{i}")
        self.assertEqual(len(fifo), 500)
        self.assertIn("utterance_0", fifo)
        self.assertIn("utterance_499", fifo)

        # Add 501st item with logger capture
        with self.assertLogs("ArbitrationEngine", level="DEBUG") as log_capture:
            fifo.add("utterance_500")

        self.assertEqual(len(fifo), 500)
        self.assertNotIn("utterance_0", fifo, "Oldest item utterance_0 must be evicted")
        self.assertIn("utterance_1", fifo)
        self.assertIn("utterance_500", fifo)
        self.assertTrue(
            any("FifoSet capacity reached" in m and "utterance_0" in m for m in log_capture.output),
            f"Expected eviction log for utterance_0, got: {log_capture.output}"
        )

        # SessionState initialization check
        state = SessionState(guild_id=123)
        self.assertIsInstance(state.analyzed_utterances, FifoSet)
        self.assertEqual(state.analyzed_utterances.maxlen, 500)

    def test_c_dispute_replay_clock_jump_clamping(self):
        """Phase 4 (c): Verify dispute_replay clamps clock jumps > 60s between consecutive rows to +1.0s."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create mock session_log.jsonl with timestamps jumping > 60s
            log_file = tmppath / "session_log.jsonl"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({"wav_filename": "clip_001.wav", "timestamp": 10.0}) + "\n")
                # Jump by 100 seconds to 110.0s
                f.write(json.dumps({"wav_filename": "clip_002.wav", "timestamp": 110.0}) + "\n")
                # Next clip normal jump by 2 seconds to 112.0s
                f.write(json.dumps({"wav_filename": "clip_003.wav", "timestamp": 112.0}) + "\n")

            # Create mock labels_DRAFT.csv
            labels_file = tmppath / "labels_DRAFT.csv"
            with open(labels_file, "w", encoding="utf-8-sig") as f:
                f.write("clip_id,wav_filename,speaker,asr_text,correct_text,topic,is_claim,anger,loud\n")
                f.write("clip_001,clip_001.wav,Alice,text1,text1,football,no,none,no\n")
                f.write("clip_002,clip_002.wav,Bob,text2,text2,football,no,none,no\n")
                f.write("clip_003,clip_003.wav,Alice,text3,text3,football,no,none,no\n")

            with self.assertLogs("DisputeReplay", level="WARNING") as log_capture:
                events = load_session_events(tmppath)

            self.assertEqual(len(events), 3)
            # clip_001 at 10.0s
            self.assertEqual(events[0].timestamp, 10.0)
            # clip_002 clamped from 110.0s to 10.0 + 1.0 = 11.0s
            self.assertEqual(events[1].timestamp, 11.0)
            # clip_003 was at 112.0s, which is a jump from clamped 11.0s (> 60s), so clamped to 11.0 + 1.0 = 12.0s
            self.assertEqual(events[2].timestamp, 12.0)

            self.assertTrue(
                any("Clamping large replay clock jump" in m for m in log_capture.output),
                f"Expected clock jump warning log, got: {log_capture.output}"
            )

    def test_d_groq_json_decode_error_logging(self):
        """Phase 4 (d): Verify JSON decode failure in complete_chat logs WARNING with excerpt."""
        client = GroqClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This is NOT json {invalid"}}]
        }

        # Mock httpx.AsyncClient.post
        import httpx
        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            with self.assertLogs("GroqClient", level="WARNING") as log_capture:
                import asyncio
                parsed, tokens, latency = asyncio.run(
                    client.complete_chat(messages=[{"role": "user", "content": "hi"}])
                )

        self.assertIsNone(parsed)
        self.assertTrue(
            any("Failed to parse JSON" in m and "This is NOT json" in m for m in log_capture.output),
            f"Expected warning log with content excerpt, got: {log_capture.output}"
        )

    def test_e_backend_config_alignment(self):
        """Phase 4 (f): Verify backend title is CallWrapped and DATABASE_URL matches .env.example."""
        from backend.app.config import Settings
        fresh_settings = Settings()
        self.assertEqual(fresh_settings.PROJECT_NAME, "CallWrapped")
        self.assertEqual(fresh_settings.DATABASE_URL, "sqlite+aiosqlite:///./data/app.db")

    def test_f_capture_atomic_write(self):
        """Phase 4 (f3-08): Verify labels_DRAFT.csv is written atomically without leaving .tmp file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            log_file = tmppath / "session_log.jsonl"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "clip_id": "clip_001",
                    "wav_filename": "utterance_001.wav",
                    "speaker": "Ahmed",
                    "text": "تجربة تسجيل صوتي",
                    "correct_text": "تجربة تسجيل صوتي",
                    "topic": "tech",
                    "is_claim": "no",
                    "anger": "none",
                    "loud": "no"
                }) + "\n")

            csv_path = generate_labels_draft_csv(tmppath)
            self.assertTrue(csv_path.exists())
            self.assertFalse(csv_path.with_suffix(".csv.tmp").exists())

            # Verify contents
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)  # header + 1 row
            self.assertIn("clip_001", lines[1])

    def test_g_speaker_loudness_lazy_recompute(self):
        """Phase 4 (f3-06): Verify baseline median/MAD are recomputed lazily every 50 frames."""
        baseline = SpeakerLoudnessBaseline(min_calibration_frames=30)
        # Add 30 frames to reach calibrated state
        for i in range(30):
            baseline.observe_eligible_frame(log_rms_db=-40.0 + (i % 5))

        self.assertTrue(baseline.calibrated)
        self.assertEqual(baseline._frames_since_recompute, 30)

        # Calling score triggers recomputation if dirty
        z1 = baseline.score(-38.0)
        self.assertIsNotNone(z1)
        self.assertEqual(baseline._frames_since_recompute, 0)
        cached_med = baseline._cached_median
        self.assertIsNotNone(cached_med)

        # Observe 10 more frames (less than recompute_interval=50)
        for i in range(10):
            baseline.observe_eligible_frame(log_rms_db=-39.0)

        self.assertEqual(baseline._frames_since_recompute, 10)
        # score() should reuse cached median and NOT recompute
        baseline.score(-38.0)
        self.assertEqual(baseline._cached_median, cached_med)
        self.assertEqual(baseline._frames_since_recompute, 10)

        # Observe 40 more frames to reach 50
        for i in range(40):
            baseline.observe_eligible_frame(log_rms_db=-39.0)

        self.assertGreaterEqual(baseline._frames_since_recompute, 50)
        # Now score() will recompute stats and reset counter
        baseline.score(-38.0)
        self.assertEqual(baseline._frames_since_recompute, 0)


if __name__ == "__main__":
    unittest.main()
