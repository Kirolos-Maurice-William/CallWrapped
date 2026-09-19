import time
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

import discord
import edge_tts
from bot.config import config

logger = logging.getLogger("VoiceSpeaker")


class VoiceSpeaker:
    """Handles high-quality neural voice synthesis and synchronized Discord audio playback."""

    def __init__(self):
        self._lock = asyncio.Lock()

    async def speak(self, voice_client: Optional[discord.VoiceClient], text: str):
        """Synthesizes natural Arabic text and plays it directly into the Discord voice channel."""
        if not voice_client or not voice_client.is_connected() or not text.strip():
            return

        async with self._lock:
            try:
                temp_dir = Path(tempfile.gettempdir())
                temp_audio = temp_dir / f"tts_{int(time.time() * 1000)}.mp3"

                communicate = edge_tts.Communicate(
                    text,
                    config.TTS_VOICE,
                    rate=config.TTS_RATE,
                    pitch=config.TTS_PITCH
                )
                await communicate.save(str(temp_audio))

                # Wait if audio is currently playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

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
                logger.info(f"🔊 [Voice Spoken] '{text}'")

                # Wait until audio finishes before releasing lock
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to speak in voice channel: {e}")


voice_speaker = VoiceSpeaker()
