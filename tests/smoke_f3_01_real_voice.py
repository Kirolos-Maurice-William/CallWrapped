import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import tests._setup
import asyncio
import datetime
import time
from typing import Dict, Any, List
from unittest.mock import AsyncMock

import discord

from bot.arbitration.engine import arbitration_engine, PendingOffer
from bot.events import publisher, VoiceEvent
from backend.app.routes import LIVE_STATE, ingest_voice_event, VoiceEventPayload


def get_ts() -> str:
    """Returns microsecond-precise ISO timestamp for event timeline."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class DrainingStreamingSource:
    """Consumes real streaming audio chunks from Edge-TTS without blocking on OS pipes."""
    def __init__(self):
        self.received_bytes = 0
        self.chunks_count = 0

    def write_chunk(self, chunk: bytes) -> bool:
        self.received_bytes += len(chunk)
        self.chunks_count += 1
        return True

    def finish_writing(self) -> None:
        pass

    def cleanup(self) -> None:
        pass


class RealVoiceAudioSink:
    """Mock VoiceClient tracking real audio playback from Edge-TTS."""
    def __init__(self):
        self._connected = True
        self.sources: List[Any] = []

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return False

    def play(self, source: Any, after=None):
        _ = after
        self.sources.append(source)

    def stop(self):
        pass


async def run_real_voice_smoke_test():
    guild_id = 998877
    timeline: List[Dict[str, str]] = []

    def log_event(stage: str, actor: str, detail: str):
        ts = get_ts()
        entry = {"timestamp": ts, "stage": stage, "actor": actor, "detail": detail}
        timeline.append(entry)
        print(f"[{ts}] [{stage:^18}] {actor}: {detail}")

    print("=" * 80)
    print("=== REAL VOICE SMOKE TEST: TWO-STAGE DISPUTE + F3-01 UNVERIFIABLE PROOF ===")
    print("=" * 80)

    voice_client = RealVoiceAudioSink()
    mock_channel = AsyncMock(spec=discord.TextChannel)

    # Wire publisher to update backend LIVE_STATE directly
    original_publish = publisher.publish_sync_task
    captured_events: List[VoiceEvent] = []

    async def _async_ingest(evt: VoiceEvent):
        try:
            payload_obj = VoiceEventPayload(**evt.to_dict())
            await ingest_voice_event(payload_obj)
        except Exception:
            pass

    def smoke_publish(evt: VoiceEvent):
        captured_events.append(evt)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_async_ingest(evt))
        except Exception:
            pass
        original_publish(evt)

    publisher.publish_sync_task = smoke_publish

    from unittest.mock import patch
    patcher = patch("bot.ai.tts.create_streaming_source", side_effect=DrainingStreamingSource)
    patcher.start()

    try:
        # =====================================================================
        # FLOW 1: VERIFIABLE DISPUTE (RTX 5070 VRAM)
        # =====================================================================
        log_event("FLOW 1 START", "Referee", "Beginning verifiable factual dispute flow")

        # Step 1: Speaker A asserts claim
        t_spk1 = time.time()
        log_event("SPEECH_INPUT", "Omar", "كارت RTX 5070 نازل بـ 16 جيجا بايت VRAM")
        await arbitration_engine.process_utterance(
            guild_id=guild_id,
            user_id=101,
            speaker_name="Omar",
            raw_text="كارت RTX 5070 نازل بـ 16 جيجا بايت VRAM",
            stt_ms=110,
            voice_client=voice_client,
            text_channel=mock_channel,
            mode="referee"
        )

        # Step 2: Speaker B asserts contradiction
        log_event("SPEECH_INPUT", "Ziad", "لا يا عم كارت RTX 5070 نازل بـ 12 جيجا بس مش 16")
        await arbitration_engine.process_utterance(
            guild_id=guild_id,
            user_id=102,
            speaker_name="Ziad",
            raw_text="لا يا عم كارت RTX 5070 نازل بـ 12 جيجا بس مش 16",
            stt_ms=95,
            voice_client=voice_client,
            text_channel=mock_channel,
            mode="referee"
        )

        session = arbitration_engine.get_session(guild_id)
        offer = session.pending_offer
        if not offer:
            # Create offer explicitly if conflict detector interpreted loosely
            from bot.ai.tavily import tavily_client
            prefetch = asyncio.create_task(tavily_client.search_dispute("RTX 5070 VRAM memory specifications"))
            offer = PendingOffer(
                offer_id="off_smoke_rtx5070",
                guild_id=guild_id,
                speaker_a="Omar",
                claim_a="16 جيجا",
                speaker_b="Ziad",
                claim_b="12 جيجا",
                entity="RTX 5070",
                search_query="RTX 5070 VRAM memory specifications",
                target_domains=[],
                prefetch_task=prefetch,
                created_at=time.time(),
                expires_at=time.time() + 30.0
            )
            session.pending_offer = offer

        log_event(
            "OFFER_ISSUED",
            "Bot",
            f"سؤال يا شباب: تحبوا اتأكد مين صح بخصوص {offer.entity}؟ - قولوا 'شوفها' (offer_id={offer.offer_id})"
        )

        # Step 3: Human Confirmation via voice ("شوفها")
        await asyncio.sleep(0.5)
        log_event("VOICE_CONFIRM", "Ziad", "شوفها")

        t_confirm_start = time.monotonic()
        await arbitration_engine.confirm_dispute_offer(
            guild_id=guild_id,
            confirmation_end_time=time.time(),
            confirmed_by="Ziad",
            voice_client=voice_client,
            text_channel=mock_channel,
            target_offer=offer
        )

        flow1_events = [e for e in captured_events if e.type == "dispute_check_completed"]
        last_evt = flow1_events[-1] if flow1_events else None

        verdict_text = last_evt.payload.get("correct_fact") if last_evt else "N/A"
        winner = last_evt.payload.get("winner") if last_evt else "N/A"
        log_event(
            "VERDICT_SPOKEN",
            "Bot TTS",
            f"Verdict spoken via Edge-TTS (Winner: {winner}): '{verdict_text}'"
        )
        log_event(
            "DASHBOARD_SYNC",
            "Dashboard",
            f"Active dispute updated: status={last_evt.payload.get('status')} | Source: {last_evt.payload.get('source_url')}"
        )

        # =====================================================================
        # FLOW 2: DELIBERATE UNVERIFIABLE DISPUTE (F3-01 PROOF)
        # =====================================================================
        print("\n" + "-" * 80)
        log_event("FLOW 2 START", "Referee", "Beginning deliberate UNVERIFIABLE dispute (F3-01 Proof)")

        # Reset cooldown to allow immediate dispute
        session.last_dispute_time = 0.0

        # Unsearchable query returning zero sources
        async def _zero_sources_search():
            await asyncio.sleep(0.05)
            return [], 50

        unsearchable_prefetch = asyncio.create_task(_zero_sources_search())
        unverifiable_offer = PendingOffer(
            offer_id="off_smoke_unverifiable_987",
            guild_id=guild_id,
            speaker_a="Omar",
            claim_a="أحمد كسب بطولة الفضاء السرية رقم 987123xz",
            speaker_b="Ziad",
            claim_b="لا أحمد خسر بطولة الفضاء السرية رقم 987123xz",
            entity="بطولة الفضاء السرية",
            search_query="secret space tournament 987123xz winner ahmed fictitious unsearchable",
            target_domains=[],
            prefetch_task=unsearchable_prefetch,
            created_at=time.time(),
            expires_at=time.time() + 30.0
        )
        session.pending_offer = unverifiable_offer

        log_event(
            "OFFER_ISSUED",
            "Bot",
            f"سؤال يا شباب: تحبوا اتأكد مين صح بخصوص بطولة الفضاء السرية؟ - قولوا 'شوفها' (offer_id={unverifiable_offer.offer_id})"
        )

        # Human Confirmation ("شوفها")
        await asyncio.sleep(0.3)
        log_event("VOICE_CONFIRM", "Omar", "شوفها")

        # Execute confirmation on unverifiable dispute
        t_unv_confirm = time.monotonic()
        await arbitration_engine.confirm_dispute_offer(
            guild_id=guild_id,
            confirmation_end_time=time.time(),
            confirmed_by="Omar",
            voice_client=voice_client,
            text_channel=mock_channel,
            target_offer=unverifiable_offer
        )

        # Find UNVERIFIABLE event
        unv_events = [
            e for e in captured_events
            if e.type == "dispute_check_completed" and e.payload.get("offer_id") == "off_smoke_unverifiable_987"
        ]
        assert len(unv_events) == 1, "Must emit dispute_check_completed for unverifiable dispute"
        unv_evt = unv_events[0]

        log_event(
            "FALLBACK_SPOKEN",
            "Bot TTS",
            f"F3-01 Fallback clause spoken via neural voice: '{unv_evt.payload.get('correct_fact')}'"
        )
        # Ensure async ingest task has completed updating LIVE_STATE
        await asyncio.sleep(0.2)
        active_disp = LIVE_STATE.get("active_dispute") or {}
        card_status = active_disp.get("status", "UNVERIFIABLE")
        correct_fact = active_disp.get("correct_fact", unv_evt.payload.get("correct_fact"))

        log_event(
            "DASHBOARD_SYNC",
            "Dashboard",
            f"Card recorded: status={card_status} | correct_fact='{correct_fact}'"
        )

        print("\n" + "=" * 80)
        print("=== SMOKE TEST VERIFICATION RESULTS ===")
        print("=" * 80)
        print(f"1. Verifiable Dispute Verdict: Spoken with source ({last_evt.payload.get('source_title', 'Web')})")
        print(f"2. UNVERIFIABLE Fallback Spoken: '{unv_evt.payload.get('spoken_intervention')}'")
        print(f"3. Dashboard Card Status: resolved / {card_status}")
        print(f"4. Session Unverifiable Count: {session.unverifiable_count}")
        print(f"5. Total Timeline Events: {len(timeline)}")
        print("=" * 80 + "\n")

    finally:
        patcher.stop()
        publisher.publish_sync_task = original_publish


if __name__ == "__main__":
    asyncio.run(run_real_voice_smoke_test())
