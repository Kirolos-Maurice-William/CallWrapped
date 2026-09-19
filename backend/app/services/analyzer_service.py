import logging
import re
import json
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

TOPICS = [
    "movies", "music", "football", "politics", "technology", "gaming", "dogs", "personal", "other"
]

TOPIC_KEYWORDS = {
    "movies": ["فيلم", "افلام", "سينما", "ممثل", "مخرج", "movie", "film", "actor", "director", "cinema", "release", "inception", "hollywood", "netflix"],
    "football": ["كورة", "اهلي", "زمالك", "ماتش", "هدف", "جون", "لاعب", "دوري", "football", "soccer", "messi", "ronaldo", "match", "goal", "league", "club", "fifa", "inter miami"],
    "music": ["اغنية", "البوم", "موسيقى", "مطرب", "تراك", "song", "album", "music", "singer", "track", "rap", "band", "concert"],
    "politics": ["حكومة", "انتخابات", "رئيس", "سياسة", "قانون", "وزير", "president", "government", "election", "politics", "law", "policy"],
    "technology": ["كمبيوتر", "برمجة", "تطبيق", "موقع", "ذكاء اصطناعي", "هاتف", "tech", "technology", "ai", "code", "app", "software", "hardware", "phone", "apple", "google"],
    "gaming": ["لعبة", "جيم", "بلايستيشن", "اكس بوكس", "game", "gaming", "playstation", "xbox", "steam", "gamer", "pc"],
    "dogs": ["كلب", "كلاب", "حيوان", "جرو", "dog", "dogs", "puppy", "pet", "breed"],
    "personal": ["انا", "انت", "امبارح", "شغلي", "بيتي", "me", "my", "yesterday", "family", "friend", "work"]
}

ARABIC_INDIC_DIGITS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}

TEXTUAL_NUMBER_MAP = {
    "ألفين": "2000", "الفين": "2000",
    "سبعة وتمانين": "1987", "سبعة وثمانين": "1987",
    "خمسة وتمانين": "1985", "خمسة وثمانين": "1985",
    "ستة وتمانين": "1986", "ستة وثمانين": "1986",
    "ثمانية وتمانين": "1988", "ثمانية وثمانين": "1988",
    "تسعة وتمانين": "1989", "تسعة وثمانين": "1989",
    "تسعين": "1990", "تمانين": "1980", "ثمانين": "1980",
    "واحد وتسعين": "1991", "اتنين وتسعين": "1992"
}

def normalize_conversational_text(text: str) -> str:
    """Normalizes Eastern Arabic digits and spoken Egyptian textual numbers."""
    for ar_d, en_d in ARABIC_INDIC_DIGITS.items():
        text = text.replace(ar_d, en_d)
    for phrase, num in TEXTUAL_NUMBER_MAP.items():
        if phrase in text:
            text = text.replace(phrase, num)
    return text

DISAGREEMENT_PHRASES = [
    "مش صح", "غلط", "كذاب", "مش مظبوط", "يا عم", "انت فاهم غلط", "أنت فاهم غلط", "مستحيل", "كلام فارغ",
    "مش حقيقي", "أنت غلطان", "انت غلطان", "مش كده", "مش كدة", "انت بتهزر", "أنت بتهزر", "مش مضبوط", "مين قال كده", "مين قال",
    "لا يا عم", "لا يا راجل", "لا يا سيدي", "لا ده", "لا دي", "لا مش", "مش ده", "مش دي", "مش هو", "مش هي", "أصلاً", "اصلا",
    "no", "not true", "wrong", "false", "disagree", "actually", "no way", "impossible", "you're wrong", "thats wrong",
    "not really", "incorrect"
]

CLAIM_MARKERS = [
    "سنة", "سنه", "نزل في", "طلع في", "تاريخ", "رقم", "سجل", "اتولد", "مولود", "مواليد",
    "عنده", "عمره", "كسب", "فاز", "مليار", "مليون",
    "released in", "came out", "born in", "founded in", "won in", "scored", "joined in", "in 20", "in 19"
]

class ConversationAnalyzerService:
    def __init__(self):
        self._previous_turns: List[Dict[str, Any]] = []

    def classify_heuristically(self, text: str, speaker_name: str) -> Dict[str, Any]:
        """Fast, robust deterministic analysis used as baseline and instant response."""
        norm_text = normalize_conversational_text(text)
        text_lower = norm_text.lower()
        
        # 1. Topic Detection
        topic_scores = {t: 0 for t in TOPICS}
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    topic_scores[topic] += 1
        
        best_topic = max(topic_scores, key=topic_scores.get)
        if topic_scores[best_topic] == 0:
            best_topic = "other"

        # 2. Intent Detection
        # Match negation tokens with word boundaries to prevent false positives like 'لاعب'
        has_negation_word = bool(re.search(r'(^|\s)(لا|مش|غلط|كذاب|مستحيل|no|wrong|false|nah|nope)(\s|$)', text_lower))
        has_disagree_phrase = any(dm in text_lower for dm in DISAGREEMENT_PHRASES)
        is_disagreement = has_negation_word or has_disagree_phrase

        has_question = "?" in text or "؟" in text or text_lower.startswith(("ليه", "ازاي", "مين", "فين", "كام", "متى", "هل", "why", "how", "who", "where", "when", "what", "is it"))
        
        words_count = len(text.strip().split())
        has_numbers = bool(re.search(r'\d+', norm_text))
        has_claim_marker = any(cm in text_lower for cm in CLAIM_MARKERS)
        is_short_filler = text_lower in ["تمام", "اه", "اوك", "ماشى", "حبيبي", "شكرا", "يا هلا", "yes", "ok", "cool", "yeah", "sure", "nice", "hello", "hi"]

        # Any substantive statement with a number/claim marker, or a factual turn >= 3 words that is not a question or filler
        is_claim = not has_question and not is_short_filler and ((has_numbers or has_claim_marker) if words_count < 3 else True)

        if is_disagreement:
            intent = "disagreement"
        elif is_claim:
            intent = "factual_claim"
        elif has_question:
            intent = "question"
        else:
            intent = "statement"

        # 3. Heat Score Calculation
        heat_score = 0.1  # base baseline
        if is_disagreement:
            heat_score += 0.35
        if "!" in text or "!!" in text or "لا يا عم" in text or "غلط" in text or "wrong" in text_lower:
            heat_score += 0.25

        # Check turn cadence with previous turn
        if self._previous_turns:
            last_turn = self._previous_turns[-1]
            # Rapid speaker shift
            if last_turn.get("speaker_name") != speaker_name:
                gap_ms = last_turn.get("end_ms", 0)
                # Overlap or interruption
                if is_disagreement:
                    heat_score += 0.15

        heat_score = min(round(heat_score, 2), 1.0)

        return {
            "topic": best_topic,
            "intent": intent,
            "heat_score": heat_score,
            "is_claim": is_claim,
            "is_disagreement": is_disagreement
        }

    async def analyze_turn(self, turn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Asynchronously enriches turn with topic, intent, and heat score.
        Uses heuristics immediately; can enrich via LLM asynchronously if configured.
        """
        text = turn.get("text", "")
        speaker_name = turn.get("speaker_name", "")
        
        result = self.classify_heuristically(text, speaker_name)
        
        # If Gemini or OpenAI is configured, we can optionally refine high-ambiguity turns
        if (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY) and result["is_claim"]:
            try:
                refined = await self._refine_with_llm(text, result)
                if refined:
                    result.update(refined)
            except Exception as e:
                logger.warning(f"LLM refinement fallback to heuristic: {e}")

        self._previous_turns.append(turn)
        if len(self._previous_turns) > 20:
            self._previous_turns.pop(0)

        return result

    async def _refine_with_llm(self, text: str, current_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Fast async prompt to refine topic and factual claim statement
        prompt = (
            f"Analyze this conversational turn from a bilingual Egyptian Arabic/English dialogue:\n"
            f"Text: \"{text}\"\n\n"
            f"Return JSON strictly with fields:\n"
            f"- topic: one of {TOPICS}\n"
            f"- is_claim: true/false\n"
            f"- claim_summary: concise English statement of the fact claimed (or null)\n"
            f"- is_disagreement: true/false"
        )
        
        if settings.GEMINI_API_KEY:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = await client.aio.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
            
        elif settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(resp.choices[0].message.content)
            
        return None
