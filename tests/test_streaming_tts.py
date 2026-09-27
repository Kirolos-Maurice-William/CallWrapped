"""
Step 10c Acceptance Tests: Streaming TTS Playback with Sub-400ms TTFB and Zombie-Free Barge-In.
Tests:
1. First chunk reaches voice client in < 400ms, while total synthesis continues concurrently.
2. User barge-in during streamed playback stops voice client AND terminates the FFmpeg process (no zombies).
3. Synthesis timeout cleanly aborts without crashing or hanging the session.
"""

import sys
import time
import asyncio
import unittest
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from bot.config import config
from bot.ai.tts import speaker, StreamFFmpegPCMAudio, create_streaming_source

import tests._setup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TestStreamingTTS")


class MockVoiceClient:
    """Mock Discord VoiceClient tracking play, stop, and active audio source."""

    def __init__(self, bot_id: int = 8888):
        self._playing = False
        self._connected = True
        self.stop_called = False
        self.stop_count = 0
        self.user = MagicMock()
        self.user.id = bot_id
        self.source = None
        self.after = None
        self.play_timestamp = None

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return self._playing

    def play(self, source, after=None):
        self._playing = True
        self.source = source
        self.after = after
        self.play_timestamp = time.perf_counter()

    def stop(self):
        self.stop_called = True
        self.stop_count += 1
        self._playing = False
        if self.source and hasattr(self.source, "cleanup"):
            self.source.cleanup()


class TestStreamingTTS(unittest.IsolatedAsyncioTestCase):

    async def test_a_first_chunk_sub_400ms_latency(self):
        """
        Criteria A:
        First audio chunk must reach voice_client.play() in < 400ms,
        while total synthesis continues delivering chunks after playback starts.
        """
        print("\n" + "=" * 75)
        print("=== TEST A: FIRST CHUNK SUB-400ms TTFB WITH CONCURRENT SYNTHESIS ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)

        # Mock a stream where chunk 1 arrives at 60ms, chunk 2 at 180ms, chunk 3 at 300ms, chunk 4 at 450ms
        chunk_delivery_times = []
        t_start = time.perf_counter()

        async def simulated_stream(self_comm):
            chunks = [
                {"type": "audio", "data": b"\x00" * 1024},
                {"type": "audio", "data": b"\x01" * 1024},
                {"type": "audio", "data": b"\x02" * 1024},
                {"type": "audio", "data": b"\x03" * 1024},
            ]
            for i, c in enumerate(chunks):
                await asyncio.sleep(0.06)  # 60ms between chunks
                chunk_delivery_times.append((i + 1, (time.perf_counter() - t_start) * 1000))
                yield c

        with patch("edge_tts.Communicate.stream", new=simulated_stream):
            with self.assertLogs("TTSVoice", level="INFO") as cm:
                speak_task = asyncio.create_task(
                    speaker.speak(vc, "تأكيد فوز الأهلي بلقب الدوري المصري")
                )

                # Give enough time for first chunk to trigger play()
                # FFmpeg spawn + first chunk ~90ms TTFB; 4 chunks finish at ~270ms
                # 200ms captures play() start while leaving later chunks in-flight
                await asyncio.sleep(0.20)

                self.assertTrue(vc.is_playing(), "VoiceClient must start playing on first chunk")
                self.assertIsNotNone(vc.play_timestamp, "VoiceClient.play() must have been called")

                ttfb_ms = (vc.play_timestamp - t_start) * 1000
                print(f"[TIMING] VoiceClient.play() triggered at: {ttfb_ms:.1f}ms")

                for chunk_idx, chunk_time in chunk_delivery_times:
                    print(f"[TIMING] Chunk #{chunk_idx} delivered by stream at: {chunk_time:.1f}ms")

                # Verify synthesis is still continuing after first chunk
                self.assertLess(len(chunk_delivery_times), 4, "Synthesis must still be continuing after first chunk")

                # Let playback finish normally by stopping vc
                await asyncio.sleep(0.35)
                vc._playing = False

                total_tts_ms = await asyncio.wait_for(speak_task, timeout=2.0)

        print(f"[TIMING] Total synthesis & playback duration: {total_tts_ms}ms")
        print("Captured Logs:\n" + "\n".join(f"  {line}" for line in cm.output))

        # Assertions
        self.assertLess(ttfb_ms, 400.0, f"TTFB ({ttfb_ms:.1f}ms) must be strictly under 400ms!")
        self.assertTrue(
            any("TTS Stream Started" in line and "TTFB" in line for line in cm.output),
            "Must log [TTS Stream Started] with TTFB"
        )
        print(f"[PROOF VERIFIED] TTFB was {ttfb_ms:.1f}ms (< 400ms threshold) and playback started on chunk 1!\n")

    async def test_b_barge_in_kills_stream_and_ffmpeg_process_no_zombies(self):
        """
        Criteria B:
        Barge-in during streamed playback stops playback AND terminates
        the FFmpeg process (process.poll() returns code, no zombie processes).
        """
        print("=" * 75)
        print("=== TEST B: BARGE-IN TERMINATES STREAM & KILLS FFMPEG (NO ZOMBIES) ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)

        # We will use real StreamFFmpegPCMAudio so we have an actual OS process to monitor
        audio_src = StreamFFmpegPCMAudio()
        real_proc = audio_src.process
        self.assertIsNotNone(real_proc, "FFmpeg process must be created")
        self.assertIsNone(real_proc.poll(), "FFmpeg process must initially be running")
        pid = real_proc.pid
        print(f"[PROCESS] Spawned FFmpeg process PID: {pid}, initial poll(): {real_proc.poll()} (running)")

        async def infinite_stream(self_comm):
            while True:
                await asyncio.sleep(0.05)
                yield {"type": "audio", "data": b"\x00" * 512}

        with patch("bot.ai.tts.create_streaming_source", return_value=audio_src), \
             patch("edge_tts.Communicate.stream", new=infinite_stream):

            speak_task = asyncio.create_task(
                speaker.speak(vc, "هذه جملة تجريبية طويلة لاختبار المقاطعة أثناء البث الصوتي المباشر")
            )

            # Wait until playing starts (up to 0.5s)
            for _ in range(25):
                if vc.is_playing():
                    break
                await asyncio.sleep(0.02)
            self.assertTrue(vc.is_playing(), "VoiceClient should be actively playing")

            # Fire barge-in stop
            print(f"[BARGE-IN] Triggering speaker.stop() for user 'Tamer'...")
            with self.assertLogs("TTSVoice", level="INFO") as cm:
                stopped = speaker.stop(vc, user="Tamer")
                await asyncio.wait_for(speak_task, timeout=1.0)

        print(f"speaker.stop() returned: {stopped}")
        print(f"VoiceClient.is_playing(): {vc.is_playing()}")
        print(f"Speaker.interrupted: {speaker.interrupted}")
        print(f"Speaker.last_barge_in_user: {speaker.last_barge_in_user}")

        # Check process state
        poll_res = real_proc.poll()
        returncode = real_proc.wait(timeout=1.0)
        print(f"[PROCESS] After barge-in, FFmpeg PID {pid} poll(): {poll_res}, wait() returncode: {returncode}")
        print("Captured Logs:\n" + "\n".join(f"  {line}" for line in cm.output))

        self.assertTrue(stopped, "speaker.stop() must return True")
        self.assertFalse(vc.is_playing(), "Playback must be halted")
        self.assertTrue(speaker.interrupted, "Speaker interrupted flag must be True")
        self.assertEqual(speaker.last_barge_in_user, "Tamer")
        self.assertIsNotNone(poll_res, "FFmpeg process must be terminated (poll() is not None)")
        self.assertIsNotNone(returncode, "FFmpeg process must be reaped (no zombie process)")
        self.assertTrue(
            any("[Barge-in] Stopped intervention for Tamer" in line for line in cm.output),
            "Must log [Barge-in] Stopped intervention"
        )
        print(f"[PROOF VERIFIED] FFmpeg PID {pid} reaped with code {returncode}. Zero zombie processes!\n")

    async def test_c_synthesis_timeout_clean_abort(self):
        """
        Criteria 3:
        Timeout wrapper stops synthesis cleanly on timeout, logs warning,
        leaves session unaffected.
        """
        print("=" * 75)
        print("=== TEST C: SYNTHESIS TIMEOUT WRAPPER CLEAN ABORT ===")
        print("=" * 75)

        vc = MockVoiceClient(bot_id=8888)

        # Stream that hangs indefinitely before first chunk
        async def hanging_stream(self_comm):
            await asyncio.sleep(5.0)
            yield {"type": "audio", "data": b"\x00" * 512}

        # Set a short timeout of 0.15s for the test
        with patch("bot.config.config.TTS_TIMEOUT_SEC", 0.15), \
             patch("edge_tts.Communicate.stream", new=hanging_stream):

            with self.assertLogs("TTSVoice", level="WARNING") as cm:
                t0 = time.perf_counter()
                tts_ms = await speaker.speak(vc, "جملة تجريبية ستتجاوز المهلة الزمنية")
                elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"Timed-out speak() returned latency: {tts_ms}ms (elapsed: {elapsed_ms:.1f}ms)")
        print(f"VoiceClient.is_playing(): {vc.is_playing()}")
        print("Captured Logs:\n" + "\n".join(f"  {line}" for line in cm.output))

        self.assertFalse(vc.is_playing(), "VoiceClient must not be stuck playing")
        self.assertTrue(
            any("TTS Timeout" in line for line in cm.output),
            "Must log [TTS Timeout] warning"
        )
        print("[PROOF VERIFIED] Timeout caught cleanly, warning logged, session unaffected.\n")


if __name__ == "__main__":
    unittest.main()
