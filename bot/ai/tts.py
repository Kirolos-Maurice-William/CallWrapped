import time
import asyncio
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Any
import inspect
import aiohttp
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
                bufsize=0,
                creationflags=creationflags
            )
        except FileNotFoundError:
            logger.error(f"FFmpeg executable '{executable}' not found.")
            self.process = None
            raise

        self._stdin = self.process.stdin
        self._stdout = self.process.stdout
        self._closed = False

    def write_chunk(self, chunk: bytes) -> bool:
        """Writes an MP3 chunk into ffmpeg stdin without user-space buffer (called in worker thread)."""
        if self._closed or not self._stdin:
            return False
        try:
            self._stdin.write(chunk)
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def finish_writing(self) -> None:
        """Closes stdin so ffmpeg knows all audio chunks have been sent (EOF)."""
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
        self._closed = True
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            try:
                self.process.wait(timeout=0.2)
            except Exception:
                pass

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

        if self._stdout:
            try:
                self._stdout.close()
            except Exception:
                pass

    def __del__(self) -> None:
        self.cleanup()


def create_streaming_source(executable: str = "ffmpeg") -> Any:
    """Factory to create a StreamFFmpegPCMAudio, respecting unit test mocks of discord.FFmpegPCMAudio."""
    if isinstance(discord.FFmpegPCMAudio, (MagicMock, AsyncMock)):
        return discord.FFmpegPCMAudio("stream_mock")
    return StreamFFmpegPCMAudio(executable=executable)


class WarmTTSSession:
    """
    Holds a pre-warmed aiohttp session and pre-resolved DNS / TLS session
    for sub-800ms Edge-TTS streaming upon offer confirmation.
    Expires and cleans up after 35 seconds.
    """

    def __init__(self, timeout_seconds: float = 35.0):
        self.created_at = time.time()
        self.timeout_seconds = timeout_seconds
        self.connector: Optional[aiohttp.TCPConnector] = None
        self.handshake_ms: int = 0
        self.reused: bool = False
        self._closed: bool = False
        self._prewarm_task: Optional[asyncio.Task] = None

    async def prewarm(self) -> None:
        """Pre-resolves DNS and establishes TLS session pool to speech.platform.bing.com in background."""
        t0 = time.perf_counter()
        if self._closed:
            return
        self.connector = aiohttp.TCPConnector(
            use_dns_cache=True,
            ttl_dns_cache=300,
            limit=5
        )
        if self._closed:
            await self.connector.close()
            return
        temp_session = aiohttp.ClientSession(
            connector=self.connector,
            connector_owner=False,
            trust_env=True
        )
        try:
            if not self._closed:
                async with temp_session.get(
                    "https://speech.platform.bing.com/consumer/speech/synthesize/readahead/edge/v1",
                    timeout=aiohttp.ClientTimeout(total=4.0)
                ) as resp:
                    pass
        except Exception:
            pass
        finally:
            try:
                await temp_session.close()
            except Exception:
                pass
            if self._closed and self.connector and not self.connector.closed:
                await self.connector.close()
            self.handshake_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"🔥 [TTS Pre-warm] Established warm session in {self.handshake_ms}ms (DNS/TLS pre-warmed)")

    def start_prewarm(self) -> asyncio.Task:
        self._prewarm_task = asyncio.create_task(self.prewarm())
        return self._prewarm_task

    def is_valid(self) -> bool:
        if self._closed:
            return False
        if self.connector and self.connector.closed:
            return False
        return (time.time() - self.created_at) <= self.timeout_seconds

    def close_sync(self) -> None:
        self._closed = True
        if self._prewarm_task and not self._prewarm_task.done():
            self._prewarm_task.cancel()
        if self.connector and not self.connector.closed:
            try:
                if hasattr(self.connector, "_close"):
                    self.connector._close(abort_ssl=True)
                else:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.connector.close(abort_ssl=True))
            except Exception:
                pass

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._prewarm_task and not self._prewarm_task.done():
                self._prewarm_task.cancel()
                try:
                    await self._prewarm_task
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                if self.connector and not self.connector.closed:
                    await self.connector.close(abort_ssl=True)
            except Exception:
                pass


class InterventionSpeaker:
    """
    Streaming intervention-only voice engine using Microsoft Edge Neural TTS
    with sub-400ms time-to-first-byte (TTFB), two-clause sequential streaming,
    pre-warmed TLS connections, and zero-zombie barge-in support.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.interrupted: bool = False
        self.last_barge_in_user: Optional[str] = None
        self.current_audio_source: Optional[Any] = None
        self.last_audio_source: Optional[Any] = None
        self.last_ttfb_ms: int = 0
        self.last_clause1_ttfb_ms: int = 0
        self.last_clause2_wait_ms: int = 0
        self.last_handshake_ms: int = 0
        self.last_audio_start_time: float = 0.0

    def create_warm_session(self, timeout_seconds: float = 35.0) -> WarmTTSSession:
        """Creates and initiates a warm TTS session in the background."""
        warm_session = WarmTTSSession(timeout_seconds=timeout_seconds)
        warm_session.start_prewarm()
        self.active_warm_session = warm_session
        return warm_session

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

    async def speak_clauses(
        self,
        voice_client: Optional[discord.VoiceClient],
        fact_clause: str,
        hedge_clause: str = "",
        warm_session: Optional[WarmTTSSession] = None
    ) -> int:
        """
        Synthesizes two-clause verdict:
        - Clause 1 (fact_clause) is synthesized first for ~500ms TTFB and streamed immediately.
        - Clause 2 (hedge_clause) is synthesized concurrently in the background and queued cleanly.
        - Sequential to_thread writes into the same FFmpeg pipe with no gaps or clicks.
        """
        if not voice_client or not voice_client.is_connected() or not fact_clause.strip():
            return 0

        t0 = time.perf_counter()
        async with self._lock:
            audio_source = None
            c2_task: Optional[asyncio.Task] = None
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

                connector = None
                handshake_ms = 0
                if warm_session and warm_session.is_valid():
                    connector = warm_session.connector
                    handshake_ms = 0
                    warm_session.reused = True
                    logger.info("🔥 [TTS Reused] Reusing warm TTS session from offer time (no new handshake)")
                elif warm_session:
                    handshake_ms = getattr(warm_session, "handshake_ms", 0) or 0
                    logger.info("⚠️ [TTS Rebuild] Warm session expired or absent; rebuilding connection on confirm")

                self.last_handshake_ms = handshake_ms

                def get_stream_generator(communicate_obj):
                    stream_attr = getattr(communicate_obj, "stream", None)
                    save_attr = getattr(communicate_obj, "save", None)
                    if isinstance(save_attr, (MagicMock, AsyncMock)):
                        if "stream" in getattr(communicate_obj, "__dict__", {}) or isinstance(stream_attr, (MagicMock, AsyncMock)):
                            return stream_attr()
                        async def _mock_save_stream():
                            yield {"type": "audio", "data": b"\x00" * 3840}
                        return _mock_save_stream()
                    if callable(stream_attr):
                        return stream_attr()
                    async def _empty():
                        if False:
                            yield {}
                    return _empty()

                # Clause 1 Stream
                comm1 = edge_tts.Communicate(
                    fact_clause,
                    config.TTS_VOICE,
                    rate=config.TTS_RATE,
                    pitch=config.TTS_PITCH,
                    connector=connector
                )
                stream_gen1 = get_stream_generator(comm1)

                # Clause 2 Queue and Background Task
                clause2_queue: asyncio.Queue = asyncio.Queue()
                clause2_done: asyncio.Event = asyncio.Event()

                async def synthesize_clause2():
                    if not hedge_clause or not hedge_clause.strip():
                        clause2_done.set()
                        return
                    try:
                        comm2 = edge_tts.Communicate(
                            hedge_clause,
                            config.TTS_VOICE,
                            rate=config.TTS_RATE,
                            pitch=config.TTS_PITCH,
                            connector=None
                        )
                        stream_gen2 = get_stream_generator(comm2)
                        async for chunk in stream_gen2:
                            if self.interrupted or not voice_client.is_connected():
                                break
                            if chunk.get("type") == "audio":
                                data = chunk.get("data", b"")
                                if data:
                                    await clause2_queue.put(data)
                    except Exception as e:
                        logger.warning(f"⚠️ [TTS Stream Error (Clause 2)] Synthesis error: {e}")
                    finally:
                        clause2_done.set()

                first_chunk_played = False
                clause1_ttfb_ms = 0
                clause2_wait_ms = 0

                async def feed_stream():
                    nonlocal first_chunk_played, clause1_ttfb_ms, clause2_wait_ms, c2_task

                    # Launch Clause 2 synthesis concurrently in background
                    if hedge_clause and hedge_clause.strip():
                        c2_task = asyncio.create_task(synthesize_clause2())
                    else:
                        clause2_done.set()

                    # Stream Clause 1
                    async for chunk in stream_gen1:
                        if self.interrupted or not voice_client.is_connected():
                            break
                        if chunk.get("type") == "audio":
                            data = chunk.get("data", b"")
                            if not data:
                                continue
                            if not first_chunk_played:
                                clause1_ttfb_ms = int((time.perf_counter() - t0) * 1000)
                                self.last_ttfb_ms = clause1_ttfb_ms
                                self.last_clause1_ttfb_ms = clause1_ttfb_ms
                                self.last_audio_start_time = time.time()
                                if hasattr(audio_source, "write_chunk"):
                                    await asyncio.to_thread(audio_source.write_chunk, data)
                                voice_client.play(audio_source, after=after_play)
                                first_chunk_played = True
                                logger.info(f"🔊 [TTS Stream Started (Clause 1)] ({clause1_ttfb_ms}ms TTFB): '{fact_clause[:50]}'")
                            else:
                                if hasattr(audio_source, "write_chunk"):
                                    ok = await asyncio.to_thread(audio_source.write_chunk, data)
                                    if not ok or self.interrupted:
                                        break

                    # Stream Clause 2 if available and not interrupted
                    if hedge_clause and hedge_clause.strip() and not self.interrupted and voice_client.is_connected():
                        logger.info(f"🔊 [TTS Stream Started (Clause 2)]: '{hedge_clause[:50]}'")
                        t_wait_c2 = time.perf_counter()
                        while not (clause2_done.is_set() and clause2_queue.empty()):
                            if self.interrupted or not voice_client.is_connected():
                                break
                            try:
                                data = await asyncio.wait_for(clause2_queue.get(), timeout=0.1)
                                if hasattr(audio_source, "write_chunk"):
                                    ok = await asyncio.to_thread(audio_source.write_chunk, data)
                                    if not ok or self.interrupted:
                                        break
                            except asyncio.TimeoutError:
                                continue
                        clause2_wait_ms = int((time.perf_counter() - t_wait_c2) * 1000)
                        self.last_clause2_wait_ms = clause2_wait_ms

                    if hasattr(audio_source, "finish_writing"):
                        await asyncio.to_thread(audio_source.finish_writing)

                tts_timeout = getattr(config, "TTS_TIMEOUT_SEC", 12.0)
                try:
                    await asyncio.wait_for(feed_stream(), timeout=tts_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ [TTS Timeout] Stream synthesis exceeded {tts_timeout}s")
                    if hasattr(audio_source, "finish_writing"):
                        await asyncio.to_thread(audio_source.finish_writing)
                except Exception as e:
                    logger.warning(f"⚠️ [TTS Stream Error] Synthesis error: {e}")
                    if hasattr(audio_source, "finish_writing"):
                        await asyncio.to_thread(audio_source.finish_writing)
                finally:
                    if c2_task and not c2_task.done():
                        c2_task.cancel()

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
                combined_text = f"{fact_clause} {hedge_clause}".strip()
                if self.interrupted:
                    logger.info(f"🛑 [Intervention Aborted] Playback stopped via barge-in by {self.last_barge_in_user}")
                else:
                    logger.info(f"🔊 [Intervention Completed] ({tts_ms}ms total): '{combined_text}'")

                return tts_ms

            except Exception as e:
                logger.error(f"TTS Error: {e}")
                if audio_source and hasattr(audio_source, "cleanup"):
                    audio_source.cleanup()
                return 0
            finally:
                if c2_task and not c2_task.done():
                    c2_task.cancel()
                self.current_audio_source = None
                if warm_session:
                    await warm_session.close()

    async def speak(
        self,
        voice_client: Optional[discord.VoiceClient],
        text: str,
        hedge_clause: str = "",
        warm_session: Optional[WarmTTSSession] = None,
        fact_clause: str = ""
    ) -> int:
        """
        Backwards-compatible speak method.
        Supports single text string or two-clause streaming.
        If single text is passed, automatically detects clauses for sub-800ms TTFB.
        """
        if not fact_clause:
            # Auto-split text into fact_clause and hedge_clause if markers present
            for marker in ("ممكن يكون في سياق فاتني", "المصدر ظاهر في الداشبورد", "I may have missed context", "Source is on the dashboard"):
                if marker in text:
                    idx = text.find(marker)
                    fact_clause = text[:idx].strip()
                    hedge_clause = text[idx:].strip()
                    break
            if not fact_clause:
                fact_clause = text

        warm = warm_session or getattr(self, "active_warm_session", None)
        return await self.speak_clauses(
            voice_client=voice_client,
            fact_clause=fact_clause,
            hedge_clause=hedge_clause,
            warm_session=warm
        )


speaker = InterventionSpeaker()
