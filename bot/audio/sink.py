import io
import time
import wave
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable

import numpy as np
import discord
from discord.ext import voice_recv
from bot.config import config

logger = logging.getLogger("MultiUserAudioSink")


def convert_discord_pcm_to_wav(pcm_chunks: List[bytes]) -> bytes:
    """
    Converts a list of Discord 48kHz stereo 16-bit PCM frames into a clean 16kHz mono WAV.
    Uses numpy 3-sample boxcar anti-aliasing filter for maximum clarity and sub-5ms performance.
    """
    if not pcm_chunks:
        return b""
    raw_bytes = b"".join(pcm_chunks)
    stereo_data = np.frombuffer(raw_bytes, dtype=np.int16)
    if stereo_data.size < 2:
        return b""

    # Reshape to (N, 2) and average stereo to mono
    stereo_matrix = stereo_data.reshape(-1, 2)
    mono_48k = stereo_matrix.mean(axis=1).astype(np.int16)

    # Downsample 48kHz -> 16kHz (3:1 integer decimation with anti-aliasing averaging)
    remainder = mono_48k.size % 3
    if remainder != 0:
        mono_48k = mono_48k[:-remainder]
    mono_16k = mono_48k.reshape(-1, 3).mean(axis=1).astype(np.int16)

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(mono_16k.tobytes())
    return wav_buf.getvalue()


class UserSpeechBuffer:
    """Tracks active speaking state, PCM frame buffer, and silence timing for a specific user.
    Includes a pre-roll ring buffer (~100ms) so speech onset is never clipped."""
    PRE_ROLL_FRAMES = 5

    def __init__(self, user_id: int, user_name: str):
        self.user_id = user_id
        self.user_name = user_name
        self.pcm_chunks: List[bytes] = []
        self.speech_start_time: float = 0.0
        self.last_speech_time: float = 0.0
        self.is_speaking: bool = False
        self._pre_roll: List[bytes] = []

    def add_frame(self, pcm_bytes: bytes, rms: float, now: float):
        if rms >= config.SILENCE_THRESHOLD_RMS:
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_start_time = now
                if self._pre_roll:
                    self.pcm_chunks.extend(self._pre_roll)
                    self._pre_roll.clear()
            self.last_speech_time = now
            self.pcm_chunks.append(pcm_bytes)
        elif self.is_speaking:
            # Trailing audio while speaking
            self.pcm_chunks.append(pcm_bytes)
        else:
            # Rolling pre-roll buffer
            self._pre_roll.append(pcm_bytes)
            if len(self._pre_roll) > self.PRE_ROLL_FRAMES:
                self._pre_roll.pop(0)

    def duration(self) -> float:
        # 1 frame = 3840 bytes = 0.02 seconds at 48kHz stereo 16-bit
        return (len(self.pcm_chunks) * 3840) / (48000 * 4)

    def reset(self):
        self.pcm_chunks = []
        self.is_speaking = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self._pre_roll.clear()


class MultiUserAudioSink(voice_recv.AudioSink):
    """
    Multi-user parallel Discord AudioSink with DAVE protocol support.
    - Decodes incoming audio per user.
    - Isolates buffers completely per speaker (true parallel multi-speaker).
    - Ignores bot audio to avoid echo loops.
    """
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_utterance: Callable[[int, str, bytes], Awaitable[None]],
        voice_client: Optional[voice_recv.VoiceRecvClient] = None
    ):
        super().__init__()
        self.loop = loop
        self.on_utterance = on_utterance
        self._voice_client = voice_client
        self._checker_task: Optional[asyncio.Task] = None
        self.buffers: Dict[int, UserSpeechBuffer] = {}
        self._is_active = True
        self._checker_task = self.loop.create_task(self._silence_checker_loop())

    def wants_opus(self) -> bool:
        return False

    def write(self, user: Optional[discord.User], data: voice_recv.VoiceData):
        if not self._is_active:
            return

        pcm_bytes = data.pcm
        if not pcm_bytes or len(pcm_bytes) < 4:
            return

        # 1. Dynamically resolve user identity
        resolved_user = user or getattr(data, "source", None)
        user_id: Optional[int] = None
        display_name: str = "المتحدث"

        if resolved_user:
            if getattr(resolved_user, "bot", False):
                return
            user_id = resolved_user.id
            display_name = getattr(resolved_user, "display_name", getattr(resolved_user, "name", str(user_id)))
        elif self.voice_client:
            ssrc = getattr(data.packet, "ssrc", None)
            if ssrc:
                user_id = self.voice_client._ssrc_to_id.get(ssrc)
                channel = getattr(self.voice_client, "channel", None)
                if user_id and channel:
                    for m in channel.members:
                        if m.id == user_id:
                            if m.bot:
                                return
                            display_name = m.display_name
                            break
                elif not user_id and channel:
                    humans = [m for m in channel.members if not m.bot]
                    if len(humans) == 1:
                        user_id = humans[0].id
                        display_name = humans[0].display_name
                    else:
                        user_id = ssrc
                        display_name = f"المتحدث_{ssrc % 1000}"

        if self.voice_client and getattr(self.voice_client, "user", None) and user_id == self.voice_client.user.id:
            return

        if not user_id:
            user_id = 9999
            display_name = "المتحدث"

        # 2. Get or create isolated user buffer
        if user_id not in self.buffers:
            self.buffers[user_id] = UserSpeechBuffer(user_id, display_name)

        buf = self.buffers[user_id]
        buf.user_name = display_name

        # 3. Calculate RMS energy
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        except Exception:
            rms = 0.0

        now = time.time()
        buf.add_frame(pcm_bytes, rms, now)

        # 4. Force utterance finalization if max speech duration exceeded
        if buf.is_speaking and (now - buf.speech_start_time >= config.MAX_SPEECH_DURATION_SEC):
            self._finalize_utterance(buf)

    async def _silence_checker_loop(self):
        """Continuously checks each active speaker buffer independently."""
        while self._is_active:
            await asyncio.sleep(0.1)
            now = time.time()
            for buf in list(self.buffers.values()):
                if buf.is_speaking and buf.pcm_chunks:
                    silence_gap = now - buf.last_speech_time
                    if silence_gap >= config.SILENCE_DURATION_SEC:
                        self._finalize_utterance(buf)

    def _finalize_utterance(self, buf: UserSpeechBuffer):
        """Dispatches completed audio for speech-to-text transcription concurrently."""
        chunks = buf.pcm_chunks
        user_id = buf.user_id
        user_name = buf.user_name
        duration = buf.duration()
        buf.reset()

        if duration >= config.MIN_SPEECH_DURATION_SEC and len(chunks) > 5:
            logger.info(f"📤 [Utterance Finished] انتهى كلام {user_name} ({duration:.1f}s, {len(chunks)} frames). جاري المعالجة...")
            wav_bytes = convert_discord_pcm_to_wav(chunks)
            if wav_bytes:
                # Dispatch async handler per user in parallel without blocking other speakers
                asyncio.run_coroutine_threadsafe(
                    self.on_utterance(user_id, user_name, wav_bytes),
                    self.loop
                )

    def cleanup(self):
        self._is_active = False
        if getattr(self, "_checker_task", None):
            try:
                self._checker_task.cancel()
            except Exception:
                pass
        if hasattr(self, "buffers"):
            self.buffers.clear()
        logger.info("[AudioSink] Cleaned up MultiUserAudioSink.")
