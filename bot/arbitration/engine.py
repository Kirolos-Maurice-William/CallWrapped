import time
import uuid
import logging
from typing import Dict, Any, List, Optional

import discord
from bot.ai.tts import speaker
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.conflict_detector import conflict_detector
from bot.arbitration.verifier import arbitration_verifier
from bot.arbitration.claim_memory import ClaimMemory, StoredClaim
from bot.events.models import VoiceEvent, LatencyBreakdown
from bot.events.publisher import publisher
from bot.config import config

logger = logging.getLogger("ArbitrationEngine")


class SessionState:
    """Tracks sliding dialogue turns, indexed claim memory, and server statistics."""

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


class ArbitrationEngine:
    """
    State Machine & Decision Pipeline:
    Raw Speech -> FastGate -> Claim Detection -> Claim Memory Indexing ->
    Scoped Conflict Detection -> Ground Truth Search (Source Policy) ->
    Template Intervention & Event Broadcast.
    """

    def __init__(self):
        self.sessions: Dict[int, SessionState] = {}

    def get_session(self, guild_id: int) -> SessionState:
        if guild_id not in self.sessions:
            self.sessions[guild_id] = SessionState(guild_id)
        return self.sessions[guild_id]

    async def process_utterance(
        self,
        guild_id: int,
        user_id: int,
        speaker_name: str,
        raw_text: str,
        stt_ms: int,
        voice_client: Optional[discord.VoiceClient],
        text_channel: Optional[discord.TextChannel],
        mode: str = "referee"
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
                "correlation_id": correlation_id
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
        is_claim, claim_data, claim_ms = await claim_detector.check_claim(raw_text)
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
                embed.set_footer(text="AssemblyAI Universal-3.5 Pro • Groq LPU • Tavily")
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
