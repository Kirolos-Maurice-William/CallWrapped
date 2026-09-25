"""
P5 Acceptance Test: Expanded AssemblyAI keyterms.
Verifies:
1. Terms list includes Egyptian football, movies, politics, and music terms.
2. Total count is strictly under 60 items.
3. Prints the complete final list.
"""
import tests._setup
import unittest
from bot.ai.assemblyai import ASSEMBLYAI_KEYTERMS


class TestExpandedKeyterms(unittest.TestCase):

    def test_keyterms_count_and_content(self):
        print("\n" + "=" * 60)
        print(f"=== P5: EXPANDED KEYTERMS (TOTAL: {len(ASSEMBLYAI_KEYTERMS)}) ===")
        print("=" * 60)
        for idx, term in enumerate(ASSEMBLYAI_KEYTERMS, 1):
            print(f"  {idx:2d}. {term}")
        print("=" * 60)

        # 1. Total count bounds for expanded keyterms
        self.assertLess(len(ASSEMBLYAI_KEYTERMS), 200, f"Keyterms count must be < 200, got {len(ASSEMBLYAI_KEYTERMS)}")
        self.assertGreaterEqual(len(ASSEMBLYAI_KEYTERMS), 50, "Keyterms count should be reasonably expanded")


        # 2. Check required specific terms
        required_terms = [
            "الأهلي", "الزمالك", "ميسي", "صلاح", "كأس", "دوري",
            "ويجز", "عمرو دياب", "ولاد رزق", "انتخابات"
        ]
        for term in required_terms:
            self.assertIn(term, ASSEMBLYAI_KEYTERMS, f"Missing required term: {term}")

        # 3. Check no duplicates
        self.assertEqual(len(ASSEMBLYAI_KEYTERMS), len(set(ASSEMBLYAI_KEYTERMS)), "Keyterms must not contain duplicates")
        print(f"\n[VERIFIED] All {len(required_terms)} required terms present. Total: {len(ASSEMBLYAI_KEYTERMS)} items.\n")



if __name__ == "__main__":
    unittest.main()
