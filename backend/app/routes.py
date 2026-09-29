import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger("AppRoutes")

router = APIRouter(prefix="/api", tags=["routes"])

# Active WebSockets pool for real-time dashboard updates
active_connections: List[WebSocket] = []

# Live Analytics State for CallWrapped
ANALYTICS_STATE: Dict[str, Any] = {
    "topic_totals": {},
    "speakers": {},
    "total_talk_seconds": 0.0,
    "total_angry_episodes": 0,
    "total_vulgarity_count": 0,
    "total_banter_count": 0,
    "longest_streak": {
        "speaker_name": None,
        "streak_seconds": 0.0
    }
}

# Live State for CallWrapped
LIVE_STATE: Dict[str, Any] = {
    "is_call_active": True,
    "last_updated": 0.0,
    "latency": {
        "stt_ms": 0,
        "llm_ms": 0,
        "search_ms": 0,
        "tts_ms": 0,
        "total_ms": 0
    },
    "turns": [],
    "active_dispute": None,
    "disputes": [],
    "disputes_history": [],
    "leaderboard": {
        "Verified Claims": 0,
        "Disputed Claims": 0,
        "Speakers": {}
    },
    "active_offer": None,
    "fact_check_mode": "OFF",
    "fact_check_mode_badge": "Fact Check Mode: OFF",
    "assemblyai_model": settings.ASSEMBLYAI_MODEL,
    "discord_invite_url": settings.discord_invite_url,
    "analytics": ANALYTICS_STATE
}


class VoiceEventPayload(BaseModel):
    event_id: str
    session_id: str = "hackathon_live_session"
    correlation_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    type: str  # "transcript" | "claim" | "dispute" | "verification" | "intervention" | "analytics_update" | "dispute_check_offered" | "dispute_check_completed" | "dispute_check_expired" | "fact_check_mode_update"
    speaker_id: Optional[str] = None
    speaker_name: str = "Unknown"
    text: str = ""
    timings: Optional[Dict[str, float]] = None
    latency: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    # Analytics fields
    topic: Optional[str] = None
    anger: Optional[str] = None
    anger_evidence: Optional[str] = None
    first_anger_quote: Optional[str] = None
    anger_episodes_history: Optional[List[Dict[str, Any]]] = None
    talk_delta_seconds: Optional[float] = None
    streak_seconds: Optional[float] = None
    angry_episodes: Optional[int] = None
    vulgarity_count: Optional[int] = None
    vulgarity_terms: Optional[List[str]] = None
    total_vulgarity_count: Optional[int] = None
    banter_count: Optional[int] = None
    banter_terms: Optional[List[str]] = None
    total_banter_count: Optional[int] = None


async def broadcast_event(event_data: dict):
    """Broadcasts event payload to all connected WebSockets."""
    for ws in list(active_connections):
        try:
            await ws.send_json(event_data)
        except Exception:
            if ws in active_connections:
                active_connections.remove(ws)


# --- Dispute Cards ---------------------------------------------------------
# One card per gate-passed dispute, carrying its full lifecycle:
#   offered -> checking -> resolved | expired | refused_private
# Cards are keyed by offer_id (falling back to correlation_id / event_id) so
# the offered / completed / expired events of one dispute collapse into a
# single card instead of stacking duplicates.

MAX_DISPUTE_CARDS = 5

DISPUTE_CARD_FIELDS = (
    "speaker_a", "claim_a", "speaker_b", "claim_b", "disputed_attribute",
    "status", "refusal_reason", "source_name", "source_url",
    "evidence_excerpt", "checked_timestamp", "t_perceived_ms"
)


def _first_present(payload: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Returns the first key present and non-empty in payload, else None."""
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _dispute_card_key(event: "VoiceEventPayload") -> str:
    """Stable identity for a dispute across its offered/completed/expired events."""
    return str(event.payload.get("offer_id") or event.correlation_id or event.event_id)


def _upsert_dispute_card(key: str, updates: Dict[str, Any], timestamp: float) -> Dict[str, Any]:
    """
    Creates or updates the dispute card identified by `key`.
    Newest dispute first; list capped at MAX_DISPUTE_CARDS.
    None-valued updates are dropped so later events never blank out earlier data.
    """
    clean = {k: v for k, v in updates.items() if v is not None}

    for card in LIVE_STATE["disputes"]:
        if card.get("dispute_id") == key:
            card.update(clean)
            card["last_updated"] = timestamp
            return card

    card: Dict[str, Any] = {"dispute_id": key}
    card.update({field: None for field in DISPUTE_CARD_FIELDS})
    card["created_at"] = timestamp
    card["last_updated"] = timestamp
    card.update(clean)

    LIVE_STATE["disputes"].insert(0, card)
    del LIVE_STATE["disputes"][MAX_DISPUTE_CARDS:]
    return card


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for live dashboard streaming."""
    origin = websocket.headers.get("origin")
    allowed_origins = (
        settings.cors_origin_list
        if hasattr(settings, "cors_origin_list")
        else [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
        if isinstance(settings.CORS_ORIGINS, str)
        else list(settings.CORS_ORIGINS)
    )
    if origin and origin not in allowed_origins:
        logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
        await websocket.close(code=1008)
        return

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

    # 3. Intervention or Dispute Check Completed (Factual Dispute Resolved)
    elif event.type in ("intervention", "dispute_check_completed"):
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
        LIVE_STATE["active_offer"] = None
        LIVE_STATE["leaderboard"]["Disputed Claims"] += 1
        LIVE_STATE["leaderboard"]["Verified Claims"] += 1

        # Dispute card: private-entity refusal never performs a lookup, so it
        # resolves to refused_private with no source; everything else resolves.
        if str(payload.get("status", "")).upper() == "REFUSED_PRIVATE":
            _upsert_dispute_card(
                _dispute_card_key(event),
                {
                    "speaker_a": spk_a,
                    "claim_a": payload.get("claim_a"),
                    "speaker_b": spk_b,
                    "claim_b": payload.get("claim_b"),
                    "disputed_attribute": _first_present(
                        payload, "disputed_attribute", "disputed_aspect", "entity", "entity_name"
                    ),
                    "status": "refused_private",
                    "refusal_reason": _first_present(
                        payload, "refusal_reason", "label", "rejection_reason"
                    ) or "private_entity",
                },
                event.timestamp
            )
        else:
            _upsert_dispute_card(
                _dispute_card_key(event),
                {
                    "speaker_a": spk_a,
                    "claim_a": payload.get("claim_a"),
                    "speaker_b": spk_b,
                    "claim_b": payload.get("claim_b"),
                    "disputed_attribute": _first_present(
                        payload, "disputed_attribute", "disputed_aspect", "entity", "entity_name"
                    ),
                    "status": "resolved",
                    "source_name": _first_present(payload, "source_name", "source_title"),
                    "source_url": payload.get("source_url"),
                    "evidence_excerpt": _first_present(
                        payload, "evidence_excerpt", "evidence_snippet"
                    ),
                    "checked_timestamp": event.timestamp,
                    "t_perceived_ms": payload.get("t_perceived_ms"),
                },
                event.timestamp
            )

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

    # 4. Dispute Check Offered
    elif event.type == "dispute_check_offered":
        payload = event.payload
        LIVE_STATE["active_offer"] = {
            "event_id": event.event_id,
            "offer_id": payload.get("offer_id"),
            "speaker_a": payload.get("speaker_a"),
            "claim_a": payload.get("claim_a"),
            "speaker_b": payload.get("speaker_b"),
            "claim_b": payload.get("claim_b"),
            "entity": payload.get("entity"),
            "expires_in_seconds": payload.get("expires_in_seconds", 30.0),
            "expires_at": payload.get("expires_at"),
            "timestamp": event.timestamp,
            "text": event.text
        }
        LIVE_STATE["last_updated"] = event.timestamp
        _upsert_dispute_card(
            _dispute_card_key(event),
            {
                "speaker_a": payload.get("speaker_a"),
                "claim_a": payload.get("claim_a"),
                "speaker_b": payload.get("speaker_b"),
                "claim_b": payload.get("claim_b"),
                "disputed_attribute": _first_present(
                    payload, "disputed_attribute", "disputed_aspect", "entity"
                ),
                "status": "offered",
            },
            event.timestamp
        )
        logger.info(f"📣 [LiveState] Dispute offer registered: {payload.get('offer_id')}")

    # 5. Dispute Check Confirmed (verification in flight)
    elif event.type in ("dispute_check_started", "dispute_check_confirmed"):
        payload = event.payload
        _upsert_dispute_card(
            _dispute_card_key(event),
            {
                "speaker_a": payload.get("speaker_a"),
                "claim_a": payload.get("claim_a"),
                "speaker_b": payload.get("speaker_b"),
                "claim_b": payload.get("claim_b"),
                "disputed_attribute": _first_present(
                    payload, "disputed_attribute", "disputed_aspect", "entity"
                ),
                "status": "checking",
            },
            event.timestamp
        )
        LIVE_STATE["last_updated"] = event.timestamp
        logger.info(f"🔎 [LiveState] Dispute check in flight: {payload.get('offer_id')}")

    # 6. Dispute Check Expired
    elif event.type == "dispute_check_expired":
        payload = event.payload
        LIVE_STATE["active_offer"] = None
        LIVE_STATE["last_updated"] = event.timestamp
        _upsert_dispute_card(
            _dispute_card_key(event),
            {
                "speaker_a": payload.get("speaker_a"),
                "claim_a": payload.get("claim_a"),
                "speaker_b": payload.get("speaker_b"),
                "claim_b": payload.get("claim_b"),
                "disputed_attribute": _first_present(
                    payload, "disputed_attribute", "disputed_aspect", "entity"
                ),
                "status": "expired",
                "refusal_reason": _first_present(payload, "refusal_reason", "reason"),
            },
            event.timestamp
        )
        logger.info(f"⌛ [LiveState] Dispute offer expired: {event.payload.get('offer_id')}")

    # 7. Fact Check Mode Update
    elif event.type == "fact_check_mode_update":
        LIVE_STATE["fact_check_mode"] = event.payload.get("mode", "ON")
        LIVE_STATE["fact_check_mode_badge"] = event.payload.get("badge", "Fact Check Mode: ON")
        LIVE_STATE["last_updated"] = event.timestamp
        logger.info(f"🛡️ [LiveState] Fact Check Mode updated: {LIVE_STATE['fact_check_mode']}")

    # 8. Analytics Aggregation (analytics_update or any event carrying analytics data)
    topic = event.topic or event.payload.get("topic")
    anger = event.anger or event.payload.get("anger")
    anger_evidence = event.anger_evidence or event.payload.get("anger_evidence")
    talk_delta = event.talk_delta_seconds if event.talk_delta_seconds is not None else event.payload.get("talk_delta_seconds")
    streak = event.streak_seconds if event.streak_seconds is not None else event.payload.get("streak_seconds")
    episodes = event.angry_episodes if event.angry_episodes is not None else event.payload.get("angry_episodes")

    if event.type == "analytics_update" or topic or talk_delta is not None or episodes is not None:
        spk = event.speaker_name or "Unknown"
        if spk not in ANALYTICS_STATE["speakers"]:
            ANALYTICS_STATE["speakers"][spk] = {
                "speaker_name": spk,
                "talk_seconds": 0.0,
                "longest_streak_seconds": 0.0,
                "angry_episodes": 0,
                "first_anger_quote": None,
                "anger_evidence": None,
                "anger_episodes_history": [],
                "vulgarity_count": 0,
                "vulgarity_terms": [],
                "banter_count": 0,
                "banter_terms": []
            }
        spk_stats = ANALYTICS_STATE["speakers"][spk]

        if "anger_episodes_history" not in spk_stats:
            spk_stats["anger_episodes_history"] = []

        if "vulgarity_terms" not in spk_stats:
            spk_stats["vulgarity_terms"] = []

        if "banter_terms" not in spk_stats:
            spk_stats["banter_terms"] = []

        if topic:
            ANALYTICS_STATE["topic_totals"][topic] = ANALYTICS_STATE["topic_totals"].get(topic, 0) + 1

        if talk_delta is not None:
            spk_stats["talk_seconds"] = round(spk_stats["talk_seconds"] + float(talk_delta), 2)
        elif "total_speak_seconds" in event.payload:
            spk_stats["talk_seconds"] = round(float(event.payload["total_speak_seconds"]), 2)

        if streak is not None:
            spk_stats["longest_streak_seconds"] = max(spk_stats["longest_streak_seconds"], round(float(streak), 2))
            if spk_stats["longest_streak_seconds"] > ANALYTICS_STATE["longest_streak"]["streak_seconds"]:
                ANALYTICS_STATE["longest_streak"]["speaker_name"] = spk
                ANALYTICS_STATE["longest_streak"]["streak_seconds"] = spk_stats["longest_streak_seconds"]

        if episodes is not None:
            spk_stats["angry_episodes"] = max(spk_stats["angry_episodes"], int(episodes))
        elif anger in ("mild", "high"):
            spk_stats["angry_episodes"] += 1

        # Banter & vulgarity tracking (Phase 2 & 3)
        vulgarity_cnt = event.vulgarity_count if event.vulgarity_count is not None else event.payload.get("vulgarity_count")
        if vulgarity_cnt is not None:
            spk_stats["vulgarity_count"] = max(spk_stats.get("vulgarity_count", 0), int(vulgarity_cnt))

        v_terms = event.vulgarity_terms or event.payload.get("vulgarity_terms")
        if v_terms and isinstance(v_terms, list):
            existing_terms = set(spk_stats.get("vulgarity_terms", []))
            for t in v_terms:
                if t not in existing_terms:
                    spk_stats.setdefault("vulgarity_terms", []).append(t)
                    existing_terms.add(t)

        banter_cnt = event.banter_count if event.banter_count is not None else event.payload.get("banter_count")
        if banter_cnt is not None:
            spk_stats["banter_count"] = max(spk_stats.get("banter_count", 0), int(banter_cnt))

        b_terms = event.banter_terms or event.payload.get("banter_terms")
        if b_terms and isinstance(b_terms, list):
            existing_b_terms = set(spk_stats.get("banter_terms", []))
            for t in b_terms:
                if t not in existing_b_terms:
                    spk_stats.setdefault("banter_terms", []).append(t)
                    existing_b_terms.add(t)

        # Preserve quotes and receipts
        first_q = event.first_anger_quote or event.payload.get("first_anger_quote")
        if first_q and not spk_stats.get("first_anger_quote"):
            spk_stats["first_anger_quote"] = str(first_q).strip()

        if anger_evidence:
            spk_stats["anger_evidence"] = str(anger_evidence).strip()
            if not spk_stats.get("first_anger_quote"):
                spk_stats["first_anger_quote"] = str(anger_evidence).strip()

        # Update episode history list
        hist = event.anger_episodes_history or event.payload.get("anger_episodes_history")
        if hist and isinstance(hist, list):
            spk_stats["anger_episodes_history"] = list(hist)
        elif anger in ("mild", "high") and anger_evidence:
            existing_quotes = {item.get("quote") for item in spk_stats["anger_episodes_history"]}
            clean_ev = str(anger_evidence).strip()
            if clean_ev not in existing_quotes:
                af = event.payload.get("audio_features") or {}
                spk_stats["anger_episodes_history"].append({
                    "episode_number": spk_stats["angry_episodes"],
                    "quote": clean_ev,
                    "timestamp": round(event.timestamp, 2),
                    "anger": str(anger).lower(),
                    "was_loud": bool(af.get("was_loud", False)),
                    "peak_z": float(af.get("peak_robust_z", 0.0)),
                    "context": str(event.payload.get("context") or ""),
                    "audio_clip": event.payload.get("audio_clip")
                })

        ANALYTICS_STATE["total_talk_seconds"] = round(sum(s["talk_seconds"] for s in ANALYTICS_STATE["speakers"].values()), 2)
        ANALYTICS_STATE["total_angry_episodes"] = sum(s["angry_episodes"] for s in ANALYTICS_STATE["speakers"].values())
        ANALYTICS_STATE["total_vulgarity_count"] = sum(s.get("vulgarity_count", 0) for s in ANALYTICS_STATE["speakers"].values())
        ANALYTICS_STATE["total_banter_count"] = sum(s.get("banter_count", 0) for s in ANALYTICS_STATE["speakers"].values())

    await broadcast_event({"type": event.type, "event": event.dict(), "live_state": LIVE_STATE, "analytics": ANALYTICS_STATE})
    return {"status": "ok", "event_id": event.event_id}


@router.get("/live")
async def get_live_state():
    """Returns current live dashboard snapshot (includes the dispute card list)."""
    return LIVE_STATE


@router.get("/analytics")
async def get_analytics():
    """Returns aggregated session analytics (topics, speaker talk time, streaks, anger)."""
    return ANALYTICS_STATE


@router.get("/audio-evidence/{filename:path}")
async def get_audio_evidence(filename: str):
    """
    Safely serves recorded audio evidence clips for dashboard inspection.
    Guards strictly against directory traversal attacks.
    """
    from fastapi.responses import FileResponse, Response

    project_root = Path(__file__).resolve().parent.parent.parent
    recordings_root = (project_root / "recordings").resolve()
    safe_filename = Path(filename).name
    if not safe_filename.endswith(".wav"):
        return Response(status_code=400, content="Invalid audio format")

    # Priority 1: dedicated active evidence directory
    evidence_path = recordings_root / "test_session" / "evidence" / safe_filename
    if evidence_path.is_file():
        target_path = evidence_path.resolve()
    else:
        # Priority 2: newest matching session clip across recordings
        candidate_paths = sorted(
            [p for p in recordings_root.rglob(safe_filename) if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not candidate_paths:
            return Response(status_code=404, content="Audio clip not found")
        target_path = candidate_paths[0].resolve()

    if not target_path.is_relative_to(recordings_root):
        return Response(status_code=403, content="Access denied")

    return FileResponse(path=str(target_path), media_type="audio/wav", filename=safe_filename, content_disposition_type="inline")


async def do_reset_state():
    """Internal helper to reset in-memory state and notify connected WebSockets."""
    LIVE_STATE["last_updated"] = 0.0
    LIVE_STATE["latency"] = {
        "stt_ms": 0,
        "llm_ms": 0,
        "search_ms": 0,
        "tts_ms": 0,
        "total_ms": 0
    }
    LIVE_STATE["turns"].clear()
    LIVE_STATE["active_dispute"] = None
    LIVE_STATE["active_offer"] = None
    LIVE_STATE["fact_check_mode"] = "OFF"
    LIVE_STATE["fact_check_mode_badge"] = "Fact Check Mode: OFF"
    LIVE_STATE["disputes_history"].clear()
    LIVE_STATE["disputes"].clear()
    LIVE_STATE["leaderboard"] = {
        "Verified Claims": 0,
        "Disputed Claims": 0,
        "Speakers": {}
    }
    ANALYTICS_STATE["topic_totals"].clear()
    ANALYTICS_STATE["speakers"].clear()
    ANALYTICS_STATE["total_talk_seconds"] = 0.0
    ANALYTICS_STATE["total_angry_episodes"] = 0
    ANALYTICS_STATE["total_vulgarity_count"] = 0
    ANALYTICS_STATE["total_banter_count"] = 0
    ANALYTICS_STATE["longest_streak"] = {
        "speaker_name": None,
        "streak_seconds": 0.0
    }
    await broadcast_event({"type": "reset", "live_state": LIVE_STATE, "analytics": ANALYTICS_STATE})
    return {"status": "ok"}


@router.post("/reset")
async def reset_live_state(request: Request):
    """Resets dashboard state for a fresh run."""
    control_key = os.getenv("CONTROL_PLANE_KEY")
    if control_key:
        auth_header = request.headers.get("x-control-key")
        if auth_header != control_key:
            return Response(status_code=401, content="Unauthorized control-plane reset")
    return await do_reset_state()


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
        try:
            await do_reset_state()
            for step in data.get("events", []):
                delay = step.get("delay_seconds", 1.0)
                await asyncio.sleep(delay)
                evt_dict = step.get("event", {})
                evt_dict["timestamp"] = time.time()
                evt = VoiceEventPayload(**evt_dict)
                await ingest_voice_event(evt)
        except Exception as e:
            logger.exception("Error in demo replay runner: %s", e)

    asyncio.create_task(_runner())
    return {"status": "started", "message": "Demo replay initiated"}
