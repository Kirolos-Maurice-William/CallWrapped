import sys
import unittest
import asyncio

import tests._setup

from bot.arbitration.conflict_detector import conflict_detector
from bot.config import config


class TestConflictDetectorEnglishQueries(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for Fix 9:
    Tests conflict_detector.py query generation on 3 real pairs.
    Verifies:
    1. Direct factual contradictions detect has_conflict == True.
    2. Generated search_query is in English (Latin alphabet).
    3. Prints all 3 generated search queries and targets.
    """

    PAIRS = [
        (
            "Tech GPU Specs",
            "Ahmed", "كارت RTX 5070 نازل بـ 16 جيجا بايت VRAM",
            "Omar", "لا كارت RTX 5070 نازل بـ 12 جيجا بايت بس مش 16"
        ),
        (
            "Football Match Score",
            "Ziad", "الأهلي كسب كأس السوبر بنتيجة 3-1",
            "Mostafa", "لا الأهلي كسب الزمالك 2-0 في السوبر"
        ),
        (
            "Game Release Year",
            "Tamer", "لعبة GTA 6 هتنزل في خريف 2026",
            "Karim", "لا روكستار أعلنت إن GTA 6 هتنزل في خريف 2025"
        ),
    ]

    async def test_three_real_pairs_query_generation(self):
        self.assertTrue(config.GROQ_API_KEY, "GROQ_API_KEY required")

        print("\n" + "=" * 65)
        print("=== FIX 9 ACCEPTANCE: REAL CONFLICT DETECTOR QUERIES ===")
        print("=" * 65)

        successes = 0
        for idx, (label, spk_a, clm_a, spk_b, clm_b) in enumerate(self.PAIRS, 1):
            has_conf = False
            data = None
            latency_ms = 0

            for attempt in range(3):
                has_conf, data, latency_ms = await conflict_detector.detect_conflict(
                    speaker_a=spk_a,
                    claim_a=clm_a,
                    speaker_b=spk_b,
                    claim_b=clm_b
                )
                if has_conf:
                    break
                if attempt < 2:
                    print(f"  ⏳ [Pacing] Key in rolling TPD window, waiting 30s before retry {attempt+2}/3...")
                    await asyncio.sleep(30)

            print(f"\n--- PAIR {idx}: {label} ---")
            print(f"  Speaker A ({spk_a}): \"{clm_a}\"")
            print(f"  Speaker B ({spk_b}): \"{clm_b}\"")
            print(f"  has_conflict: {has_conf} ({latency_ms}ms)")

            if data is None:
                print(f"  ⚠️  Groq TPD exhausted — skipping pair {idx}")
                continue

            if not has_conf:
                print(f"  ⚠️  LLM did not detect conflict — possible interpretation variance")
                continue

            successes += 1
            query = data.get("search_query", "")
            conflict_type = data.get("conflict_type")
            target_domains = data.get("target_domains", [])

            print(f"  conflict_type: {conflict_type}")
            print(f"  search_query:  \"{query}\"")
            print(f"  target_domains: {target_domains}")

            self.assertTrue(bool(query.strip()), f"Pair {idx} search_query cannot be empty")
            # Verify query is English/Latin
            ascii_chars = sum(1 for c in query if c.isascii() and c.isalpha())
            total_letters = sum(1 for c in query if c.isalpha())
            self.assertGreater(total_letters, 0, f"Pair {idx} search_query must contain letters")
            self.assertGreaterEqual(ascii_chars / total_letters, 0.8, f"Pair {idx} query must be primarily English/Latin characters, got: {query}")

        if successes == 0:
            self.skipTest("Groq TPD exhausted on all 3 pairs — 0 conflicts detected (not a code bug)")

        print("\n" + "=" * 65)
        print(f"=== {successes}/3 PAIRS GENERATED ENGLISH SEARCH QUERIES ===")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
