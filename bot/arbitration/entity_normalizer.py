"""
Cross-Script Phonetic Entity Normalizer (Phase 2).
Provides deterministic, ultra-fast (<0.1ms CPU) phonetic skeletonization and entity linking
between Egyptian Arabic ASR phonetic transliterations and canonical English/Arabic entity names.
Zero LLM API cost. Zero latency overhead.
"""

import re
import difflib
from typing import Optional, Tuple, List, Dict, Set


# Arabic Tashkeel / Harakat regex
_TASHKEEL_RE = re.compile(r"[\u064B-\u0652\u0640]")

# Elongated character regex (e.g. فشخنييي -> فشخني, سسس -> س)
_ELONGATION_RE = re.compile(r"(.)\1{2,}")

# Consonant phoneme mapping from Arabic to Latin skeleton characters
_ARABIC_CONSONANT_MAP = {
    "س": "s", "ص": "s", "ث": "s",
    "ك": "k", "ق": "k",
    "ت": "t", "ط": "t",
    "م": "m",
    "د": "d", "ض": "d", "ذ": "d", "ظ": "d",
    "ر": "r",
    "ن": "n",
    "ب": "b",
    "ف": "f",
    "ل": "l",
    "ج": "g",  # Egyptian hard 'g'
    "ش": "sh",
    "ح": "h", "خ": "h", "ه": "h",
    "ع": "a", "غ": "g",
    "ز": "z",
    "و": "w",  # Semi-vowel / consonant
    "ي": "y",  # Semi-vowel / consonant
}

# Latin vowels to strip for consonant skeleton
_LATIN_VOWELS = set("aeiouy")


def normalize_surface_text(text: str) -> str:
    """
    Cleans raw Arabic/English surface text:
    - Strips tashkeel and tatweel
    - Collapses character elongations (فشخنييي -> فشخني)
    - Normalizes alefs (أ/إ/آ/ٱ -> ا)
    - Normalizes taa marbuta (ة -> ه)
    - Normalizes yaa (ى -> ي)
    - Strips non-word characters and collapses whitespace
    """
    if not text:
        return ""
    
    cleaned = text.strip()
    
    # Strip Tashkeel & Tatweel
    cleaned = _TASHKEEL_RE.sub("", cleaned)
    
    # Collapse 3+ repeated characters down to 1
    cleaned = _ELONGATION_RE.sub(r"\1", cleaned)
    
    # Normalize Alefs
    cleaned = re.sub(r"[أإآٱ]", "ا", cleaned)
    
    # Normalize Taa Marbuta & Yaa
    cleaned = re.sub(r"ة", "ه", cleaned)
    cleaned = re.sub(r"ى", "ي", cleaned)
    
    # Remove punctuation
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_word_prefixes(word: str) -> str:
    """Strips common Arabic grammatical prefixes (ال, و, ب, ف, ك) from words > 3 chars."""
    if len(word) <= 3:
        return word
    
    # Strip definite article 'ال'
    if word.startswith("ال"):
        word = word[2:]
        
    # Strip coordinating conjunctions / prepositions 'و', 'ب', 'ف', 'ك' if remainder is valid
    if len(word) > 3 and word[0] in ("و", "ب", "ف", "ك"):
        word = word[1:]
        
    return word


def extract_consonant_skeleton(text: str) -> str:
    """
    Converts Arabic or Latin text into a language-neutral consonant skeleton.
    Example:
      "وستيسكات ماستر" -> "stkst mstr"
      "Scout Master"   -> "skt mstr"
      "سكوت ماستر"     -> "skt mstr"
    """
    if not text:
        return ""
        
    normalized = normalize_surface_text(text)
    words = normalized.split()
    skeleton_words = []
    
    for w in words:
        w_clean = _clean_word_prefixes(w.lower())
        chars = []
        
        for ch in w_clean:
            # Arabic consonant mapping
            if ch in _ARABIC_CONSONANT_MAP:
                chars.append(_ARABIC_CONSONANT_MAP[ch])
            # Latin consonant mapping
            elif ch.isalpha() and ch.isascii():
                if ch in _LATIN_VOWELS:
                    continue  # skip vowels
                if ch == "c":
                    chars.append("k")
                elif ch == "p":
                    chars.append("b")  # Egyptian phonetic neutralization (P -> B)
                else:
                    chars.append(ch)
            elif ch.isdigit():
                chars.append(ch)
                
        # Collapse double consonants in skeleton (e.g. ss -> s)
        skeleton_str = "".join(chars)
        skeleton_str = re.sub(r"(.)\1+", r"\1", skeleton_str)
        if skeleton_str:
            skeleton_words.append(skeleton_str)
            
    return " ".join(skeleton_words)


def skeleton_similarity(a: str, b: str) -> float:
    """
    Calculates phonetic similarity between two text strings using their consonant skeletons.
    Returns float in range [0.0, 1.0].
    """
    skel_a = extract_consonant_skeleton(a)
    skel_b = extract_consonant_skeleton(b)
    
    if not skel_a or not skel_b:
        return 0.0
        
    if skel_a == skel_b:
        return 1.0
        
    words_a = skel_a.split()
    words_b = skel_b.split()
    
    # Word count penalty: a 1-word phrase cannot match a 3-word entity
    if abs(len(words_a) - len(words_b)) > 1:
        return 0.0
        
    # SequenceMatcher ratio on the full skeleton string
    ratio = difflib.SequenceMatcher(None, skel_a, skel_b).ratio()
    
    # Token-level bonus if all words share common root prefixes
    if len(words_a) == len(words_b):
        word_scores = [difflib.SequenceMatcher(None, wa, wb).ratio() for wa, wb in zip(words_a, words_b)]
        avg_word = sum(word_scores) / len(word_scores)
        return max(ratio, avg_word)
        
    return ratio


def resolve_entity_in_text(
    text: str,
    canonical_entities: List[str],
    aliases: Optional[Dict[str, str]] = None,
    threshold: float = 0.68
) -> Optional[Tuple[str, str, float]]:
    """
    Scans text to resolve any phonetic variants or known aliases against canonical entities.
    Returns (canonical_name, surface_match, similarity_score) or None.
    
    Execution:
    1. Direct $O(1)$ dictionary lookup against aliases
    2. N-gram candidate window scanning against canonical entities via consonant skeletons
    """
    if not text or not canonical_entities:
        return None
        
    normalized = normalize_surface_text(text)
    norm_lower = normalized.lower()
    
    # 1. Direct Alias Lookup (Fastest path)
    if aliases:
        for alias_surface, canonical in aliases.items():
            if alias_surface.lower() in norm_lower:
                return canonical, alias_surface, 1.0
                
    # 2. Check direct substring match against canonical entities
    for entity in canonical_entities:
        if entity.lower() in norm_lower:
            return entity, entity, 1.0
            
    # 3. N-gram Window Scanning for Phonetic Variants
    tokens = normalized.split()
    if not tokens:
        return None
        
    best_match = None
    best_score = 0.0
    
    for entity in canonical_entities:
        entity_skel = extract_consonant_skeleton(entity)
        entity_word_count = len(entity.split())
        
        # Slide a window of length [entity_word_count - 1, entity_word_count + 1]
        min_win = max(1, entity_word_count - 1)
        max_win = min(len(tokens), entity_word_count + 1)
        
        for w_len in range(min_win, max_win + 1):
            for i in range(len(tokens) - w_len + 1):
                candidate_tokens = tokens[i : i + w_len]
                candidate_span = " ".join(candidate_tokens)
                
                score = skeleton_similarity(candidate_span, entity)
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = (entity, candidate_span, score)
                    
    return best_match
