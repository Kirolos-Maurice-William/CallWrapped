import tests._setup
import os
import csv
import json
import shutil
import tempfile
import unittest
import asyncio
from pathlib import Path

from audit.score_test_session import score_session
from bot.config import PROJECT_ROOT


class TestScoreTestSession(unittest.IsolatedAsyncioTestCase):
    """
    Phase 3 Acceptance Test for SCR-01:
    - Step 9 scorer accepts session folder with labels_DRAFT.csv + WAVs
    - Transcribes real audio via AssemblyAI with production settings
    - Computes WER (jiwer), numbers, topic, claim, anger agreement
    - Refuses to score rows with empty correct_text (lists as skipped)
    - Output written to audit/score_results.md
    - Human CSV is preserved unmodified
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_score_session_")
        self.session_path = Path(self.temp_dir)
        self.clips_dir = PROJECT_ROOT / "audit" / "mgb3_clips"
        self.output_md = self.session_path / "test_score_results.md"

    def tearDown(self):
        if self.session_path.exists():
            shutil.rmtree(self.session_path, ignore_errors=True)

    async def test_score_three_synthetic_labeled_rows_and_refusal_path(self):
        # 1. Setup 3 real audio WAVs from mgb3_clips into the session folder
        clip_names = [
            "sports_48_first_12min_49.822_55.542.wav",
            "comedy_09_first_12min_4.754_12.352.wav",
            "moviesDrama_68_first_12min_84.717_91.758.wav"
        ]
        for name in clip_names:
            src = self.clips_dir / name
            self.assertTrue(src.exists(), f"Source audio {src} must exist")
            shutil.copy(src, self.session_path / name)

        # Also add a 4th dummy WAV for the empty refusal test
        unlabeled_wav = self.session_path / "unlabeled_clip.wav"
        shutil.copy(self.clips_dir / clip_names[0], unlabeled_wav)

        # 2. Create labels_DRAFT.csv in the session folder
        # 3 rows with correct_text, 1 row with empty correct_text (refusal path)
        csv_path = self.session_path / "labels_DRAFT.csv"
        rows = [
            {
                "clip_id": "clip_001",
                "wav_filename": clip_names[0],
                "speaker": "Ahmed",
                "asr_text": "لكن تميزت في الفترة الأخيرة هي رياضة السباحة",
                "correct_text": "لكن تميزت في الفترة الأخيرة هي رياضة السباحة بالزعانف تابعونا النهارده في حلم جديد وإحلم معانا",
                "topic": "sports",
                "is_claim": "no",
                "anger": "none",
                "loud": "normal",
                "claim_pair": ""
            },
            {
                "clip_id": "clip_002",
                "wav_filename": clip_names[1],
                "speaker": "Tamer",
                "asr_text": "سلامات عليكم حكلمكو النهارده عن ال uncertainty",
                "correct_text": "سلامات عليكم حكلمكو النهارده عن ال uncertainty",
                "topic": "other",
                "is_claim": "no",
                "anger": "none",
                "loud": "normal",
                "claim_pair": ""
            },
            {
                "clip_id": "clip_003",
                "wav_filename": clip_names[2],
                "speaker": "Kareem",
                "asr_text": "فهو لا يعدو كونه سلوكا وكل سلوك على ضوء الحتمية السيكولوجية",
                "correct_text": "فهو لا يعدو كونه سلوكا وكل سلوك على ضوء الحتمية السيكولوجية",
                "topic": "movies",
                "is_claim": "no",
                "anger": "none",
                "loud": "normal",
                "claim_pair": ""
            },
            {
                "clip_id": "clip_004",
                "wav_filename": "unlabeled_clip.wav",
                "speaker": "Ziad",
                "asr_text": "كلام لم يقم الإنسان بمراجعته",
                "correct_text": "",  # EMPTY - must be skipped by refusal rule
                "topic": "",
                "is_claim": "",
                "anger": "",
                "loud": "",
                "claim_pair": ""
            }
        ]

        fieldnames = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # 3. Execute score_session with 1s pacing between calls
        summary = await score_session(
            session_dir=self.session_path,
            output_md=self.output_md,
            pace_delay_sec=1.0
        )

        # 4. Invariant Assertions
        # (a) Refusal Path Check:
        self.assertEqual(summary["total_rows"], 4)
        self.assertEqual(summary["scored_count"], 3, "Exactly 3 labeled rows should be scored")
        self.assertEqual(summary["skipped_count"], 1, "Exactly 1 empty row should be skipped")
        self.assertEqual(summary["skipped_records"][0]["clip_id"], "clip_004")
        self.assertIn("Empty correct_text", summary["skipped_records"][0]["reason"])

        # (b) WER and Accuracy Metrics:
        self.assertGreater(len(summary["scored_records"]), 0)
        self.assertIsInstance(summary["overall_wer"], float)
        self.assertLess(summary["overall_wer"], 0.40, "WER should be reasonably low on real audio")

        # (c) Report File Generated:
        self.assertTrue(self.output_md.exists())
        md_text = self.output_md.read_text(encoding="utf-8")
        self.assertIn("# Step 9: Captured Test Session Scoring Report", md_text)
        self.assertIn("Executive Metric Summary", md_text)
        self.assertIn("Detailed Per-Clip Scoring Table", md_text)
        self.assertIn("Skipped Clips", md_text)
        self.assertIn("clip_004", md_text)

        # (d) Human CSV Unmodified Check:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            post_rows = list(csv.DictReader(f))
        self.assertEqual(len(post_rows), 4)
        self.assertEqual(post_rows[3]["correct_text"], "")
        self.assertEqual(post_rows[0]["correct_text"], rows[0]["correct_text"])

        print("\n" + "=" * 65)
        print("=== SCR-01 ACCEPTANCE: STEP 9 SCORER REPORT ===")
        print("=" * 65)
        print(md_text)
        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
