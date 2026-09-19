import time
import logging
from typing import Dict, Any, List
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("LiveSync")

router = APIRouter(prefix="/api", tags=["live_sync"])

# In-memory real-time state for live dashboard
LIVE_STATE = {
    "is_call_active": True,
    "last_updated": time.time(),
    "turns": [],
    "disputes": [],
    "leaderboard": {}
}


class LiveTurnPayload(BaseModel):
    speaker_name: str
    text: str
    timestamp: float = 0.0


class LiveDisputePayload(BaseModel):
    speaker_a: str
    claim_a: str
    speaker_b: str
    claim_b: str
    truth: str
    winner: str = None
    confidence: int = 95
    sources: List[Dict[str, Any]] = []


@router.post("/turns")
async def record_live_turn(payload: LiveTurnPayload):
    turn_data = {
        "speaker_name": payload.speaker_name,
        "text": payload.text,
        "timestamp": payload.timestamp or time.time()
    }
    LIVE_STATE["turns"].append(turn_data)
    if len(LIVE_STATE["turns"]) > 50:
        LIVE_STATE["turns"].pop(0)

    # Update speaker turn stats
    name = payload.speaker_name
    if name not in LIVE_STATE["leaderboard"]:
        LIVE_STATE["leaderboard"][name] = {"turns": 0, "wins": 0, "losses": 0}
    LIVE_STATE["leaderboard"][name]["turns"] += 1
    LIVE_STATE["last_updated"] = time.time()
    return {"status": "ok", "total_turns": len(LIVE_STATE["turns"])}


@router.post("/disputes")
async def record_live_dispute(payload: LiveDisputePayload):
    dispute_data = payload.dict()
    dispute_data["timestamp"] = time.time()
    LIVE_STATE["disputes"].append(dispute_data)

    if payload.winner:
        w = payload.winner
        if w not in LIVE_STATE["leaderboard"]:
            LIVE_STATE["leaderboard"][w] = {"turns": 0, "wins": 0, "losses": 0}
        LIVE_STATE["leaderboard"][w]["wins"] += 1

    loser = payload.speaker_b if payload.winner == payload.speaker_a else payload.speaker_a
    if loser and loser in LIVE_STATE["leaderboard"]:
        LIVE_STATE["leaderboard"][loser]["losses"] += 1

    LIVE_STATE["last_updated"] = time.time()
    return {"status": "ok", "total_disputes": len(LIVE_STATE["disputes"])}


@router.get("/live")
async def get_live_data():
    """Returns real-time turns, disputes, and leaderboard for the Next.js frontend."""
    return LIVE_STATE
