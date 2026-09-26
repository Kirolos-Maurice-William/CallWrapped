import tests._setup
import os
import csv
import json
import time
import shutil
import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from bot.config import config, PROJECT_ROOT
from bot.audio.capture import (
    save_captured_utterance_sync,
    save_captured_utterance_async,
    generate_labels_draft_csv,
    start_capture_session,
    stop_capture_session,
    get_active_session_dir,
    DEFAULT_RECORDINGS_DIR
)
from bot.main import stop_capture_command, start_capture_command, leave_channel


class TestCaptureMode(unittest.IsolatedAsyncioTestCase):
    """
    Phase 3 Acceptance:
    - New config flag TEST_CAPTURE_MODE=0 (default off).
    - When enabled, every finalized utterance saves audio (16kHz mono WAV) and JSONL line.
    - Non-blocking (delegated via asyncio.to_thread).
    - !stop-capture generates labels_DRAFT.csv pre-filling clip_id, wav_filename, speaker, asr_text
      with empty human annotation columns.
    - When disabled, zero files written.
    """

    def setUp(self):
        self.test_dir = PROJECT_ROOT / "recordings" / "test_session_unit_test"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)
        self.orig_mode = config.TEST_CAPTURE_MODE
        config.TEST_CAPTURE_MODE = 0

    def tearDown(self):
        config.TEST_CAPTURE_MODE = self.orig_mode
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_a_capture_disabled_writes_zero_files(self):
        """When TEST_CAPTURE_MODE is 0 (default off), zero files are written."""
        config.TEST_CAPTURE_MODE = 0

        dummy_wav = b"RIFF____WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

        res_sync = save_captured_utterance_sync(
            speaker_name="Omar",
            wav_bytes=dummy_wav,
            asr_text="كلام تجريبي",
            stt_latency_ms=150.0,
            ended_by="silence",
            recordings_dir=self.test_dir
        )
        self.assertIsNone(res_sync, "Must return None when TEST_CAPTURE_MODE=0")

        res_async = await save_captured_utterance_async(
            speaker_name="Ziad",
            wav_bytes=dummy_wav,
            asr_text="كلام تجريبي آخر",
            stt_latency_ms=180.0,
            ended_by="forcesplit",
            recordings_dir=self.test_dir
        )
        self.assertIsNone(res_async, "Must return None when TEST_CAPTURE_MODE=0")

        self.assertFalse(self.test_dir.exists(), "No directory or files should be created when capture is disabled")
        print("\n=== [Phase 3 - A] Capture Disabled: 0 files written (PASS) ===")

    async def test_b_capture_three_synthetic_utterances_and_stop_capture_csv(self):
        """
        Enable capture, process 3 synthetic utterances:
        -> 3 WAVs exist + 3 JSONL lines with correct fields
        -> stop-capture generates labels_DRAFT.csv with pre-filled asr_text & empty human columns
        -> capture disabled -> zero subsequent files written
        """
        config.TEST_CAPTURE_MODE = 1

        # 3 synthetic utterances
        dummy_wav_1 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x01\x02" * 100
        dummy_wav_2 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x03\x04" * 100
        dummy_wav_3 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x05\x06" * 100

        utterances = [
            ("Omar", dummy_wav_1, "الـ 5070 فيها 16 جيجا", 210.5, "silence", 1700000001.0),
            ("Ziad", dummy_wav_2, "لا هي 12 بس", 195.0, "silence", 1700000002.0),
            ("Mostafa", dummy_wav_3, "الكلام ده مش مظبوط خالص يا شباب", 340.2, "forcesplit", 1700000003.0)
        ]

        saved_entries = []
        for spk, wav, txt, lat, end_reason, ts in utterances:
            entry = await save_captured_utterance_async(
                speaker_name=spk,
                wav_bytes=wav,
                asr_text=txt,
                stt_latency_ms=lat,
                ended_by=end_reason,
                timestamp=ts,
                recordings_dir=self.test_dir
            )
            self.assertIsNotNone(entry)
            saved_entries.append(entry)

        # 1. Assert 3 WAVs exist
        wav_files = sorted(list(self.test_dir.glob("*.wav")))
        print(f"\n=== [Phase 3 - B1] WAV files generated ({len(wav_files)}): ===")
        for w in wav_files:
            print(f"  - {w.name} ({w.stat().st_size} bytes)")
        self.assertEqual(len(wav_files), 3, "Exactly 3 WAV files must exist")

        # 2. Assert session_log.jsonl has 3 lines with correct fields
        log_file = self.test_dir / "session_log.jsonl"
        self.assertTrue(log_file.exists(), "session_log.jsonl must exist")

        with open(log_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line.strip()) for line in f if line.strip()]

        print(f"\n=== [Phase 3 - B2] session_log.jsonl lines ({len(lines)}): ===")
        for line in lines:
            print(" ", json.dumps(line, ensure_ascii=False))

        self.assertEqual(len(lines), 3, "Must have exactly 3 JSONL entries")
        expected_fields = {"timestamp", "speaker_name", "wav_filename", "asr_text", "stt_latency_ms", "ended_by"}
        for idx, line in enumerate(lines):
            self.assertEqual(set(line.keys()), expected_fields)
            self.assertEqual(line["speaker_name"], utterances[idx][0])
            self.assertEqual(line["asr_text"], utterances[idx][2])
            self.assertEqual(line["stt_latency_ms"], utterances[idx][3])
            self.assertEqual(line["ended_by"], utterances[idx][4])
            self.assertTrue((self.test_dir / line["wav_filename"]).exists())

        # 3. Stop capture & generate labels_DRAFT.csv
        csv_path = generate_labels_draft_csv(recordings_dir=self.test_dir)
        config.TEST_CAPTURE_MODE = 0  # Stop capture
        self.assertTrue(csv_path.exists(), "labels_DRAFT.csv must be created")

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)

        print(f"\n=== [Phase 3 - B3] labels_DRAFT.csv rows ({len(csv_rows)}): ===")
        for r in csv_rows:
            print(" ", r)

        expected_columns = [
            "clip_id", "wav_filename", "speaker", "asr_text",
            "correct_text", "topic", "is_claim", "anger", "loud"
        ]
        self.assertEqual(reader.fieldnames, expected_columns)
        self.assertEqual(len(csv_rows), 3)

        for idx, row in enumerate(csv_rows):
            self.assertEqual(row["clip_id"], f"clip_{idx+1:03d}")
            self.assertEqual(row["wav_filename"], lines[idx]["wav_filename"])
            self.assertEqual(row["speaker"], utterances[idx][0])
            self.assertEqual(row["asr_text"], utterances[idx][2])
            # Human annotation columns must be EMPTY
            self.assertEqual(row["correct_text"], "")
            self.assertEqual(row["topic"], "")
            self.assertEqual(row["is_claim"], "")
            self.assertEqual(row["anger"], "")
            self.assertEqual(row["loud"], "")

        # 4. Verify no new files written when capture is now disabled
        post_stop = await save_captured_utterance_async(
            speaker_name="Tamer",
            wav_bytes=dummy_wav_1,
            asr_text="بعد إيقاف التسجيل",
            stt_latency_ms=120.0,
            ended_by="silence",
            recordings_dir=self.test_dir
        )
        self.assertIsNone(post_stop)
        updated_wavs = list(self.test_dir.glob("*.wav"))
        self.assertEqual(len(updated_wavs), 3, "No additional WAV files should be written after stop")

        with open(log_file, "r", encoding="utf-8") as f:
            post_lines = [l for l in f if l.strip()]
        self.assertEqual(len(post_lines), 3, "No additional JSONL lines should be written after stop")
        print("\n=== [Phase 3 - B] All 3 clips + JSONL + labels_DRAFT.csv validated (PASS) ===")

    async def test_c_discord_stop_capture_command_message(self):
        """Verify !stop-capture command executes, resets mode, and outputs bilingual notice."""
        config.TEST_CAPTURE_MODE = 1
        mock_ctx = AsyncMock()

        await stop_capture_command(mock_ctx)
        self.assertEqual(config.TEST_CAPTURE_MODE, 0, "!stop-capture must turn off TEST_CAPTURE_MODE")
        mock_ctx.send.assert_awaited_once()
        sent_message = mock_ctx.send.await_args[0][0]

        print("\n=== [Phase 3 - C] Discord Command Message: ===")
        print(sent_message)

        self.assertIn("labels_DRAFT.csv", sent_message)
        self.assertIn("correct_text", sent_message)
        self.assertIn("topic", sent_message)
        self.assertIn("is_claim", sent_message)
        self.assertIn("anger", sent_message)
        self.assertIn("loud", sent_message)
        self.assertIn("العربية", sent_message)
        self.assertIn("English", sent_message)
        self.assertIn("Session Folder", sent_message)

    async def test_d_two_consecutive_isolated_capture_sessions(self):
        """
        Acceptance test for Phase 1:
        Session A (2 utterances) -> stop -> Session B (1 utterance) -> stop
        -> Verify two DISTINCT timestamped folders
        -> Each contains ONLY its own WAVs, its own session_log.jsonl, and its own labels_DRAFT.csv
        -> Zero files in parent folder
        """
        dummy_wav_1 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x01\x02" * 50
        dummy_wav_2 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x03\x04" * 50
        dummy_wav_3 = b"RIFF" + b"\x00" * 36 + b"data" + b"\x05\x06" * 50

        # === SESSION A ===
        session_a_dir = start_capture_session(base_dir=self.test_dir)
        self.assertTrue(session_a_dir.exists())

        # Utterance 1
        entry_a1 = await save_captured_utterance_async(
            speaker_name="Omar",
            wav_bytes=dummy_wav_1,
            asr_text="الجملة الأولى في جلسة أ",
            stt_latency_ms=105.0,
            ended_by="silence"
        )
        self.assertIsNotNone(entry_a1)

        # Utterance 2
        entry_a2 = await save_captured_utterance_async(
            speaker_name="Ziad",
            wav_bytes=dummy_wav_2,
            asr_text="الجملة الثانية في جلسة أ",
            stt_latency_ms=115.0,
            ended_by="silence"
        )
        self.assertIsNotNone(entry_a2)

        # Stop Session A
        csv_a, dir_a = stop_capture_session()
        self.assertEqual(dir_a, session_a_dir)
        self.assertTrue(csv_a.exists())
        self.assertEqual(config.TEST_CAPTURE_MODE, 0)

        # === SESSION B ===
        session_b_dir = start_capture_session(base_dir=self.test_dir)
        self.assertTrue(session_b_dir.exists())
        self.assertNotEqual(session_a_dir, session_b_dir, "Session B must have a distinct timestamped folder")

        # Utterance 3
        entry_b1 = await save_captured_utterance_async(
            speaker_name="Mostafa",
            wav_bytes=dummy_wav_3,
            asr_text="الجملة الوحيدة في جلسة ب",
            stt_latency_ms=95.0,
            ended_by="silence"
        )
        self.assertIsNotNone(entry_b1)

        # Stop Session B
        csv_b, dir_b = stop_capture_session()
        self.assertEqual(dir_b, session_b_dir)
        self.assertTrue(csv_b.exists())
        self.assertEqual(config.TEST_CAPTURE_MODE, 0)

        # === VERIFICATION ===
        # 1. Distinct folders exist
        session_folders = sorted([d for d in self.test_dir.iterdir() if d.is_dir()])
        self.assertEqual(len(session_folders), 2, "Must have exactly 2 distinct session folders")
        self.assertEqual(session_folders[0], session_a_dir)
        self.assertEqual(session_folders[1], session_b_dir)

        # 2. Session A contents: exactly 2 WAVs + 1 session_log.jsonl + 1 labels_DRAFT.csv
        wavs_a = sorted(list(session_a_dir.glob("*.wav")))
        self.assertEqual(len(wavs_a), 2, "Session A must contain exactly 2 WAVs")
        log_a = session_a_dir / "session_log.jsonl"
        self.assertTrue(log_a.exists())
        with open(log_a, "r", encoding="utf-8") as f:
            lines_a = [json.loads(l.strip()) for l in f if l.strip()]
        self.assertEqual(len(lines_a), 2)
        with open(csv_a, "r", encoding="utf-8-sig") as f:
            rows_a = list(csv.DictReader(f))
        self.assertEqual(len(rows_a), 2)

        # 3. Session B contents: exactly 1 WAV + 1 session_log.jsonl + 1 labels_DRAFT.csv
        wavs_b = sorted(list(session_b_dir.glob("*.wav")))
        self.assertEqual(len(wavs_b), 1, "Session B must contain exactly 1 WAV")
        log_b = session_b_dir / "session_log.jsonl"
        self.assertTrue(log_b.exists())
        with open(log_b, "r", encoding="utf-8") as f:
            lines_b = [json.loads(l.strip()) for l in f if l.strip()]
        self.assertEqual(len(lines_b), 1)
        with open(csv_b, "r", encoding="utf-8-sig") as f:
            rows_b = list(csv.DictReader(f))
        self.assertEqual(len(rows_b), 1)

        # 4. Parent directory contains ZERO direct WAVs or JSONL/CSV files
        parent_wavs = list(self.test_dir.glob("*.wav"))
        parent_logs = list(self.test_dir.glob("*.jsonl"))
        parent_csvs = list(self.test_dir.glob("*.csv"))
        self.assertEqual(len(parent_wavs), 0, "No WAV files should exist at root of recordings/")
        self.assertEqual(len(parent_logs), 0, "No jsonl files should exist at root of recordings/")
        self.assertEqual(len(parent_csvs), 0, "No csv files should exist at root of recordings/")

        # 5. Print the full folder tree
        print("\n" + "=" * 65)
        print("=== PHASE 1 ACCEPTANCE: TWO CONSECUTIVE ISOLATED SESSIONS ===")
        print("=" * 65)
        print(f"Root: {self.test_dir}")
        for folder in session_folders:
            print(f"\n📁 {folder.name}/")
            for item in sorted(folder.iterdir()):
                print(f"   └── 📄 {item.name} ({item.stat().st_size} bytes)")
        print("=" * 65 + "\n")

    async def test_e_leave_finalizes_active_capture_session(self):
        """
        Acceptance test for CAP-02 (Phase 1):
        start-capture -> save 1 clip -> simulate !leave ->
        CSV exists in the session folder, capture flag is 0, session dir released.
        """
        dummy_wav = b"RIFF" + b"\x00" * 36 + b"data" + b"\x07\x08" * 50

        # 1. Start capture session
        session_dir = start_capture_session(base_dir=self.test_dir)
        self.assertTrue(session_dir.exists())
        self.assertEqual(config.TEST_CAPTURE_MODE, 1)
        self.assertEqual(get_active_session_dir(), session_dir)

        # 2. Save 1 clip
        entry = await save_captured_utterance_async(
            speaker_name="Mostafa",
            wav_bytes=dummy_wav,
            asr_text="كلام قبل الخروج النهائي",
            stt_latency_ms=110.0,
            ended_by="silence"
        )
        self.assertIsNotNone(entry)
        self.assertTrue((session_dir / entry["wav_filename"]).exists())

        # 3. Simulate !leave
        mock_ctx = AsyncMock()
        mock_ctx.guild.id = 999111
        await leave_channel(mock_ctx)

        # 4. Invariant checks
        self.assertEqual(config.TEST_CAPTURE_MODE, 0, "Capture flag must be reset to 0 on !leave")
        self.assertIsNone(get_active_session_dir(), "Session dir must be released on !leave")

        csv_path = session_dir / "labels_DRAFT.csv"
        self.assertTrue(csv_path.exists(), "labels_DRAFT.csv must exist in session folder")

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1, "CSV must contain the 1 captured clip")
        self.assertEqual(rows[0]["wav_filename"], entry["wav_filename"])
        self.assertEqual(rows[0]["speaker"], "Mostafa")

        mock_ctx.send.assert_awaited_once()
        sent_msg = mock_ctx.send.await_args[0][0]
        self.assertIn("Capture Finalized", sent_msg)
        self.assertIn("labels_DRAFT.csv", sent_msg)

        print("\n" + "=" * 65)
        print("=== CAP-02 ACCEPTANCE: !leave FINALIZES ACTIVE CAPTURE ===")
        print("=" * 65)
        print(f"Session Folder:  {session_dir}")
        print(f"Draft CSV:       {csv_path} (exists: {csv_path.exists()})")
        print(f"CSV Rows:        {len(rows)}")
        print(f"Capture Flag:    {config.TEST_CAPTURE_MODE}")
        print(f"Active Dir:      {get_active_session_dir()}")
        print(f"Discord Message:\n{sent_msg}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
