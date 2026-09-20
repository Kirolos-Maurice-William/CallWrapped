import time
import asyncio
import logging
from typing import Dict, Optional, Callable, Awaitable
import numpy as np
import discord
from discord.ext import voice_recv
from bot.config import config
from bot.audio.pcm import UserSpeechBuffer, convert_discord_pcm_to_wav

logger = logging.getLogger("AudioReceiver")


class AudioReceiver(voice_recv.AudioSink):
    """
    Multi-user parallel Discord AudioSink.
    - Decodes incoming audio per user.
    - Isolates buffers completely per speaker (true parallel multi-speaker).
    - Ignores bot audio to avoid echo loops.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_utterance: Callable[..., Awaitable[None]],
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
        display_name: str = "Speaker"

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
                        display_name = f"Speaker_{ssrc % 1000}"

        if self.voice_client and getattr(self.voice_client, "user", None) and user_id == self.voice_client.user.id:
            return

        if not user_id:
            user_id = 9999
            display_name = "Speaker"

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
        speech_start = buf.speech_start_time
        speech_end = buf.last_speech_time
        duration = buf.duration()
        buf.reset()

        if duration >= config.MIN_SPEECH_DURATION_SEC and len(chunks) > 5:
            logger.info(f"🎙️ [Speech Finished] {user_name} ({duration:.1f}s, {len(chunks)} frames, window={speech_start:.2f}-{speech_end:.2f}). Processing...")
            wav_bytes = convert_discord_pcm_to_wav(chunks)
            if wav_bytes:
                asyncio.run_coroutine_threadsafe(
                    self.on_utterance(user_id, user_name, wav_bytes, speech_start, speech_end),
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
        logger.info("[AudioReceiver] Cleaned up receiver resources.")
