import tests._setup

import time
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.main import manual_arbitrate
from bot.arbitration import arbitration_engine


class TestFix6ArbitrateKeys(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for Fix 6:
    - Test !arbitrate creates offer with zero direct TTS.
    - Confirm offer via confirm_dispute_offer, assert link appears in verdict embed.
    - For UNVERIFIABLE verdict, confirm_dispute_offer returns early without verdict embed.
    """

    def setUp(self):
        arbitration_engine.sessions.pop(123456, None)

    async def test_selected_source_url_appears_in_embed(self):
        ctx = AsyncMock()
        ctx.guild.id = 123456
        ctx.author.id = 456789
        ctx.author.display_name = "Kareem"
        ctx.channel = AsyncMock()
        ctx.send = AsyncMock()

        mock_verdict = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "fact_clause": "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16.",
            "hedge_clause": "المصدر ظاهر في الداشبورد.",
            "selected_source_url": "https://nvidia.com/rtx-5070",
            "selected_source_title": "NVIDIA RTX 5070 Specs",
            "confidence": 99,
        }

        with patch("bot.main.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock) as mock_synth, \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock):

            mock_synth.return_value = (mock_verdict, 150, 120, [{"url": "https://nvidia.com/rtx-5070", "title": "NVIDIA RTX 5070 Specs"}])

            # Step 1: !arbitrate creates offer
            await manual_arbitrate(ctx, query="RTX 5070 has 16GB")

            # Assert offer sent to chat, zero direct TTS
            ctx.send.assert_called_once()
            offer_text = ctx.send.call_args[0][0]
            self.assertIn("RTX 5070 has 16GB", offer_text)
            mock_speak.assert_not_called()

            # Step 2: Confirm offer
            await arbitration_engine.confirm_dispute_offer(
                guild_id=ctx.guild.id,
                confirmation_end_time=time.time(),
                confirmed_by="Kareem",
                text_channel=ctx.channel
            )

            # Assert verdict embed contains selected_source_url
            ctx.channel.send.assert_called_once()
            embed = ctx.channel.send.call_args.kwargs.get("embed")
            self.assertIsNotNone(embed)
            self.assertIn("https://nvidia.com/rtx-5070", embed.description)
            self.assertIn("NVIDIA RTX 5070 Specs", embed.description)
            print("\n--- FIX 6 ACCEPTANCE 1: Embed contains selected_source_url ---")
            print(f"Embed description:\n{embed.description}")

    async def test_unverifiable_case_insensitive_early_return(self):
        ctx = AsyncMock()
        ctx.guild.id = 123457
        ctx.author.id = 456790
        ctx.author.display_name = "Kareem"
        ctx.channel = AsyncMock()
        ctx.send = AsyncMock()

        mock_verdict = {
            "status": "UNVERIFIABLE",
            "speaker_a_status": "UNVERIFIABLE",
            "speaker_b_status": "UNVERIFIABLE",
            "confidence": 0
        }

        with patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = (mock_verdict, 200, 100, [])

            # Step 1: !arbitrate creates offer
            await manual_arbitrate(ctx, query="Mysterious unprovable claim")

            # Step 2: Confirm offer
            await arbitration_engine.confirm_dispute_offer(
                guild_id=ctx.guild.id,
                confirmation_end_time=time.time(),
                confirmed_by="Kareem",
                text_channel=ctx.channel
            )

            session = arbitration_engine.get_session(ctx.guild.id)
            self.assertEqual(session.unverifiable_count, 1)
            ctx.channel.send.assert_called_once()
            embed = ctx.channel.send.call_args.kwargs.get("embed")
            self.assertIsNotNone(embed)
            self.assertIn("تعذر التحقق", embed.description)
            print("\n--- FIX 6 ACCEPTANCE 2: Case-insensitive UNVERIFIABLE delivers fallback notice ---")


if __name__ == "__main__":
    unittest.main()
