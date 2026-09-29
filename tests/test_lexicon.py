import unittest
from bot.arbitration.lexicon import normalize_bilingual_text, analyze_banter, mask_term


class TestBilingualLexicon(unittest.TestCase):
    def test_a_orthographic_normalization(self):
        # 1. Alef variants
        self.assertEqual(normalize_bilingual_text("أحمد"), "احمد")
        self.assertEqual(normalize_bilingual_text("إسلام"), "اسلام")
        self.assertEqual(normalize_bilingual_text("آدم"), "ادم")
        self.assertEqual(normalize_bilingual_text("ٱبن"), "ابن")

        # 2. Tashkeel stripping
        self.assertEqual(normalize_bilingual_text("فَشَخَ"), "فشخ")

        # 3. Tatweel stripping
        self.assertEqual(normalize_bilingual_text("فـــشـــخ"), "فشخ")

        # 4. Teh Marbuta and Alef Maksura
        self.assertEqual(normalize_bilingual_text("شرموطة"), "شرموطه")
        self.assertEqual(normalize_bilingual_text("منى"), "مني")

        # 5. Elongation collapse (3+ -> 1)
        self.assertEqual(normalize_bilingual_text("فششششخ"), "فشخ")
        self.assertEqual(normalize_bilingual_text("احاااااا"), "احا")
        self.assertEqual(normalize_bilingual_text("fuuuuck"), "fuck")
        self.assertEqual(normalize_bilingual_text("shiiiit"), "shit")

    def test_b_arabic_vulgarity_matches(self):
        cases = [
            ("احا يا عم", 1, ["احا"]),
            ("واحا بقى", 1, ["واحا"]),
            ("فاحا بجد", 1, ["فاحا"]),
            ("يا شرموط", 1, ["شرموط"]),
            ("دي شرموطة", 1, ["شرموطه"]),
            ("بطل منيكة", 1, ["منيكه"]),
            ("انت متناك", 1, ["متناك"]),
            ("يا معرص", 1, ["معرص"]),
            ("يامعرص", 1, ["يامعرص"]),
            ("بطل تعريص", 1, ["تعريص"]),
            ("يا خول", 1, ["خول"]),
            ("ياخول", 1, ["ياخول"]),
            ("ده بيفشخ في الكلام", 1, ["بيفشخ"]),
            ("بتفشخ من الضحك", 1, ["بتفشخ"]),
            ("كسمك", 1, ["كسمك"]),
            ("كس امك", 1, ["كس امك"]),
            ("كسختك", 1, ["كسختك"]),
            ("يابن الكلب", 1, ["يابن الكلب"]),
            ("يا ابن الوسخة", 1, ["ابن الوسخه"]),
            ("ولاد الكلب", 1, ["ولاد الكلب"]),
            ("اولاد الوسخة", 1, ["اولاد الوسخه"]),
            ("اوسخ واحد شفته", 1, ["اوسخ"]),
        ]
        for text, expected_count, expected_terms in cases:
            res = analyze_banter(text)
            self.assertTrue(res.has_vulgarity, f"Failed to detect vulgarity in: '{text}'")
            self.assertEqual(res.vulgarity_count, expected_count, f"Count mismatch for: '{text}'")
            for term in expected_terms:
                self.assertIn(term, res.matched_terms, f"Term '{term}' not found in matches for: '{text}'")

    def test_c_english_vulgarity_matches(self):
        cases = [
            ("fuck you", 1, ["fuck"]),
            ("fucking idiot", 1, ["fucking"]),
            ("motherfucker", 1, ["motherfucker"]),
            ("stfu man", 1, ["stfu"]),
            ("wtf is this", 1, ["wtf"]),
            ("bullshit", 1, ["bullshit"]),
            ("bitch", 1, ["bitch"]),
            ("dumbass", 1, ["dumbass"]),
            ("asshole", 1, ["asshole"]),
            ("dickhead", 1, ["dickhead"]),
            ("bastard", 1, ["bastard"]),
            ("cunt", 1, ["cunt"]),
        ]
        for text, expected_count, expected_terms in cases:
            res = analyze_banter(text)
            self.assertTrue(res.has_vulgarity, f"Failed to detect English vulgarity in: '{text}'")
            self.assertEqual(res.vulgarity_count, expected_count, f"Count mismatch for: '{text}'")
            for term in expected_terms:
                self.assertIn(term, res.matched_terms, f"Term '{term}' not found in matches for: '{text}'")

    def test_d_hostile_negative_edge_cases_zero_false_positives(self):
        # 30+ benign Arabic and English words that embed substrings of vulgarities
        # Must produce 0 false positives!
        benign_texts = [
            "امنيات كتير للسنة الجديدة",
            "بطل تدخين النيكوتين مضر جدا",
            "الولد كسلان النهاردة ومذاكرش",
            "كسوف الشمس ظاهرة فلكية",
            "تكسير الحجارة في الموقع",
            "ابعتلي الفاتورة على الفاكس",
            "ركبت تاكسي وروحت البيت",
            "سافرت شرم الشيخ وقضيت أسبوع",
            "كل الاحترام والتقدير لحضرتك",
            "عندي احاسيس طيبة نحو المشروع",
            "الساحر مبهر في العرض",
            "الباحث العلمي نشر الورقة",
            "دخول ممنوع لغير العاملين",
            "تحول رقمي شامل في مصر",
            "بلاش فشخرة كدابة ع الفاضي",
            "مسخ مشوه في الفيلم",
            "نسخة طبق الاصل من العقد",
            "فاسخ العقد ملزم بالشرط الجزائي",
            "أهلاً بالأحبة الكرام",
            "classic football match",
            "company asset management",
            "I assume that is correct",
            "passive player in midfield",
            "beautiful peacock in the zoo",
            "pilot in the cockpit",
            "read the official document",
            "scunthorpe united match",
            "virtual voice assistant",
            "turn up the bass",
            "join the morning class",
        ]
        for text in benign_texts:
            res = analyze_banter(text)
            self.assertFalse(
                res.has_vulgarity,
                f"FALSE POSITIVE DETECTED in benign sentence: '{text}'. Matches: {res.matched_terms}"
            )
            self.assertEqual(res.vulgarity_count, 0)
            self.assertEqual(len(res.matched_terms), 0)

    def test_e_mask_term(self):
        # Single-word masking
        self.assertEqual(mask_term("fuck"), "f***")
        self.assertEqual(mask_term("احا"), "ا**")
        self.assertEqual(mask_term("خول"), "خ**")

        # Multi-word masking preserving spaces
        self.assertEqual(mask_term("كس امك"), "ك* ا**")
        self.assertEqual(mask_term("ابن الكلب"), "ا** ا****")
        self.assertEqual(mask_term("ولاد الوسخة"), "و*** ا*****")


if __name__ == "__main__":
    unittest.main()
