import time
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Any
import discord
import edge_tts
from bot.config import config

logger = logging.getLogger("TTSVoice")


class InterventionSpeaker:
    """Intervention-only voice engine using Microsoft Edge Neural TTS with barge-in support."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.interrupted: bool = False
        self.last_barge_in_user: Optional[str] = None

    def stop(self, voice_client: Optional[discord.VoiceClient], user: Optional[Any] = None) -> bool:
        """
        Immediately stops ongoing intervention playback on user barge-in.
        Logs: [Barge-in] Stopped intervention for {user}
        """
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            user_label = user if user is not None else "user"
            self.interrupted = True
            self.last_barge_in_user = str(user_label)
            logger.info(f"[Barge-in] Stopped intervention for {user_label}")
            return True
        return False

    async def speak(self, voice_client: Optional[discord.VoiceClient], text: str) -> int:
        """Synthesizes text and plays directly into voice channel. Returns tts_ms latency."""
        if not voice_client or not voice_client.is_connected() or not text.strip():
            return 0

        t0 = time.perf_counter()
        async with self._lock:
            try:
                temp_dir = Path(tempfile.gettempdir())
                temp_audio = temp_dir / f"intervention_{int(time.time() * 1000)}.mp3"

                communicate = edge_tts.Communicate(
                    text,
                    config.TTS_VOICE,
                    rate=config.TTS_RATE,
                    pitch=config.TTS_PITCH
                )
                await communicate.save(str(temp_audio))
                tts_ms = int((time.perf_counter() - t0) * 1000)

                # Wait if audio is currently playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.05)

                self.interrupted = False
                self.last_barge_in_user = None

                def after_play(error):
                    if error:
                        logger.error(f"Error playing voice audio: {error}")
                    try:
                        if temp_audio.exists():
                            temp_audio.unlink()
                    except Exception:
                        pass

                audio_source = discord.FFmpegPCMAudio(str(temp_audio))
                voice_client.play(audio_source, after=after_play)
                logger.info(f"🔊 [Intervention Spoken] ({tts_ms}ms): '{text}'")

                while voice_client.is_playing():
                    await asyncio.sleep(0.05)

                if self.interrupted:
                    logger.info(f"🛑 [Intervention Aborted] Playback stopped via barge-in by {self.last_barge_in_user}")

                return tts_ms
            except Exception as e:
                logger.error(f"TTS Error: {e}")
                return 0


speaker = InterventionSpeaker()
