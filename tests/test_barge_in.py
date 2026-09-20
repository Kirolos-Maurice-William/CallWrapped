"""
Acceptance Test for Barge-in Mid-Sentence Interruption (Step 9).
Tests:
1. User speech (RMS >= threshold) while bot is playing immediately triggers voice_client.stop()
   and logs '[Barge-in] Stopped intervention for {user}'.
2. The pipeline continues cleanly after aborted playback (no crash, session state unaffected).
3. The bot's OWN audio (self-echo / bot=True / user_id == bot_id) does NOT trigger barge-in.
4. Silence (RMS < threshold) during playback does NOT trigger barge-in.
"""

import sys
import io
import time
import asyncio
import unittest
import logging
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TestBargeIn")

from bot.config import config
from bot.ai.tts import speaker, InterventionSpeaker
from bot.audio.receiver import AudioReceiver
from bot.arbitration.engine import arbitration_engine
from discord.ext import voice_recv


def create_pcm_frame(amplitude: int = 2000) -> bytes:
    """Creates a 20ms 48kHz stereo 16-bit PCM frame (3840 bytes) with target amplitude."""
    # 48000 samples/sec * 2 channels * 0.02s = 1920 int16 samples
    samples = np.full(1920, amplitude, dtype=np.int16)
    return samples.tobytes()


class MockVoiceClient:
    """Simulates Discord VoiceClient playing audio with stop() capability."""

    def __init__(self, bot_id: int = 8888):
        self._playing = True
        self._connected = True
        self.stop_called = False
        self.stop_count = 0
        self.user = MagicMock()
        self.user.id = bot_id
        self._ssrc_to_id = {}
        self.channel = MagicMock()
        self.channel.members = []

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return self._playing

    def stop(self):
        self.stop_called = True
        self.stop_count += 1
        self._playing = False

    def play(self, source, after=None):
        self._playing = True
        self.after = after


class TestBargeIn(unittest.IsolatedAsyncioTestCase):

    async def test_1_user_speech_triggers_barge_in_and_logs(self):
        """
        Criteria 1: When bot is playing and ANY user's voice crosses speech threshold,
        immediately voice_client.stop() and log '[Barge-in] Stopped intervention for {user}'.
        """
        print("\n" + "=" * 75)
        print("=== TEST 1: USER SPEECH TRIGGERS BARGE-IN MID-PLAYBACK ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)
        self.assertTrue(vc.is_playing())

        async def dummy_on_utterance(*args):
            pass

        receiver = AudioReceiver(
            loop=asyncio.get_running_loop(),
            on_utterance=dummy_on_utterance,
            voice_client=vc
        )

        user = MagicMock()
        user.id = 12345
        user.display_name = "Ziad"
        user.bot = False

        data = MagicMock(spec=voice_recv.VoiceData)
        data.pcm = create_pcm_frame(amplitude=2500)
        data.source = user

        # Capture log to verify exact "[Barge-in] Stopped intervention for {user}"
        with self.assertLogs("TTSVoice", level="INFO") as cm:
            receiver.write(user, data)

        print(f"VoiceClient stop() called: {vc.stop_called}")
        print(f"VoiceClient is_playing(): {vc.is_playing()}")
        print(f"Captured Logs:\n" + "\n".join(f"  {line}" for line in cm.output))

        self.assertTrue(vc.stop_called, "voice_client.stop() must be called immediately")
        self.assertFalse(vc.is_playing(), "voice_client.is_playing() must become False")
        self.assertTrue(
            any("[Barge-in] Stopped intervention for Ziad" in line for line in cm.output),
            "Must log '[Barge-in] Stopped intervention for {user}'"
        )
        print("[PROOF VERIFIED] Barge-in stopped playback and logged user receipt.\n")
        receiver.cleanup()

    async def test_2_bot_own_audio_does_not_trigger_barge_in(self):
        """
        Criteria 2: Bot's OWN audio does NOT trigger barge-in (self-echo filter).
        """
        print("=" * 75)
        print("=== TEST 2: BOT'S OWN AUDIO (SELF-ECHO) DOES NOT TRIGGER BARGE-IN ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)
        self.assertTrue(vc.is_playing())

        async def dummy_on_utterance(*args):
            pass

        receiver = AudioReceiver(
            loop=asyncio.get_running_loop(),
            on_utterance=dummy_on_utterance,
            voice_client=vc
        )

        # 1. Packet from bot itself via user.id matching vc.user.id
        bot_user = MagicMock()
        bot_user.id = 8888
        bot_user.display_name = "VoiceArbitratorBot"
        bot_user.bot = True

        data = MagicMock(spec=voice_recv.VoiceData)
        data.pcm = create_pcm_frame(amplitude=5000)  # Very loud sound
        data.source = bot_user

        receiver.write(bot_user, data)

        print(f"After bot audio packet:")
        print(f"  VoiceClient stop() called: {vc.stop_called}")
        print(f"  VoiceClient is_playing(): {vc.is_playing()}")

        self.assertFalse(vc.stop_called, "Bot's own audio must NEVER trigger stop()")
        self.assertTrue(vc.is_playing(), "Playback must continue uninterrupted during bot audio")

        # 2. Packet from another bot (bot=True)
        other_bot = MagicMock()
        other_bot.id = 9991
        other_bot.display_name = "MusicBot"
        other_bot.bot = True

        receiver.write(other_bot, data)
        self.assertFalse(vc.stop_called, "Other bot audio must NEVER trigger stop()")
        self.assertTrue(vc.is_playing())

        print("[PROOF VERIFIED] Self-echo and bot audio filtered out without triggering barge-in.\n")
        receiver.cleanup()

    async def test_3_pipeline_continues_cleanly_after_aborted_playback(self):
        """
        Criteria 3: Aborted playback completes gracefully without crash or stuck session,
        and session stats remain unaffected.
        """
        print("=" * 75)
        print("=== TEST 3: PIPELINE CONTINUATION & SESSION HEALTH AFTER ABORTED PLAYBACK ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)
        vc._playing = False  # Idle before speak() is called

        test_guild_id = 77112233
        session = arbitration_engine.get_session(test_guild_id)
        session.reset()
        session.verified_claims_count = 5
        session.disputed_claims_count = 3

        async def dummy_on_utterance(*args):
            pass

        receiver = AudioReceiver(
            loop=asyncio.get_running_loop(),
            on_utterance=dummy_on_utterance,
            voice_client=vc
        )

        # Mock edge_tts synthesis to avoid external network delay
        with patch("edge_tts.Communicate.save", new_callable=AsyncMock) as mock_save, \
             patch("discord.FFmpegPCMAudio", return_value=MagicMock()):

            # Start speak in background task
            speak_task = asyncio.create_task(
                speaker.speak(vc, "الأهلي فاز بالبطولة مرتين على التوالي")
            )

            # Allow speak to enter playback loop
            await asyncio.sleep(0.05)
            self.assertTrue(vc.is_playing(), "Bot should be actively playing intervention")

            # Simulate user barge-in speech arriving mid-playback
            interrupter = MagicMock()
            interrupter.id = 54321
            interrupter.display_name = "Kareem"
            interrupter.bot = False

            data = MagicMock(spec=voice_recv.VoiceData)
            data.pcm = create_pcm_frame(amplitude=3000)
            data.source = interrupter

            with self.assertLogs("TTSVoice", level="INFO") as cm:
                receiver.write(interrupter, data)
                # Await speak task completion
                tts_ms = await asyncio.wait_for(speak_task, timeout=2.0)

        print(f"Intervention speak() returned latency: {tts_ms}ms")
        print(f"Interrupted state: {speaker.interrupted}")
        print(f"Last barge-in user: {speaker.last_barge_in_user}")
        print(f"Session verified claims: {session.verified_claims_count}")
        print(f"Session disputed claims: {session.disputed_claims_count}")
        print(f"Session is_arbitrating: {session.is_arbitrating}")
        print(f"Captured Logs:\n" + "\n".join(f"  {line}" for line in cm.output))

        self.assertTrue(speaker.interrupted, "Speaker interrupted flag must be True")
        self.assertEqual(speaker.last_barge_in_user, "Kareem")
        self.assertFalse(vc.is_playing(), "Playback must be stopped")
        self.assertEqual(session.verified_claims_count, 5, "Session stats must remain unaffected")
        self.assertEqual(session.disputed_claims_count, 3, "Session stats must remain unaffected")
        self.assertFalse(session.is_arbitrating, "Session must not remain stuck in arbitrating state")
        print("[PROOF VERIFIED] Aborted playback completed cleanly, session healthy and unaffected.\n")
        receiver.cleanup()

    async def test_4_silence_does_not_trigger_barge_in(self):
        """
        Criteria 4: Audio below SILENCE_THRESHOLD_RMS (background noise/silence)
        does NOT trigger barge-in.
        """
        print("=" * 75)
        print("=== TEST 4: SILENCE / BACKGROUND NOISE DOES NOT TRIGGER BARGE-IN ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)
        self.assertTrue(vc.is_playing())

        async def dummy_on_utterance(*args):
            pass

        receiver = AudioReceiver(
            loop=asyncio.get_running_loop(),
            on_utterance=dummy_on_utterance,
            voice_client=vc
        )

        user = MagicMock()
        user.id = 11111
        user.display_name = "SilentUser"
        user.bot = False

        # Silent packet (amplitude 10, RMS << threshold)
        data = MagicMock(spec=voice_recv.VoiceData)
        data.pcm = create_pcm_frame(amplitude=10)
        data.source = user

        receiver.write(user, data)

        print(f"After silent packet:")
        print(f"  VoiceClient stop() called: {vc.stop_called}")
        print(f"  VoiceClient is_playing(): {vc.is_playing()}")

        self.assertFalse(vc.stop_called, "Silent frame must NOT trigger barge-in")
        self.assertTrue(vc.is_playing(), "Playback must continue during silence")
        print("[PROOF VERIFIED] Silent audio does not trigger barge-in.\n")
        receiver.cleanup()


if __name__ == "__main__":
    unittest.main()
