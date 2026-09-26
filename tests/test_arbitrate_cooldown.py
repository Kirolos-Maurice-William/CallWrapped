import tests._setup

import time
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bot.main import manual_arbitrate
from bot.arbitration import arbitration_engine


class TestArbitrateCooldown(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for INV-01:
    - Create an offer via !arbitrate.
    - Let it expire / cancel.
    - Immediately !arbitrate again -> suppressed with remaining-time message, 0 speech, no new offer.
    - Simulate cooldown elapsed -> offer created successfully.
    """

    def setUp(self):
        self.guild_id = 888999
        arbitration_engine.sessions.pop(self.guild_id, None)

    async def test_arbitrate_cooldown_suppression_and_elapsed(self):
        ctx = AsyncMock()
        ctx.guild.id = self.guild_id
        ctx.author.id = 12345
        ctx.author.display_name = "Adel"
        ctx.channel = AsyncMock()
        ctx.send = AsyncMock()

        with patch("bot.main.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.main.publisher.publish_sync_task"):

            # Step 1: Initial !arbitrate creates offer
            await manual_arbitrate(ctx, query="RTX 5070 has 16GB")
            session = arbitration_engine.get_session(self.guild_id)
            self.assertIsNotNone(session.pending_offer)
            initial_offer_id = session.pending_offer.offer_id
            self.assertEqual(session.pending_offer.claim_a, "RTX 5070 has 16GB")
            mock_speak.assert_not_called()
            first_msg = ctx.send.call_args[0][0]
            self.assertIn("RTX 5070 has 16GB", first_msg)
            print("\n" + "=" * 65)
            print("=== STEP 1: INITIAL !arbitrate CREATED OFFER ===")
            print(f"Offer ID: {initial_offer_id}")
            print(f"Message: {first_msg[:80]}...")

            # Step 2: Simulate offer expiration
            session.pending_offer.cancel()
            self.assertTrue(session.pending_offer.is_resolved)

            # Step 3: Immediately !arbitrate again -> must be suppressed with remaining time
            ctx.send.reset_mock()
            await manual_arbitrate(ctx, query="RTX 5070 has 12GB")

            mock_speak.assert_not_called()
            ctx.send.assert_called_once()
            suppressed_msg = ctx.send.call_args[0][0]
            self.assertIn("فترة التهدئة نشطة", suppressed_msg)
            self.assertIn("Cooldown active", suppressed_msg)
            # Offer must NOT be replaced
            self.assertEqual(session.pending_offer.offer_id, initial_offer_id)
            print("\n" + "=" * 65)
            print("=== STEP 2: IMMEDIATE !arbitrate SUPPRESSED IN COOLDOWN ===")
            print(f"Suppressed Response: {suppressed_msg}")
            print("Zero speech called, no new offer created.")

            # Step 4: Simulate cooldown elapsed (181 seconds past)
            session.last_offer_time = time.time() - 181.0
            ctx.send.reset_mock()
            await manual_arbitrate(ctx, query="RTX 5070 has 12GB")

            mock_speak.assert_not_called()
            ctx.send.assert_called_once()
            allowed_msg = ctx.send.call_args[0][0]
            self.assertIn("RTX 5070 has 12GB", allowed_msg)
            self.assertNotEqual(session.pending_offer.offer_id, initial_offer_id)
            self.assertEqual(session.pending_offer.claim_a, "RTX 5070 has 12GB")
            print("\n" + "=" * 65)
            print("=== STEP 3: COOLDOWN ELAPSED -> NEW OFFER CREATED ===")
            print(f"New Offer ID: {session.pending_offer.offer_id}")
            print(f"Message: {allowed_msg[:80]}...")
            print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
