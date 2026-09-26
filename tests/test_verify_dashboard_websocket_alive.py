import tests._setup
import unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.routes import active_connections


class TestDashboardWebSocketStreaming(unittest.TestCase):
    """
    Verification 2: Proof the dashboard WebSocket stays connected during playback
    and receives real-time streamed events from the bot.
    """

    def test_dashboard_websocket_streaming_health(self):
        print("\n" + "=" * 65)
        print("=== VERIFICATION 2: DASHBOARD WEBSOCKET HEALTH & STREAMING ===")
        print("=" * 65)

        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as ws:
                # 1. Connected and received initial live state
                initial = ws.receive_json()
                self.assertEqual(initial.get("type"), "initial_state")
                print("✅ [1] Dashboard WebSocket connected to /api/ws.")
                print(f"       Initial payload type: '{initial.get('type')}' | is_call_active: {initial.get('data', {}).get('is_call_active')}")

                # 2. Simulate bot streaming events during playback
                test_event = {
                    "event_id": "evt_stream_test_01",
                    "session_id": "hackathon_live_session",
                    "type": "transcript",
                    "speaker_name": "Mostafa",
                    "text": "تصحيح سريع: المصدر اللي لقيته بيقول...",
                    "payload": {}
                }
                resp = client.post("/api/events", json=test_event)
                self.assertEqual(resp.status_code, 200)
                print("✅ [2] Bot published transcript event to /api/events (HTTP 200).")

                # 3. Verify event is received live on the WebSocket
                received = ws.receive_json()
                event_data = received.get("event", {})
                self.assertEqual(event_data.get("event_id"), "evt_stream_test_01")
                self.assertEqual(event_data.get("speaker_name"), "Mostafa")
                print(f"✅ [3] Event streamed live to WebSocket client: '{event_data.get('text')}'")

                # 4. Simulate arbitration intervention event during playback
                intervention_event = {
                    "event_id": "evt_stream_test_02",
                    "session_id": "hackathon_live_session",
                    "type": "intervention",
                    "speaker_name": "RefereeBot",
                    "text": "تصحيح سريع",
                    "payload": {
                        "speaker_a": "Omar",
                        "claim_a": "16 جيجا",
                        "speaker_b": "Ziad",
                        "claim_b": "12 جيجا",
                        "correct_fact": "RTX 5070 has 12GB VRAM",
                        "status": "CONTRADICTED"
                    }
                }
                resp = client.post("/api/events", json=intervention_event)
                self.assertEqual(resp.status_code, 200)

                received_intervention = ws.receive_json()
                interv_event = received_intervention.get("event", {})
                self.assertEqual(interv_event.get("event_id"), "evt_stream_test_02")
                print("✅ [4] Intervention event streamed live to WebSocket client.")

        print("=" * 65)
        print("✅ [PROOF VERIFIED] Dashboard WebSocket remained 100% connected & responsive!")
        print("=" * 65 + "\n")

    def test_ws_origin_allowed(self):
        """Test (a): Origin http://localhost:3000 -> accepted."""
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws", headers={"Origin": "http://localhost:3000"}) as ws:
                initial = ws.receive_json()
                self.assertEqual(initial.get("type"), "initial_state")

    def test_ws_origin_rejected(self):
        """Test (b): Origin http://evil.com -> rejected before accept with code 1008."""
        from starlette.websockets import WebSocketDisconnect
        with TestClient(app) as client:
            with self.assertRaises(WebSocketDisconnect) as cm:
                with client.websocket_connect("/api/ws", headers={"Origin": "http://evil.com"}):
                    pass
            self.assertEqual(cm.exception.code, 1008)

    def test_ws_no_origin_allowed(self):
        """Test (c): no Origin header -> accepted."""
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as ws:
                initial = ws.receive_json()
                self.assertEqual(initial.get("type"), "initial_state")


if __name__ == "__main__":
    unittest.main()
