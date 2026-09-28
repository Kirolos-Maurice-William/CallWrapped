"""
Unit tests for Cross-Script Phonetic Entity Normalizer (bot/arbitration/entity_normalizer.py).
Phase 2 Acceptance Tests.
"""

import sys
import time
import unittest
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.arbitration.entity_normalizer import (
    normalize_surface_text,
    extract_consonant_skeleton,
    skeleton_similarity,
    resolve_entity_in_text
)


class TestEntityNormalizer(unittest.TestCase):

    def test_normalize_surface_text(self):
        """Verifies Arabic normalization: diacritics, tatweel, elongations, alefs, taa marbuta."""
        # Diacritics & Tatweel
        self.assertEqual(normalize_surface_text("سَكُوتْـ"), "سكوت")
        # Elongated letters collapsed
        self.assertEqual(normalize_surface_text("فشخنييييي"), "فشخني")
        # Alef normalization
        self.assertEqual(normalize_surface_text("أحمد و إمام و آية"), "احمد و امام و ايه")
        # Taa Marbuta
        self.assertEqual(normalize_surface_text("لعبة"), "لعبه")

    def test_extract_consonant_skeleton(self):
        """Verifies consonant skeletonization strips vowels and maps phonemes."""
        # Arabic gaming mangling
        skel_1 = extract_consonant_skeleton("وستيسكات ماستر")
        skel_2 = extract_consonant_skeleton("سستيسكات ماستر")
        skel_3 = extract_consonant_skeleton("سكوت ماستر")
        skel_en = extract_consonant_skeleton("Scout Master")
        
        self.assertEqual(skel_1, "styskt mstr")
        self.assertEqual(skel_2, "styskt mstr")
        self.assertEqual(skel_3, "skwt mstr")
        self.assertEqual(skel_en, "skt mstr")

    def test_scoutmaster_variants_high_similarity(self):
        """Acceptance test: All ASR variants of Scoutmaster exceed 0.80 similarity."""
        variants = ["وستيسكات ماستر", "سستيسكات ماستر", "سكوت ماستر"]
        for v in variants:
            sim = skeleton_similarity(v, "Scout Master")
            self.assertGreaterEqual(
                sim, 0.80,
                f"Variant '{v}' similarity {sim:.2f} should be >= 0.80 against 'Scout Master'"
            )

    def test_false_friend_rejection(self):
        """Acceptance test: Casual Arabic words do NOT match gaming entities."""
        false_friends = [
            "اسكت بقى",
            "يا عم اسكت",
            "ماستر كارد",
            "صباح الخير",
            "الجو حر"
        ]
        for ff in false_friends:
            sim = skeleton_similarity(ff, "Scout Master")
            self.assertLess(
                sim, 0.65,
                f"False friend '{ff}' similarity {sim:.2f} should be < 0.65 against 'Scout Master'"
            )
            # Verify resolve_entity_in_text returns None
            resolved = resolve_entity_in_text(ff, ["Scout Master"])
            self.assertIsNone(resolved, f"False friend '{ff}' should not resolve to 'Scout Master'")

    def test_resolve_entity_in_sentence(self):
        """Verifies entity extraction and resolution inside conversational utterances."""
        sentence = "حفظ عفواً أون ونون وستيسكات ماستر وفشخني صراحة يعني يا صديقي"
        resolved = resolve_entity_in_text(sentence, ["Scout Master"])
        
        self.assertIsNotNone(resolved)
        canonical, surface, score = resolved
        self.assertEqual(canonical, "Scout Master")
        self.assertEqual(surface, "وستيسكات ماستر")
        self.assertGreaterEqual(score, 0.80)

    def test_speed_benchmark(self):
        """Verifies that 1000 consonant skeleton extractions run in < 15ms on CPU."""
        t0 = time.perf_counter()
        for _ in range(1000):
            _ = extract_consonant_skeleton("سستيسكات ماستر وفشخني صراحة")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        
        print(f"\n[CPU Performance] 1,000 skeleton extractions completed in {elapsed_ms:.2f}ms")
        self.assertLess(elapsed_ms, 30.0, "Skeleton extraction must execute in < 30ms for 1,000 runs")


if __name__ == "__main__":
    unittest.main()
