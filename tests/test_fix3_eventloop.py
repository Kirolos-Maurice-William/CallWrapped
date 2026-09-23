import sys
import time
import asyncio
import unittest
import logging

import tests._setup

from bot.arbitration.engine import SessionState, arbitration_engine
from bot.main import render_recap


class TestEventLoopFreezeAndRecap(unittest.IsolatedAsyncioTestCase):

    async def test_a_reading_stats_tracker_does_not_block_loop(self):
        """
        Acceptance Test (a):
        Reading stats_tracker and topic_counts with a populated buffer must NOT block
        the asyncio event loop. Proves loop delay < 50ms during property reads.
        """
        session = SessionState(guild_id=888111)
        # Populate buffer with mock pending items
        for i in range(10):
            session.analytics_buffer.append({
                "timestamp": time.time(),
                "speaker_id": "user_1",
                "speaker_name": "User 1",
                "user_id": 101,
                "text": f"Sample pending utterance {i}",
                "talk_delta_seconds": 3.0,
                "streak_seconds": 3.0,
                "correlation_id": "corr_test"
            })

        max_ticker_delay_ms = 0.0
        stop_ticker = False

        async def ticker():
            nonlocal max_ticker_delay_ms, stop_ticker
            while not stop_ticker:
                t_tick_start = time.perf_counter()
                await asyncio.sleep(0.005)
                delay_ms = (time.perf_counter() - t_tick_start - 0.005) * 1000.0
                if delay_ms > max_ticker_delay_ms:
                    max_ticker_delay_ms = delay_ms

        ticker_task = asyncio.create_task(ticker())

        t_reads_start = time.perf_counter()
        # Perform 50 consecutive property reads with pending buffer items
        for _ in range(50):
            st = session.stats_tracker
            tc = session.topic_counts
            _ = st.speakers
            _ = tc
            await asyncio.sleep(0.001)

        total_read_elapsed_ms = (time.perf_counter() - t_reads_start) * 1000.0
        stop_ticker = True
        await ticker_task

        print("\n" + "=" * 65)
        print("=== ACCEPTANCE TEST (A): EVENT LOOP RESPONSIVENESS ===")
        print("=" * 65)
        print(f"Total time for 50 property reads + yields: {total_read_elapsed_ms:.3f}ms")
        print(f"Max loop ticker latency delay observed:  {max_ticker_delay_ms:.3f}ms (Budget: < 50ms)")
        print("=" * 65)

        self.assertLess(max_ticker_delay_ms, 50.0, "Event loop ticker delay exceeded 50ms!")
        # Buffer must remain untouched by simple property reads
        self.assertEqual(len(session.analytics_buffer), 10)

    async def test_b_recap_includes_buffered_unflushed_utterances(self):
        """
        Acceptance Test (b):
        !recap command awaits flush_analytics before calling render_recap,
        guaranteeing all buffered utterances are flushed to Groq and rendered.
        """
        guild_id = 888222
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        # Add 3 utterances that populate the analytics buffer
        utterances = [
            {
                "speaker_name": "Tamer",
                "user_id": 301,
                "text": "عمرو دياب نزل ألبوم جديد اسمه مكانك وفيه أغاني جامدة جدا",
                "speech_start": 0.0,
                "speech_end": 4.5
            },
            {
                "speaker_name": "Mostafa",
                "user_id": 302,
                "text": "الجون التاني في ماتش السوبر الأهلي جابه بمهارة عالية قوي",
                "speech_start": 5.0,
                "speech_end": 9.8
            },
            {
                "speaker_name": "Tamer",
                "user_id": 301,
                "text": "أنا مبسوط وفرحان جدا باليوم اللطيف ده",
                "speech_start": 10.5,
                "speech_end": 14.0
            }
        ]

        for u in utterances:
            await arbitration_engine.process_utterance(
                guild_id=guild_id,
                user_id=u["user_id"],
                speaker_name=u["speaker_name"],
                raw_text=u["text"],
                stt_ms=150,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=u["speech_start"],
                speech_end=u["speech_end"]
            )

        print("\n" + "=" * 65)
        print("=== ACCEPTANCE TEST (B): !recap AWAIT-FLUSH GUARANTEE ===")
        print("=" * 65)
        print(f"Buffer size before !recap: {len(session.analytics_buffer)}")
        self.assertEqual(len(session.analytics_buffer), 3, "Buffer must hold 3 pending utterances before recap")

        # Simulate !recap command execution (await flush then pure sync render)
        if session.analytics_buffer:
            await arbitration_engine.flush_analytics(guild_id, reason="recap_render")

        self.assertEqual(len(session.analytics_buffer), 0, "Buffer must be empty after recap flush")

        recap_text = render_recap(session)
        print(f"Buffer size after recap: {len(session.analytics_buffer)}")
        print("\nRendered Recap Output:\n" + recap_text)
        print("=" * 65)

        self.assertIn("Tamer", recap_text)
        self.assertIn("Mostafa", recap_text)
        self.assertIn("ملخص المكالمة", recap_text)
        self.assertNotIn("No data yet in this call.", recap_text)

    def test_c_session_reset_logs_warning_when_buffer_not_empty(self):
        """
        Acceptance Test Amendment 3:
        SessionState.reset() must log a warning with the dropped count if buffer is non-empty.
        """
        session = SessionState(guild_id=888333)
        session.analytics_buffer.append({"text": "dropping item 1"})
        session.analytics_buffer.append({"text": "dropping item 2"})

        with self.assertLogs("ArbitrationEngine", level="WARNING") as cm:
            session.reset()

        self.assertEqual(len(session.analytics_buffer), 0)
        self.assertTrue(any("Dropping 2 un-flushed analytics utterances" in msg for msg in cm.output))
        print("\n[Amendment 3 Test] Warning logged as expected on reset with 2 items:")
        print("  " + cm.output[0])


if __name__ == "__main__":
    unittest.main()
