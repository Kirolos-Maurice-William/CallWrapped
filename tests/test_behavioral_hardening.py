"""
Unit tests for behavioral hardening:
- FIX 5 (BEHAVE-02): Private entity gate checks channel members (case-insensitive partial match)
- FIX 6 (BEHAVE-03): Language-matched verdicts (English -> English, Arabic -> Arabic, Mixed -> last assertion)
"""

import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bot.arbitration.verifier import (
    is_private_claim,
    determine_verdict_language,
    arbitration_verifier,
)
from bot.arbitration.conflict_detector import conflict_detector


class TestBehavioralHardening(unittest.IsolatedAsyncioTestCase):

    def test_private_entity_gate_channel_members(self):
        """
        ACCEPTANCE (FIX 5 / BEHAVE-02):
        - Claim about 'Mostafa' when 'Mostafa' is in channel_members -> refused_private.
        - Claim about 'Mohamed Salah' when 'Mostafa' is the only member -> allowed (public figure).
        """
        members = ["Mostafa"]

        # Case 1: Claim about "Mostafa" with "Mostafa" in the voice channel
        is_priv_member, reason_member = is_private_claim("Mostafa", channel_members=members)
        self.assertTrue(is_priv_member, "Claim about channel member must be flagged private")
        self.assertEqual(reason_member, "voice_channel_member")
        print(f"[Private Gate Output] Entity 'Mostafa' with channel members {members} -> refused_private ({reason_member})")

        # Case 2: Claim about "Mohamed Salah" with "Mostafa" as the only member
        is_priv_public, reason_public = is_private_claim("Mohamed Salah", channel_members=members)
        self.assertFalse(is_priv_public, "Public figure claim must be allowed even if other members exist")
        self.assertIsNone(reason_public)
        print(f"[Private Gate Output] Entity 'Mohamed Salah' with channel members {members} -> allowed (public figure, is_private={is_priv_public})")

        # Case 3: Case-insensitive and partial match tests
        is_priv_lower, _ = is_private_claim("mostafa", channel_members=["Mostafa"])
        self.assertTrue(is_priv_lower, "Case-insensitive match must be flagged private")

        is_priv_partial, _ = is_private_claim("Mostafa's computer", channel_members=["Mostafa"])
        self.assertTrue(is_priv_partial, "Partial substring match must be flagged private")

    async def test_private_entity_gate_in_conflict_detector(self):
        """
        Verifies that ConflictDetector.detect_conflict refuses channel members without LLM call.
        """
        is_conflict, data, latency = await conflict_detector.detect_conflict(
            speaker_a="Ziad",
            claim_a="Mostafa said the meeting is at 5 PM",
            speaker_b="Omar",
            claim_b="No he said 6 PM",
            channel_members=["Mostafa"]
        )
        self.assertFalse(is_conflict)
        self.assertIsNotNone(data)
        self.assertTrue(data.get("is_refused_private"))
        self.assertEqual(data.get("entity_type"), "PRIVATE")
        print(f"[ConflictDetector Output] Channel member in claim -> refused_private: {data.get('dashboard_label')}")

    async def test_language_matched_verdicts_english_and_arabic(self):
        """
        ACCEPTANCE (FIX 6 / BEHAVE-03):
        - English claims -> English verdict (hedged English template)
        - Arabic claims -> Arabic verdict (Arabic template)
        - Mixed claims -> match the language of the last assertion
        """
        # --- 1. English Argument -> English Verdict ---
        claim_a_en = "Python 3.12 was released in October 2023"
        claim_b_en = "No, Python 3.12 was released in November 2023"
        self.assertFalse(determine_verdict_language(claim_a_en, claim_b_en), "English argument must select English")

        assessment_en = {
            "speaker_a_status": "SUPPORTED",
            "speaker_b_status": "CONTRADICTED",
            "correct_fact": "Python 3.12 was officially released on October 2, 2023"
        }
        fact_en, hedge_en = arbitration_verifier.format_intervention_clauses(assessment_en, is_arabic=False)
        spoken_en = arbitration_verifier.format_intervention_template(assessment_en, is_arabic=False)

        self.assertIn("Quick fact check: the source I found says", fact_en)
        self.assertIn("I may have missed context — source is on the dashboard.", hedge_en)
        self.assertTrue(spoken_en.startswith("Quick fact check:"))
        # Ensure zero Arabic characters in English verdict
        self.assertFalse(any("\u0600" <= c <= "\u06FF" for c in spoken_en), "English verdict must not contain Arabic")
        print(f"\n[Language Verdict Output - English]:\n  '{spoken_en}'")

        # --- 2. Arabic Argument -> Arabic Verdict ---
        claim_a_ar = "كارت الـ 5070 نازل بـ 16 جيجا بايت"
        claim_b_ar = "لا هو 12 جيجا بايت بس"
        self.assertTrue(determine_verdict_language(claim_a_ar, claim_b_ar), "Arabic argument must select Arabic")

        assessment_ar = {
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM"
        }
        fact_ar, hedge_ar = arbitration_verifier.format_intervention_clauses(assessment_ar, is_arabic=True)
        spoken_ar = arbitration_verifier.format_intervention_template(assessment_ar, is_arabic=True)

        self.assertIn("تصحيح سريع: المصدر اللي لقيته بيقول", fact_ar)
        self.assertIn("ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد.", hedge_ar)
        self.assertTrue(spoken_ar.startswith("تصحيح سريع:"))
        # Ensure Arabic characters present
        self.assertTrue(any("\u0600" <= c <= "\u06FF" for c in spoken_ar), "Arabic verdict must contain Arabic")
        print(f"\n[Language Verdict Output - Arabic]:\n  '{spoken_ar}'")

        # --- 3. Mixed Argument -> Match Last Assertion ---
        # First Arabic, last English -> English verdict
        self.assertFalse(
            determine_verdict_language("كارت الشاشة ده جامد جداً", "The RTX 5070 has 12GB VRAM"),
            "Mixed with English last assertion must select English"
        )
        # First English, last Arabic -> Arabic verdict
        self.assertTrue(
            determine_verdict_language("The RTX 5070 has 16GB VRAM", "لا هو 12 جيجا بس"),
            "Mixed with Arabic last assertion must select Arabic"
        )
        print("[Language Verdict Output - Mixed]: Successfully matches language of last assertion")


if __name__ == "__main__":
    unittest.main()
