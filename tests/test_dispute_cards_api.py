import tests._setup
import json
import unittest
from fastapi.testclient import TestClient
from backend.app.main import app


def _event(event_id, evt_type, payload, speaker_name="Referee", text="", timestamp=1700000000.0, correlation_id=None):
    return {
        "event_id": event_id,
        "session_id": "hackathon_live_session",
        "correlation_id": correlation_id,
        "timestamp": timestamp,
        "type": evt_type,
        "speaker_name": speaker_name,
        "text": text,
        "payload": payload
    }


OFFERED_PAYLOAD = {
    "offer_id": "off_a1b2c3d4",
    "speaker_a": "Omar",
    "claim_a": "فيها 16 جيجا",
    "speaker_b": "Ziad",
    "claim_b": "لا هي 12 بس",
    "entity": "RTX 5070",
    "search_query": "RTX 5070 VRAM specification",
    "expires_in_seconds": 30.0,
    "expires_at": 1700000030.0
}

COMPLETED_PAYLOAD = {
    "offer_id": "off_a1b2c3d4",
    "confirmed_by": "Mostafa",
    "t_perceived_ms": 1642,
    "status": "CONTRADICTED",
    "confidence": 97,
    "evidence_strength": "HIGH",
    "correct_fact": "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM",
    "speaker_a": "Omar",
    "claim_a": "فيها 16 جيجا",
    "speaker_a_status": "CONTRADICTED",
    "speaker_b": "Ziad",
    "claim_b": "لا هي 12 بس",
    "speaker_b_status": "SUPPORTED",
    "source_url": "https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070/",
    "source_title": "NVIDIA Official Product Specifications",
    "evidence_excerpt": "GeForce RTX 5070 — 12GB GDDR7 memory.",
    "disputed_aspect": "VRAM capacity"
}


class TestDisputeCardsAPI(unittest.TestCase):
    """
    Phase 1 acceptance: LIVE_STATE carries a dispute card per gate-passed dispute
    (offered / checking / resolved / expired / refused_private), exposed on
    /api/live and pushed over /api/ws.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/api/reset")

    def tearDown(self):
        self.client.post("/api/reset")
        self.client.close()

    def test_a_empty_state_has_empty_disputes_list(self):
        live = self.client.get("/api/live").json()
        print("\n=== [A] GET /api/live — EMPTY STATE ===")
        print(json.dumps({"disputes": live["disputes"]}, ensure_ascii=False, indent=2))
        self.assertIn("disputes", live)
        self.assertEqual(live["disputes"], [])

    def test_b_offered_then_completed_collapse_into_one_resolved_card(self):
        r1 = self.client.post("/api/events", json=_event(
            "evt_offer_01", "dispute_check_offered", OFFERED_PAYLOAD,
            speaker_name="Ziad", text="🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟"
        ))
        self.assertEqual(r1.status_code, 200)

        offered_card = self.client.get("/api/live").json()["disputes"][0]
        print("\n=== [B1] After dispute_check_offered ===")
        print(json.dumps(offered_card, ensure_ascii=False, indent=2))

        self.assertEqual(offered_card["status"], "offered")
        self.assertEqual(offered_card["speaker_a"], OFFERED_PAYLOAD["speaker_a"])
        self.assertEqual(offered_card["claim_a"], OFFERED_PAYLOAD["claim_a"])
        self.assertEqual(offered_card["speaker_b"], OFFERED_PAYLOAD["speaker_b"])
        self.assertEqual(offered_card["claim_b"], OFFERED_PAYLOAD["claim_b"])
        self.assertEqual(offered_card["disputed_attribute"], OFFERED_PAYLOAD["entity"])
        self.assertIsNone(offered_card["source_url"])
        self.assertIsNone(offered_card["t_perceived_ms"])
        self.assertIsNone(offered_card["checked_timestamp"])

        r2 = self.client.post("/api/events", json=_event(
            "evt_completed_01", "dispute_check_completed", COMPLETED_PAYLOAD,
            speaker_name="Mostafa", text="على حسب اللي لقيته، الكارت 12 جيجا", timestamp=1700000012.5
        ))
        self.assertEqual(r2.status_code, 200)

        live = self.client.get("/api/live").json()
        print("\n=== [B2] GET /api/live after dispute_check_completed ===")
        print(json.dumps({"disputes": live["disputes"]}, ensure_ascii=False, indent=2))

        self.assertEqual(len(live["disputes"]), 1, "offered + completed for one offer_id must be ONE card")
        card = live["disputes"][0]
        self.assertEqual(card["status"], "resolved")
        self.assertEqual(card["speaker_a"], COMPLETED_PAYLOAD["speaker_a"])
        self.assertEqual(card["claim_a"], COMPLETED_PAYLOAD["claim_a"])
        self.assertEqual(card["speaker_b"], COMPLETED_PAYLOAD["speaker_b"])
        self.assertEqual(card["claim_b"], COMPLETED_PAYLOAD["claim_b"])
        self.assertEqual(card["disputed_attribute"], COMPLETED_PAYLOAD["disputed_aspect"])
        self.assertEqual(card["source_name"], COMPLETED_PAYLOAD["source_title"])
        self.assertEqual(card["source_url"], COMPLETED_PAYLOAD["source_url"])
        self.assertEqual(card["evidence_excerpt"], COMPLETED_PAYLOAD["evidence_excerpt"])
        self.assertEqual(card["t_perceived_ms"], COMPLETED_PAYLOAD["t_perceived_ms"])
        self.assertEqual(card["checked_timestamp"], 1700000012.5)
        self.assertIsNone(card["refusal_reason"])

    def test_c_checking_status_transition(self):
        self.client.post("/api/events", json=_event(
            "evt_offer_02", "dispute_check_offered", OFFERED_PAYLOAD))
        self.client.post("/api/events", json=_event(
            "evt_started_02", "dispute_check_started",
            {"offer_id": OFFERED_PAYLOAD["offer_id"], "confirmed_by": "Mostafa"},
            timestamp=1700000009.0))

        card = self.client.get("/api/live").json()["disputes"][0]
        print("\n=== [C] After dispute_check_started ===")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        self.assertEqual(card["status"], "checking")
        self.assertEqual(card["claim_a"], OFFERED_PAYLOAD["claim_a"], "offered data must survive the transition")

    def test_d_expired_card_carries_refusal_reason(self):
        self.client.post("/api/events", json=_event(
            "evt_offer_03", "dispute_check_offered", OFFERED_PAYLOAD))
        self.client.post("/api/events", json=_event(
            "evt_expired_03", "dispute_check_expired",
            {
                "offer_id": OFFERED_PAYLOAD["offer_id"],
                "speaker_a": "Omar", "claim_a": "فيها 16 جيجا",
                "speaker_b": "Ziad", "claim_b": "لا هي 12 بس",
                "entity": "RTX 5070",
                "reason": "offered_not_confirmed"
            },
            timestamp=1700000030.0))

        card = self.client.get("/api/live").json()["disputes"][0]
        print("\n=== [D] After dispute_check_expired ===")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        self.assertEqual(card["status"], "expired")
        self.assertEqual(card["refusal_reason"], "offered_not_confirmed")
        self.assertIsNone(card["checked_timestamp"], "expired offers were never checked")

    def test_e_private_entity_refusal_card(self):
        self.client.post("/api/events", json=_event(
            "evt_private_04", "intervention",
            {
                "status": "REFUSED_PRIVATE",
                "label": "Private claim — no lookup performed",
                "correct_fact": "Private claim — no lookup performed",
                "entity_type": "PRIVATE",
                "entity_name": "محمد",
                "speaker_a": "Omar", "claim_a": "محمد قال الماتش الساعة 8",
                "speaker_b": "Ziad", "claim_b": "لا هو قال 9"
            },
            correlation_id="corr_private_04", timestamp=1700000100.0))

        card = self.client.get("/api/live").json()["disputes"][0]
        print("\n=== [E] Private entity refusal card ===")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        self.assertEqual(card["status"], "refused_private")
        self.assertEqual(card["refusal_reason"], "Private claim — no lookup performed")
        self.assertEqual(card["claim_a"], "محمد قال الماتش الساعة 8")
        self.assertIsNone(card["source_url"], "a refused private claim must carry NO looked-up source")
        self.assertIsNone(card["evidence_excerpt"])

    def test_f_list_is_newest_first_and_capped_at_five(self):
        for i in range(7):
            self.client.post("/api/events", json=_event(
                f"evt_bulk_{i}", "dispute_check_offered",
                {
                    "offer_id": f"off_bulk_{i}",
                    "speaker_a": "Omar", "claim_a": f"claim A {i}",
                    "speaker_b": "Ziad", "claim_b": f"claim B {i}",
                    "entity": f"entity_{i}"
                },
                timestamp=1700000200.0 + i))

        disputes = self.client.get("/api/live").json()["disputes"]
        print("\n=== [F] Cap + ordering ===")
        print(json.dumps([{"dispute_id": c["dispute_id"], "status": c["status"]} for c in disputes],
                         ensure_ascii=False, indent=2))
        self.assertEqual(len(disputes), 5, "list keeps the latest 5 disputes")
        self.assertEqual([c["dispute_id"] for c in disputes],
                         ["off_bulk_6", "off_bulk_5", "off_bulk_4", "off_bulk_3", "off_bulk_2"],
                         "newest first")

    def test_g_websocket_pushes_dispute_updates_live(self):
        with self.client.websocket_connect("/api/ws") as ws:
            initial = ws.receive_json()
            self.assertEqual(initial["type"], "initial_state")
            self.assertIn("disputes", initial["data"])
            print("\n=== [G1] /api/ws initial_state carries disputes ===")
            print(json.dumps({"disputes": initial["data"]["disputes"]}, ensure_ascii=False))

            self.client.post("/api/events", json=_event(
                "evt_ws_offer", "dispute_check_offered", OFFERED_PAYLOAD))
            pushed_offer = ws.receive_json()
            self.assertEqual(pushed_offer["type"], "dispute_check_offered")
            offer_card = pushed_offer["live_state"]["disputes"][0]
            self.assertEqual(offer_card["status"], "offered")
            print("\n=== [G2] WS push after offered ===")
            print(json.dumps(offer_card, ensure_ascii=False, indent=2))

            self.client.post("/api/events", json=_event(
                "evt_ws_completed", "dispute_check_completed", COMPLETED_PAYLOAD,
                timestamp=1700000012.5))
            pushed_done = ws.receive_json()
            done_card = pushed_done["live_state"]["disputes"][0]
            self.assertEqual(done_card["status"], "resolved")
            self.assertEqual(done_card["t_perceived_ms"], 1642)
            print("\n=== [G3] WS push after completed ===")
            print(json.dumps(done_card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()
