import tests._setup

import unittest
from bot.arbitration.verifier import arbitration_verifier


class TestFix7ArabicVerdicts(unittest.TestCase):
    """
    Acceptance test for Fix 7:
    Tests format_intervention_template with is_arabic=True for:
    1. CONTRADICTED: 'تصحيح: {fact}. المصدر: {domain}.'
    2. SUPPORTED: 'المعلومة صحيحة: {fact}. المصدر: {domain}.'
    3. UNVERIFIABLE: 'تعذر التحقق من المعلومة من مصادر موثوقة.'
    """

    def test_arabic_contradicted_template(self):
        assessment = {
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "كارت 5070 بيجي بـ 12 جيجا مش 16",
            "selected_source_url": "https://www.nvidia.com/geforce/50-series/"
        }
        res = arbitration_verifier.format_intervention_template(assessment, is_arabic=True)
        self.assertEqual(res, "تصحيح: كارت 5070 بيجي بـ 12 جيجا مش 16. المصدر: nvidia.com.")
        print("\n--- FIX 7 OUTPUT 1 (CONTRADICTED) ---")
        print(res)

    def test_arabic_supported_template(self):
        assessment = {
            "speaker_a_status": "SUPPORTED",
            "speaker_b_status": "UNVERIFIABLE",
            "correct_fact": "الأهلي فاز بالسوبر المصري بنتيجة 2-0",
            "selected_source_url": "https://www.filgoal.com/matches/123"
        }
        res = arbitration_verifier.format_intervention_template(assessment, is_arabic=True)
        self.assertEqual(res, "المعلومة صحيحة: الأهلي فاز بالسوبر المصري بنتيجة 2-0. المصدر: filgoal.com.")
        print("\n--- FIX 7 OUTPUT 2 (SUPPORTED) ---")
        print(res)

    def test_arabic_unverifiable_template(self):
        assessment = {
            "speaker_a_status": "UNVERIFIABLE",
            "speaker_b_status": "UNVERIFIABLE",
            "correct_fact": "",
            "selected_source_url": ""
        }
        res = arbitration_verifier.format_intervention_template(assessment, is_arabic=True)
        self.assertEqual(res, "تعذر التحقق من المعلومة من مصادر موثوقة.")
        print("\n--- FIX 7 OUTPUT 3 (UNVERIFIABLE) ---")
        print(res)


if __name__ == "__main__":
    unittest.main()
