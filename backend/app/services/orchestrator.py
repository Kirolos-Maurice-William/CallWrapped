import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy.future import select
from sqlalchemy import update

try:
    import orjson
    def fast_serialize(obj): return orjson.dumps(obj).decode("utf-8")
except ImportError:
    import json
    def fast_serialize(obj): return json.dumps(obj)

from app.database import AsyncSessionLocal
from app.models import Call, Participant, TranscriptTurn, AnalysisEvent, Claim, FactCheck, Argument
from app.services.assemblyai_service import AssemblyAIRealtimeSession
from app.services.analyzer_service import ConversationAnalyzerService
from app.services.claim_detector_service import ClaimDetectorService
from app.services.fact_checker_service import FactCheckerService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)

DISAGREEMENT_TRIGGER_WORDS = ["لا", "غلط", "مش صح", "كذاب", "مش مظبوط", "no", "wrong", "false", "actually"]

class CallSessionOrchestrator:
    """
    High-Performance Orchestrator with Sub-Second Turnaround:
    - Zero-copy orjson WebSocket broadcasting
    - Detached Write-Behind DB engine (non-blocking persistence)
    - Speculative Fact-Checking on streaming partials
    - Granular millisecond latency watermarking
    """
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.analyzer = ConversationAnalyzerService()
        self.claim_detector = ClaimDetectorService()
        self.fact_checker = FactCheckerService()
        self.tts = TTSService()

        self.audio_sessions: Dict[str, AssemblyAIRealtimeSession] = {}
        self.connected_clients: List[Any] = []
        self.last_interruption_time = 0.0
        # Active recent claim for speculative prefetching
        self._last_active_claim: Optional[Dict[str, Any]] = None

    async def register_client(self, websocket: Any):
        self.connected_clients.append(websocket)

    async def unregister_client(self, websocket: Any):
        if websocket in self.connected_clients:
            self.connected_clients.remove(websocket)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Zero-latency orjson broadcast to all active room clients."""
        payload_str = fast_serialize({"type": event_type, "call_id": self.call_id, "data": data})
        dead_clients = []
        for client in self.connected_clients:
            try:
                await client.send_text(payload_str)
            except Exception:
                dead_clients.append(client)
        for dead in dead_clients:
            if dead in self.connected_clients:
                self.connected_clients.remove(dead)

    async def get_or_create_stream_session(self, speaker_id: str, speaker_name: str) -> AssemblyAIRealtimeSession:
        if speaker_id not in self.audio_sessions:
            session = AssemblyAIRealtimeSession(
                call_id=self.call_id,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                on_partial=lambda d: asyncio.create_task(self.handle_partial(d)),
                on_final=lambda d: asyncio.create_task(self.handle_final(d))
            )
            await session.connect()
            self.audio_sessions[speaker_id] = session
        return self.audio_sessions[speaker_id]

    async def handle_partial(self, event_data: Dict[str, Any]):
        """
        Processes streaming partial transcript:
        1. Broadcasts to UI for instant typing effect.
        2. SPECULATIVE PREFETCH: Checks for early disagreement marker to trigger search before turn finishes!
        """
        text = event_data.get("text", "")
        speaker_name = event_data.get("speaker_name", "")

        # Speculative search check
        if self._last_active_claim and self._last_active_claim["speaker_name"] != speaker_name:
            text_lower = text.lower()
            has_disagree_marker = any(w in text_lower for w in DISAGREEMENT_TRIGGER_WORDS)
            if has_disagree_marker:
                # Trigger background prefetch
                asyncio.create_task(
                    self.fact_checker.prefetch_speculative_search(
                        self._last_active_claim["text"],
                        text,
                        self._last_active_claim["topic"]
                    )
                )

        await self.broadcast("transcript_partial", event_data)

    async def handle_final(self, event_data: Dict[str, Any]):
        """
        Zero-blocking turn handler:
        - DB persistence is detached into background task.
        - Conversation intelligence, claims, and fact checking start at t = 0ms.
        """
        t_pipeline_start = time.perf_counter()
        speaker_id = event_data.get("speaker_id")
        speaker_name = event_data.get("speaker_name")
        start_ms = event_data.get("start_ms", 0)
        end_ms = event_data.get("end_ms", 0)
        text = event_data.get("text", "")
        language = event_data.get("language", "mixed")
        turn_id = str(uuid.uuid4())

        # 1. DETACHED PERSISTENCE (Write-Behind Cache Pattern: 0ms blocking)
        asyncio.create_task(
            self._persist_turn_bg(turn_id, speaker_id, speaker_name, start_ms, end_ms, text, language)
        )

        # 2. IMMEDIATE CONCURRENT ANALYSIS
        analysis = await self.analyzer.analyze_turn(event_data)
        t_analysis_done = time.perf_counter()

        analysis_latency_ms = round((t_analysis_done - t_pipeline_start) * 1000, 1)

        # Broadcast final turn immediately
        await self.broadcast("transcript_final", {
            "turn_id": turn_id,
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "language": language,
            "analysis": analysis,
            "latency_telemetry": {
                "turn_analysis_ms": analysis_latency_ms
            }
        })

        # Save analysis in background
        asyncio.create_task(self._persist_analysis_bg(turn_id, analysis))

        # 3. CLAIM & DISAGREEMENT DETECTION
        dispute = self.claim_detector.register_turn(event_data, analysis)
        if dispute:
            if dispute.get("type") == "disagreement" and dispute.get("fact_check_required"):
                asyncio.create_task(
                    self._process_factual_disagreement(dispute, turn_id, speaker_id, t_pipeline_start)
                )
            elif dispute.get("type") == "factual_claim":
                self._last_active_claim = {
                    "speaker_name": speaker_name,
                    "text": dispute["claim"],
                    "topic": dispute["topic"]
                }
                asyncio.create_task(self._save_single_claim(dispute, turn_id, speaker_id))

    async def _persist_turn_bg(self, turn_id: str, speaker_id: str, speaker_name: str, start_ms: int, end_ms: int, text: str, language: str):
        try:
            turn_duration = max(0, end_ms - start_ms)
            async with AsyncSessionLocal() as db:
                turn = TranscriptTurn(
                    id=turn_id,
                    call_id=self.call_id,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    language=language
                )
                db.add(turn)
                if speaker_id:
                    stmt = (
                        update(Participant)
                        .where(Participant.id == speaker_id)
                        .values(speaking_time_ms=Participant.speaking_time_ms + turn_duration)
                    )
                    await db.execute(stmt)
                await db.commit()
        except Exception as e:
            logger.error(f"[Orchestrator] Background turn persist error: {e}")

    async def _persist_analysis_bg(self, turn_id: str, analysis: Dict[str, Any]):
        try:
            async with AsyncSessionLocal() as db:
                analysis_event = AnalysisEvent(
                    call_id=self.call_id,
                    turn_id=turn_id,
                    topic=analysis["topic"],
                    intent=analysis["intent"],
                    heat_score=analysis["heat_score"],
                    is_claim=analysis["is_claim"],
                    is_disagreement=analysis["is_disagreement"]
                )
                db.add(analysis_event)
                await db.commit()
        except Exception as e:
            logger.error(f"[Orchestrator] Background analysis persist error: {e}")

    async def _save_single_claim(self, claim_data: Dict[str, Any], turn_id: str, speaker_id: str):
        claim_id = str(uuid.uuid4())
        try:
            async with AsyncSessionLocal() as db:
                claim = Claim(
                    id=claim_id,
                    call_id=self.call_id,
                    speaker_id=speaker_id,
                    turn_id=turn_id,
                    text=claim_data["claim"],
                    topic=claim_data["topic"],
                    status="pending",
                    confidence=0.0
                )
                db.add(claim)
                await db.commit()
        except Exception as e:
            logger.error(f"[Orchestrator] Save claim error: {e}")

        await self.broadcast("claim_detected", {
            "claim_id": claim_id,
            "speaker": claim_data["speaker"],
            "claim": claim_data["claim"],
            "topic": claim_data["topic"]
        })

    async def _process_factual_disagreement(self, dispute: Dict[str, Any], turn_id: str, speaker_id: str, t_pipeline_start: float):
        """Executes sub-second fact-checking and low-latency voice intervention."""
        logger.info(f"[Orchestrator] Sub-second fact checking dispute: {dispute}")

        # Broadcast argument started immediately
        await self.broadcast("argument_started", {
            "topic": dispute["topic"],
            "participants": [dispute["speaker_a"], dispute["speaker_b"]],
            "claim_a": dispute["claim_a"],
            "claim_b": dispute["claim_b"]
        })

        # Asynchronously verify with external sources
        fact_result = await self.fact_checker.verify_disagreement(dispute)
        t_fact_checked = time.perf_counter()

        fact_check_latency_ms = round((t_fact_checked - t_pipeline_start) * 1000, 1)

        # Interruption Evaluation
        now = time.time()
        cooldown_elapsed = (now - self.last_interruption_time) > 25.0
        should_interrupt = (
            fact_result["confidence"] >= 0.80
            and fact_result["result"] in ["supported", "contradicted"]
            and cooldown_elapsed
            and fact_result.get("factual_truth") is not None
        )

        interruption_audio = None
        interruption_text = None
        t_tts_start = time.perf_counter()

        if should_interrupt:
            truth = fact_result.get("factual_truth", "")
            is_arabic = any('\u0600' <= char <= '\u06FF' for char in dispute["claim_a"] + dispute["claim_b"])
            if is_arabic:
                interruption_text = f"ثواني يا شباب — راجعت المعلومة دي: {truth} تقدروا تكملوا."
            else:
                interruption_text = f"Wait a second — I checked that: {truth} You can continue."

            interruption_audio = await self.tts.synthesize_speech(interruption_text)
            self.last_interruption_time = now

        tts_latency_ms = round((time.perf_counter() - t_tts_start) * 1000, 1) if should_interrupt else 0.0
        total_end_to_end_ms = round((time.perf_counter() - t_pipeline_start) * 1000, 1)

        # Save DB entities in background
        asyncio.create_task(self._persist_disagreement_bg(dispute, turn_id, speaker_id, fact_result, should_interrupt, interruption_text))

        # Broadcast Fact Check Alert with full Latency Watermarks
        await self.broadcast("fact_check_result", {
            "claim_id": str(uuid.uuid4()),
            "topic": dispute["topic"],
            "dispute": dispute,
            "result": fact_result["result"],
            "confidence": fact_result["confidence"],
            "evidence": fact_result.get("evidence", ""),
            "sources": fact_result.get("sources", []),
            "interrupted": should_interrupt,
            "interruption_text": interruption_text,
            "audio_data": interruption_audio,
            "latency_waterfall": {
                "search_retrieval_ms": fact_result.get("search_latency_ms", 0),
                "fact_verification_ms": fact_check_latency_ms,
                "tts_synthesis_ms": tts_latency_ms,
                "total_end_to_end_ms": total_end_to_end_ms
            }
        })

    async def _persist_disagreement_bg(self, dispute: Dict[str, Any], turn_id: str, speaker_id: str, fact_result: Dict[str, Any], interrupted: bool, interruption_text: Optional[str]):
        try:
            async with AsyncSessionLocal() as db:
                argument = Argument(
                    call_id=self.call_id,
                    topic=dispute["topic"],
                    start_ms=dispute["start_ms"],
                    end_ms=dispute["end_ms"],
                    participants=[dispute["speaker_a"], dispute["speaker_b"]],
                    claim_a=dispute["claim_a"],
                    claim_b=dispute["claim_b"]
                )
                db.add(argument)

                claim = Claim(
                    call_id=self.call_id,
                    speaker_id=speaker_id,
                    turn_id=turn_id,
                    text=f"{dispute['claim_a']} vs {dispute['claim_b']}",
                    topic=dispute["topic"],
                    status=fact_result["result"],
                    confidence=fact_result["confidence"]
                )
                db.add(claim)
                await db.flush()

                fact_check = FactCheck(
                    call_id=self.call_id,
                    claim_id=claim.id,
                    result=fact_result["result"],
                    confidence=fact_result["confidence"],
                    sources=fact_result.get("sources", []),
                    evidence=fact_result.get("evidence", ""),
                    interrupted=interrupted,
                    interruption_text=interruption_text
                )
                db.add(fact_check)
                await db.commit()
        except Exception as e:
            logger.error(f"[Orchestrator] Error persisting disagreement in background: {e}")

    async def close(self):
        for session in self.audio_sessions.values():
            await session.close()
        self.audio_sessions.clear()
        self.connected_clients.clear()

active_sessions: Dict[str, CallSessionOrchestrator] = {}

def get_call_orchestrator(call_id: str) -> CallSessionOrchestrator:
    if call_id not in active_sessions:
        active_sessions[call_id] = CallSessionOrchestrator(call_id)
    return active_sessions[call_id]
