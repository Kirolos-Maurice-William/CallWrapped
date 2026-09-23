import sys
import unittest

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from bot.arbitration.engine import SessionState
from bot.main import build_stats_embed, build_status_embed, GuildContext


class TestStatsAndStatusRendering(unittest.TestCase):
    def test_populated_session_stats_render(self):
        """Verify rendering !stats embed from populated session does not crash and formats keys properly."""
        session = SessionState(guild_id=999888)
        session.verified_claims_count = 4
        session.disputed_claims_count = 2
        session.unverifiable_count = 1

        # Real session format populated by engine.py (turns, verified, refuted)
        session.speaker_stats["Alice"] = {"turns": 7, "verified": 3, "refuted": 1}
        session.speaker_stats["Bob"] = {"turns": 4, "verified": 1, "refuted": 1}

        embed = build_stats_embed(session)
        self.assertIsNotNone(embed)
        self.assertEqual(embed.title, "📊 Server Insights & Evidence Leaderboard")
        self.assertIn("• **Verified Claims:** `4`", embed.description)
        self.assertIn("• **Disputed Claims:** `2`", embed.description)

        # Print rendered embed content for acceptance proof
        print("\n" + "=" * 60)
        print("=== RENDERED !stats EMBED (POPULATED SESSION) ===")
        print("=" * 60)
        print(f"Title: {embed.title}")
        print(f"Description:\n{embed.description}")
        print("Fields:")
        for f in embed.fields:
            print(f"  Field: {f.name}\n    {f.value}")
        print("=" * 60)

        # Assertions on fields
        fields_dict = {f.name: f.value for f in embed.fields}
        self.assertIn("👤 Alice", fields_dict)
        self.assertIn("• Total Turns: `7`", fields_dict["👤 Alice"])
        self.assertIn("• Verified Facts: `✅ 3`", fields_dict["👤 Alice"])
        self.assertIn("• Refuted Claims: `❌ 1`", fields_dict["👤 Alice"])

        self.assertIn("👤 Bob", fields_dict)
        self.assertIn("• Total Turns: `4`", fields_dict["👤 Bob"])
        self.assertIn("• Verified Facts: `✅ 1`", fields_dict["👤 Bob"])
        self.assertIn("• Refuted Claims: `❌ 1`", fields_dict["👤 Bob"])

    def test_empty_session_stats_render(self):
        """Verify rendering !stats on an empty session without errors."""
        session = SessionState(guild_id=999889)
        embed = build_stats_embed(session)
        self.assertEqual(len(embed.fields), 1)
        self.assertEqual(embed.fields[0].name, "Participants")
        self.assertEqual(embed.fields[0].value, "No voice activity recorded yet.")

    def test_status_embed_render(self):
        """Verify rendering !status embed defensively."""
        session = SessionState(guild_id=999890)
        guild_ctx = GuildContext(guild_id=999890)
        guild_ctx.mode = "referee"
        embed = build_status_embed(guild_ctx, session, ping_ms=42)
        self.assertEqual(embed.title, "⚙️ Voice Arbitrator — Operational Status")
        fields_dict = {f.name: f.value for f in embed.fields}
        self.assertIn("⚡ Bot Ping", fields_dict)
        self.assertEqual(fields_dict["⚡ Bot Ping"], "`42ms`")
        self.assertIn("🛡️ Active Mode", fields_dict)
        self.assertEqual(fields_dict["🛡️ Active Mode"], "`REFEREE`")


if __name__ == "__main__":
    unittest.main()
