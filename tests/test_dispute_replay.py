import json
import tempfile
import unittest
from pathlib import Path

from bot.arbitration.dispute_models import ThreadState, ClaimEvent
from bot.arbitration.dispute_replay import (
    ReplayClock,
    extract_claim_from_row,
    load_session_events,
    replay_session,
    format_decision_timeline,
)


class TestDisputeReplay(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.recordings_dir = self.base_dir / "recordings" / "test_session"

    def test_replay_clock_interface(self):
        clock = ReplayClock(100.0)
        self.assertEqual(clock(), 100.0)
        clock.set(150.5)
        self.assertEqual(clock(), 150.5)
        clock.advance(10.0)
        self.assertEqual(clock(), 160.5)

    def test_extract_claim_from_row_non_claim(self):
        row = {
            "clip_id": "clip_001",
            "speaker": "Mostafa",
            "topic": "null_topic",
            "is_claim": "no",
            "correct_text": "ماشي زي الفل",
            "anger": "none",
        }
        prop_key, val_key, conf, feats = extract_claim_from_row(row)
        self.assertEqual(prop_key, "")
        self.assertEqual(val_key, "")
        self.assertEqual(conf, 0.0)
        self.assertEqual(feats.get("escalation"), 0.0)

    def test_extract_claim_from_row_world_cup(self):
        row = {
            "clip_id": "clip_005",
            "speaker": "2xDanger",
            "topic": "football",
            "is_claim": "yes",
            "correct_text": "يا جدعان اللي كسب كاس العالم هي اسبانيا",
            "anger": "high",
        }
        prop_key, val_key, conf, feats = extract_claim_from_row(row)
        self.assertIn("كاس عالم", prop_key)
        self.assertEqual(val_key, "spain")
        self.assertEqual(conf, 0.95)
        self.assertEqual(feats.get("escalation"), 1.0)

    def test_extract_claim_from_row_movies(self):
        row1 = {
            "clip_id": "clip_005",
            "speaker": "2xDanger",
            "topic": "movies",
            "is_claim": "yes",
            "correct_text": "سبايدر مان مسح ذكرته عشان محدش يفتكره",
            "anger": "none",
        }
        prop_key1, val_key1, conf1, _ = extract_claim_from_row(row1)
        self.assertIn("سبايدرمان", prop_key1)
        self.assertEqual(val_key1, "spiderman_self")

        row2 = {
            "clip_id": "clip_009",
            "speaker": "Mostafa",
            "topic": "movies",
            "is_claim": "yes",
            "correct_text": "يا عم لا الدكتور هو المسح زاكرته",
            "anger": "none",
        }
        prop_key2, val_key2, conf2, _ = extract_claim_from_row(row2)
        self.assertEqual(prop_key1, prop_key2)
        self.assertEqual(val_key2, "doctor_strange")

    def test_load_session_events_batch1_casual(self):
        batch1_dir = self.recordings_dir / "2026-09-26_1817"
        if not batch1_dir.exists():
            self.skipTest(f"{batch1_dir} not present")
        events = load_session_events(batch1_dir)
        self.assertEqual(len(events), 25)
        # All events should be non-claims
        self.assertTrue(all(e.proposition_key == "" for e in events))
        self.assertTrue(all(e.value_key == "" for e in events))

    def test_load_session_events_world_cup(self):
        wc_dir = self.recordings_dir / "2026-09-27_1806"
        if not wc_dir.exists():
            self.skipTest(f"{wc_dir} not present")
        events = load_session_events(wc_dir)
        self.assertGreaterEqual(len(events), 19)
        # Check claim values exist
        claim_events = [e for e in events if e.proposition_key != ""]
        self.assertGreater(len(claim_events), 10)
        countries = {e.value_key for e in claim_events}
        self.assertIn("spain", countries)
        self.assertIn("argentina", countries)
        self.assertIn("egypt", countries)

    def test_replay_session_batch1_zero_offers(self):
        batch1_dir = self.recordings_dir / "2026-09-26_1817"
        if not batch1_dir.exists():
            self.skipTest(f"{batch1_dir} not present")
        events = load_session_events(batch1_dir)
        tracker, decisions = replay_session(events)
        self.assertEqual(len(decisions), len(events))
        # Zero offers expected on casual talk
        offers = [d for d in decisions if d.action == "request_offer"]
        self.assertEqual(len(offers), 0)

    def test_replay_session_world_cup_triggers_offer(self):
        wc_dir = self.recordings_dir / "2026-09-27_1806"
        if not wc_dir.exists():
            self.skipTest(f"{wc_dir} not present")
        events = load_session_events(wc_dir)

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            tracker, decisions = replay_session(events, shadow_log_path=tmp_path)
            self.assertEqual(len(decisions), len(events))
            offers = [d for d in decisions if d.action == "request_offer"]
            self.assertEqual(len(offers), 1)
            self.assertEqual(offers[0].state, ThreadState.OFFERED)
            self.assertGreaterEqual(offers[0].confidence, 0.72)

            # Check shadow log file was populated
            with open(tmp_path, "r", encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lines), len(events))
            offer_lines = [l for l in lines if l["action"] == "request_offer"]
            self.assertEqual(len(offer_lines), 1)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_format_decision_timeline(self):
        events = [
            ClaimEvent("clip_001", 100.0, "Alice", "", "", 0.0, "hello"),
            ClaimEvent("clip_002", 102.0, "Bob", "p1", "v1", 0.9, "claim"),
        ]
        clock = ReplayClock(100.0)
        from bot.arbitration.dispute_tracker import DisputeTracker
        tracker = DisputeTracker(clock=clock)
        _, decisions = replay_session(events, tracker=tracker)
        timeline = format_decision_timeline(events, decisions)
        self.assertIn("clip_001", timeline)
        self.assertIn("clip_002", timeline)
        self.assertIn("Alice", timeline)
        self.assertIn("Bob", timeline)


if __name__ == "__main__":
    unittest.main()
