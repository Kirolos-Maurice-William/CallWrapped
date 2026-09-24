"""
P1 Acceptance Test: Privacy Trio.
Verifies:
a) On voice-channel join: bot posts a short Arabic notice that it analyzes the call
   live (talk time, topics, frustration signals, fact-checking with web search) and
   stores nothing after the session ends.
b) !privacy command: explains live analysis, zero retention, and that anger/frustration
   is an automated AI inference that may be mistaken.
c) !leave command: bot disconnects AND clears the session, reusing reset drop warnings
   if buffer non-empty (never silent drops).
"""
import tests._setup
import unittest
from unittest.mock import AsyncMock, MagicMock
from bot.arbitration.engine import arbitration_engine
from bot.main import (
    build_privacy_notice_text,
    build_join_embed,
    build_privacy_embed,
    show_privacy,
    leave_channel,
    get_guild_context
)


class TestPrivacyTrio(unittest.TestCase):

    def test_a_join_privacy_notice(self):
        """Test (a): Arabic privacy notice rendered on voice channel join."""
        notice_text = build_privacy_notice_text()
        embed = build_join_embed(channel_name="General Voice", mode="referee")

        print("\n" + "=" * 65)
        print("=== P1 (A) ACCEPTANCE: ARABIC PRIVACY NOTICE ON JOIN ===")
        print("=" * 65)
        print(f"Notice Text:\n{notice_text}\n")
        print(f"Join Embed Title: {embed.title}")
        print(f"Join Embed Fields:")
        for f in embed.fields:
            print(f"  [{f.name}]:\n    {f.value}")
        print("=" * 65)

        # Assertions
        self.assertIn("وقت التحدث", notice_text)
        self.assertIn("المواضيع", notice_text)
        self.assertIn("نوبات الإحباط", notice_text)
        self.assertIn("التحقق من الحقائق", notice_text)
        self.assertIn("لا يتم حفظ أو تخزين", notice_text)

        # Notice is part of the join embed
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("الخصوصية" in name for name in field_names))
        field_values = [f.value for f in embed.fields]
        self.assertTrue(any(notice_text in val for val in field_values))

    def test_b_privacy_command(self):
        """Test (b): !privacy command flow and embed explanation."""
        embed = build_privacy_embed()

        print("\n" + "=" * 65)
        print("=== P1 (B) ACCEPTANCE: !privacy COMMAND EMBED ===")
        print("=" * 65)
        print(f"Title:       {embed.title}")
        print(f"Description:\n{embed.description}\n")
        for f in embed.fields:
            print(f"Field [{f.name}]:\n  {f.value}")
        if embed.footer:
            print(f"Footer:      {embed.footer.text}")
        print("=" * 65)

        # Assertions
        # 1. Real-time analysis explained
        self.assertIn("تحليل لحظي فقط", embed.description)
        # 2. Zero retention explained
        self.assertIn("انعدام التخزين الدائم", embed.description)
        # 3. Frustration / emotion inference disclaimer
        self.assertIn("تنويه نوبات الإحباط", embed.description)
        self.assertIn("تقدير آلي", embed.description)

        # Test command execution
        mock_ctx = MagicMock()
        mock_ctx.send = AsyncMock()

        import asyncio
        asyncio.run(show_privacy(mock_ctx))
        mock_ctx.send.assert_called_once()
        sent_embed = mock_ctx.send.call_args[1].get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertEqual(sent_embed.title, embed.title)

    def test_c_leave_command_disconnects_and_resets_session(self):
        """Test (c): !leave disconnects voice AND clears session with drop warnings."""
        guild_id = 777999
        session = arbitration_engine.get_session(guild_id)
        guild_ctx = get_guild_context(guild_id)

        # Populate session state
        session.turns.append({"speaker": "Tamer", "text": "Some speech turn"})
        session.verified_claims_count = 2
        session.analytics_buffer.append({"speaker": "Tamer", "text": "Buffered utterance"})
        session.pending_utterances.append({"speaker": "Karim", "text": "Queued utterance"})
        session.claim_memory.add_claim("c1", "Tamer", "1", "raw", "claim", "entity", "topic", "metric")

        # Mock voice client
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()
        guild_ctx.voice_client = mock_vc

        mock_sink = MagicMock()
        guild_ctx.sink = mock_sink

        mock_ctx = MagicMock()
        mock_ctx.guild.id = guild_id
        mock_ctx.send = AsyncMock()

        print("\n" + "=" * 65)
        print("=== P1 (C) ACCEPTANCE: !leave DISCONNECT & SESSION RESET ===")
        print("=" * 65)

        import asyncio
        with self.assertLogs("ArbitrationEngine", level="WARNING") as cm:
            asyncio.run(leave_channel(mock_ctx))

        print("Logged drop warnings (never silent drops):")
        for log in cm.output:
            print(f"  {log}")

        print(f"\nPost-leave session state:")
        print(f"  Turns count:         {len(session.turns)}")
        print(f"  Claim memory items:  {len(session.claim_memory.claims)}")
        print(f"  Analytics buffer:    {len(session.analytics_buffer)}")
        print(f"  Pending queue:       {len(session.pending_utterances)}")
        print(f"  Voice disconnected:  {mock_vc.disconnect.called}")
        print(f"  Sink cleaned up:     {mock_sink.cleanup.called}")
        print(f"  Bot message:         {mock_ctx.send.call_args[0][0]}")
        print("=" * 65 + "\n")

        # Assertions
        # 1. Session completely reset
        self.assertEqual(len(session.turns), 0)
        self.assertEqual(len(session.claim_memory.claims), 0)
        self.assertEqual(len(session.analytics_buffer), 0)
        self.assertEqual(len(session.pending_utterances), 0)
        self.assertEqual(session.verified_claims_count, 0)

        # 2. Voice disconnected & sink cleaned up
        mock_vc.disconnect.assert_called_once()
        mock_sink.cleanup.assert_called_once()
        mock_ctx.send.assert_called_once()

        # 3. Drop warnings were logged (never silent drops)
        warning_text = " ".join(cm.output)
        self.assertIn("Dropping 1 un-flushed analytics utterances", warning_text)
        self.assertIn("Dropping 1 queued arbitration utterances", warning_text)


if __name__ == "__main__":
    unittest.main()
