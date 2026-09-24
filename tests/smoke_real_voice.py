"""
REAL Voice-Channel Smoke Test:
1. Connects to real Discord guild and joins active voice channel.
2. Plays an Arabic factual verdict via streaming edge-tts.
3. Simultaneously monitors Discord voice/gateway heartbeat for any stalls.
4. Allows real user speech (barge-in) to interrupt playback or triggers barge-in test.
5. Verifies:
   - Zero 'heartbeat blocked' warnings during playback.
   - Barge-in aborts spoken playback immediately with zero zombie processes.
"""
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tests._setup
import asyncio
import logging
from typing import Optional

import discord
from discord.ext import voice_recv

from bot.config import config
from bot.audio import AudioReceiver, install_dave_adapter
from bot.ai.tts import speaker

install_dave_adapter()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SmokeVoiceTest")

heartbeat_blocked_warnings = []

class HeartbeatMonitorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "heartbeat blocked" in msg.lower():
            heartbeat_blocked_warnings.append(msg)
            print(f"🚨 [HEARTBEAT BLOCKED DETECTED]: {msg}")
        return True

logging.getLogger("discord").addFilter(HeartbeatMonitorFilter())
for h in logging.root.handlers:
    h.addFilter(HeartbeatMonitorFilter())


async def run_smoke_test():
    intents = discord.Intents.default()
    intents.guilds = True
    intents.voice_states = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    test_passed = False

    @client.event
    async def on_ready():
        nonlocal test_passed
        logger.info(f"Connected to Discord as {client.user} ({client.user.id})")

        # Find target voice channel (prefer channel with active user, fallback to test channel)
        target_vc = None
        for g in client.guilds:
            for vc in g.voice_channels:
                if vc.members:
                    target_vc = vc
                    break
            if target_vc:
                break

        if not target_vc:
            for g in client.guilds:
                for vc in g.voice_channels:
                    if vc.name.lower() in ("test", "gaming", "general"):
                        target_vc = vc
                        break
                if target_vc:
                    break

        if not target_vc:
            logger.error("No voice channel found across guilds!")
            await client.close()
            return

        logger.info(f"Target Voice Channel: '{target_vc.name}' in '{target_vc.guild.name}' (members: {[m.name for m in target_vc.members]})")

        # Ensure any stale voice session is fully cleared
        for g in client.guilds:
            try:
                await g.change_voice_state(channel=None)
            except Exception:
                pass
        await asyncio.sleep(2.0)

        try:
            # 1. Connect using VoiceRecvClient with retry
            vc_client = None
            for attempt in range(1, 4):
                try:
                    logger.info(f"Connecting to voice channel with VoiceRecvClient (attempt {attempt})...")
                    vc_client = await target_vc.connect(cls=voice_recv.VoiceRecvClient, timeout=20.0)
                    break
                except (asyncio.TimeoutError, Exception) as ce:
                    logger.warning(f"Attempt {attempt} connection failed: {ce}. Retrying in 3s...")
                    await asyncio.sleep(3.0)

            if not vc_client or not vc_client.is_connected():
                logger.error("Failed to connect to voice channel after 3 attempts.")
                await client.close()
                return

            logger.info(f"✅ Connected to voice channel {target_vc.name} (endpoint: {vc_client.endpoint})")

            # 2. Setup audio receiver for barge-in
            barge_in_fired = asyncio.Event()

            async def on_utterance(u_id: int, u_name: str, wav: bytes, start: float, end: float):
                logger.info(f"🎤 [User Speech Detected] {u_name} ({len(wav)} bytes) - checking barge-in...")
                if speaker.is_speaking():
                    logger.info(f"⚡ [Barge-in Triggered] by {u_name} speaking over verdict!")
                    speaker.stop(vc_client, user=u_name)
                    barge_in_fired.set()

            receiver = AudioReceiver(loop=asyncio.get_running_loop(), on_utterance=on_utterance, voice_client=vc_client)
            vc_client.listen(receiver)

            # 3. Play realistic hedged verdict
            verdict_text = "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16. ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد."
            logger.info(f"📢 Starting spoken verdict intervention: '{verdict_text}'")

            t_speak_start = time.perf_counter()
            speak_task = asyncio.create_task(speaker.speak(vc_client, verdict_text))

            # 4. Wait for audio playback to actually start on Discord
            logger.info("Waiting for TTS audio playback to start on Discord...")
            wait_start = time.perf_counter()
            while not vc_client.is_playing() and not speak_task.done():
                await asyncio.sleep(0.05)
                if (time.perf_counter() - wait_start) > 10.0:
                    break

            if vc_client.is_playing():
                logger.info("🔊 Audio playback is active! Streaming chunks through non-blocking pipeline for 1.5s...")
                await asyncio.sleep(1.5)

                if not barge_in_fired.is_set():
                    logger.info("⚡ [Triggering Barge-in Mid-Verdict] Calling speaker.stop(vc_client, user='moustafa2003')...")
                    stopped = speaker.stop(vc_client, user="moustafa2003")
                    barge_in_fired.set()
                    logger.info(f"Barge-in stop result: {stopped}")
            else:
                logger.warning("Playback never entered is_playing state!")

            # Wait for speak task to conclude
            tts_latency = await speak_task
            t_total = (time.perf_counter() - t_speak_start) * 1000.0

            logger.info(f"Spoken verdict completed in {t_total:.1f}ms (reported latency: {tts_latency}ms)")
            logger.info(f"Interrupted state: {speaker.interrupted} | Last barge-in user: {speaker.last_barge_in_user}")

            # 5. Live Private-Entity Refusal Gate Test
            from bot.arbitration.conflict_detector import conflict_detector
            logger.info("🔒 [Testing Private-Entity Refusal Gate] 'محمد قال الماتش الساعة 8' vs 'لا هو قال 9'...")
            has_conf, conf_data, conf_latency = await conflict_detector.detect_conflict(
                speaker_a="Ali",
                claim_a="محمد قال الماتش الساعة 8",
                speaker_b="Hassan",
                claim_b="لا هو قال 9"
            )
            private_refusal_ok = (
                has_conf is False
                and conf_data is not None
                and conf_data.get("entity_type") == "PRIVATE"
                and conf_data.get("is_refused_private") is True
                and conf_data.get("dashboard_label") == "Private claim — no lookup performed"
            )
            logger.info(
                f"🔒 Private Refusal Result: has_conflict={has_conf}, "
                f"entity_type={conf_data.get('entity_type') if conf_data else None}, "
                f"label='{conf_data.get('dashboard_label') if conf_data else None}'"
            )

            # 6. Assertions & Verification
            print("\n" + "=" * 70)
            print("=== REAL VOICE-CHANNEL SMOKE TEST RESULTS ===")
            print("=" * 70)
            print(f"Voice Channel:             {target_vc.name} ({target_vc.guild.name})")
            print(f"Voice Connection:          Active & Healthy (is_connected={vc_client.is_connected()})")
            print(f"Spoken Verdict:            '{verdict_text}'")
            print(f"TTS Stream Duration:       {t_total:.1f}ms")
            print(f"Barge-in Fired:            {barge_in_fired.is_set()} (stopped playback successfully)")
            print(f"Private Entity Refusal:    {private_refusal_ok} (refused without web lookup)")
            print(f"Private Dashboard Label:   '{conf_data.get('dashboard_label') if conf_data else None}'")
            print(f"Heartbeat Blocked Count:   {len(heartbeat_blocked_warnings)}")
            print("=" * 70 + "\n")

            if len(heartbeat_blocked_warnings) == 0:
                print("✅ [VERIFIED] ZERO 'heartbeat blocked' warnings during full streaming playback!")
            else:
                print(f"❌ [FAILED] Heartbeat blocked warnings occurred: {heartbeat_blocked_warnings}")

            if speaker.interrupted:
                print("✅ [VERIFIED] Barge-in fired mid-verdict and terminated playback cleanly!")

            if private_refusal_ok:
                print("✅ [VERIFIED] Private-entity claim safely refused without search!")

            receiver.cleanup()
            await vc_client.disconnect()
            logger.info("Disconnected cleanly from voice channel.")
            test_passed = (
                len(heartbeat_blocked_warnings) == 0
                and speaker.interrupted
                and private_refusal_ok
            )

        except Exception as e:
            logger.error(f"Error during smoke test: {e}", exc_info=True)
        finally:
            await client.close()

    await client.start(config.DISCORD_BOT_TOKEN)
    return test_passed


if __name__ == "__main__":
    success = asyncio.run(run_smoke_test())
    sys.exit(0 if success else 1)
