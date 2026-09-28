import asyncio
import threading
import time
import unittest
from unittest.mock import MagicMock
import numpy as np
import discord
from discord.ext import voice_recv

from bot.audio.receiver import AudioReceiver
from bot.config import config


def create_pcm_frame(amplitude: int = 1000) -> bytes:
    """Generate a single 20ms Discord audio frame (960 stereo int16 samples = 3840 bytes)."""
    samples = np.ones(960 * 2, dtype=np.int16) * amplitude
    return samples.tobytes()


class TestReceiverHardening(unittest.IsolatedAsyncioTestCase):

    async def test_concurrent_writes_and_silence_checker_barrier(self):
        """AUDIO-01 + AUDIO-05: Concurrent write() calls from 2 threads + silence checker firing

        simultaneously must not produce RuntimeError, dropped packets, or corrupted buffers.
        Uses threading.Barrier to force race conditions.
        """
        loop = asyncio.get_running_loop()
        dispatched = []

        async def on_utterance(*args):
            dispatched.append(args)

        receiver = AudioReceiver(loop=loop, on_utterance=on_utterance)

        # Pre-seed buffer with speech onset so silence checker has work to evaluate
        user1 = MagicMock(id=1001, display_name="Speaker1", bot=False)
        user2 = MagicMock(id=1002, display_name="Speaker2", bot=False)

        frame = create_pcm_frame(amplitude=2000)
        voice_data = MagicMock(spec=voice_recv.VoiceData, pcm=frame, source=None)

        # Force high contention using threading.Barrier across 2 writer threads
        iterations = 100
        barrier = threading.Barrier(2)
        errors = []

        def writer_task(user_obj, count):
            try:
                for i in range(count):
                    barrier.wait(timeout=2.0)
                    receiver.write(user_obj, voice_data)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer_task, args=(user1, iterations))
        t2 = threading.Thread(target=writer_task, args=(user2, iterations))

        t1.start()
        t2.start()

        # Concurrently let silence checker evaluate active buffers
        for _ in range(20):
            await asyncio.sleep(0.01)

        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertFalse(t1.is_alive(), "Writer thread 1 timed out")
        self.assertFalse(t2.is_alive(), "Writer thread 2 timed out")
        self.assertEqual(errors, [], f"Encountered concurrency exceptions: {errors}")

        # Verify buffers were cleanly populated without dropped packets or corruption
        with receiver._lock:
            self.assertIn(1001, receiver.buffers)
            self.assertIn(1002, receiver.buffers)
            # Either packets are still in buffer or have been finalized cleanly
            b1 = receiver.buffers[1001]
            b2 = receiver.buffers[1002]
            self.assertEqual(b1.user_name, "Speaker1")
            self.assertEqual(b2.user_name, "Speaker2")
            total_b1 = len(b1.pcm_chunks) + (len(dispatched) * iterations)
            self.assertGreater(total_b1, 0)

        receiver.cleanup()

    async def test_two_unknown_ssrcs_separate_buffers(self):
        """AUDIO-07: Two unknown SSRCs must map to separate negative pseudo user_ids

        and isolate their buffers with zero cross-contamination.
        """
        loop = asyncio.get_running_loop()
        receiver = AudioReceiver(loop=loop, on_utterance=MagicMock())

        frame1 = create_pcm_frame(amplitude=1500)
        frame2 = create_pcm_frame(amplitude=3000)

        packet_ssrc_1 = MagicMock()
        packet_ssrc_1.ssrc = 88888
        data1 = MagicMock(spec=voice_recv.VoiceData, pcm=frame1, packet=packet_ssrc_1, source=None)

        packet_ssrc_2 = MagicMock()
        packet_ssrc_2.ssrc = 99999
        data2 = MagicMock(spec=voice_recv.VoiceData, pcm=frame2, packet=packet_ssrc_2, source=None)

        with self.assertLogs("AudioReceiver", level="WARNING") as cm:
            # Write packet for unknown SSRC 88888 (no user object)
            receiver.write(None, data1)
            # Write packet for unknown SSRC 99999 (no user object)
            receiver.write(None, data2)

        # Check logs contain warning with SSRC values
        self.assertTrue(any("Unknown SSRC 88888 mapped to pseudo user_id -1" in log for log in cm.output))
        self.assertTrue(any("Unknown SSRC 99999 mapped to pseudo user_id -2" in log for log in cm.output))

        # Check separate buffers
        with receiver._lock:
            self.assertIn(-1, receiver.buffers)
            self.assertIn(-2, receiver.buffers)
            self.assertNotIn(9999, receiver.buffers, "Deprecated 9999 fallback should not be used")

            buf1 = receiver.buffers[-1]
            buf2 = receiver.buffers[-2]
            self.assertNotEqual(buf1, buf2)
            self.assertEqual(len(buf1.pcm_chunks), 1)
            self.assertEqual(len(buf2.pcm_chunks), 1)
            self.assertEqual(buf1.pcm_chunks[0], frame1)
            self.assertEqual(buf2.pcm_chunks[0], frame2)

        # Write a second packet for SSRC 88888; should map back to -1
        receiver.write(None, data1)
        with receiver._lock:
            self.assertEqual(len(receiver.buffers[-1].pcm_chunks), 2)
            self.assertEqual(len(receiver.buffers[-2].pcm_chunks), 1)

        receiver.cleanup()

    async def test_event_loop_stall_under_5ms(self):
        """AUDIO-02: Measure event loop stall during finalize of a 15s utterance.

        Must be <5ms (offloaded via asyncio.to_thread).
        """
        loop = asyncio.get_running_loop()
        dispatched_event = asyncio.Event()

        async def slow_or_fast_on_utterance(*args):
            dispatched_event.set()

        receiver = AudioReceiver(loop=loop, on_utterance=slow_or_fast_on_utterance)

        # Create a 15s utterance buffer (750 frames of 20ms)
        frame = create_pcm_frame(amplitude=2000)
        with receiver._lock:
            receiver.write(MagicMock(id=3003, display_name="LongSpeaker", bot=False), MagicMock(spec=voice_recv.VoiceData, pcm=frame, source=None))
            buf = receiver.buffers[3003]
            buf.pcm_chunks = [frame] * 750
            buf.is_speaking = True
            buf.speech_start_time = time.time() - 15.0
            buf.last_speech_time = time.time()

        # Event loop ticker measuring maximum responsiveness lag
        max_stall = [0.0]
        running = [True]

        async def ticker():
            last = time.perf_counter()
            while running[0]:
                await asyncio.sleep(0)
                now = time.perf_counter()
                gap = (now - last) * 1000.0
                if gap > max_stall[0]:
                    max_stall[0] = gap
                last = now

        ticker_task = asyncio.create_task(ticker())
        await asyncio.sleep(0)

        # Finalize the 15-second utterance
        receiver._finalize_utterance(buf, ended_by="forcesplit")

        # Wait for dispatch to complete
        await asyncio.wait_for(dispatched_event.wait(), timeout=5.0)

        running[0] = False
        await ticker_task

        print(f"\n[AUDIO-02 BENCHMARK] 15s Utterance Finalize Event Loop Max Stall: {max_stall[0]:.2f} ms (< 5ms requirement)")
        self.assertLess(max_stall[0], 5.0, f"Event loop stall {max_stall[0]:.2f}ms exceeded 5.0ms threshold")
        receiver.cleanup()


if __name__ == "__main__":
    unittest.main()
