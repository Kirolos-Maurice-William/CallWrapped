import re
import time
import uuid
import logging
from collections import OrderedDict
from typing import Dict, Any, List, Optional, Tuple

import discord
from bot.ai.tts import speaker
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.conflict_detector import conflict_detector
from bot.arbitration.verifier import arbitration_verifier
from bot.arbitration.claim_memory import ClaimMemory, StoredClaim
from bot.arbitration.stats import SessionStatsTracker
from bot.arbitration.fast_gate import fast_gate
from bot.arbitration.corroboration import independence_filter
from bot.events.models import VoiceEvent, LatencyBreakdown
from bot.events.publisher import publisher
from bot.config import config
from bot.audio.fusion import fuse_anger
import asyncio
from cachetools import TTLCache

logger = logging.getLogger("ArbitrationEngine")


def normalize_topic_key(entity: Optional[str] = None, topic: Optional[str] = None) -> str:
    """Normalizes entity/topic into a consistent cache key for per-topic cooldown tracking."""
    ent = (entity or "").strip().lower()
    top = (topic or "").strip().lower()
    if ent and top:
        return f"{top}:{ent}"
    return ent or top or "general_dispute"


class FifoSet:
    """Ordered set with strict FIFO eviction when capacity is reached."""

    def __init__(self, maxlen: int = 500):
        self._data: OrderedDict = OrderedDict()
        self.maxlen = maxlen

    def add(self, item: Any) -> None:
        if item in self._data:
            return
        if len(self._data) >= self.maxlen:
            evicted, _ = self._data.popitem(last=False)
            logger.debug(f"FifoSet capacity reached ({self.maxlen}); evicted oldest entry: {evicted}")
        self._data[item] = None

    def __contains__(self, item: Any) -> bool:
        return item in self._data

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()


class PendingOffer:
    """Represents an active, unconfirmed dispute verification offer awaiting user consent."""

    def __init__(
        self,
        offer_id: str,
        guild_id: int,
        speaker_a: str,
        claim_a: str,
        speaker_b: str,
        claim_b: str,
        entity: Optional[str],
        search_query: str,
        target_domains: List[str],
        prefetch_task: asyncio.Task,
        created_at: float,
        expires_at: float,
        correlation_id: str = "",
        voice_client: Optional[discord.VoiceClient] = None,
        text_channel: Optional[discord.TextChannel] = None,
        user_id: Optional[int] = None,
        stt_ms: int = 0,
        warm_tts_session: Optional[Any] = None,
        planner_ms: int = 0
    ):
        self.offer_id = offer_id
        self.guild_id = guild_id
        self.speaker_a = speaker_a
        self.claim_a = claim_a
        self.speaker_b = speaker_b
        self.claim_b = claim_b
        self.entity = entity
        self.search_query = search_query
        self.target_domains = target_domains
        self.prefetch_task = prefetch_task
        self.created_at = created_at
        self.expires_at = expires_at
        self.correlation_id = correlation_id
        self.voice_client = voice_client
        self.text_channel = text_channel
        self.user_id = user_id
        self.stt_ms = stt_ms
        self.warm_tts_session = warm_tts_session
        self.planner_ms = planner_ms
        self.is_resolved: bool = False
        self.is_confirmed: bool = False
        self.expiry_task: Optional[asyncio.Task] = None

    def cancel(self):
        self.is_resolved = True
        if self.expiry_task and not self.expiry_task.done():
            self.expiry_task.cancel()
        if self.prefetch_task and not self.prefetch_task.done():
            self.prefetch_task.cancel()
        if self.warm_tts_session:
            if hasattr(self.warm_tts_session, "close_sync"):
                self.warm_tts_session.close_sync()
            elif hasattr(self.warm_tts_session, "close"):
                try:
                    asyncio.create_task(self.warm_tts_session.close())
                except Exception:
                    pass
            self.warm_tts_session = None


def is_confirmation_utterance(text: str) -> bool:
    """
    Checks if an utterance matches two-stage referee confirmation keywords.
    Keywords: ["شوفها", "شوف", "اكد", "اتأكد", "تحقق", "check it", "check"]
    Strictly local string/regex normalization — ZERO LLM calls.
    """
    if not text:
        return False
    cleaned = text.lower()
    # Normalize Alefs: أ, إ, آ, ٱ -> ا
    cleaned = re.sub(r"[أإآٱ]", "ا", cleaned)
    # Normalize Ta Marbuta: ة -> ه
    cleaned = re.sub(r"ة", "ه", cleaned)
    # Strip Tashkeel & Tatweel
    cleaned = re.sub(r"[\u064B-\u0652\u0640]", "", cleaned)
    # Replace punctuation and non-word characters with spaces
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)

    tokens = set(cleaned.split())
    arabic_keywords = {"شوفها", "شوف", "اكد", "اتاكد", "تحقق"}
    if any(kw in tokens for kw in arabic_keywords):
        return True

    if "check it" in cleaned:
        return True
    if "check" in tokens:
        return True

    return False


class SessionState:
    """Tracks sliding dialogue turns, indexed claim memory, server statistics, and batched analytics."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.turns: List[Dict[str, Any]] = []
        self.claim_memory = ClaimMemory(capacity=30)
        self.verified_claims_count: int = 0
        self.disputed_claims_count: int = 0
        self.unverifiable_count: int = 0
        self.speaker_stats: Dict[str, Dict[str, int]] = {}
        self.is_arbitrating: bool = False
        self.pending_utterances: List[Dict[str, Any]] = []
        self.is_draining: bool = False
        self._stats_tracker = SessionStatsTracker(session_id=str(guild_id))
        self.analyzed_utterances: FifoSet = FifoSet(maxlen=500)
        self.analytics_buffer: List[Dict[str, Any]] = []
        self.last_analytics_flush: float = time.time()
        self._topic_counts: Dict[str, int] = {}
        self._flush_lock = asyncio.Lock()
        self.analytics_timer_task: Optional[asyncio.Task] = None
        self.pending_offer: Optional[PendingOffer] = None
        self.confirm_lock: asyncio.Lock = asyncio.Lock()
        self.last_offer_time: float = 0.0
        self.topic_cooldowns: TTLCache = TTLCache(maxsize=100, ttl=getattr(config, "DISPUTE_OFFER_COOLDOWN_SEC", 180.0))
        self.fact_check_mode: bool = False

    @property
    def stats_tracker(self) -> SessionStatsTracker:
        return self._stats_tracker

    @stats_tracker.setter
    def stats_tracker(self, val: SessionStatsTracker):
        self._stats_tracker = val

    @property
    def topic_counts(self) -> Dict[str, int]:
        return self._topic_counts

    @topic_counts.setter
    def topic_counts(self, val: Dict[str, int]):
        self._topic_counts = val

    def add_turn(self, speaker_name: str, text: str, user_id: int):
        self.turns.append({
            "speaker_name": speaker_name,
            "text": text,
            "user_id": str(user_id),
            "timestamp": time.time()
        })
        if len(self.turns) > 40:
            self.turns.pop(0)

        if speaker_name not in self.speaker_stats:
            self.speaker_stats[speaker_name] = {"turns": 0, "verified": 0, "refuted": 0}
        self.speaker_stats[speaker_name]["turns"] += 1

    def reset(self):
        """Resets all session statistics without blocking the event loop."""
        if self.analytics_buffer:
            dropped_count = len(self.analytics_buffer)
            logger.warning(
                f"⚠️ [SessionReset] Dropping {dropped_count} un-flushed analytics utterances on session reset"
            )
        if self.pending_utterances:
            dropped_queue = len(self.pending_utterances)
            logger.warning(
                f"⚠️ [SessionReset] Dropping {dropped_queue} queued arbitration utterances on session reset"
            )
        self.turns.clear()
        self.analytics_buffer.clear()
        self._topic_counts.clear()
        self.verified_claims_count = 0
        self.disputed_claims_count = 0
        self.unverifiable_count = 0
        self.speaker_stats.clear()
        self.is_arbitrating = False
        self.pending_utterances.clear()
        self.is_draining = False
        self._stats_tracker.reset()
        self.analyzed_utterances.clear()
        if hasattr(self, "claim_memory") and hasattr(self.claim_memory, "clear"):
            self.claim_memory.clear()
        if self.analytics_timer_task and not self.analytics_timer_task.done():
            self.analytics_timer_task.cancel()
        if self.pending_offer and not self.pending_offer.is_resolved:
            logger.warning(
                f"⚠️ [SessionReset] Dropping pending dispute check offer {self.pending_offer.offer_id} on session reset"
            )
            self.pending_offer.cancel()
        self.pending_offer = None
        self.last_offer_time = 0.0
        self.topic_cooldowns.clear()
        self.fact_check_mode = False

    def is_in_cooldown(self, topic_key: str, now: Optional[float] = None) -> Tuple[bool, int, str]:
        """
        Evaluates whether an offer is rate-limited:
        1. Global backstop cooldown (e.g. 30s) prevents back-to-back spam.
        2. Per-topic cooldown (180s) prevents repeating the same dispute.
        Returns (is_cooldown, remaining_seconds, reason).
        """
        now = now if now is not None else time.time()
        global_backstop = getattr(config, "DISPUTE_GLOBAL_BACKSTOP_SEC", 30.0)
        cooldown_sec = getattr(config, "DISPUTE_OFFER_COOLDOWN_SEC", 180.0)

        # If last_offer_time was elapsed or forced in the past >= cooldown_sec, clear expired topic cache
        if self.last_offer_time > 0 and (now - self.last_offer_time) >= cooldown_sec:
            self.topic_cooldowns.clear()

        # 1. Check global backstop
        if self.last_offer_time > 0 and (now - self.last_offer_time) < global_backstop:
            rem = int(global_backstop - (now - self.last_offer_time))
            return True, rem, "global_backstop"

        # 2. Check per-topic cooldown
        if topic_key in self.topic_cooldowns:
            offered_at = self.topic_cooldowns[topic_key]
            if (now - offered_at) < cooldown_sec:
                rem = int(cooldown_sec - (now - offered_at))
                return True, rem, f"topic:{topic_key}"

        return False, 0, "none"

    def record_offer(self, topic_key: str, now: Optional[float] = None):
        """Records offer timestamp globally and in the per-topic TTL cache."""
        now = now if now is not None else time.time()
        self.last_offer_time = now
        self.topic_cooldowns[topic_key] = now

    def arbitration_lease(self, engine: "ArbitrationEngine") -> "ArbitrationLease":
        return ArbitrationLease(engine, self.guild_id, self)


class ArbitrationLease:
    """
    Supervised lifecycle lease that guarantees reset of arbitration state
    and safe queue draining, even if synthesis, TTS, or network calls encounter
    an unhandled exception, cancellation, or watchdog timeout.
    """

    def __init__(self, engine: "ArbitrationEngine", guild_id: int, session: SessionState):
        self.engine = engine
        self.guild_id = guild_id
        self.session = session

    async def __aenter__(self):
        self.session.is_arbitrating = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.session.pending_offer = None
        finally:
            self.session.is_arbitrating = False
            try:
                await self.engine._drain_queue(self.guild_id, self.session)
            except Exception as e:
                logger.error(f"[ArbitrationLease] Error during queue drain: {e}", exc_info=True)
                self.session.is_draining = False
        return False


class ArbitrationEngine:
    """
    State Machine & Decision Pipeline:
    Raw Speech -> FastGate -> Claim Detection -> Claim Memory Indexing ->
    Scoped Conflict Detection -> Ground Truth Search (Source Policy) ->
    Template Intervention & Event Broadcast.
    Also fans out to Analytics path for per-speaker talk & anger tracking.
    """

    def __init__(self):
        self.sessions: Dict[int, SessionState] = {}
        self._in_flight_classifications: Dict[str, asyncio.Task] = {}

    def get_session(self, guild_id: int) -> SessionState:
        if guild_id not in self.sessions:
            self.sessions[guild_id] = SessionState(guild_id)
        return self.sessions[guild_id]

    async def _classify_utterance(self, raw_text: str) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        """
        Deduplicates in-flight classification so each utterance is classified by Groq EXACTLY ONCE,
        even though it feeds both the analytics path and the arbitrator path concurrently.
        """
        cache_key = raw_text.strip()
        if cache_key in self._in_flight_classifications:
            return await self._in_flight_classifications[cache_key]

        task = asyncio.create_task(claim_detector.check_claim(raw_text))
        self._in_flight_classifications[cache_key] = task
        try:
            return await task
        finally:
            self._in_flight_classifications.pop(cache_key, None)

    def _record_analytics(
        self,
        session: SessionState,
        guild_id: int,
        user_id: int,
        speaker_name: str,
        raw_text: str,
        speech_start: float,
        speech_end: float,
        correlation_id: str,
        audio_features: Optional[Any] = None
    ):
        """Records talk-time and appends to the session analytics buffer for batched topic/anger classification."""
        t_fanout_start = time.perf_counter()
        utterance_key = f"{user_id}_{speech_start}_{raw_text.strip()}"
        if getattr(config, "ANALYTICS_ENABLED", 1) != 0 and utterance_key not in session.analyzed_utterances:
            session.analyzed_utterances.add(utterance_key)

            spk_key = str(user_id)
            duration = max(0.0, speech_end - speech_start)
            if speech_start == 0.0 and speech_end == 0.0:
                speech_start = time.time()
                word_count = len(raw_text.split())
                duration = max(1.5, word_count * 0.4)
                speech_end = speech_start + duration

            spk_stats_before = session._stats_tracker.get_speaker(spk_key)
            prev_total = spk_stats_before.total_speak_seconds if spk_stats_before else 0.0

            stats = session._stats_tracker.record_utterance(
                speaker_id=spk_key,
                speech_start=speech_start,
                speech_end=speech_end,
                speaker_name=speaker_name
            )
            talk_delta_seconds = round(stats.total_speak_seconds - prev_total, 3)
            streak_seconds = round(stats.current_streak, 3)

            session.analytics_buffer.append({
                "timestamp": speech_end,
                "speaker_id": spk_key,
                "speaker_name": speaker_name,
                "user_id": user_id,
                "text": raw_text,
                "talk_delta_seconds": talk_delta_seconds,
                "streak_seconds": streak_seconds,
                "correlation_id": correlation_id,
                "audio_features": audio_features
            })

            # Check if buffer overflow, analytics window expired, or schedule timer flush
            if len(session.analytics_buffer) >= 20:
                asyncio.create_task(self.flush_analytics(guild_id, reason="buffer_overflow"))
            elif (time.time() - session.last_analytics_flush) >= config.ANALYTICS_WINDOW_SEC:
                asyncio.create_task(self.flush_analytics(guild_id, reason="window_timer"))
            elif session.analytics_timer_task is None or session.analytics_timer_task.done():
                session.analytics_timer_task = asyncio.create_task(
                    self._delayed_flush(guild_id, config.ANALYTICS_WINDOW_SEC)
                )

        fanout_overhead_ms = (time.perf_counter() - t_fanout_start) * 1000
        logger.info(f"⚡ [Fan-out Dispatcher] Batched analytics buffered in {fanout_overhead_ms:.3f}ms")

    async def _delayed_flush(self, guild_id: int, delay: float):
        """Asynchronously flushes analytics after the window delay without blocking."""
        try:
            await asyncio.sleep(delay)
            await self.flush_analytics(guild_id, reason="window_timer")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[ArbitrationEngine] Delayed flush error: {e}")

    async def flush_analytics(self, guild_id: int, reason: str = "flush"):
        """
        Batched Path (async): Flushes pending analytics buffer via a single Groq call.
        Updates topic stats, records anger episodes (90s debounce), and publishes events.
        On batch failure or 429: retries once, then KEEPS the buffer for the next window.
        """
        session = self.get_session(guild_id)
        if not session.analytics_buffer:
            return

        async with session._flush_lock:
            if not session.analytics_buffer:
                return
            buffer_to_process = list(session.analytics_buffer)
            try:
                results, tokens, latency_ms = await claim_detector.batch_classify(buffer_to_process)
            except Exception as e:
                logger.warning(
                    f"⚠️ [BatchAnalytics] Batch classification failed after retry: {e}. "
                    f"Keeping {len(buffer_to_process)} buffered items for next window."
                )
                return

            # On success: drain processed items and update timestamp
            session.analytics_buffer = session.analytics_buffer[len(buffer_to_process):]
            session.last_analytics_flush = time.time()

            self._apply_batch_results(session, guild_id, buffer_to_process, results, tokens, reason)

    def _apply_batch_results(
        self,
        session: SessionState,
        guild_id: int,
        buffer_to_process: list,
        results: list,
        tokens: dict,
        reason: str
    ):
        results_by_line = {r.get("line_number", i + 1): r for i, r in enumerate(results)}
        has_active_dispute = bool(session.pending_offer and not session.pending_offer.is_resolved)

        for idx, item in enumerate(buffer_to_process, 1):
            res = results_by_line.get(idx, {})
            topic = res.get("topic", "other")
            raw_anger = res.get("anger", "none")
            anger_evidence = res.get("anger_evidence") or ""

            # Deterministic late fusion (guarded by ACOUSTIC_FUSION_ENABLED)
            audio_feat = item.get("audio_features")
            if getattr(config, "ACOUSTIC_FUSION_ENABLED", 0):
                fusion = fuse_anger(
                    raw_anger=raw_anger,
                    audio_features=audio_feat,
                    has_active_dispute=has_active_dispute,
                    text=item["text"]
                )
                anger = fusion.final_anger
                boost_val = fusion.acoustic_boost
                gate_reason = fusion.gate_reason
            else:
                anger = raw_anger
                boost_val = 0.0
                gate_reason = "disabled_by_config"

            # 1. Update topic stats (avoid duplicate increment if publisher is hooked by main.py)
            if getattr(publisher.publish_sync_task, "__name__", "") != "_on_event_published":
                session._topic_counts[topic] = session._topic_counts.get(topic, 0) + 1

            # 2. Update anger with 90s debounce (record_anger ONLY when anger is mild or high)
            spk_key = str(item["user_id"])
            if anger and str(anger).lower() in ("mild", "high"):
                stats = session._stats_tracker.record_anger(
                    speaker_id=spk_key,
                    timestamp=item["timestamp"],
                    anger=anger,
                    anger_quote=anger_evidence,
                    speaker_name=item["speaker_name"]
                )
            else:
                stats = session._stats_tracker.get_or_create_speaker(spk_key, item["speaker_name"])

            logger.info(
                f"📈 [Batched Analytics Line] {item['speaker_name']}: topic={topic} | anger={anger} (raw={raw_anger}, boost={boost_val:.2f}, gate={gate_reason}) | "
                f"episodes={stats.angry_episodes} | quote='{anger_evidence}'"
            )

            # 3. Publish VoiceEvent(type="analytics_update")
            analytics_event = VoiceEvent(
                session_id=str(guild_id),
                correlation_id=item["correlation_id"],
                type="analytics_update",
                speaker_id=str(item["user_id"]),
                speaker_name=item["speaker_name"],
                text=item["text"],
                topic=topic,
                anger=anger,
                anger_evidence=anger_evidence,
                talk_delta_seconds=item["talk_delta_seconds"],
                streak_seconds=item["streak_seconds"],
                angry_episodes=stats.angry_episodes,
                payload={
                    "topic": topic,
                    "anger": anger,
                    "anger_evidence": anger_evidence,
                    "talk_delta_seconds": item["talk_delta_seconds"],
                    "streak_seconds": item["streak_seconds"],
                    "angry_episodes": stats.angry_episodes,
                    "total_speak_seconds": round(stats.total_speak_seconds, 3),
                    "utterance_count": stats.utterance_count,
                    "first_anger_quote": stats.first_anger_quote,
                    "tokens": tokens,
                    "batch_reason": reason,
                    "classification": {
                        "topic": topic,
                        "anger": anger,
                        "anger_evidence": anger_evidence
                    }
                }
            )
            publisher.publish_sync_task(analytics_event)

    async def process_utterance(
        self,
        guild_id: int,
        user_id: int,
        speaker_name: str,
        raw_text: str,
        stt_ms: int,
        voice_client: Optional[discord.VoiceClient],
        text_channel: Optional[discord.TextChannel],
        mode: str = "referee",
        speech_start: float = 0.0,
        speech_end: float = 0.0,
        audio_features: Optional[Any] = None
    ):
        t_start = time.monotonic()
        correlation_id = f"arb_{uuid.uuid4().hex[:8]}"

        session = self.get_session(guild_id)
        session.add_turn(speaker_name, raw_text, user_id)

        features_dict = None
        if audio_features:
            from dataclasses import is_dataclass, asdict
            features_dict = asdict(audio_features) if is_dataclass(audio_features) else (audio_features if isinstance(audio_features, dict) else None)

        payload_dict = {"mode": mode}
        if features_dict:
            payload_dict["audio_features"] = features_dict

        # 1. Publish Transcript VoiceEvent
        turn_event = VoiceEvent(
            correlation_id=correlation_id,
            type="transcript",
            speaker_id=str(user_id),
            speaker_name=speaker_name,
            text=raw_text,
            timings={
                "audio_finished_at": round(t_start - (stt_ms / 1000.0), 3),
                "stt_final_at": round(t_start, 3)
            },
            latency=LatencyBreakdown(stt_ms=stt_ms),
            payload=payload_dict,
            audio_features=features_dict
        )
        publisher.publish_sync_task(turn_event)

        # 2. Mirror transcript to Discord text channel if available
        if text_channel:
            try:
                await text_channel.send(f"🗣️ **{speaker_name}**: {raw_text}")
            except Exception as e:
                logger.debug(f"Could not post to text channel: {e}")

        # Check for confirmation utterance if an offer is currently pending
        if session.pending_offer and not session.pending_offer.is_resolved:
            if is_confirmation_utterance(raw_text):
                offer = session.pending_offer
                offer.is_resolved = True
                if offer.expiry_task and not offer.expiry_task.done():
                    offer.expiry_task.cancel()
                logger.info(
                    f"🎯 [Voice Confirmation] Detected confirmation keyword from {speaker_name}: '{raw_text}'. "
                    f"Confirming offer {offer.offer_id}."
                )
                asyncio.create_task(
                    self.confirm_dispute_offer(
                        guild_id=guild_id,
                        confirmation_end_time=speech_end if speech_end > 0 else time.time(),
                        confirmed_by=speaker_name,
                        voice_client=voice_client,
                        text_channel=text_channel,
                        target_offer=offer
                    )
                )

        # Echo Mode (Diagnostic testing only)
        if mode == "echo":
            await speaker.speak(voice_client, f"{speaker_name} said: {raw_text}")
            return

        # Assistant Mode
        if mode == "assistant":
            if any(k in raw_text.lower() for k in ["hey bot", "referee", "يا بوت", "يا حكم"]):
                await speaker.speak(voice_client, f"I hear you {speaker_name}. Referee mode is active and listening.")
            return

        # 3. Mode is Referee: Proceed with Filtered Pipeline
        if session.is_arbitrating:
            if len(session.pending_utterances) >= 3:
                dropped = session.pending_utterances.pop(0)
                logger.warning(
                    f"⚠️ [Queue Overflow] Dropped oldest queued utterance from {dropped['speaker_name']}: '{dropped['raw_text']}'"
                )
            session.pending_utterances.append({
                "user_id": user_id,
                "speaker_name": speaker_name,
                "raw_text": raw_text,
                "stt_ms": stt_ms,
                "voice_client": voice_client,
                "text_channel": text_channel,
                "mode": mode,
                "t_start": t_start,
                "correlation_id": correlation_id,
                "speech_start": speech_start,
                "speech_end": speech_end,
                "audio_features": audio_features,
            })
            logger.info(
                f"📥 [Queued Utterance] Session {guild_id} is arbitrating. "
                f"Queued utterance from {speaker_name} (queue size: {len(session.pending_utterances)}/3)"
            )
            return

        # BATCHED ANALYTICS PATH: Track talk-time & buffer for batched topic/anger reader
        self._record_analytics(
            session=session,
            guild_id=guild_id,
            user_id=user_id,
            speaker_name=speaker_name,
            raw_text=raw_text,
            speech_start=speech_start,
            speech_end=speech_end,
            correlation_id=correlation_id,
            audio_features=audio_features
        )

        await self._run_pipeline(
            guild_id=guild_id,
            session=session,
            user_id=user_id,
            speaker_name=speaker_name,
            raw_text=raw_text,
            stt_ms=stt_ms,
            voice_client=voice_client,
            text_channel=text_channel,
            mode=mode,
            t_start=t_start,
            correlation_id=correlation_id
        )

    async def _run_pipeline(
        self,
        guild_id: int,
        session: SessionState,
        user_id: int,
        speaker_name: str,
        raw_text: str,
        stt_ms: int,
        voice_client: Optional[discord.VoiceClient],
        text_channel: Optional[discord.TextChannel],
        mode: str,
        t_start: float,
        correlation_id: str
    ):

        # Step A: FastGate deterministic filter
        is_candidate, reason = fast_gate.is_candidate(raw_text)
        if not is_candidate:
            logger.info(
                f"⚡ [FastGate Skip] Skipped arbitration for {speaker_name} ({reason}): '{raw_text}'"
            )
            return

        # Step B: Groq Claim Detector
        t_claim_start = time.monotonic()
        is_claim, claim_data, claim_ms = await self._classify_utterance(raw_text)
        t_claim_end = time.monotonic()

        if not is_claim or not claim_data:
            return  # Filtered out as casual chat

        entity = claim_data.get("entity")
        topic = claim_data.get("topic")
        metric = claim_data.get("metric")
        claim_stmt = claim_data.get("claim", raw_text)

        # Step B: Log Claim in Event stream
        claim_event = VoiceEvent(
            correlation_id=correlation_id,
            type="claim",
            speaker_id=str(user_id),
            speaker_name=speaker_name,
            text=raw_text,
            timings={
                "stt_final_at": round(t_start, 3),
                "claim_done_at": round(t_claim_end, 3)
            },
            latency=LatencyBreakdown(stt_ms=stt_ms, llm_ms=claim_ms),
            payload={
                "claim": claim_stmt,
                "entity": entity,
                "topic": topic,
                "metric": metric
            }
        )
        publisher.publish_sync_task(claim_event)

        # Step C: Scoped Conflict Detection via ClaimMemory
        prior_claim: Optional[StoredClaim] = session.claim_memory.find_relevant_prior_claim(
            new_speaker_id=str(user_id),
            entity=entity,
            topic=topic,
            metric=metric,
            raw_text=raw_text,
            max_age_seconds=180.0
        )

        # Record this claim in memory for future comparisons
        session.claim_memory.add_claim(
            claim_id=claim_event.event_id,
            speaker_name=speaker_name,
            speaker_id=str(user_id),
            raw_text=raw_text,
            claim_text=claim_stmt,
            entity=entity,
            topic=topic,
            metric=metric
        )

        if not prior_claim:
            # No conflicting statement on same topic/entity from another speaker yet
            return

        # Extract voice channel member display names
        channel_members: List[str] = []
        if voice_client and hasattr(voice_client, "channel") and voice_client.channel and hasattr(voice_client.channel, "members"):
            channel_members = [getattr(m, "display_name", str(m)) for m in voice_client.channel.members]

        # Fast-gate private channel member check before conflict detection
        from bot.arbitration.verifier import is_private_claim
        is_member_private, priv_reason = is_private_claim(entity, channel_members=channel_members, claim_text=claim_stmt)
        if is_member_private:
            logger.info(
                f"🚫 [Private Entity Refusal] Skipping lookup for voice channel member / private entity "
                f"'{entity}': Private claim — no lookup performed ({priv_reason})"
            )
            private_event = VoiceEvent(
                session_id=str(guild_id),
                correlation_id=correlation_id,
                type="intervention",
                speaker_id=str(user_id),
                speaker_name=speaker_name,
                text=raw_text,
                payload={
                    "status": "REFUSED_PRIVATE",
                    "label": "Private claim — no lookup performed",
                    "correct_fact": "Private claim — no lookup performed",
                    "entity_type": "PRIVATE",
                    "entity_name": entity,
                    "speaker_a": prior_claim.speaker_name,
                    "claim_a": prior_claim.claim_text,
                    "speaker_b": speaker_name,
                    "claim_b": claim_stmt,
                    "why_i_spoke": [
                        "Private entity detected (bare first name / call participant)",
                        "Web lookup refused: Private claim — no lookup performed"
                    ]
                }
            )
            publisher.publish_sync_task(private_event)
            return

        # Step D: Groq Conflict Analyzer between the two relevant claims
        t_conflict_start = time.monotonic()
        try:
            is_conflict, conflict_data, conflict_ms = await conflict_detector.detect_conflict(
                speaker_a=prior_claim.speaker_name,
                claim_a=prior_claim.claim_text,
                speaker_b=speaker_name,
                claim_b=claim_stmt,
                channel_members=channel_members
            )
        except TypeError:
            is_conflict, conflict_data, conflict_ms = await conflict_detector.detect_conflict(
                speaker_a=prior_claim.speaker_name,
                claim_a=prior_claim.claim_text,
                speaker_b=speaker_name,
                claim_b=claim_stmt
            )
        t_conflict_end = time.monotonic()

        if conflict_data and conflict_data.get("entity_type") == "PRIVATE":
            logger.info(
                f"🚫 [Private Entity Refusal] Skipping lookup for private entity "
                f"'{conflict_data.get('entity_name')}': Private claim — no lookup performed"
            )
            private_event = VoiceEvent(
                session_id=str(guild_id),
                correlation_id=correlation_id,
                type="intervention",
                speaker_id=str(user_id),
                speaker_name=speaker_name,
                text=raw_text,
                payload={
                    "status": "REFUSED_PRIVATE",
                    "label": "Private claim — no lookup performed",
                    "correct_fact": "Private claim — no lookup performed",
                    "entity_type": "PRIVATE",
                    "entity_name": conflict_data.get("entity_name"),
                    "speaker_a": prior_claim.speaker_name,
                    "claim_a": prior_claim.claim_text,
                    "speaker_b": speaker_name,
                    "claim_b": claim_stmt,
                    "why_i_spoke": [
                        "Private entity detected (bare first name / call participant)",
                        "Web lookup refused: Private claim — no lookup performed"
                    ]
                }
            )
            publisher.publish_sync_task(private_event)
            return

        if not is_conflict or not conflict_data:
            return

        search_query = conflict_data.get("search_query")
        target_domains = conflict_data.get("target_domains", [])
        if not search_query:
            return

        # Step E: Two-Stage Referee Flow: Detect and OFFER (Zero Unsolicited Speech)
        now_check = time.time()
        topic_key = normalize_topic_key(
            entity=entity or conflict_data.get("entity_name"),
            topic=topic or conflict_data.get("conflict_type")
        )
        is_cooldown, remaining, reason = session.is_in_cooldown(topic_key, now_check)
        if is_cooldown:
            logger.info(f"DISPUTE_SUPPRESSED: cooldown active (remaining: {remaining}s)")
            return

        # Query Planner: Step-Back abstraction + query variants (runs before offer is posted)
        search_plan = None
        query_variants = [search_query]
        t_plan_start = time.time()
        try:
            from bot.arbitration.query_planner import query_planner
            search_plan = await query_planner.plan_search(
                entity=entity or conflict_data.get("entity_name"),
                dimension=conflict_data.get("disputed_aspect") or conflict_data.get("conflict_type"),
                speaker_a=prior_claim.speaker_name,
                claim_a=prior_claim.claim_text,
                speaker_b=speaker_name,
                claim_b=claim_stmt,
                fallback_query=search_query,
                target_domains=target_domains
            )
            if search_plan and search_plan.query_variants:
                query_variants = search_plan.query_variants
        except Exception as e:
            logger.warning(f"⚠️ [QueryPlanner] Planning failed, falling back to single query: {e}")
            query_variants = [search_query]
        t_plan_end = time.time()
        planner_ms = int((t_plan_end - t_plan_start) * 1000)

        # Stamp offered_at and created_at AFTER planner completes
        now = time.time()

        # If a new offer triggers while an older one is pending (unconfirmed), replace older one with warning
        if session.pending_offer and not session.pending_offer.is_resolved:
            logger.warning(
                f"⚠️ Replacing older unconfirmed pending offer ({session.pending_offer.offer_id}) with new dispute offer"
            )
            session.pending_offer.cancel()

        session.record_offer(topic_key, now)

        # Pre-fetch: fire fan-out search in background immediately (do NOT wait before offering)
        async def _dispatch_prefetch():
            try:
                return await arbitration_verifier.search_evidence(
                    search_query,
                    target_domains=target_domains,
                    query_variants=query_variants,
                    claim_context=f"{prior_claim.claim_text} vs {claim_stmt}",
                    entity=entity or (search_plan.subject if search_plan else None)
                )
            except TypeError as te:
                if "unexpected keyword argument" in str(te):
                    return await arbitration_verifier.search_evidence(
                        search_query,
                        target_domains=target_domains
                    )
                raise

        prefetch_task = asyncio.create_task(_dispatch_prefetch())

        # Pre-warm: establish and hold warm Edge-TTS connection in background alongside search prefetch (35s timeout)
        warm_tts = speaker.create_warm_session(timeout_seconds=35.0)

        offer_id = f"off_{uuid.uuid4().hex[:8]}"
        offer = PendingOffer(
            offer_id=offer_id,
            guild_id=guild_id,
            speaker_a=prior_claim.speaker_name,
            claim_a=prior_claim.claim_text,
            speaker_b=speaker_name,
            claim_b=claim_stmt,
            entity=entity,
            search_query=search_query,
            target_domains=target_domains,
            prefetch_task=prefetch_task,
            created_at=now,
            expires_at=now + 30.0,
            correlation_id=correlation_id,
            voice_client=voice_client,
            text_channel=text_channel,
            user_id=user_id,
            stt_ms=stt_ms,
            warm_tts_session=warm_tts,
            planner_ms=planner_ms
        )
        offer.query_variants = query_variants
        offer.search_plan = search_plan
        session.pending_offer = offer

        # Post Arabic offer message to Discord text channel
        offer_text = "🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟ قول «شوفها» أو اكتب !check"
        if text_channel:
            try:
                await text_channel.send(offer_text)
            except Exception as e:
                logger.debug(f"Could not post dispute offer to text channel: {e}")

        # Publish VoiceEvent(type="dispute_check_offered")
        offer_event = VoiceEvent(
            session_id=str(guild_id),
            correlation_id=correlation_id,
            type="dispute_check_offered",
            speaker_id=str(user_id),
            speaker_name=speaker_name,
            text=offer_text,
            timings={
                "stt_final_at": round(t_start, 3),
                "claim_done_at": round(t_claim_end, 3),
                "conflict_done_at": round(t_conflict_end, 3),
                "planner_done_at": round(t_plan_end, 3),
                "offered_at": round(now, 3)
            },
            latency=LatencyBreakdown(
                stt_ms=stt_ms,
                llm_ms=claim_ms + conflict_ms + planner_ms,
                planner_ms=planner_ms
            ),
            payload={
                "offer_id": offer_id,
                "speaker_a": prior_claim.speaker_name,
                "claim_a": prior_claim.claim_text,
                "speaker_b": speaker_name,
                "claim_b": claim_stmt,
                "entity": entity,
                "search_query": search_query,
                "query_variants": query_variants,
                "ambiguity_type": search_plan.ambiguity_type.value if search_plan else "none",
                "planner_ms": planner_ms,
                "claim_ms": claim_ms,
                "conflict_ms": conflict_ms,
                "expires_in_seconds": 30.0,
                "expires_at": round(now + 30.0, 3)
            }
        )
        publisher.publish_sync_task(offer_event)
        logger.info(
            f"📣 [Dispute Offer Created] ({offer_id}) Posted offer for '{entity or 'topic'}'. "
            f"Search prefetch started in background. Awaiting confirmation (30s timeout)."
        )

        expiry_sec = getattr(config, "DISPUTE_OFFER_EXPIRY_SEC", 30.0)
        offer.expiry_task = asyncio.create_task(
            self._offer_expiry_timer(guild_id=guild_id, offer_id=offer_id, timeout_seconds=expiry_sec)
        )

    async def _offer_expiry_timer(self, guild_id: int, offer_id: str, timeout_seconds: float = 30.0):
        try:
            await asyncio.sleep(timeout_seconds)
            await self._expire_pending_offer(guild_id, offer_id)
        except asyncio.CancelledError:
            pass

    async def _expire_pending_offer(self, guild_id: int, offer_id: str):
        session = self.get_session(guild_id)
        offer = session.pending_offer
        if not offer or offer.offer_id != offer_id or offer.is_resolved:
            return

        offer.cancel()
        session.pending_offer = None

        logger.info(f"ABSTAIN: offered_not_confirmed (offer_id: {offer_id})")

        expired_event = VoiceEvent(
            session_id=str(guild_id),
            correlation_id=offer.correlation_id,
            type="dispute_check_expired",
            speaker_name="Referee",
            text="Dispute check offer expired without confirmation",
            payload={
                "offer_id": offer_id,
                "speaker_a": offer.speaker_a,
                "claim_a": offer.claim_a,
                "speaker_b": offer.speaker_b,
                "claim_b": offer.claim_b,
                "entity": offer.entity,
                "reason": "offered_not_confirmed"
            }
        )
        publisher.publish_sync_task(expired_event)

    async def _handle_unverifiable_dispute(
        self,
        guild_id: int,
        session: SessionState,
        offer: PendingOffer,
        confirmed_by: str,
        vc: Any,
        tc: Any,
        t_confirm_start: float,
        search_ms: int = 0,
        synth_ms: int = 0
    ) -> None:
        session.unverifiable_count += 1
        logger.info(f"ABSTAIN: unverifiable_dispute (offer_id: {offer.offer_id})")
        fallback_text = "تعذر التحقق من المعلومة من مصادر موثوقة."

        # Publish dispute_check_completed BEFORE TTS speak (DATA-05)
        completed_event = VoiceEvent(
            session_id=str(guild_id),
            correlation_id=offer.correlation_id,
            type="dispute_check_completed",
            speaker_id=str(offer.user_id or 0),
            speaker_name=offer.speaker_b,
            confirmed_by=confirmed_by,
            text=fallback_text,
            timings={
                "search_done_at": round(t_confirm_start, 3),
                "synth_done_at": round(time.monotonic(), 3),
            },
            latency=LatencyBreakdown(
                stt_ms=offer.stt_ms,
                llm_ms=synth_ms,
                planner_ms=getattr(offer, "planner_ms", 0),
                search_ms=search_ms,
                total_ms=int((time.monotonic() - t_confirm_start) * 1000)
            ),
            payload={
                "offer_id": offer.offer_id,
                "status": "UNVERIFIABLE",
                "confirmed_by": confirmed_by,
                "planner_ms": getattr(offer, "planner_ms", 0),
                "correct_fact": fallback_text,
                "speaker_a": offer.speaker_a,
                "claim_a": offer.claim_a,
                "speaker_b": offer.speaker_b,
                "claim_b": offer.claim_b,
                "winner": None,
                "loser": None,
                "source_url": None,
                "source_title": None,
                "spoken_intervention": fallback_text,
                "why_i_spoke": [
                    "Factual dispute detected and offer issued",
                    f"Explicit confirmation received from '{confirmed_by}'",
                    "Authoritative sources insufficient or claim unverifiable",
                    "Polite abstention fallback delivered"
                ]
            }
        )
        publisher.publish_sync_task(completed_event)

        t_tts_start = time.monotonic()
        tts_ms = await speaker.speak(vc, fallback_text)
        t_tts_end = time.monotonic()

        if tc:
            try:
                embed = discord.Embed(
                    title="⚖️ Verified Factual Arbitration",
                    description=f"⚠️ **{fallback_text}**\n\n• **{offer.speaker_a}:** {offer.claim_a}\n• **{offer.speaker_b}:** {offer.claim_b}",
                    color=config.EMBED_COLOR_VERDICT
                )
                embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
                await tc.send(embed=embed)
            except Exception as e:
                logger.debug(f"Could not send unverifiable embed to text channel: {e}")

    async def confirm_dispute_offer(
        self,
        guild_id: int,
        confirmation_end_time: float,
        confirmed_by: str,
        voice_client: Optional[discord.VoiceClient] = None,
        text_channel: Optional[discord.TextChannel] = None,
        target_offer: Optional[PendingOffer] = None
    ):
        """
        Executes confirmation of a pending dispute offer:
        1. Awaits pre-fetched search (cap wait at 5s)
        2. Synthesizes verdict via Groq verifier + template
        3. Speaks hedged verdict via TTS (ONLY path that speaks)
        4. Logs headline metric: T_perceived = t_first_audio - t_confirm_end
        5. Publishes dispute_check_completed VoiceEvent and sends Discord embed
        """
        session = self.get_session(guild_id)
        offer = target_offer or session.pending_offer
        if not offer:
            logger.debug(f"[DisputeConfirm] No active pending offer for guild {guild_id}")
            return "already confirmed"

        async with session.confirm_lock:
            if getattr(offer, "is_confirmed", False) or (target_offer is None and offer.is_resolved):
                logger.debug(f"[DisputeConfirm] Offer {offer.offer_id} already confirmed or resolved")
                return "already confirmed"
            offer.is_confirmed = True
            offer.is_resolved = True

        if offer.expiry_task and not offer.expiry_task.done():
            offer.expiry_task.cancel()

        vc = voice_client or offer.voice_client
        tc = text_channel or offer.text_channel

        t_confirm_start = time.monotonic()
        timeout_sec = getattr(config, "DISPUTE_CONFIRM_TOTAL_TIMEOUT_SEC", 25.0)
        try:
            async with asyncio.timeout(timeout_sec):
                async with ArbitrationLease(self, guild_id, session):
                    await self._execute_confirmation_cycle(
                        guild_id=guild_id,
                        session=session,
                        offer=offer,
                        confirmation_end_time=confirmation_end_time,
                        confirmed_by=confirmed_by,
                        vc=vc,
                        tc=tc,
                        t_confirm_start=t_confirm_start
                    )
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(
                f"⚠️ [DisputeConfirm Watchdog] Dispute confirmation timed out after {timeout_sec}s for offer {offer.offer_id}"
            )
        except Exception as err:
            logger.error(f"Dispute confirmation cycle failed: {err}", exc_info=True)

    async def _execute_confirmation_cycle(
        self,
        guild_id: int,
        session: SessionState,
        offer: PendingOffer,
        confirmation_end_time: float,
        confirmed_by: str,
        vc: Any,
        tc: Any,
        t_confirm_start: float
    ):
        # Step A: Await pre-fetched search (cap at 8.0s for network jitter tolerance)
            sources = []
            search_ms = 0
            confirm_timeout = getattr(config, "DISPUTE_CONFIRM_SEARCH_TIMEOUT_SEC", 8.0)
            try:
                sources, search_ms = await asyncio.wait_for(offer.prefetch_task, timeout=confirm_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ [DisputeConfirm] Pre-fetched search timed out after {confirm_timeout}s for offer {offer.offer_id}")
            except Exception as e:
                logger.warning(f"⚠️ [DisputeConfirm] Pre-fetched search failed: {e}")

            if not sources:
                logger.warning(f"⚠️ [DisputeConfirm] No search sources found for query: '{offer.search_query}'")
                await self._handle_unverifiable_dispute(
                    guild_id=guild_id,
                    session=session,
                    offer=offer,
                    confirmed_by=confirmed_by,
                    vc=vc,
                    tc=tc,
                    t_confirm_start=t_confirm_start,
                    search_ms=search_ms,
                    synth_ms=0
                )
                return

            # Step A½: Corroboration — filter syndicated/co-dependent sources
            corr = independence_filter(sources, target_domains=getattr(offer, "target_domains", None))
            if corr.verdict_tier == "abstain":
                logger.warning(
                    f"⚠️ [DisputeConfirm] Corroboration: 0 independent sources "
                    f"(before filter: {corr.total_before_filter})"
                )
                await self._handle_unverifiable_dispute(
                    guild_id=guild_id,
                    session=session,
                    offer=offer,
                    confirmed_by=confirmed_by,
                    vc=vc,
                    tc=tc,
                    t_confirm_start=t_confirm_start,
                    search_ms=search_ms,
                    synth_ms=0
                )
                return
            sources = corr.independent_sources

            # Step B: Synthesize via Groq verifier
            t_synth_start = time.monotonic()
            assessment, search_ms, synth_ms, sources = await arbitration_verifier.synthesize_verdict(
                speaker_a=offer.speaker_a,
                claim_a=offer.claim_a,
                speaker_b=offer.speaker_b,
                claim_b=offer.claim_b,
                sources=sources,
                search_ms=search_ms
            )
            t_synth_end = time.monotonic()

            if not assessment or assessment.get("status") == "UNVERIFIABLE":
                await self._handle_unverifiable_dispute(
                    guild_id=guild_id,
                    session=session,
                    offer=offer,
                    confirmed_by=confirmed_by,
                    vc=vc,
                    tc=tc,
                    t_confirm_start=t_confirm_start,
                    search_ms=search_ms,
                    synth_ms=synth_ms
                )
                return

            confidence = assessment.get("confidence", 95)
            spoken_text = assessment.get("spoken_intervention", "")
            source_url = assessment.get("selected_source_url", "")
            source_title = assessment.get("selected_source_title", "Official Source")
            evidence_strength = assessment.get("evidence_strength", "HIGH")
            spk_a_status = assessment.get("speaker_a_status", "UNKNOWN")
            spk_b_status = assessment.get("speaker_b_status", "UNKNOWN")

            # Corroboration metadata for event payload
            assessment["corroboration"] = {
                "independent_count": corr.independent_count,
                "total_before_filter": corr.total_before_filter,
                "has_official_source": corr.has_official_source,
                "verdict_tier": corr.verdict_tier,
                "clusters_merged": len(corr.duplicate_clusters),
            }

            # Update speaker stats
            if offer.speaker_a in session.speaker_stats:
                if spk_a_status == "SUPPORTED":
                    session.speaker_stats[offer.speaker_a]["verified"] += 1
                elif spk_a_status == "CONTRADICTED":
                    session.speaker_stats[offer.speaker_a]["refuted"] += 1

            if offer.speaker_b in session.speaker_stats:
                if spk_b_status == "SUPPORTED":
                    session.speaker_stats[offer.speaker_b]["verified"] += 1
                elif spk_b_status == "CONTRADICTED":
                    session.speaker_stats[offer.speaker_b]["refuted"] += 1

            session.disputed_claims_count += 1
            session.verified_claims_count += 1

            # Step C: Speak verdict via TTS (the ONLY path that speaks)
            fact_clause = assessment.get("fact_clause") or assessment.get("correct_fact") or spoken_text
            hedge_clause = assessment.get("hedge_clause") or ""

            # Corroboration: hedged_single → low-confidence hedge override
            if corr.verdict_tier == "hedged_single":
                from bot.arbitration.verifier import determine_verdict_language
                use_arabic = determine_verdict_language(offer.claim_a, offer.claim_b)
                if use_arabic:
                    from bot.arbitration.corroboration import CorroborationResult
                    hedge_clause = CorroborationResult.HEDGED_SINGLE_AR
                else:
                    hedge_clause = "This info came from a single source — take it with a grain of salt. Link on the dashboard."
                spoken_text = f"{fact_clause} {hedge_clause}"
                assessment["spoken_intervention"] = spoken_text
                assessment["hedge_clause"] = hedge_clause

            # Step C1: Publish VoiceEvent(type="dispute_check_completed") BEFORE TTS speak (DATA-05)
            completed_event = VoiceEvent(
                session_id=str(guild_id),
                correlation_id=offer.correlation_id,
                type="dispute_check_completed",
                speaker_id=str(offer.user_id or 0),
                speaker_name=offer.speaker_b,
                confirmed_by=confirmed_by,
                text=spoken_text,
                timings={
                    "search_done_at": round(t_synth_start, 3),
                    "synth_done_at": round(t_synth_end, 3),
                },
                latency=LatencyBreakdown(
                    stt_ms=offer.stt_ms,
                    llm_ms=synth_ms,
                    planner_ms=getattr(offer, "planner_ms", 0),
                    search_ms=search_ms,
                    total_ms=int((t_synth_end - t_confirm_start) * 1000)
                ),
                payload={
                    "offer_id": offer.offer_id,
                    "confirmed_by": confirmed_by,
                    "planner_ms": getattr(offer, "planner_ms", 0),
                    "status": assessment.get("status", "CONTRADICTED"),
                    "confidence": confidence,
                    "evidence_strength": evidence_strength,
                    "correct_fact": fact_clause,
                    "speaker_a": offer.speaker_a,
                    "claim_a": offer.claim_a,
                    "speaker_a_status": spk_a_status,
                    "speaker_b": offer.speaker_b,
                    "claim_b": offer.claim_b,
                    "speaker_b_status": spk_b_status,
                    "winner": offer.speaker_a if spk_a_status == "SUPPORTED" else (offer.speaker_b if spk_b_status == "SUPPORTED" else None),
                    "loser": offer.speaker_a if spk_a_status == "CONTRADICTED" else (offer.speaker_b if spk_b_status == "CONTRADICTED" else None),
                    "source_url": source_url,
                    "source_title": source_title,
                    "spoken_intervention": spoken_text,
                    "corroboration": assessment.get("corroboration"),
                    "why_i_spoke": [
                        "Factual dispute detected and offer issued",
                        f"Explicit confirmation received from '{confirmed_by}'",
                        f"Pre-fetched evidence verified ({search_ms}ms search, {synth_ms}ms Groq)",
                        f"Corroboration: {corr.independent_count}/{corr.total_before_filter} independent sources (tier={corr.verdict_tier})",
                        f"Authoritative source located: {source_title}",
                        "Spoken hedged verdict delivered"
                    ]
                }
            )
            publisher.publish_sync_task(completed_event)

            # Step C2: Speak verdict via TTS (the ONLY path that speaks)
            warm_session = getattr(offer, "warm_tts_session", None)
            handshake_ms = 0
            if warm_session and warm_session.is_valid():
                logger.info("🔥 [TTS Reused] Reusing warm TTS session from offer time (no new handshake)")
                warm_session.reused = True
                handshake_ms = 0
            else:
                logger.info("⚠️ [TTS Rebuild] Warm session expired or absent; rebuilding connection on confirm")
                handshake_ms = getattr(warm_session, "handshake_ms", 0) if warm_session else 0
                warm_session = None

            t_tts_start = time.monotonic()
            tts_ms = await speaker.speak(vc, spoken_text)
            t_tts_end = time.monotonic()

            # Step D: Headline metric: T_perceived = t_first_audio - t_confirm_end
            clause1_ttfb_ms = getattr(speaker, "last_clause1_ttfb_ms", 0) or getattr(speaker, "last_ttfb_ms", 0) or 0
            ttfb_sec = clause1_ttfb_ms / 1000.0
            clause2_wait_ms = getattr(speaker, "last_clause2_wait_ms", 0) or 0
            if hasattr(speaker, "last_handshake_ms") and speaker.last_handshake_ms is not None:
                handshake_ms = speaker.last_handshake_ms

            if confirmation_end_time > 1e8:
                t_first_audio = getattr(speaker, "last_audio_start_time", 0.0) or (time.time() - (t_tts_end - t_tts_start) + ttfb_sec)
                t_perceived_sec = max(0.0, t_first_audio - confirmation_end_time)
            else:
                t_first_audio = t_tts_start + ttfb_sec
                t_perceived_sec = max(0.0, t_first_audio - confirmation_end_time)
            t_perceived_ms = int(t_perceived_sec * 1000)

            logger.info(
                f"⏱️ [Headline Metric] T_perceived = {t_perceived_ms}ms (target: <1800ms, "
                f"handshake_ms={handshake_ms}ms, clause1_ttfb_ms={clause1_ttfb_ms}ms, "
                f"clause2_wait_ms={clause2_wait_ms}ms, prefetch search_ms={search_ms}ms, synth_ms={synth_ms}ms)"
            )

            # Step E: Post Discord Embed
            if tc:
                try:
                    comparison_details = assessment.get("comparison_details", "")
                    comp_text = f"💡 **Details:** {comparison_details}\n\n" if comparison_details else ""
                    embed = discord.Embed(
                        title="⚖️ Verified Factual Arbitration",
                        description=(
                            f"📢 **{fact_clause}**\n\n"
                            f"{comp_text}"
                            f"• **{offer.speaker_a}:** `{spk_a_status}`\n"
                            f"• **{offer.speaker_b}:** `{spk_b_status}`\n\n"
                            f"🎯 **Evidence Strength:** `{evidence_strength}` ({confidence}%)\n"
                            f"🔗 **Source:** [{source_title}]({source_url})\n\n"
                            f"⚡ *Latency: Pre-fetch {search_ms}ms | LPU {synth_ms}ms | TTS {tts_ms}ms | T_perceived {t_perceived_ms}ms*"
                        ),
                        color=config.EMBED_COLOR_VERDICT
                    )
                    embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
                    await tc.send(embed=embed)
                except Exception as e:
                    logger.debug(f"Could not send embed to text channel: {e}")

    async def _drain_queue(self, guild_id: int, session: SessionState):
        """Drains pending queued utterances through the normal pipeline after arbitration ends."""
        if session.is_draining:
            return
        session.is_draining = True
        try:
            while session.pending_utterances and not session.is_arbitrating:
                queued = session.pending_utterances.pop(0)
                logger.info(
                    f"📤 [Draining Queue] Processing queued utterance from {queued['speaker_name']}: '{queued['raw_text']}'"
                )
                try:
                    # 1. Analytics path: record talk time, streak, and buffer for topic/anger classification
                    self._record_analytics(
                        session=session,
                        guild_id=guild_id,
                        user_id=queued["user_id"],
                        speaker_name=queued["speaker_name"],
                        raw_text=queued["raw_text"],
                        speech_start=queued.get("speech_start", 0.0),
                        speech_end=queued.get("speech_end", 0.0),
                        correlation_id=queued.get("correlation_id", f"arb_{uuid.uuid4().hex[:8]}"),
                        audio_features=queued.get("audio_features")
                    )

                    # 2. Arbitration pipeline path
                    await self._run_pipeline(
                        guild_id=guild_id,
                        session=session,
                        user_id=queued["user_id"],
                        speaker_name=queued["speaker_name"],
                        raw_text=queued["raw_text"],
                        stt_ms=queued["stt_ms"],
                        voice_client=queued["voice_client"],
                        text_channel=queued["text_channel"],
                        mode=queued["mode"],
                        t_start=queued.get("t_start", time.monotonic()),
                        correlation_id=queued.get("correlation_id", f"arb_{uuid.uuid4().hex[:8]}")
                    )
                except Exception as ex:
                    logger.error(
                        f"Error processing queued utterance from {queued['speaker_name']}: {ex}",
                        exc_info=True
                    )
        finally:
            session.is_draining = False


arbitration_engine = ArbitrationEngine()
