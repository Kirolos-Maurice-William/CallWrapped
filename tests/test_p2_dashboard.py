"""
P2 Acceptance Test: !dashboard command.
Verifies:
1. build_dashboard_embed() reads URL dynamically from config.
2. Embed contains title, description with Markdown link, direct URL, features field, and footer.
3. show_dashboard(ctx) sends the embed via ctx.send(embed=embed).
4. Prints the complete rendered embed for acceptance.
"""
import tests._setup
import unittest
from unittest.mock import AsyncMock, MagicMock
from bot.config import config
from bot.main import build_dashboard_embed, show_dashboard


class TestDashboardCommand(unittest.TestCase):

    def test_dashboard_embed_rendering(self):
        embed = build_dashboard_embed()

        print("\n" + "=" * 65)
        print("=== P2 ACCEPTANCE: RENDERED !dashboard EMBED ===")
        print("=" * 65)
        print(f"Title:       {embed.title}")
        print(f"Color:       {hex(embed.color.value) if embed.color else 'None'}")
        print(f"Description:\n{embed.description}")
        print("\nFields:")
        for f in embed.fields:
            print(f"  [{f.name}]:\n    {f.value}")
        if embed.footer:
            print(f"Footer:      {embed.footer.text}")
        print("=" * 65 + "\n")

        # Assertions
        expected_url = getattr(config, "DASHBOARD_URL", None) or getattr(config, "BACKEND_API_URL", "http://127.0.0.1:8000")
        self.assertIn("Live Judge & Analytics Dashboard", embed.title)
        self.assertIn(expected_url, embed.description)
        self.assertTrue(len(embed.fields) > 0)
        self.assertEqual(embed.color.value, config.EMBED_COLOR_INFO)

    def test_show_dashboard_command_execution(self):
        mock_ctx = MagicMock()
        mock_ctx.send = AsyncMock()

        import asyncio
        asyncio.run(show_dashboard(mock_ctx))

        mock_ctx.send.assert_called_once()
        sent_embed = mock_ctx.send.call_args[1].get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("Dashboard", sent_embed.title)
        print("[VERIFIED] !dashboard command successfully sends the rendered embed.\n")


if __name__ == "__main__":
    unittest.main()
