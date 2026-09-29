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


if __name__ == "__main__":
    unittest.main()

