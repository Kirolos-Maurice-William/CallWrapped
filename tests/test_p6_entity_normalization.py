"""
P6 Acceptance: Entity normalization in ClaimMemory.
Tests that canonicalize_entity strips Arabic articles (ال), English articles,
and common noun prefixes (كارت، لعبة، فيلم) for substring matching.
"""
import tests._setup
import unittest
from bot.arbitration.claim_memory import ClaimMemory, canonicalize_entity


class TestEntityNormalization(unittest.TestCase):

    def test_canonicalize_entity_cases(self):
        """Verify canonicalize strips articles and prefixes correctly."""
        cases = [
            ("الكارت RTX 5070", "rtx 5070"),
            ("RTX 5070", "rtx 5070"),
            ("the RTX 5070", "rtx 5070"),
            ("لعبة GTA 6", "gta 6"),
            ("GTA 6", "gta 6"),
            ("فيلم ولاد رزق", "ولاد رزق"),
            ("الأهلي", "أهلي"),
            (None, ""),
            ("", ""),
        ]
        print("\n" + "=" * 60)
        print("=== P6: ENTITY NORMALIZATION CASES ===")
        print("=" * 60)
        for raw, expected in cases:
            result = canonicalize_entity(raw)
            print(f"  {str(raw):25s} → '{result}' (expected '{expected}')")
            self.assertEqual(result, expected, f"canonicalize_entity({raw!r}) should be {expected!r}, got {result!r}")
        print("=" * 60)

    def test_claim_memory_normalized_entity_match(self):
        """
        Acceptance: 'الكارت RTX 5070' from speaker A must match 'rtx 5070'
        from speaker B via canonicalized entity comparison.
        """
        print("\n" + "=" * 60)
        print("=== P6 ACCEPTANCE: CROSS-ENTITY MATCH ===")
        print("=" * 60)

        mem = ClaimMemory(capacity=10)

        # Speaker A stores claim with Arabic prefix
        mem.add_claim(
            claim_id="c1",
            speaker_name="Ahmed",
            speaker_id="100",
            raw_text="الكارت RTX 5070 نازل بـ 16 جيجا",
            claim_text="RTX 5070 has 16GB",
            entity="الكارت RTX 5070",
            topic="tech",
            metric="16 جيجا"
        )

        # Speaker B queries with bare entity
        match = mem.find_relevant_prior_claim(
            new_speaker_id="200",
            entity="rtx 5070",
            topic="tech",
            metric="12 جيجا",
            raw_text="كارت الـ RTX 5070 نازل بـ 12 جيجا بس"
        )

        self.assertIsNotNone(match, "Must find prior claim: 'الكارت RTX 5070' should match 'rtx 5070'")
        print(f"  Prior claim found: speaker={match.speaker_name}, entity='{match.entity}'")
        print(f"  Queried entity: 'rtx 5070'")
        print(f"  Canonical prior: '{canonicalize_entity(match.entity)}'")
        print(f"  Canonical query: '{canonicalize_entity('rtx 5070')}'")
        print("  [MATCH VERIFIED] ✅")
        print("=" * 60)

    def test_claim_memory_clear(self):
        """Verify ClaimMemory.clear() empties all claims."""
        mem = ClaimMemory(capacity=10)
        mem.add_claim("c1", "A", "1", "text", "claim", "entity", "topic", "metric")
        mem.add_claim("c2", "B", "2", "text2", "claim2", "entity2", "topic2", "metric2")
        self.assertEqual(len(mem.claims), 2)
        mem.clear()
        self.assertEqual(len(mem.claims), 0, "Claims must be empty after clear()")
        print("\n[VERIFIED] ClaimMemory.clear() empties all claims.")


if __name__ == "__main__":
    unittest.main()
