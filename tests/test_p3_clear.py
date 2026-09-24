"""
P3 Acceptance Test: !clear full reset.
Verifies:
1. session.reset() clears session turns, speaker stats, analytics_buffer.
2. claim_memory is completely emptied.
3. arbitration pending_utterances queue is emptied.
4. Drop warnings are logged when analytics_buffer or queue are non-empty at reset.
5. Invoking clear_session(ctx) resets all state and sends confirmation message.
"""
import tests._setup
import unittest
from unittest.mock import AsyncMock, MagicMock
from bot.arbitration.engine import arbitration_engine, SessionState
from bot.main import clear_session


class TestClearFullReset(unittest.TestCase):

    def test_clear_session_empties_all_state_and_warns(self):
        guild_id = 999888
        session = arbitration_engine.get_session(guild_id)

        # 1. Populate session with rich data
        session.turns.append({"speaker": "Ahmed", "text": "RTX 5070 has 16GB"})
        session.verified_claims_count = 3
        session.disputed_claims_count = 2
        session.unverifiable_count = 1
        session.speaker_stats["Ahmed"] = {"turns": 5, "verified": 2, "refuted": 1}

        # Populate analytics buffer (should trigger drop warning)
        session.analytics_buffer.append({"speaker": "Ahmed", "text": "Buffer item 1"})
        session.analytics_buffer.append({"speaker": "Omar", "text": "Buffer item 2"})

        # Populate pending utterances queue (should trigger drop warning)
        session.pending_utterances.append({"speaker": "Ziad", "text": "Queued item 1"})

        # Populate claim memory
        session.claim_memory.add_claim(
            claim_id="c_test_1",
            speaker_name="Ahmed",
            speaker_id="101",
            raw_text="RTX 5070 has 16GB",
            claim_text="5070 16GB",
            entity="RTX 5070",
            topic="tech",
            metric="16GB"
        )
        session.claim_memory.add_claim(
            claim_id="c_test_2",
            speaker_name="Omar",
            speaker_id="102",
            raw_text="GTA 6 launches 2025",
            claim_text="GTA 6 2025",
            entity="GTA 6",
            topic="gaming",
            metric="2025"
        )

        # Verify populated state
        self.assertEqual(len(session.claim_memory.claims), 2)
        self.assertEqual(len(session.pending_utterances), 1)
        self.assertEqual(len(session.analytics_buffer), 2)
        self.assertEqual(len(session.turns), 1)

        print("\n" + "=" * 65)
        print("=== P3: PRE-CLEAR POPULATED STATE ===")
        print("=" * 65)
        print(f"  Turns count:              {len(session.turns)}")
        print(f"  Claim memory items:       {len(session.claim_memory.claims)}")
        print(f"  Queued utterances:        {len(session.pending_utterances)}")
        print(f"  Analytics buffer items:   {len(session.analytics_buffer)}")
        print(f"  Verified/Disputed counts: {session.verified_claims_count}/{session.disputed_claims_count}")

        # 2. Execute clear_session(ctx)
        mock_ctx = MagicMock()
        mock_ctx.guild.id = guild_id
        mock_ctx.send = AsyncMock()

        import asyncio
        with self.assertLogs("ArbitrationEngine", level="WARNING") as cm:
            asyncio.run(clear_session(mock_ctx))

        print("\n" + "=" * 65)
        print("=== P3: LOGGED DROP WARNINGS DURING RESET ===")
        print("=" * 65)
        for log in cm.output:
            print(f"  {log}")

        print("\n" + "=" * 65)
        print("=== P3: POST-CLEAR STATE ===")
        print("=" * 65)
        print(f"  Turns count:              {len(session.turns)}")
        print(f"  Claim memory items:       {len(session.claim_memory.claims)}")
        print(f"  Queued utterances:        {len(session.pending_utterances)}")
        print(f"  Analytics buffer items:   {len(session.analytics_buffer)}")
        print(f"  Verified/Disputed counts: {session.verified_claims_count}/{session.disputed_claims_count}")
        print(f"  Bot confirmation message: {mock_ctx.send.call_args[0][0]}")
        print("=" * 65 + "\n")

        # 3. Assert full clean reset
        self.assertEqual(len(session.claim_memory.claims), 0, "Claim memory MUST be empty after !clear")
        self.assertEqual(len(session.pending_utterances), 0, "Arbitration queue MUST be empty after !clear")
        self.assertEqual(len(session.analytics_buffer), 0, "Analytics buffer MUST be empty after !clear")
        self.assertEqual(len(session.turns), 0, "Turns MUST be empty after !clear")
        self.assertEqual(session.verified_claims_count, 0)
        self.assertEqual(session.disputed_claims_count, 0)

        # 4. Assert both drop warnings were emitted
        warning_text = " ".join(cm.output)
        self.assertIn("Dropping 2 un-flushed analytics utterances", warning_text)
        self.assertIn("Dropping 1 queued arbitration utterances", warning_text)
        mock_ctx.send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
