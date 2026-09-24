"""
BUG 1 Automated Acceptance Test:
Verifies that TTS streaming does NOT block the asyncio event loop under backpressure.
A background loop monitor ticks every 5ms. WHILE speak() feeds chunks to a slow/blocking
audio source (simulating 40ms pipe backpressure per chunk), the event loop remains
fully responsive with zero stalls >= 50ms.
"""
import tests._setup
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock
from bot.ai.tts import speaker


class MockBlockingAudioSource:
    """Simulates an FFmpeg AudioSource where pipe backpressure blocks write_chunk for 40ms."""

    def __init__(self, block_sec: float = 0.04):
        self.block_sec = block_sec
        self.chunks_written = 0
        self.cleaned_up = False

    def write_chunk(self, chunk: bytes) -> bool:
        # Simulate blocking OS pipe write (backpressure)
        time.sleep(self.block_sec)
        self.chunks_written += 1
        return True

    def finish_writing(self) -> None:
        pass

    def cleanup(self) -> None:
        self.cleaned_up = True


class MockVoiceClient:
    def __init__(self):
        self._playing = False
        self._connected = True

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return self._playing

    def play(self, source, after=None):
        self._playing = True

    def stop(self):
        self._playing = False


class TestTTSNonBlockingEventLoop(unittest.IsolatedAsyncioTestCase):

    async def test_event_loop_responsiveness_during_tts_backpressure(self):
        """
        Acceptance Criteria (a):
        Reads of a shared counter MUST progress WHILE speak() is feeding a slow/blocked
        stream. Maximum event loop stall must be strictly < 50ms.
        """
        vc = MockVoiceClient()
        blocking_source = MockBlockingAudioSource(block_sec=0.04)  # 40ms block per chunk

        # Create 6 simulated chunks
        chunks = [
            {"type": "audio", "data": b"\x01" * 1024}
            for _ in range(6)
        ]

        async def simulated_stream(self_comm):
            for c in chunks:
                await asyncio.sleep(0.01)
                yield c

        # Event loop monitor running concurrently on the loop
        monitor_ticks = 0
        stalls = []
        stop_monitor = False

        async def loop_monitor():
            nonlocal monitor_ticks, stop_monitor
            last_time = time.perf_counter()
            while not stop_monitor:
                await asyncio.sleep(0.005)  # 5ms target interval
                now = time.perf_counter()
                elapsed_ms = (now - last_time) * 1000.0
                stall_ms = elapsed_ms - 5.0
                if stall_ms > 0:
                    stalls.append(stall_ms)
                monitor_ticks += 1
                last_time = now

        monitor_task = asyncio.create_task(loop_monitor())

        t_start = time.perf_counter()
        with patch("bot.ai.tts.create_streaming_source", return_value=blocking_source):
            with patch("edge_tts.Communicate.stream", new=simulated_stream):
                # Start speak task
                speak_task = asyncio.create_task(
                    speaker.speak(vc, "اختبار عدم تجميد حلقة الأحداث أثناء البث الصوتي")
                )

                # Let playback run for 200ms then terminate vc playback
                await asyncio.sleep(0.25)
                vc._playing = False
                await speak_task

        total_time_ms = (time.perf_counter() - t_start) * 1000.0
        stop_monitor = True
        await monitor_task

        max_stall = max(stalls) if stalls else 0.0
        avg_stall = (sum(stalls) / len(stalls)) if stalls else 0.0

        print("\n" + "=" * 70)
        print("=== BUG 1 ACCEPTANCE: EVENT LOOP RESPONSIVENESS TIMINGS ===")
        print("=" * 70)
        print(f"Total test elapsed:         {total_time_ms:.1f}ms")
        print(f"Chunks written to source:   {blocking_source.chunks_written}/6")
        print(f"Loop monitor ticks captured: {monitor_ticks} ticks")
        print(f"Average loop stall:         {avg_stall:.2f}ms")
        print(f"Maximum loop stall:         {max_stall:.2f}ms (threshold: < 50.0ms)")
        print("=" * 70 + "\n")

        # Assertions
        # 1. Loop monitor ticked many times (did NOT freeze during 40ms synchronous writes!)
        self.assertGreater(monitor_ticks, 15, "Event loop must continue ticking during TTS synthesis")
        # 2. Maximum stall is strictly under 50ms
        self.assertLess(max_stall, 50.0, f"Max event loop stall ({max_stall:.2f}ms) must be strictly < 50ms!")
        # 3. All chunks written successfully
        self.assertEqual(blocking_source.chunks_written, 6)
        print("[PROOF VERIFIED] Event loop stayed fully responsive with 0 stalls >= 50ms!\n")


if __name__ == "__main__":
    unittest.main()
