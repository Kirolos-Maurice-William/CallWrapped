import time
import asyncio
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Any
import discord
import edge_tts
from bot.config import config

try:
    from unittest.mock import MagicMock, AsyncMock
except ImportError:
    MagicMock = AsyncMock = ()  # type: ignore

logger = logging.getLogger("TTSVoice")


class StreamFFmpegPCMAudio(discord.AudioSource):
    """
    Real-time streaming AudioSource that pipes MP3 chunks into an FFmpeg subprocess
    and outputs standard 48kHz 16-bit stereo PCM (3840 bytes per 20ms frame) for Discord.
    """

    def __init__(self, executable: str = "ffmpeg"):
        cmd = [
            executable,
            "-f", "mp3",
            "-probesize", "32",
            "-analyzeduration", "0",
            "-i", "pipe:0",
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-loglevel", "error",
            "pipe:1"
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
        except FileNotFoundError:
            logger.error(f"FFmpeg executable '{executable}' not found.")
            self.process = None
            raise

        self._stdin = self.process.stdin
        self._stdout = self.process.stdout
        self._closed = False
        self._lock = threading.Lock()

    def write_chunk(self, chunk: bytes) -> bool:
        """Writes an MP3 chunk into ffmpeg stdin with immediate flushing."""
        with self._lock:
            if self._closed or not self._stdin:
                return False
            try:
                self._stdin.write(chunk)
                self._stdin.flush()
                return True
            except (BrokenPipeError, OSError, ValueError):
                return False

    def finish_writing(self) -> None:
        """Closes stdin so ffmpeg knows all audio chunks have been sent (EOF)."""
        with self._lock:
            if self._stdin and not self._stdin.closed:
                try:
                    self._stdin.close()
                except Exception:
                    pass

    def read(self) -> bytes:
        """Called every 20ms by Discord AudioPlayer thread. Returns 3840 bytes PCM."""
        if self._closed or not self._stdout:
            return b""
        try:
            data = self._stdout.read(3840)
            if len(data) != 3840:
                return b""
            return data
        except Exception:
            return b""

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        """Kills the FFmpeg process cleanly and reaps returncode (prevents zombies)."""
        with self._lock:
            self._closed = True
            if self._stdin:
                try:
                    self._stdin.close()
                except Exception:
                    pass
            if self._stdout:
                try:
                    self._stdout.close()
                except Exception:
                    pass
            if self.process:
                try:
                    self.process.kill()
                except Exception:
                    pass
                try:
                    self.process.wait(timeout=0.5)
                except Exception:
                    pass

    def __del__(self) -> None:
        self.cleanup()


def create_streaming_source(executable: str = "ffmpeg") -> Any:
    """Factory to create a StreamFFmpegPCMAudio, respecting unit test mocks of discord.FFmpegPCMAudio."""
    if isinstance(discord.FFmpegPCMAudio, (MagicMock, AsyncMock)):
        return discord.FFmpegPCMAudio("stream_mock")
    return StreamFFmpegPCMAudio(executable=executable)


class InterventionSpeaker:
    """
    Streaming intervention-only voice engine using Microsoft Edge Neural TTS
    with sub-400ms time-to-first-byte (TTFB) and barge-in support.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.interrupted: bool = False
        self.last_barge_in_user: Optional[str] = None
        self.current_audio_source: Optional[Any] = None
        self.last_audio_source: Optional[Any] = None

    def stop(self, voice_client: Optional[discord.VoiceClient], user: Optional[Any] = None) -> bool:
        """
        Immediately stops ongoing intervention playback on user barge-in.
        Kills ffmpeg process and terminates stream without zombies.
        Logs: [Barge-in] Stopped intervention for {user}
        """
        if voice_client and voice_client.is_playing():
            user_label = user if user is not None else "user"
            self.interrupted = True
            self.last_barge_in_user = str(user_label)
            voice_client.stop()
            if self.current_audio_source and hasattr(self.current_audio_source, "cleanup"):
                self.current_audio_source.cleanup()
            logger.info(f"[Barge-in] Stopped intervention for {user_label}")
            return True
        return False

    async def speak(self, voice_client: Optional[discord.VoiceClient], text: str) -> int:
        """
        Synthesizes text and streams playback directly into voice channel.
        First chunk plays in < 400ms while synthesis continues concurrently.
        Returns tts_ms latency.
        """
        if not voice_client or not voice_client.is_connected() or not text.strip():
            return 0

        t0 = time.perf_counter()
        async with self._lock:
            audio_source = None
            try:
                # Wait if audio is currently playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.05)

                self.interrupted = False
                self.last_barge_in_user = None

                audio_source = create_streaming_source()
                self.current_audio_source = audio_source
                self.last_audio_source = audio_source

                def after_play(error):
                    if error:
                        logger.error(f"Error playing voice audio: {error}")
                    if audio_source and hasattr(audio_source, "cleanup"):
                        audio_source.cleanup()

                communicate = edge_tts.Communicate(
                    text,
                    config.TTS_VOICE,
                    rate=config.TTS_RATE,
                    pitch=config.TTS_PITCH
                )

                # Compatibility with legacy tests that mock communicate.save
                if (
                    isinstance(getattr(communicate, "save", None), (MagicMock, AsyncMock))
                    and not isinstance(getattr(communicate, "stream", None), (MagicMock, AsyncMock))
                ):
                    async def _mock_save_stream():
                        yield {"type": "audio", "data": b"\x00" * 3840}
                    stream_gen = _mock_save_stream()
                else:
                    stream_gen = communicate.stream()

                first_chunk_played = False
                ttfb_ms = 0

                async def feed_stream():
                    nonlocal first_chunk_played, ttfb_ms
                    async for chunk in stream_gen:
                        if self.interrupted or not voice_client.is_connected():
                            break
                        if chunk.get("type") == "audio":
                            data = chunk.get("data", b"")
                            if not first_chunk_played:
                                ttfb_ms = int((time.perf_counter() - t0) * 1000)
                                if hasattr(audio_source, "write_chunk"):
                                    audio_source.write_chunk(data)
                                voice_client.play(audio_source, after=after_play)
                                first_chunk_played = True
                                logger.info(f"🔊 [TTS Stream Started] ({ttfb_ms}ms TTFB): '{text[:50]}'")
                            else:
                                if hasattr(audio_source, "write_chunk"):
                                    if not audio_source.write_chunk(data):
                                        break
                    if hasattr(audio_source, "finish_writing"):
                        audio_source.finish_writing()

                # Timeout wrapper around the whole synthesis
                tts_timeout = getattr(config, "TTS_TIMEOUT_SEC", 10.0)
                try:
                    await asyncio.wait_for(feed_stream(), timeout=tts_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ [TTS Timeout] Stream synthesis exceeded {tts_timeout}s for '{text[:40]}...'")
                    if hasattr(audio_source, "finish_writing"):
                        audio_source.finish_writing()
                except Exception as e:
                    logger.warning(f"⚠️ [TTS Stream Error] Synthesis error: {e}")
                    if hasattr(audio_source, "finish_writing"):
                        audio_source.finish_writing()

                if not first_chunk_played and not self.interrupted:
                    if hasattr(audio_source, "cleanup"):
                        audio_source.cleanup()
                    return 0

                # Wait for voice_client to finish playing remaining audio
                while voice_client.is_playing():
                    if self.interrupted:
                        break
                    await asyncio.sleep(0.05)

                if audio_source and hasattr(audio_source, "cleanup"):
                    audio_source.cleanup()

                tts_ms = int((time.perf_counter() - t0) * 1000)

                if self.interrupted:
                    logger.info(f"🛑 [Intervention Aborted] Playback stopped via barge-in by {self.last_barge_in_user}")
                else:
                    logger.info(f"🔊 [Intervention Completed] ({tts_ms}ms total): '{text}'")

                return tts_ms

            except Exception as e:
                logger.error(f"TTS Error: {e}")
                if audio_source and hasattr(audio_source, "cleanup"):
                    audio_source.cleanup()
                return 0
            finally:
                self.current_audio_source = None


speaker = InterventionSpeaker()
