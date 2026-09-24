"""
BUG 3 Acceptance Test:
Verifies that:
1. When speakers' claims are in Arabic and web evidence is in English,
   the verifier generates `correct_fact` in natural Arabic (not English).
2. Spoken template strips doubled punctuation cleanly (e.g. '..' -> '.').
3. Pastes both Arabic and English verdict outputs for acceptance.
"""
import tests._setup
import unittest
import asyncio
from bot.config import config
from bot.ai.groq import groq_client
from bot.arbitration.verifier import (
    arbitration_verifier,
    VERIFICATION_SYNTHESIS_PROMPT
)


class TestArabicFactVerification(unittest.TestCase):

    def test_strip_doubled_punctuation(self):
        """Verifies template formatting strips doubled or trailing punctuation."""
        assessment = {
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "كريستيانو رونالدو اتولد في 5 فبراير 1985..",
            "selected_source_url": "https://en.wikipedia.org/wiki/Cristiano_Ronaldo"
        }
        spoken = arbitration_verifier.format_intervention_template(assessment, is_arabic=True)
        print("\n" + "=" * 65)
        print("=== BUG 3: DOUBLED PUNCTUATION STRIPPING ===")
        print("=" * 65)
        print(f"Raw fact with '..':    '{assessment['correct_fact']}'")
        print(f"Formatted intervention: '{spoken}'")
        print("=" * 65)

        self.assertNotIn("..", spoken, "Intervention must not contain doubled periods")
        self.assertTrue(spoken.endswith("."), "Intervention must end with a single period")

    def test_arabic_claim_with_english_evidence_real_groq(self):
        """
        Acceptance: Arabic utterances + English evidence -> correct_fact in Arabic.
        """
        if not config.GROQ_API_KEY:
            self.skipTest("GROQ_API_KEY required for real LLM verification")

        print("\n" + "=" * 65)
        print("=== BUG 3 ACCEPTANCE: ARABIC CLAIMS + ENGLISH EVIDENCE ===")
        print("=" * 65)

        # Arabic claims
        speaker_a = "أحمد"
        claim_a = "كريستيانو رونالدو اتولد في فبراير 1990"
        speaker_b = "عمر"
        claim_b = "لا كريستيانو رونالدو اتولد في 5 فبراير 1985"

        # English evidence
        english_evidence = (
            "[Source 1 - Tier 1] Cristiano Ronaldo - Wikipedia (wikipedia.org):\n"
            "Cristiano Ronaldo dos Santos Aveiro (born 5 February 1985) is a Portuguese "
            "professional footballer who plays as a forward and captains the Portugal national team.\n"
            "URL: https://en.wikipedia.org/wiki/Cristiano_Ronaldo"
        )

        has_arabic = any("\u0600" <= c <= "\u06FF" for c in (claim_a + claim_b))
        lang_note = (
            "\nLanguage Note: The claims are in Arabic. 'correct_fact' MUST be written in natural Arabic (translate facts from English evidence as needed)."
            if has_arabic else ""
        )

        user_prompt = (
            f"Conversation Context:\n"
            f"- {speaker_a} claimed: \"{claim_a}\"\n"
            f"- {speaker_b} claimed: \"{claim_b}\"{lang_note}\n\n"
            f"Authoritative Web Evidence (Sorted by Trust Tier):\n{english_evidence}"
        )

        async def run_check():
            return await groq_client.complete_json(VERIFICATION_SYNTHESIS_PROMPT, user_prompt)

        assessment, llm_ms = asyncio.run(run_check())

        if assessment is None:
            self.skipTest("Groq rate limit (429) hit — skipping live test")

        spoken_arabic = arbitration_verifier.format_intervention_template(assessment, is_arabic=True)

        print(f"LLM Latency: {llm_ms}ms")
        print(f"Speaker A Status: {assessment.get('speaker_a_status')}")
        print(f"Speaker B Status: {assessment.get('speaker_b_status')}")
        print(f"Selected Source:  {assessment.get('selected_source_title')} ({assessment.get('selected_source_url')})")
        print(f"\n--- ARABIC OUTPUT (CORRECT_FACT) ---")
        print(f"correct_fact:     \"{assessment.get('correct_fact')}\"")
        print(f"Spoken Arabic:    \"{spoken_arabic}\"")

        # Verify correct_fact is in Arabic
        fact = assessment.get("correct_fact", "")
        arabic_chars = sum(1 for c in fact if "\u0600" <= c <= "\u06FF")
        self.assertGreater(arabic_chars, 5, f"correct_fact must be written in Arabic, got: {fact}")
        self.assertNotIn("..", spoken_arabic)

        # Now test English claim + English evidence for comparison
        user_prompt_en = (
            f"Conversation Context:\n"
            f"- Alice claimed: \"Cristiano Ronaldo was born in 1990\"\n"
            f"- Bob claimed: \"Cristiano Ronaldo was born in 1985\"\n\n"
            f"Authoritative Web Evidence (Sorted by Trust Tier):\n{english_evidence}"
        )

        async def run_en():
            return await groq_client.complete_json(VERIFICATION_SYNTHESIS_PROMPT, user_prompt_en)

        assessment_en, _ = asyncio.run(run_en())
        if assessment_en:
            spoken_en = arbitration_verifier.format_intervention_template(assessment_en, is_arabic=False)
            print(f"\n--- ENGLISH OUTPUT (FOR COMPARISON) ---")
            print(f"correct_fact:     \"{assessment_en.get('correct_fact')}\"")
            print(f"Spoken English:   \"{spoken_en}\"")

        print("=" * 65 + "\n")


if __name__ == "__main__":
    unittest.main()
