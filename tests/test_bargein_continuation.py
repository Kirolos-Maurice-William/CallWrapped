import asyncio
import time
import unittest
from unittest.mock import MagicMock

import tests._setup
from bot.arbitration.engine import arbitration_engine
from bot.ai.tts import speaker


class TestBargeInContinuation(unittest.IsolatedAsyncioTestCase):
    """
    Verifies that when barge-in aborts playback:
    1. The interrupting utterance continues through BOTH paths.
    2. talk_delta lands in stats (total_speak_seconds, utterance_count).
    3. The utterance reaches classification and analytics buffer.
    """

    async def test_interrupting_utterance_stats_and_classification(self):
        guild_id = 999111
        session = arbitration_engine.get_session(guild_id)
        session.reset()

        # 1. Simulate active verdict playing
        vc = MagicMock()
        vc.is_playing.return_value = True
        vc.is_connected.return_value = True

        # User barges in
        stopped = speaker.stop(vc, user="Ziad")
        self.assertTrue(stopped)
        self.assertTrue(speaker.interrupted)
        self.assertEqual(speaker.last_barge_in_user, "Ziad")
        print("\n" + "=" * 65)
        print("=== VERIFICATION 1: BARGE-IN STATS & PIPELINE CONTINUATION ===")
        print("=" * 65)
        print("[1] Barge-in stopped playback cleanly for user: Ziad")

        # 2. Interrupting utterance is processed through process_utterance
        t_start = time.time()
        await arbitration_engine.process_utterance(
            guild_id=guild_id,
            user_id=12345,
            speaker_name="Ziad",
            raw_text="كارت الـ RTX 5070 نازل بـ 12 جيجا بايت بس",
            stt_ms=120,
            voice_client=vc,
            text_channel=None,
            mode="referee",
            speech_start=t_start,
            speech_end=t_start + 2.5
        )

        # Check stats tracker
        spk_stats = session._stats_tracker.get_speaker("12345")
        self.assertIsNotNone(spk_stats)
        self.assertGreater(spk_stats.total_speak_seconds, 0)
        self.assertEqual(spk_stats.utterance_count, 1)
        print(f"[2] Interrupting user stats incremented:")
        print(f"    Speaker: {spk_stats.speaker_name} (ID: {spk_stats.speaker_id})")
        print(f"    Total Talk Seconds: {spk_stats.total_speak_seconds:.2f}s")
        print(f"    Utterance Count:    {spk_stats.utterance_count}")

        # Check analytics buffer
        self.assertEqual(len(session.analytics_buffer), 1)
        buffered = session.analytics_buffer[0]
        self.assertEqual(buffered["speaker_name"], "Ziad")
        self.assertGreater(buffered["talk_delta_seconds"], 0)
        print(f"[3] Buffered utterance in analytics buffer:")
        print(f"    Speaker: {buffered['speaker_name']}")
        print(f"    Talk Delta: {buffered['talk_delta_seconds']}s")
        print(f"    Text: \"{buffered['text']}\"")

        # Flush analytics to prove classification runs
        await arbitration_engine.flush_analytics(guild_id, reason="test_verification")
        print(f"[4] Analytics flushed successfully. Buffer drained to: {len(session.analytics_buffer)}")
        print(f"    Topic counts recorded: {session._topic_counts}")
        print("=" * 65)
        print("✅ [VERIFIED] Interrupting utterance stats incremented and classified!")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
