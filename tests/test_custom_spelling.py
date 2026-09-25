import unittest
from bot.ai.assemblyai import ASSEMBLYAI_CUSTOM_SPELLING

class TestCustomSpelling(unittest.TestCase):
    def test_custom_spelling_validity(self):
        self.assertGreaterEqual(len(ASSEMBLYAI_CUSTOM_SPELLING), 20)
        self.assertLessEqual(len(ASSEMBLYAI_CUSTOM_SPELLING), 50)

        for idx, entry in enumerate(ASSEMBLYAI_CUSTOM_SPELLING, 1):
            self.assertIn("from", entry, f"Entry {idx} missing 'from'")
            self.assertIn("to", entry, f"Entry {idx} missing 'to'")
            self.assertIsInstance(entry["from"], list, f"Entry {idx} 'from' must be a list")
            self.assertGreater(len(entry["from"]), 0, f"Entry {idx} 'from' cannot be empty")
            self.assertIsInstance(entry["to"], str, f"Entry {idx} 'to' must be a string")
            
            # AssemblyAI requirement: 'to' must contain only ONE word
            words_in_to = entry["to"].strip().split()
            self.assertEqual(len(words_in_to), 1, f"Entry {idx} 'to' field '{entry['to']}' must be exactly one word")

    def test_key_mappings_present(self):
        tos = {entry["to"] for entry in ASSEMBLYAI_CUSTOM_SPELLING}
        # Latin gaming/tech keyterms
        self.assertIn("uncertainty", tos)
        self.assertIn("RTX", tos)
        self.assertIn("ping", tos)
        # Arabic Egyptian colloquial keyterms
        self.assertIn("كتيره", tos)
        self.assertIn("بالزعانف", tos)
        self.assertIn("تلت", tos)
        self.assertIn("تلاتين", tos)

if __name__ == "__main__":
    unittest.main()
