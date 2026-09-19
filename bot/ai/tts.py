import time
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple
import discord
import edge_tts
from bot.config import config

logger = logging.getLogger("TTSVoice")


class InterventionSpeaker:
    """Intervention-only voice engine using Microsoft Edge Neural TTS."""

    def __init__(self):
        self._lock = asyncio.Lock()

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

                return tts_ms
            except Exception as e:
                logger.error(f"TTS Error: {e}")
                return 0


speaker = InterventionSpeaker()
