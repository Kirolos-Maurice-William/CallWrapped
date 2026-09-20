import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

import discord
from bot.ai.tts import speaker
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.conflict_detector import conflict_detector
from bot.arbitration.verifier import arbitration_verifier
from bot.arbitration.claim_memory import ClaimMemory, StoredClaim
from bot.arbitration.stats import SessionStatsTracker
from bot.events.models import VoiceEvent, LatencyBreakdown
from bot.events.publisher import publisher
from bot.config import config
import asyncio

logger = logging.getLogger("ArbitrationEngine")


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
        self.analyzed_utterances: set = set()
        self.analytics_buffer: List[Dict[str, Any]] = []
        self.last_analytics_flush: float = time.time()
        self._topic_counts: Dict[str, int] = {}
        self._flush_lock = asyncio.Lock()
        self._is_sync_flushing: bool = False
        self.analytics_timer_task: Optional[asyncio.Task] = None

    @property
    def stats_tracker(self) -> SessionStatsTracker:
        if self.analytics_buffer and not self._is_sync_flushing:
            arbitration_engine.flush_analytics_sync(self.guild_id, reason="stats_tracker_read")
        return self._stats_tracker

    @stats_tracker.setter
    def stats_tracker(self, val: SessionStatsTracker):
        self._stats_tracker = val

    @property
    def topic_counts(self) -> Dict[str, int]:
        if self.analytics_buffer and not self._is_sync_flushing:
            arbitration_engine.flush_analytics_sync(self.guild_id, reason="recap_render")
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
        """Flushes pending analytics buffer and resets all session statistics."""
        if self.analytics_buffer:
            arbitration_engine.flush_analytics_sync(self.guild_id, reason="session_reset")
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
        if self.analytics_timer_task and not self.analytics_timer_task.done():
            self.analytics_timer_task.cancel()


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

    def flush_analytics_sync(self, guild_id: int, reason: str = "sync_flush"):
        """
        Batched Path (sync): Synchronously flushes pending buffer before !recap rendering or session end.
        On failure or 429: retries once, then KEEPS the buffer.
        """
        session = self.get_session(guild_id)
        if not session.analytics_buffer:
            return

        if session._is_sync_flushing:
            return
        session._is_sync_flushing = True
        try:
            buffer_to_process = list(session.analytics_buffer)
            try:
                results, tokens, latency_ms = claim_detector.batch_classify_sync(buffer_to_process)
            except Exception as e:
                logger.warning(
                    f"⚠️ [BatchAnalytics Sync] Batch classification failed after retry: {e}. "
                    f"Keeping {len(buffer_to_process)} buffered items for next window."
                )
                return

            session.analytics_buffer = session.analytics_buffer[len(buffer_to_process):]
            session.last_analytics_flush = time.time()

            self._apply_batch_results(session, guild_id, buffer_to_process, results, tokens, reason)
        finally:
            session._is_sync_flushing = False

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

        for idx, item in enumerate(buffer_to_process, 1):
            res = results_by_line.get(idx, {})
            topic = res.get("topic", "other")
            anger = res.get("anger", "none")
            anger_evidence = res.get("anger_evidence") or ""

            # 1. Update topic stats (avoid duplicate increment if publisher is hooked by main.py)
            if getattr(publisher.publish_sync_task, "__name__", "") != "_on_event_published":
                session._topic_counts[topic] = session._topic_counts.get(topic, 0) + 1

            # 2. Update anger with 90s debounce
            stats = session._stats_tracker.record_anger(
                speaker_id=str(item["user_id"]),
                timestamp=item["timestamp"],
                anger=anger,
                anger_quote=anger_evidence,
                speaker_name=item["speaker_name"]
            )

            logger.info(
                f"📈 [Batched Analytics Line] {item['speaker_name']}: topic={topic} | anger={anger} | "
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
        is_drained: bool = False
    ):
        t_start = time.monotonic()
        correlation_id = f"arb_{uuid.uuid4().hex[:8]}"

        session = self.get_session(guild_id)
        session.add_turn(speaker_name, raw_text, user_id)

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
            payload={"mode": mode}
        )
        publisher.publish_sync_task(turn_event)

        # 2. Mirror transcript to Discord text channel if available
        if text_channel:
            try:
                await text_channel.send(f"🗣️ **{speaker_name}**: {raw_text}")
            except Exception as e:
                logger.debug(f"Could not post to text channel: {e}")

        # BATCHED ANALYTICS PATH: Track talk-time & buffer for batched topic/anger reader
        t_fanout_start = time.perf_counter()
        utterance_key = f"{user_id}_{speech_start}_{raw_text.strip()}"
        if getattr(config, "ANALYTICS_ENABLED", 1) != 0 and utterance_key not in session.analyzed_utterances and not is_drained:
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
                "correlation_id": correlation_id
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
        logger.info(f"⚡ [Fan-out Dispatcher] Batched analytics buffered in {fanout_overhead_ms:.3f}ms (non-blocking, arbitrator path running)")

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
                "is_drained": True
            })
            logger.info(
                f"📥 [Queued Utterance] Session {guild_id} is arbitrating. "
                f"Queued utterance from {speaker_name} (queue size: {len(session.pending_utterances)}/3)"
            )
            return

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

        # Step A: FastGate + Groq Claim Detector
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

        # Step D: Groq Conflict Analyzer between the two relevant claims
        t_conflict_start = time.monotonic()
        is_conflict, conflict_data, conflict_ms = await conflict_detector.detect_conflict(
            speaker_a=prior_claim.speaker_name,
            claim_a=prior_claim.claim_text,
            speaker_b=speaker_name,
            claim_b=claim_stmt
        )
        t_conflict_end = time.monotonic()

        if not is_conflict or not conflict_data:
            return

        search_query = conflict_data.get("search_query")
        target_domains = conflict_data.get("target_domains", [])
        if not search_query:
            return

        # Lock session while arbitrating
        session.is_arbitrating = True
        try:
            # Step E: Ground Truth Verification via Tavily with Source Policy
            t_search_start = time.monotonic()
            assessment, search_ms, synth_ms, sources = await arbitration_verifier.verify_dispute(
                speaker_a=prior_claim.speaker_name,
                claim_a=prior_claim.claim_text,
                speaker_b=speaker_name,
                claim_b=claim_stmt,
                search_query=search_query,
                target_domains=target_domains
            )
            t_search_end = time.monotonic()

            if not assessment or assessment.get("status") == "UNVERIFIABLE":
                session.unverifiable_count += 1
                return

            confidence = assessment.get("confidence", 95)
            spoken_text = assessment.get("spoken_intervention", "")
            correct_fact = assessment.get("correct_fact", "")
            source_url = assessment.get("selected_source_url", "")
            source_title = assessment.get("selected_source_title", "Official Source")
            evidence_strength = assessment.get("evidence_strength", "HIGH")
            spk_a_status = assessment.get("speaker_a_status", "UNKNOWN")
            spk_b_status = assessment.get("speaker_b_status", "UNKNOWN")

            # Update speaker accuracy stats
            if prior_claim.speaker_name in session.speaker_stats:
                if spk_a_status == "SUPPORTED":
                    session.speaker_stats[prior_claim.speaker_name]["verified"] += 1
                elif spk_a_status == "CONTRADICTED":
                    session.speaker_stats[prior_claim.speaker_name]["refuted"] += 1

            if speaker_name in session.speaker_stats:
                if spk_b_status == "SUPPORTED":
                    session.speaker_stats[speaker_name]["verified"] += 1
                elif spk_b_status == "CONTRADICTED":
                    session.speaker_stats[speaker_name]["refuted"] += 1

            session.disputed_claims_count += 1
            session.verified_claims_count += 1

            # Step F: Voice Intervention (Template-based via Edge-TTS)
            t_tts_start = time.monotonic()
            tts_ms = await speaker.speak(voice_client, spoken_text)
            t_tts_end = time.monotonic()

            total_elapsed_ms = int((time.monotonic() - t_start) * 1000)

            # Step G: Post Rich Discord Embed to Text Channel
            if text_channel:
                embed = discord.Embed(
                    title="⚖️ Verified Factual Arbitration",
                    description=(
                        f"📢 **{correct_fact}**\n\n"
                        f"• **{prior_claim.speaker_name}:** `{spk_a_status}`\n"
                        f"• **{speaker_name}:** `{spk_b_status}`\n\n"
                        f"🎯 **Evidence Strength:** `{evidence_strength}` ({confidence}%)\n"
                        f"🔗 **Source:** [{source_title}]({source_url})\n\n"
                        f"⚡ *Latency: STT {stt_ms}ms | LPU {claim_ms + conflict_ms + synth_ms}ms | Web {search_ms}ms | TTS {tts_ms}ms (Total: {total_elapsed_ms}ms)*"
                    ),
                    color=config.EMBED_COLOR_VERDICT
                )
                embed.set_footer(text=f"AssemblyAI {config.speech_model_display} • Groq LPU • Tavily")
                await text_channel.send(embed=embed)

            # Step H: Broadcast Unified Intervention Event with Explainability
            intervention_event = VoiceEvent(
                correlation_id=correlation_id,
                type="intervention",
                speaker_id=str(user_id),
                speaker_name=speaker_name,
                text=spoken_text,
                timings={
                    "stt_final_at": round(t_start, 3),
                    "claim_done_at": round(t_claim_end, 3),
                    "conflict_done_at": round(t_conflict_end, 3),
                    "search_done_at": round(t_search_end, 3),
                    "tts_done_at": round(t_tts_end, 3)
                },
                latency=LatencyBreakdown(
                    stt_ms=stt_ms,
                    llm_ms=claim_ms + conflict_ms + synth_ms,
                    search_ms=search_ms,
                    tts_ms=tts_ms,
                    total_ms=total_elapsed_ms
                ),
                payload={
                    "status": "CONTRADICTED" if "CONTRADICTED" in (spk_a_status, spk_b_status) else "SUPPORTED",
                    "confidence": confidence,
                    "evidence_strength": evidence_strength,
                    "correct_fact": correct_fact,
                    "speaker_a": prior_claim.speaker_name,
                    "claim_a": prior_claim.claim_text,
                    "speaker_a_status": spk_a_status,
                    "speaker_b": speaker_name,
                    "claim_b": claim_stmt,
                    "speaker_b_status": spk_b_status,
                    "winner": prior_claim.speaker_name if spk_a_status == "SUPPORTED" else (speaker_name if spk_b_status == "SUPPORTED" else None),
                    "loser": prior_claim.speaker_name if spk_a_status == "CONTRADICTED" else (speaker_name if spk_b_status == "CONTRADICTED" else None),
                    "source_url": source_url,
                    "source_title": source_title,
                    "spoken_intervention": spoken_text,
                    "why_i_spoke": [
                        "Factual claim detected via FastGate + Groq",
                        f"Direct contradiction identified on '{entity or 'topic'}'",
                        f"Tier-1 authoritative source located ({source_title})",
                        f"Evidence confidence high ({confidence}%)",
                        "Spoken intervention delivered via neural voice"
                    ]
                }
            )
            publisher.publish_sync_task(intervention_event)

        except Exception as err:
            logger.error(f"Arbitration cycle failed: {err}", exc_info=True)
        finally:
            session.is_arbitrating = False
            await self._drain_queue(guild_id, session)

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
