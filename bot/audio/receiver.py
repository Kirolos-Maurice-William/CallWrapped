import time
import asyncio
import threading
import logging
from typing import Dict, Optional, Callable, Awaitable, List
import numpy as np
import discord
from discord.ext import voice_recv
from bot.config import config
from bot.audio.pcm import UserSpeechBuffer, convert_discord_pcm_to_wav
from bot.audio.loudness import (
    SpeakerLoudnessBaseline,
    UtteranceLoudnessAccumulator,
    UtteranceAudioFeatures,
    PCM16Adapter,
    rms_to_db,
    log_loudness_shadow,
)
from bot.ai.tts import speaker

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
        self._lock = threading.RLock()
        self._checker_task: Optional[asyncio.Task] = None
        self.buffers: Dict[int, UserSpeechBuffer] = {}
        self.speaker_baselines: Dict[int, SpeakerLoudnessBaseline] = {}
        self.utterance_accumulators: Dict[int, UtteranceLoudnessAccumulator] = {}
        self._unknown_ssrc_map: Dict[int, int] = {}
        self._next_unknown_id: int = -1
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

        vc = self._voice_client or getattr(self, "voice_client", None)
        if vc and getattr(vc, "user", None) and user_id == vc.user.id:
            return

        if user_id is None:
            ssrc = getattr(getattr(data, "packet", None), "ssrc", None) or getattr(data, "ssrc", None)
            with self._lock:
                if ssrc is not None:
                    if ssrc not in self._unknown_ssrc_map:
                        self._unknown_ssrc_map[ssrc] = self._next_unknown_id
                        self._next_unknown_id -= 1
                        logger.warning(f"⚠️ [AudioReceiver] Unknown SSRC {ssrc} mapped to pseudo user_id {self._unknown_ssrc_map[ssrc]}")
                    user_id = self._unknown_ssrc_map[ssrc]
                    display_name = f"Speaker_{abs(ssrc) % 1000}"
                else:
                    user_id = self._next_unknown_id
                    self._next_unknown_id -= 1
                    display_name = f"Speaker_{-user_id}"
                    logger.warning(f"⚠️ [AudioReceiver] Voice packet without user or SSRC mapped to pseudo user_id {user_id}")

        # 2. Calculate RMS energy
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        except Exception:
            rms = 0.0

        # Barge-in: stop bot playback if user speaks above the barge-in threshold
        barge_threshold = getattr(config, "BARGE_IN_THRESHOLD_RMS", 220)
        if vc and vc.is_playing() and rms >= barge_threshold:
            user_label = display_name if display_name and display_name != "Speaker" else (
                getattr(user, "display_name", None) or getattr(user, "name", None) or (str(user) if user else f"User_{user_id}")
            )
            speaker.stop(vc, user_label)

        now = time.time()

        with self._lock:
            # Get or create isolated user buffer
            if user_id not in self.buffers:
                self.buffers[user_id] = UserSpeechBuffer(user_id, display_name)
            if user_id not in self.speaker_baselines:
                self.speaker_baselines[user_id] = SpeakerLoudnessBaseline()
            if user_id not in self.utterance_accumulators:
                self.utterance_accumulators[user_id] = UtteranceLoudnessAccumulator()

            buf = self.buffers[user_id]
            buf.user_name = display_name
            baseline = self.speaker_baselines[user_id]
            acc = self.utterance_accumulators[user_id]

            buf.add_frame(pcm_bytes, rms, now)

            # Feature B: Acoustic loudness tracking (O(1), no I/O, no awaits)
            log_rms_db = rms_to_db(rms)
            clipped_count, total_samples = PCM16Adapter.count_clipped_samples(pcm_bytes)
            is_frame_clipped = (clipped_count / total_samples >= PCM16Adapter.FRAME_CLIP_RATIO_THRESHOLD) if total_samples > 0 else False
            baseline.observe_eligible_frame(log_rms_db, is_frame_clipped)

            if buf.is_speaking:
                if not acc.is_active:
                    acc.begin(utterance_id=f"utt_{user_id}_{int(now * 1000)}", speaker_id=str(user_id))
                acc.observe_frame_raw(rms=rms, log_rms_db=log_rms_db, clipped_samples=clipped_count, total_samples=total_samples)

            # 3. Force utterance finalization if max speech duration exceeded
            if buf.is_speaking and (now - buf.speech_start_time >= config.MAX_SPEECH_DURATION_SEC):
                self._finalize_utterance(buf, ended_by="forcesplit")

    async def _silence_checker_loop(self):
        """Continuously checks each active speaker buffer independently."""
        while self._is_active:
            await asyncio.sleep(0.1)
            now = time.time()
            with self._lock:
                active_buffers = list(self.buffers.values())

            for buf in active_buffers:
                with self._lock:
                    if buf.is_speaking and buf.pcm_chunks:
                        silence_gap = now - buf.last_speech_time
                        if silence_gap >= config.SILENCE_DURATION_SEC:
                            self._finalize_utterance(buf, ended_by="silence")

    def _finalize_utterance(self, buf: UserSpeechBuffer, ended_by: str = "silence"):
        """Dispatches completed audio for speech-to-text transcription concurrently."""
        with self._lock:
            if not buf.is_speaking and not buf.pcm_chunks:
                return
            chunks = list(buf.pcm_chunks)
            user_id = buf.user_id
            user_name = buf.user_name
            speech_start = buf.speech_start_time
            speech_end = buf.last_speech_time
            duration = buf.duration()
            buf.reset()

            baseline = self.speaker_baselines.get(user_id)
            acc = self.utterance_accumulators.get(user_id)
            audio_features: Optional[UtteranceAudioFeatures] = acc.finalize(baseline) if acc else None

        if duration >= config.MIN_SPEECH_DURATION_SEC and len(chunks) > 5:
            coro = self._async_finalize(
                user_id, user_name, chunks, speech_start, speech_end, duration, ended_by, audio_features
            )

            def _log_future_exception(f):
                try:
                    exc = f.exception()
                    if exc:
                        logger.error(
                            f"❌ [AudioReceiver] Unhandled exception in utterance pipeline for {user_name} ({user_id}): {exc}",
                            exc_info=exc
                        )
                except (asyncio.CancelledError, Exception) as cb_err:
                    if not isinstance(cb_err, asyncio.CancelledError):
                        logger.error(f"❌ [AudioReceiver] Failed retrieving future result: {cb_err}")

            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is self.loop:
                task = self.loop.create_task(coro)
                task.add_done_callback(_log_future_exception)
            else:
                fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
                fut.add_done_callback(_log_future_exception)

    async def _async_finalize(
        self,
        user_id: int,
        user_name: str,
        chunks: List[bytes],
        speech_start: float,
        speech_end: float,
        duration: float,
        ended_by: str,
        audio_features: Optional[UtteranceAudioFeatures]
    ):
        logger.info(f"🎙️ [Speech Finished] {user_name} ({duration:.1f}s, {len(chunks)} frames, window={speech_start:.2f}-{speech_end:.2f}, ended_by={ended_by}). Processing...")

        # Shadow logging: log was_loud events only if capture mode is active to strictly honor privacy policy
        if audio_features and audio_features.was_loud and getattr(config, "TEST_CAPTURE_MODE", 0):
            log_loudness_shadow(user_name, audio_features)

        wav_bytes = await asyncio.to_thread(convert_discord_pcm_to_wav, chunks)
        if wav_bytes:
            try:
                coro = self.on_utterance(user_id, user_name, wav_bytes, speech_start, speech_end, ended_by, audio_features)
            except TypeError:
                try:
                    coro = self.on_utterance(user_id, user_name, wav_bytes, speech_start, speech_end, ended_by)
                except TypeError:
                    coro = self.on_utterance(user_id, user_name, wav_bytes, speech_start, speech_end)

            await coro

    def cleanup(self):
        self._is_active = False
        if getattr(self, "_checker_task", None):
            try:
                self._checker_task.cancel()
            except Exception:
                pass
        with self._lock:
            if hasattr(self, "buffers"):
                self.buffers.clear()
            if hasattr(self, "speaker_baselines"):
                self.speaker_baselines.clear()
            if hasattr(self, "utterance_accumulators"):
                self.utterance_accumulators.clear()
            if hasattr(self, "_unknown_ssrc_map"):
                self._unknown_ssrc_map.clear()
        logger.info("[AudioReceiver] Cleaned up receiver resources.")
