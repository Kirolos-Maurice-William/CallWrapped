import json
import logging
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.orchestrator import get_call_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["audio_stream"])

# Active audio connections for 2-way peer voice relay: {call_id: {speaker_id: WebSocket}}
active_audio_sockets: Dict[str, Dict[str, WebSocket]] = {}

@router.websocket("/room/{call_id}")
async def room_events_websocket(websocket: WebSocket, call_id: str):
    """
    WebSocket channel for the frontend room UI to receive live transcripts,
    topic events, heat updates, fact check alerts, and audio interventions.
    """
    await websocket.accept()
    orchestrator = get_call_orchestrator(call_id)
    await orchestrator.register_client(websocket)
    logger.info(f"[WS Room] Client joined room {call_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "simulate_turn":
                    turn_data = msg.get("turn", {})
                    await orchestrator.handle_final(turn_data)
            except Exception:
                pass
    except WebSocketDisconnect:
        logger.info(f"[WS Room] Client left room {call_id}")
    finally:
        await orchestrator.unregister_client(websocket)


@router.websocket("/audio/{call_id}/{speaker_id}")
async def audio_stream_websocket(websocket: WebSocket, call_id: str, speaker_id: str):
    """
    Binary WebSocket channel receiving live 16kHz PCM audio stream from a participant's microphone.
    1. Feeds audio directly to AssemblyAI Realtime STT.
    2. Relays audio in real-time to the other participant so both speakers hear each other.
    """
    await websocket.accept()
    orchestrator = get_call_orchestrator(call_id)

    # Register in active audio sockets with dynamic caller disambiguation
    if call_id not in active_audio_sockets:
        active_audio_sockets[call_id] = {}

    # If stream_a is already occupied and incoming is stream_a, automatically promote to stream_b
    effective_speaker_id = speaker_id
    if "stream_b" in speaker_id:
        effective_speaker_id = "stream_b"
    elif "stream_a" not in active_audio_sockets[call_id]:
        effective_speaker_id = "stream_a"
    elif "stream_b" not in active_audio_sockets[call_id]:
        effective_speaker_id = "stream_b"
    else:
        effective_speaker_id = f"stream_{len(active_audio_sockets[call_id]) + 1}"

    active_audio_sockets[call_id][effective_speaker_id] = websocket

    effective_speaker_name = "You" if effective_speaker_id == "stream_a" else "Friend"
    session = await orchestrator.get_or_create_stream_session(effective_speaker_id, effective_speaker_name)
    logger.info(f"[WS Audio] Audio stream started for {effective_speaker_name} ({effective_speaker_id})")

    # Determine peer stream ID
    peer_speaker_id = "stream_b" if effective_speaker_id == "stream_a" else "stream_a"

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                raw_audio = message["bytes"]
                # 1. Send to AssemblyAI STT
                await session.send_audio(raw_audio)

                # 2. Peer audio relay: forward to other participant so they hear your voice!
                peer_ws = active_audio_sockets.get(call_id, {}).get(peer_speaker_id)
                if peer_ws:
                    try:
                        await peer_ws.send_bytes(raw_audio)
                    except Exception:
                        pass

            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    if payload.get("action") == "simulate_turn":
                        turn = payload.get("turn", {})
                        turn["call_id"] = call_id
                        turn["speaker_id"] = effective_speaker_id
                        turn["speaker_name"] = effective_speaker_name
                        await orchestrator.handle_final(turn)
                except Exception:
                    pass
    except WebSocketDisconnect:
        logger.info(f"[WS Audio] Audio stream disconnected for {effective_speaker_name}")
    except Exception as e:
        logger.error(f"[WS Audio] Stream error for {effective_speaker_name}: {e}")
    finally:
        if call_id in active_audio_sockets and effective_speaker_id in active_audio_sockets[call_id]:
            del active_audio_sockets[call_id][effective_speaker_id]
        if call_id in active_audio_sockets and not active_audio_sockets[call_id]:
            del active_audio_sockets[call_id]


async def close_call_audio_sockets(call_id: str):
    """Closes all peer audio sockets for a call session so no audio streams remain active."""
    if call_id in active_audio_sockets:
        sockets = list(active_audio_sockets[call_id].values())
        active_audio_sockets[call_id].clear()
        del active_audio_sockets[call_id]
        for ws in sockets:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
        logger.info(f"[WS Audio] Closed all audio sockets for call {call_id}")
