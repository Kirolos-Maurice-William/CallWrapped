"""
Bilingual Token-Boundary Lexicon & Banter Detection Engine.
Specialized for Egyptian Arabic vernacular and English gaming/Discord chatter.
Applies computational morphology to prevent false positives from Arabic agglutination.
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class BanterAnalysisResult:
    has_vulgarity: bool
    vulgarity_count: int
    matched_terms: List[str] = field(default_factory=list)
    masked_text: str = ""


# ---------------------------------------------------------------------------
# Orthographic Normalization
# ---------------------------------------------------------------------------
_ALEF_PATTERN = re.compile(r"[أإآٱ]")
_TASHKEEL_PATTERN = re.compile(r"[\u064B-\u0652\u0670]")
_TATWEEL_PATTERN = re.compile(r"ـ+")
_TEH_MARBUTA_PATTERN = re.compile(r"ة")
_ALEF_MAKSURA_PATTERN = re.compile(r"ى")
_REPETITION_PATTERN = re.compile(r"(.)\1{2,}")


def normalize_bilingual_text(text: str) -> str:
    """
    Normalizes Egyptian Arabic and English text for robust token-boundary lexicon matching.
    1. Lowercases English.
    2. Unifies Alef variants (أ, إ, آ, ٱ -> ا).
    3. Strips Tashkeel (Arabic diacritics).
    4. Strips Tatweel (kashida).
    5. Normalizes Teh Marbuta (ة -> ه) and Alef Maksura (ى -> ي).
    6. Collapses excessive character repetitions (3+ identical characters -> 1).
    """
    if not text:
        return ""
    t = text.lower()
    t = _ALEF_PATTERN.sub("ا", t)
    t = _TASHKEEL_PATTERN.sub("", t)
    t = _TATWEEL_PATTERN.sub("", t)
    t = _TEH_MARBUTA_PATTERN.sub("ه", t)
    t = _ALEF_MAKSURA_PATTERN.sub("ي", t)
    t = _REPETITION_PATTERN.sub(r"\1", t)
    return t


# ---------------------------------------------------------------------------
# Token-Boundary Regex Patterns
# ---------------------------------------------------------------------------
# Strict word-boundary guards:
# In Arabic, (?<!\w) matches at string start or non-word character boundary.
# Agglutinative prefixes handled: [وفب]? (and/so/with), (?:ال)? (optional definite article),
# and continuous imperfective aspect (?:بي|بت)? where appropriate.
ARABIC_VULGARITY_PATTERNS = [
    # احا / واحا / فاحا
    r"(?<!\w)[وف]?اح+ا+(?!\w)",
    # شرموط / شرموطة / شرمطة (excluding شرم الشيخ)
    r"(?<!\w)[وفب]?(?:يا)?(?:ال)?(?:شرموط[ةهين]?|شرمط[ةه]?)(?!\w)",
    # منيك / منيكة / متناك / تناكة (excluding امنيات / ميكانيكا)
    r"(?<!\w)[وفب]?(?:يا)?(?:ال)?(?:منيك[ةه]?|متناك[ةهين]?|تناك[ةه]?)(?!\w)",
    # عرص / معرص / تعريص (excluding عرض / عرش / معرض)
    r"(?<!\w)[وفب]?(?:يا)?(?:ال)?(?:بي|بت)?(?:عرص|معرص|تعريص)[ةهين]?(?!\w)",
    # خول / الخول (excluding دخول / مخول / تحول)
    r"(?<!\w)[وفب]?(?:يا)?(?:ال)?خول[ةه]?(?!\w)",
    # فشخ / بتفشخ / بيفشخ / مفشوخ (excluding فشخرة / بيفشخر)
    r"(?<!\w)[وفب]?(?:ال)?(?:بي|بت)?(?:فشخ|فاشخ|مفشوخ)[ةهين]?(?!\w)",
    # كس compounds: كسمك / كسم / كس امك / كسختك (excluding كسلان / كسوف / تكسير / فاكس / تاكسي)
    r"(?<!\w)(?:كسم[ك]?|كس\s+ام[ك]?|كسخت[ك]?|كس\s+اخت[ك]?)(?!\w)",
    # ابن الكلب / يابن الكلب / ولاد الكلب / ابن الوسخة / ابن المتناكة (excluding ابن حلال / ابن النيل)
    r"(?<!\w)(?:يا\s*ب?ن|ابن|ولاد|اولاد)\s+(?:الكلب|الوسخ[ةه]|المتناك[ةه]|الشرموط[ةه]|القحب[ةه]|الاحب[ةه])(?!\w)",
    # وسخ / وسخة / اوسخ (excluding مسخ / نسخة / فاسخ)
    r"(?<!\w)[وفب]?(?:يا)?(?:ال)?(?:وسخ[ةه]?|اوسخ)(?!\w)",
]

ENGLISH_VULGARITY_PATTERNS = [
    r"\b(fuck(ing|er|ers|ed|s)?|motherfucker|stfu|wtf)\b",
    r"\b(shit|shitty|bullshit|shitting)\b",
    r"\b(bitch(es|ing)?)\b",
    r"\b(ass|asshole|assholes|dumbass|jackass)\b",
    r"\b(dick|dicks|dickhead|cock|cocksucker)\b",
    r"\b(bastard|bastards|cunt|cunts|puss(y|ies))\b",
]

# Combine all patterns into a single optimized pre-compiled regex
_COMBINED_PATTERN_STR = "|".join(f"(?:{p})" for p in (ARABIC_VULGARITY_PATTERNS + ENGLISH_VULGARITY_PATTERNS))
COMPILED_BANTER_REGEX = re.compile(_COMBINED_PATTERN_STR, re.IGNORECASE)


def mask_term(term: str) -> str:
    """
    Politely masks a vulgarity for clean, professional dashboard and social card display.
    Example: 'fuck' -> 'f***', 'احا' -> 'ا**', 'ابن الكلب' -> 'ا** ال****'.
    """
    clean = str(term).strip()
    if not clean:
        return ""
    words = clean.split()
    if len(words) > 1:
        return " ".join(mask_term(w) for w in words)
    if len(clean) <= 2:
        return clean[0] + "*"
    return clean[0] + "*" * (len(clean) - 1)


def analyze_banter(text: str) -> BanterAnalysisResult:
    """
    Analyzes an utterance for banter and vulgarity tokens.
    Returns BanterAnalysisResult with match count, matched terms, and masked text.
    Execution time: <0.1ms per utterance.
    """
    if not text or not str(text).strip():
        return BanterAnalysisResult(has_vulgarity=False, vulgarity_count=0)

    raw_text = str(text)
    norm_text = normalize_bilingual_text(raw_text)

    matches = list(COMPILED_BANTER_REGEX.finditer(norm_text))
    if not matches:
        return BanterAnalysisResult(
            has_vulgarity=False,
            vulgarity_count=0,
            matched_terms=[],
            masked_text=raw_text
        )

    matched_terms = [m.group(0) for m in matches]
    vulgarity_count = len(matched_terms)

    # Generate politely masked text
    # Sort matches in reverse order to preserve spans during replacement
    masked = norm_text
    for m in reversed(matches):
        span = m.span()
        masked = masked[:span[0]] + mask_term(m.group(0)) + masked[span[1]:]

    return BanterAnalysisResult(
        has_vulgarity=True,
        vulgarity_count=vulgarity_count,
        matched_terms=matched_terms,
        masked_text=masked
    )


# Backward-compatible alias
detect_vulgarity = analyze_banter

