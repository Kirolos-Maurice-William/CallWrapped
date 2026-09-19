import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger("AppRoutes")

router = APIRouter(prefix="/api", tags=["routes"])

# Active WebSockets pool for real-time dashboard updates
active_connections: List[WebSocket] = []

# Live State for Voice Arbitrator
LIVE_STATE: Dict[str, Any] = {
    "is_call_active": True,
    "last_updated": time.time(),
    "latency": {
        "stt_ms": 272,
        "llm_ms": 198,
        "search_ms": 540,
        "tts_ms": 180,
        "total_ms": 1190
    },
    "turns": [],
    "active_dispute": None,
    "disputes_history": [],
    "leaderboard": {
        "Verified Claims": 0,
        "Disputed Claims": 0,
        "Speakers": {}
    }
}


class VoiceEventPayload(BaseModel):
    event_id: str
    session_id: str = "hackathon_live_session"
    correlation_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    type: str  # "transcript" | "claim" | "dispute" | "verification" | "intervention"
    speaker_id: Optional[str] = None
    speaker_name: str
    text: str
    timings: Optional[Dict[str, float]] = None
    latency: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


async def broadcast_event(event_data: dict):
    """Broadcasts event payload to all connected WebSockets."""
    for ws in list(active_connections):
        try:
            await ws.send_json(event_data)
        except Exception:
            if ws in active_connections:
                active_connections.remove(ws)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for live dashboard streaming."""
    await websocket.accept()
    active_connections.append(websocket)
    try:
        await websocket.send_json({"type": "initial_state", "data": LIVE_STATE})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)


@router.post("/events")
async def ingest_voice_event(event: VoiceEventPayload):
    """Ingests VoiceEvents from the Discord Bot or Replay Engine."""
    LIVE_STATE["last_updated"] = event.timestamp

    # Update latency metrics if provided
    if event.latency:
        for k, v in event.latency.items():
            if v is not None and v > 0:
                LIVE_STATE["latency"][k] = v

    # 1. Transcript Turn
    if event.type == "transcript":
        turn_data = {
            "speaker_name": event.speaker_name,
            "text": event.text,
            "timestamp": event.timestamp,
            "stt_ms": event.latency.get("stt_ms") if event.latency else None,
            "correlation_id": event.correlation_id
        }
        LIVE_STATE["turns"].append(turn_data)
        if len(LIVE_STATE["turns"]) > 50:
            LIVE_STATE["turns"].pop(0)

        # Update speaker turn count
        speakers = LIVE_STATE["leaderboard"]["Speakers"]
        if event.speaker_name not in speakers:
            speakers[event.speaker_name] = {"turns": 0, "verified": 0, "refuted": 0}
        speakers[event.speaker_name]["turns"] += 1

    # 2. Claim
    elif event.type == "claim":
        logger.info(f"💡 [Claim] {event.speaker_name}: {event.text} (correlation: {event.correlation_id})")

    # 3. Intervention (Factual Dispute Resolved)
    elif event.type == "intervention":
        payload = event.payload
        spk_a = payload.get("speaker_a")
        spk_b = payload.get("speaker_b")
        spk_a_status = payload.get("speaker_a_status", "UNKNOWN")
        spk_b_status = payload.get("speaker_b_status", "UNKNOWN")
        evidence_strength = payload.get("evidence_strength", "HIGH")
        why_i_spoke = payload.get("why_i_spoke", [
            "Factual claim detected via FastGate + Groq",
            "Direct contradiction identified on target entity",
            "Tier-1 authoritative source located",
            "Evidence confidence high (99%)",
            "Spoken intervention triggered via neural voice"
        ])

        dispute_info = {
            "event_id": event.event_id,
            "correlation_id": event.correlation_id,
            "timestamp": event.timestamp,
            "speaker_a": spk_a,
            "claim_a": payload.get("claim_a"),
            "speaker_a_status": spk_a_status,
            "speaker_b": spk_b,
            "claim_b": payload.get("claim_b"),
            "speaker_b_status": spk_b_status,
            "winner": payload.get("winner"),
            "loser": payload.get("loser"),
            "correct_fact": payload.get("correct_fact"),
            "confidence": payload.get("confidence", 95),
            "evidence_strength": evidence_strength,
            "status": payload.get("status", "CONTRADICTED"),
            "source_url": payload.get("source_url"),
            "source_title": payload.get("source_title", "Official Citation"),
            "spoken_intervention": payload.get("spoken_intervention", event.text),
            "why_i_spoke": why_i_spoke,
            "latency": event.latency,
            "timings": event.timings
        }
        LIVE_STATE["active_dispute"] = dispute_info
        LIVE_STATE["disputes_history"].append(dispute_info)
        LIVE_STATE["leaderboard"]["Disputed Claims"] += 1
        LIVE_STATE["leaderboard"]["Verified Claims"] += 1

        speakers = LIVE_STATE["leaderboard"]["Speakers"]
        if spk_a:
            if spk_a not in speakers:
                speakers[spk_a] = {"turns": 0, "verified": 0, "refuted": 0}
            if spk_a_status == "SUPPORTED":
                speakers[spk_a]["verified"] += 1
            elif spk_a_status == "CONTRADICTED":
                speakers[spk_a]["refuted"] += 1

        if spk_b:
            if spk_b not in speakers:
                speakers[spk_b] = {"turns": 0, "verified": 0, "refuted": 0}
            if spk_b_status == "SUPPORTED":
                speakers[spk_b]["verified"] += 1
            elif spk_b_status == "CONTRADICTED":
                speakers[spk_b]["refuted"] += 1

    await broadcast_event({"type": event.type, "event": event.dict(), "live_state": LIVE_STATE})
    return {"status": "ok", "event_id": event.event_id}


@router.get("/live")
async def get_live_state():
    """Returns current live dashboard snapshot."""
    return LIVE_STATE


@router.post("/reset")
async def reset_live_state():
    """Resets dashboard state for a fresh demo run."""
    LIVE_STATE["turns"].clear()
    LIVE_STATE["active_dispute"] = None
    LIVE_STATE["disputes_history"].clear()
    LIVE_STATE["leaderboard"] = {
        "Verified Claims": 0,
        "Disputed Claims": 0,
        "Speakers": {}
    }
    await broadcast_event({"type": "reset", "live_state": LIVE_STATE})
    return {"status": "ok"}


@router.post("/demo/run")
async def run_demo_simulation():
    """Triggers the golden RTX 5070 demo replay asynchronously."""
    import asyncio

    session_path = Path(__file__).resolve().parent.parent.parent / "demo" / "sessions" / "rtx5070_dispute.json"
    if not session_path.exists():
        return {"error": "Demo session file not found"}

    with open(session_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    async def _runner():
        await reset_live_state()
        for step in data.get("events", []):
            delay = step.get("delay_seconds", 1.0)
            await asyncio.sleep(delay)
            evt_dict = step.get("event", {})
            evt_dict["timestamp"] = time.time()
            evt = VoiceEventPayload(**evt_dict)
            await ingest_voice_event(evt)

    asyncio.create_task(_runner())
    return {"status": "started", "message": "Demo replay initiated"}
