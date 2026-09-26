import unittest
import tempfile
import shutil
import json
import csv
from pathlib import Path
from datetime import datetime

from bot.audio.migrate_recordings import migrate_recordings_directory


class TestMigrateRecordings(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_migration_")
        self.target_dir = Path(self.test_dir)

    def tearDown(self):
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_empty_directory(self):
        result = migrate_recordings_directory(self.target_dir)
        self.assertIn(result["status"], ["empty", "no_stacked_clips"])
        self.assertEqual(result["session_count"], 0)

    def test_migration_existing_subfolders_only(self):
        subfolder = self.target_dir / "2026-09-20_1400"
        subfolder.mkdir(parents=True)
        dummy_wav = subfolder / "dummy.wav"
        dummy_wav.write_bytes(b"dummy")

        result = migrate_recordings_directory(self.target_dir)
        self.assertEqual(result["status"], "no_stacked_clips")
        self.assertEqual(result["session_count"], 0)
        self.assertTrue(dummy_wav.exists())

    def test_stacked_loose_files_split_by_10min_gap_and_labels_preserved(self):
        # 1. Create stacked WAV files in root
        wav1 = self.target_dir / "1700000000_Alice.wav"
        wav2 = self.target_dir / "1700000120_Bob.wav"
        wav3 = self.target_dir / "1700001200_Charlie.wav"
        wav1.write_bytes(b"RIFF_WAV1")
        wav2.write_bytes(b"RIFF_WAV2")
        wav3.write_bytes(b"RIFF_WAV3")

        # 2. Create session_log.jsonl with entries
        log_file = self.target_dir / "session_log.jsonl"
        log_entries = [
            {
                "timestamp": 1700000000,
                "speaker_name": "Alice",
                "wav_filename": "1700000000_Alice.wav",
                "asr_text": "مرحبا جميعا",
                "stt_latency_ms": 250.0,
                "ended_by": "silence"
            },
            {
                "timestamp": 1700000120,
                "speaker_name": "Bob",
                "wav_filename": "1700000120_Bob.wav",
                "asr_text": "أهلا بك",
                "stt_latency_ms": 210.0,
                "ended_by": "silence"
            },
            {
                "timestamp": 1700001200,
                "speaker_name": "Charlie",
                "wav_filename": "1700001200_Charlie.wav",
                "asr_text": "جلسة جديدة",
                "stt_latency_ms": 300.0,
                "ended_by": "silence"
            }
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for entry in log_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 3. Create labels_DRAFT.csv with human annotations on wav1
        csv_file = self.target_dir / "labels_DRAFT.csv"
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "clip_id", "wav_filename", "speaker", "asr_text",
                "correct_text", "topic", "is_claim", "anger", "loud"
            ])
            writer.writeheader()
            writer.writerow({
                "clip_id": "clip_001",
                "wav_filename": "1700000000_Alice.wav",
                "speaker": "Alice",
                "asr_text": "مرحبا جميعا",
                "correct_text": "مرحبا بالجميع أهلا وسهلا",
                "topic": "ترحيب",
                "is_claim": "0",
                "anger": "0",
                "loud": "1"
            })
            writer.writerow({
                "clip_id": "clip_002",
                "wav_filename": "1700000120_Bob.wav",
                "speaker": "Bob",
                "asr_text": "أهلا بك",
                "correct_text": "",
                "topic": "",
                "is_claim": "",
                "anger": "",
                "loud": ""
            })
            writer.writerow({
                "clip_id": "clip_003",
                "wav_filename": "1700001200_Charlie.wav",
                "speaker": "Charlie",
                "asr_text": "جلسة جديدة",
                "correct_text": "",
                "topic": "",
                "is_claim": "",
                "anger": "",
                "loud": ""
            })

        # 4. Create an unattributed file and pre-existing subfolder
        unattributed = self.target_dir / "unattributed_notes.txt"
        unattributed.write_text("Do not delete me!", encoding="utf-8")

        existing_folder = self.target_dir / "2026-09-20_1000"
        existing_folder.mkdir()
        (existing_folder / "old.wav").write_bytes(b"OLD")

        # 5. Run migration with 10-minute (600s) threshold
        result = migrate_recordings_directory(self.target_dir, gap_seconds=600.0)

        # 6. Verify result dictionary
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["session_count"], 2)
        self.assertIn("unattributed_notes.txt", result["unattributed_files"])

        # 7. Verify unattributed file is preserved in root (DELETE NOTHING rule)
        self.assertTrue(unattributed.exists())
        self.assertEqual(unattributed.read_text(encoding="utf-8"), "Do not delete me!")

        # 8. Verify pre-existing subfolder was untouched
        self.assertTrue((existing_folder / "old.wav").exists())

        # 9. Verify root has no loose WAVs, and root log & draft csv are cleaned up
        root_wavs = list(self.target_dir.glob("*.wav"))
        self.assertEqual(len(root_wavs), 0)
        self.assertFalse(log_file.exists())
        self.assertFalse(csv_file.exists())

        # 10. Verify created session folders
        session_folders = result["session_folders"]
        self.assertEqual(len(session_folders), 2)

        folder_s1 = self.target_dir / session_folders[0]
        folder_s2 = self.target_dir / session_folders[1]

        # Session 1 checks (wav1, wav2)
        self.assertTrue((folder_s1 / "1700000000_Alice.wav").exists())
        self.assertTrue((folder_s1 / "1700000120_Bob.wav").exists())
        self.assertTrue((folder_s1 / "session_log.jsonl").exists())
        self.assertTrue((folder_s1 / "labels_DRAFT.csv").exists())

        with open(folder_s1 / "session_log.jsonl", "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["wav_filename"], "1700000000_Alice.wav")
            self.assertEqual(lines[1]["wav_filename"], "1700000120_Bob.wav")

        # Verify human annotation preservation in Session 1
        with open(folder_s1 / "labels_DRAFT.csv", "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 2)
            self.assertEqual(reader[0]["wav_filename"], "1700000000_Alice.wav")
            self.assertEqual(reader[0]["correct_text"], "مرحبا بالجميع أهلا وسهلا")
            self.assertEqual(reader[0]["topic"], "ترحيب")
            self.assertEqual(reader[0]["loud"], "1")

        # Session 2 checks (wav3)
        self.assertTrue((folder_s2 / "1700001200_Charlie.wav").exists())
        self.assertTrue((folder_s2 / "session_log.jsonl").exists())
        self.assertTrue((folder_s2 / "labels_DRAFT.csv").exists())

        with open(folder_s2 / "session_log.jsonl", "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["wav_filename"], "1700001200_Charlie.wav")

        with open(folder_s2 / "labels_DRAFT.csv", "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["wav_filename"], "1700001200_Charlie.wav")
            self.assertEqual(reader[0]["correct_text"], "")


if __name__ == "__main__":
    unittest.main()
