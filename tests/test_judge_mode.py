import tests._setup
import unittest
import asyncio
from bot.arbitration.judge_mode import run_judge_mode_harness


class TestJudgeMode(unittest.IsolatedAsyncioTestCase):
    """
    Phase 4 Acceptance:
    - 7-Card Judge Attack Mode harness executes with scripted inputs and real pipeline outputs.
    - Card 1: Opinion rejected
    - Card 2: Agreement has no conflict
    - Card 3: Real dispute verified with ground truth web search
    - Card 4: Private entity refused without search
    - Card 5: Weak/ambiguous rejected
    - Card 6: Barge-in stops playback and reaps ffmpeg
    - Card 7: PII redaction exhibit via AssemblyAI
    """

    async def test_judge_mode_harness_all_cards(self):
        results = await run_judge_mode_harness(verbose=True)
        self.assertEqual(len(results), 7, "Must execute all 7 cards")

        for r in results:
            self.assertTrue(
                r["passed"],
                f"Card {r.get('card')}: {r.get('name')} failed. Actual: {r.get('actual')}"
            )


if __name__ == "__main__":
    unittest.main()
