import re
from typing import Tuple

class FastGate:
    """
    Deterministic rule-based filter before invoking Groq LLM.
    Discards greetings, short acknowledgements, laughter, and questions,
    while passing candidate factual assertions (numbers, specs, corrections, comparisons).
    """

    # Laughter & filler patterns
    IGNORE_EXACT = {
        "ok", "okay", "yes", "yeah", "yep", "nope", "sure", "cool", "nice", "gg", "wp",
        "hello", "hi", "hey", "bye", "goodbye", "thanks", "ty",
        "اه", "ايوة", "ايوه", "تمام", "اوكي", "ماشي", "حاضر", "طيب",
        "سلام", "مع السلامة", "شكرا", "تسلم", "يلا", "باي",
        "أهلاً", "اهلا", "صباح الخير", "مساء الخير"
    }

    IGNORE_REGEX = [
        r"^(ha|he|lol|lmao|rofl|hah)+$",
        r"^(هه|خخ)+$",
        r"^!\w+",  # Bot commands
        r"^(can you hear me|can anyone hear me|mic test|testing)$",
        r"^(حد سامعني|سامعني|الوو|الو)$",
    ]

    # Candidate factual indicators
    CANDIDATE_REGEX = [
        # Numeric values, measurements, hardware specs
        r"\b\d+(\.\d+)?\s*(gb|mb|tb|mhz|ghz|fps|k|hz|vram|ram|usd|egp|\$|جيجا|ميجا|تيرا|دولار|جنيه|فريم)?\b",
        # Assertions & specs in Arabic
        r"(بيجي|بيحتوي|مواصفات|نزلت|نزل|سعره|أسرع|أقوى|أحسن|أرخص|أغلى|تاريخ|سنة|تحديث)",
        # Disagreements & counters in Arabic
        r"(لا غلط|مش صح|أنت غلطان|كلامك غلط|مش كدا|مش كده|بالعكس|أصلاً|أصلا|أكيد|مستحيل|متأكد)",
        # Assertions in English
        r"\b(is|has|features|specs|released|supports|faster|better|cheaper|expensive|costs|weighs|dated)\b",
        # Disagreements & counters in English
        r"\b(no you're wrong|that's wrong|not true|actually|incorrect|false|nope|definitely not)\b"
    ]

    def is_candidate(self, text: str) -> Tuple[bool, str]:
        """
        Evaluates whether an utterance is a candidate for factual arbitration.
        Returns (is_candidate, reason).
        """
        clean_text = text.strip().lower()

        # Reject empty or very short inputs
        if len(clean_text) < 4:
            return False, "too_short"

        # Reject exact match fillers
        if clean_text in self.IGNORE_EXACT:
            return False, "filler_exact_match"

        # Reject regex patterns for laughter, mic checks, bot commands
        for pattern in self.IGNORE_REGEX:
            if re.search(pattern, clean_text):
                return False, "filler_or_command"

        # Check for candidate triggers
        for pattern in self.CANDIDATE_REGEX:
            if re.search(pattern, clean_text, re.IGNORE_IGNORECASE if hasattr(re, 'IGNORE_IGNORECASE') else re.IGNORECASE):
                return True, "matched_candidate_pattern"

        # If it has more than 5 words and doesn't look like a trivial sentence
        words = clean_text.split()
        if len(words) >= 6 and not clean_text.endswith("?"):
            return True, "length_and_structure_heuristic"

        return False, "no_claim_indicator"


fast_gate = FastGate()
