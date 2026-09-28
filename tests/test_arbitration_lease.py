import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.arbitration.engine import arbitration_engine, ArbitrationLease, SessionState, PendingOffer
from bot.config import config


class TestArbitrationLease(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild_id = 998877
        self.session = arbitration_engine.get_session(self.guild_id)
        self.session.reset()

    def tearDown(self):
        self.session.reset()

    async def test_lease_normal_lifecycle(self):
        """Verifies ArbitrationLease sets is_arbitrating=True and resets to False upon exit."""
        self.assertFalse(self.session.is_arbitrating)
        async with ArbitrationLease(arbitration_engine, self.guild_id, self.session):
            self.assertTrue(self.session.is_arbitrating)
        self.assertFalse(self.session.is_arbitrating)

    async def test_lease_resets_state_on_unhandled_exception(self):
        """Verifies lease guarantees is_arbitrating=False and pending_offer=None even when exception occurs."""
        self.session.pending_offer = MagicMock(spec=PendingOffer)
        try:
            async with ArbitrationLease(arbitration_engine, self.guild_id, self.session):
                self.assertTrue(self.session.is_arbitrating)
                raise RuntimeError("Simulated unexpected crash during arbitration")
        except RuntimeError:
            pass

        self.assertFalse(self.session.is_arbitrating)
        self.assertIsNone(self.session.pending_offer)

    async def test_lease_drains_queue_on_exit(self):
        """Verifies lease triggers _drain_queue on completion."""
        # Enqueue dummy utterances
        self.session.pending_utterances.append({
            "user_id": 123,
            "speaker_name": "Tamer",
            "raw_text": "queued utterance 1",
            "stt_ms": 100,
            "voice_client": None,
            "text_channel": None,
            "mode": "referee",
            "t_start": time.monotonic(),
            "correlation_id": "test_corr_1"
        })

        drain_called = asyncio.Event()

        async def mock_drain(gid, sess):
            sess.pending_utterances.clear()
            drain_called.set()

        with patch.object(arbitration_engine, "_drain_queue", side_effect=mock_drain):
            async with ArbitrationLease(arbitration_engine, self.guild_id, self.session):
                self.assertEqual(len(self.session.pending_utterances), 1)

        self.assertTrue(drain_called.is_set())
        self.assertEqual(len(self.session.pending_utterances), 0)
        self.assertFalse(self.session.is_arbitrating)

    async def test_confirm_dispute_offer_watchdog_timeout(self):
        """Verifies watchdog timeout prevents bot from going deaf if confirmation stalls."""
        mock_offer = MagicMock(spec=PendingOffer)
        mock_offer.offer_id = "off_timeout_test"
        mock_offer.is_confirmed = False
        mock_offer.is_resolved = False
        mock_offer.expiry_task = None
        mock_offer.voice_client = None
        mock_offer.text_channel = None

        # Simulate a stalled confirmation cycle that never finishes
        async def stall_confirmation(*args, **kwargs):
            await asyncio.sleep(10.0)

        with patch.object(config, "DISPUTE_CONFIRM_TOTAL_TIMEOUT_SEC", 0.05):
            with patch.object(arbitration_engine, "_execute_confirmation_cycle", side_effect=stall_confirmation):
                t0 = time.monotonic()
                await arbitration_engine.confirm_dispute_offer(
                    guild_id=self.guild_id,
                    confirmation_end_time=time.time(),
                    confirmed_by="Tester",
                    target_offer=mock_offer
                )
                elapsed = time.monotonic() - t0

        # Assert watchdog fired quickly (< 0.5s instead of hanging for 10s)
        self.assertLess(elapsed, 0.5)
        # Assert session state recovered cleanly
        self.assertFalse(self.session.is_arbitrating)
        self.assertIsNone(self.session.pending_offer)


if __name__ == "__main__":
    unittest.main()
