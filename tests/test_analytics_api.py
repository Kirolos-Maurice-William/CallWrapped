import tests._setup
import unittest
from fastapi.testclient import TestClient
from backend.app.main import app


class TestAnalyticsVulgarityApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/api/reset")

    def tearDown(self):
        self.client.post("/api/reset")

    def test_analytics_update_stores_vulgarity_and_computes_totals(self):
        # 1. Post analytics_update event for Alice with vulgarity
        event_alice = {
            "event_id": "evt_alice_01",
            "type": "analytics_update",
            "speaker_name": "Alice",
            "talk_delta_seconds": 15.0,
            "vulgarity_count": 2,
            "vulgarity_terms": ["ا**", "f***"],
            "payload": {
                "vulgarity_count": 2,
                "vulgarity_terms": ["ا**", "f***"]
            }
        }
        res1 = self.client.post("/api/events", json=event_alice)
        self.assertEqual(res1.status_code, 200)

        # 2. Post analytics_update event for Bob with clean speech
        event_bob = {
            "event_id": "evt_bob_01",
            "type": "analytics_update",
            "speaker_name": "Bob",
            "talk_delta_seconds": 25.0,
            "vulgarity_count": 0,
            "vulgarity_terms": [],
            "payload": {
                "vulgarity_count": 0,
                "vulgarity_terms": []
            }
        }
        res2 = self.client.post("/api/events", json=event_bob)
        self.assertEqual(res2.status_code, 200)

        # 3. Verify GET /api/live includes analytics with vulgarity state
        live_res = self.client.get("/api/live")
        self.assertEqual(live_res.status_code, 200)
        analytics = live_res.json().get("analytics", {})

        self.assertEqual(analytics.get("total_vulgarity_count"), 2)
        speakers = analytics.get("speakers", {})
        self.assertIn("Alice", speakers)
        self.assertIn("Bob", speakers)

        self.assertEqual(speakers["Alice"]["vulgarity_count"], 2)
        self.assertEqual(speakers["Alice"]["vulgarity_terms"], ["ا**", "f***"])

        self.assertEqual(speakers["Bob"]["vulgarity_count"], 0)
        self.assertEqual(speakers["Bob"]["vulgarity_terms"], [])

        # 4. Verify /api/reset clears vulgarity totals
        self.client.post("/api/reset")
        reset_res = self.client.get("/api/live")
        reset_analytics = reset_res.json().get("analytics", {})
        self.assertEqual(reset_analytics.get("total_vulgarity_count"), 0)
        self.assertEqual(len(reset_analytics.get("speakers", {})), 0)

    def test_banter_telemetry_and_audio_evidence_api(self):
        # 1. Post analytics_update with banter metrics
        event_banter = {
            "event_id": "evt_banter_01",
            "type": "analytics_update",
            "speaker_name": "Alice",
            "talk_delta_seconds": 10.0,
            "banter_count": 3,
            "banter_terms": ["roast1", "roast2"],
            "payload": {
                "banter_count": 3,
                "banter_terms": ["roast1", "roast2"]
            }
        }
        res1 = self.client.post("/api/events", json=event_banter)
        self.assertEqual(res1.status_code, 200)

        # 2. Check /api/analytics
        res_analytics = self.client.get("/api/analytics")
        self.assertEqual(res_analytics.status_code, 200)
        data = res_analytics.json()
        self.assertEqual(data.get("total_banter_count"), 3)
        self.assertEqual(data["speakers"]["Alice"]["banter_count"], 3)
        self.assertEqual(data["speakers"]["Alice"]["banter_terms"], ["roast1", "roast2"])

        # 3. Test /api/audio-evidence with non-existent file -> 404
        res_audio = self.client.get("/api/audio-evidence/non_existent_clip_123.wav")
        self.assertEqual(res_audio.status_code, 404)

        # 4. Test /api/audio-evidence with invalid extension -> 400
        res_bad = self.client.get("/api/audio-evidence/exploit.exe")
        self.assertEqual(res_bad.status_code, 400)

        # 5. Test /api/audio-evidence with real WAV file
        from bot.config import PROJECT_ROOT
        test_rec_dir = PROJECT_ROOT / "recordings" / "test_session_unit_test"
        test_rec_dir.mkdir(parents=True, exist_ok=True)
        dummy_wav = test_rec_dir / "evidence_sample_999.wav"
        dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

        try:
            res_valid = self.client.get("/api/audio-evidence/evidence_sample_999.wav")
            self.assertEqual(res_valid.status_code, 200)
            self.assertEqual(res_valid.headers["content-type"], "audio/wav")
            self.assertIn("inline", res_valid.headers.get("content-disposition", "") or "inline")
        finally:
            if dummy_wav.exists():
                dummy_wav.unlink()

        # 6. Test path traversal defense -> Path(filename).name strips directory separators
        res_trav = self.client.get("/api/audio-evidence/..%2F..%2Fsecret.wav")
        # Since safe_filename strips traversal, it searches for 'secret.wav' which doesn't exist -> 404 (safe)
        self.assertIn(res_trav.status_code, (400, 404))

        # 7. Test fallback anger_episodes_history preserving context and audio_clip
        event_anger_fallback = {
            "event_id": "evt_anger_fb",
            "type": "analytics_update",
            "speaker_name": "Bob",
            "anger": "high",
            "anger_evidence": "بقولك اخرس",
            "payload": {
                "anger": "high",
                "anger_evidence": "بقولك اخرس",
                "context": "hostile_escalation (sustained attack)",
                "audio_clip": "1700000099_Bob.wav",
                "audio_features": {"was_loud": True, "peak_robust_z": 3.5}
            }
        }
        res_fb = self.client.post("/api/events", json=event_anger_fallback)
        self.assertEqual(res_fb.status_code, 200)

        res_analytics_fb = self.client.get("/api/analytics")
        bob_stats = res_analytics_fb.json()["speakers"]["Bob"]
        self.assertEqual(bob_stats["angry_episodes"], 1)
        self.assertEqual(len(bob_stats["anger_episodes_history"]), 1)
        ep = bob_stats["anger_episodes_history"][0]
        self.assertEqual(ep["quote"], "بقولك اخرس")
        self.assertEqual(ep["was_loud"], True)
        self.assertEqual(ep["peak_z"], 3.5)
        self.assertEqual(ep["context"], "hostile_escalation (sustained attack)")
        self.assertEqual(ep["audio_clip"], "1700000099_Bob.wav")


if __name__ == "__main__":
    unittest.main()

