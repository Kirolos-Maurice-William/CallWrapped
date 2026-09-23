import tests._setup

import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.main import manual_arbitrate


class TestFix6ArbitrateKeys(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for Fix 6:
    - Pass mock verdict with only 'selected_source_url', assert link appears in embed.
    - Pass status='UNVERIFIABLE' (uppercase), assert early return without embed.
    """

    async def test_selected_source_url_appears_in_embed(self):
        ctx = AsyncMock()
        ctx.guild.id = 123456
        ctx.author.display_name = "Kareem"
        mock_msg = AsyncMock()
        ctx.send = AsyncMock(return_value=mock_msg)

        mock_verdict = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "RTX 5070 has 12GB VRAM",
            "selected_source_url": "https://nvidia.com/rtx-5070",
            "selected_source_title": "NVIDIA RTX 5070 Specs",
            "confidence": 99,
            "spoken_intervention": "Correction: RTX 5070 has 12GB VRAM."
        }

        with patch("bot.main.arbitration_verifier.verify_dispute", new_callable=AsyncMock) as mock_verify, \
             patch("bot.main.publisher.publish_sync_task", MagicMock()):

            mock_verify.return_value = (mock_verdict, 150, 120, [])

            await manual_arbitrate(ctx, query="RTX 5070 has 16GB")

            mock_msg.edit.assert_called_once()
            edit_kwargs = mock_msg.edit.call_args.kwargs
            self.assertIn("embed", edit_kwargs, "Must edit message with an embed")
            embed = edit_kwargs["embed"]
            self.assertIn("https://nvidia.com/rtx-5070", embed.description, "selected_source_url must appear in embed link")
            self.assertIn("NVIDIA RTX 5070 Specs", embed.description)
            print("\n--- FIX 6 ACCEPTANCE 1: Embed contains selected_source_url ---")
            print(f"Embed description:\n{embed.description}")

    async def test_unverifiable_case_insensitive_early_return(self):
        ctx = AsyncMock()
        ctx.guild.id = 123457
        ctx.author.display_name = "Kareem"
        mock_msg = AsyncMock()
        ctx.send = AsyncMock(return_value=mock_msg)

        mock_verdict = {
            "status": "UNVERIFIABLE",
            "speaker_a_status": "UNVERIFIABLE",
            "speaker_b_status": "UNVERIFIABLE",
            "correct_fact": "",
            "confidence": 0
        }

        with patch("bot.main.arbitration_verifier.verify_dispute", new_callable=AsyncMock) as mock_verify, \
             patch("bot.main.publisher.publish_sync_task", MagicMock()) as mock_publish:

            mock_verify.return_value = (mock_verdict, 200, 100, [])

            await manual_arbitrate(ctx, query="Mysterious unprovable claim")

            mock_msg.edit.assert_called_once()
            edit_kwargs = mock_msg.edit.call_args.kwargs
            content = edit_kwargs.get("content", "")
            self.assertIn("Unable to conclusively verify", content)
            self.assertNotIn("embed", edit_kwargs, "Must not send verdict embed for UNVERIFIABLE")
            mock_publish.assert_not_called()
            print("\n--- FIX 6 ACCEPTANCE 2: Case-insensitive UNVERIFIABLE early returns ---")
            print(f"Edited message content: {content}")


if __name__ == "__main__":
    unittest.main()
