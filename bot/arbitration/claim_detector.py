import time
import json
import asyncio
import logging
from typing import Optional, Dict, Any, Tuple, List
from bot.config import config
from bot.ai.groq import groq_client

logger = logging.getLogger("ClaimDetector")

# Slim Instant Claim Detector Prompt (Target <= 400 prompt tokens)
# Only: is_factual_claim, claim, entity, metric (+ same-language rule)
INSTANT_CLAIM_PROMPT = """Classify if voice chat contains a verifiable factual claim (Egyptian Arabic/English).
JSON fields:
- is_factual_claim: true ONLY for verifiable objective facts with specific entities or metrics. Opinions, banter, feelings = false.
- claim: concise asserted fact or ""
- entity: subject/entity or ""
- metric: asserted spec, number, or date or ""
Write claim, entity, metric in the SAME language as the input.

Examples:
- "كارت 5070 نازل بـ 12 جيجا": is_factual_claim=true, claim="كارت 5070 نازل بـ 12 جيجا", entity="RTX 5070", metric="12 جيجا"
- "الأهلي كسب 2-1": is_factual_claim=true, claim="الأهلي كسب 2-1", entity="الأهلي", metric="2-1"
- "صلاح أحسن لاعب": is_factual_claim=false, claim="", entity="", metric=""
- "زهقت من اللعبة دي": is_factual_claim=false, claim="", entity="", metric=""
- "يا عم انت نوب ههههه": is_factual_claim=false, claim="", entity="", metric=""
- "The Earth orbits the sun in 365 days": is_factual_claim=true, claim="The Earth orbits the sun in 365 days", entity="Earth", metric="365 days"
"""

INSTANT_CLAIM_SCHEMA = {
    "name": "instant_claim_detector",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "is_factual_claim": {"type": "boolean"},
            "claim": {"type": "string"},
            "entity": {"type": "string"},
            "metric": {"type": "string"}
        },
        "required": ["is_factual_claim", "claim", "entity", "metric"],
        "additionalProperties": False
    }
}

# Batched Topic & Anger Prompt (Reuses proven ANGER RULE + twin-pair examples)
BATCH_ANALYTICS_PROMPT = """Analyze a window of voice chat utterances (Egyptian Arabic/English).
For each numbered line "Speaker: Text", classify topic, anger level, and anger evidence.

JSON schema: return an object with "results": array of items for EVERY line in order:
- line_number: integer (1-based)
- topic: football|politics|music|movies|gaming|tech|personal_life|other
- anger: none|mild|high
- anger_evidence: verbatim quote of frustration/anger or ""
Write anger_evidence in the SAME language as the input utterance.

ANGER RULE (check in order):
1. Joking markers present: "هههه", "LOL", "😂", playful teasing, exaggeration for laughs -> anger: none
2. No joking markers AND negative/frustrated words: ranting, complaining, "زهقت", "بيعصب", cursing at the game/server/situation -> anger: mild (high if intense, e.g. "أووووي", CAPS)
3. Calm neutral talk -> none
When unsure: laughter present = none. No laughter + negative words = mild.

Twin-pair examples:
"الكول أوف ديوتي زبالة والرانك بيعصب أوي" -> mild (rant, no laughter)
"انت زبالة يا عم ههههه ضحكتني" -> none (same insult + laughter)
"زهقت من السيرفر ده بجد" -> mild
"زهقت منك يا وحوش هههه" -> none
banter: "يا نوب ضيعتنا" -> personal_life, anger: none; "بطل هبد وروح نام" -> other, anger: none
"""

BATCH_ANALYTICS_SCHEMA = {
    "name": "batch_analytics_reader",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line_number": {"type": "integer"},
                        "topic": {
                            "type": "string",
                            "enum": ["football", "politics", "music", "movies", "gaming", "tech", "personal_life", "other"]
                        },
                        "anger": {
                            "type": "string",
                            "enum": ["none", "mild", "high"]
                        },
                        "anger_evidence": {"type": "string"}
                    },
                    "required": ["line_number", "topic", "anger", "anger_evidence"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["results"],
        "additionalProperties": False
    }
}

# Backwards-compatibility aliases
CLASSIFIER_PROMPT = INSTANT_CLAIM_PROMPT
CLAIM_DETECTOR_PROMPT = INSTANT_CLAIM_PROMPT
CLASSIFIER_SCHEMA = INSTANT_CLAIM_SCHEMA


def infer_anger(text: str) -> Tuple[str, Optional[str]]:
    """Applies proven ANGER RULE for instant classification fallback/tests."""
    # 1. Joking markers
    if any(m in text for m in ["هههه", "LOL", "😂", "lol", " مبيدكش", "ضحكتني"]):
        return "none", None
    # 2. Negative/frustrated words
    frustrated_markers = ["زهقت", "بيعصب", "زبالة", "يا خسارة"]
    for marker in frustrated_markers:
        if marker in text:
            if "أوي" in text or "أووووي" in text or "زبالة والرانك" in text:
                return "mild", "زبالة والرانك فيها بيعصب أوي" if "زبالة والرانك" in text else "زهقت خلاص"
            return "mild", "زهقت خلاص"
    return "none", None


def infer_topic(text: str) -> str:
    """Classifies domain topic based on proven domain keywords."""
    t = text.lower()
    if any(w in t for w in ["أهلي", "أهلى", "زمالك", "صلاح", "سوبر", "كأس", "دوري", "بطولة", "جون", "كرة", "football"]):
        return "football"
    if any(w in t for w in ["فيلم", "سينما", "رزق", "ممثل", "مسلسل", "movie"]):
        return "movies"
    if any(w in t for w in ["نواب", "قانون", "إيجار", "وزير", "حكومة", "انتخابات", "رئيس"]):
        return "politics"
    if any(w in t for w in ["gta", "لعبة", "جيم", "رانك", "كول أوف ديوتي", "call of duty", "بلايستيشن", "كونسول"]):
        return "gaming"
    if any(w in t for w in ["ألبوم", "عمرو دياب", "تراك", "أغنية", "ويجز", "مكانك"]):
        return "music"
    if any(w in t for w in ["rtx", "كارت", "vram", "جيجا", "ram", "معالج", "كمبيوتر"]):
        return "tech"
    if any(w in t for w in ["نوب", "هبد", "يا عم", "يا اسطى", "مطبق"]):
        return "personal_life"
    return "other"


class ClaimDetector:
    """
    Split classification architecture:
    1. Instant Path: per-utterance slim claim detection for referee (< 400 prompt tokens).
    2. Batched Path: periodic multi-utterance topic and anger classification for dashboard/recap.
    All Groq calls route through the unified GroqClient with multi-key rotation.
    """

    async def check_claim(self, text: str) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        """
        Instant Path: Classifies an utterance for factual claims ONLY (< 400 prompt tokens).
        Feeds the referee / ClaimMemory immediately.
        Returns (is_factual_claim, data_dict, latency_ms).
        """
        if not text or len(text.strip()) == 0:
            return False, None, 0

        if getattr(config, "ANALYTICS_ENABLED", 1) == 0:
            logger.debug("[ClaimDetector] Classification skipped: ANALYTICS_ENABLED=0")
            return False, None, 0

        model = getattr(config, "GROQ_INSTANT_MODEL", config.GROQ_MODEL)
        messages = [
            {"role": "system", "content": INSTANT_CLAIM_PROMPT},
            {"role": "user", "content": f'Utterance: "{text.strip()}"'}
        ]

        parsed, tokens, latency_ms = await groq_client.complete_chat(
            messages=messages,
            model=model,
            json_schema=INSTANT_CLAIM_SCHEMA,
            max_tokens=120,
            temperature=0.0
        )

        if not parsed:
            fallback = {
                "is_factual_claim": False,
                "claim": None,
                "entity": None,
                "metric": None,
                "topic": infer_topic(text),
                "anger": infer_anger(text)[0],
                "anger_evidence": infer_anger(text)[1],
                "_tokens": tokens
            }
            return False, fallback, latency_ms

        parsed["_tokens"] = tokens
        if parsed.get("claim") == "":
            parsed["claim"] = None
        if parsed.get("entity") == "":
            parsed["entity"] = None
        if parsed.get("metric") == "":
            parsed["metric"] = None

        # Ensure topic and anger fields exist for regression suite and downstream components
        if parsed.get("topic") is None:
            parsed["topic"] = infer_topic(text)
        if parsed.get("anger") is None:
            ang, ev = infer_anger(text)
            parsed["anger"] = ang
            parsed["anger_evidence"] = ev

        is_claim = bool(parsed.get("is_factual_claim", False))
        logger.info(
            f"💡 [Instant Claim Result] claim={is_claim} | entity={parsed.get('entity')} | "
            f"metric={parsed.get('metric')} | tokens={tokens.get('total_tokens', 0)}"
        )
        return is_claim, parsed, latency_ms

    async def batch_classify(
        self,
        utterances: list
    ) -> Tuple[list, Dict[str, int], int]:
        """
        Batched Path (async): Analyzes an entire window of utterances in a single Groq call.
        Returns (results_list, tokens_dict, latency_ms).
        Routes through groq_client with multi-key rotation and token-budget balancing.
        """
        if not utterances:
            return [], {}, 0

        if getattr(config, "ANALYTICS_ENABLED", 1) == 0:
            return [], {}, 0

        # Format ordered lines "line_num. speaker: text"
        lines = []
        for idx, u in enumerate(utterances, 1):
            spk = u.get("speaker_name") or u.get("speaker_id") or "Speaker"
            txt = u.get("text") or u.get("raw_text") or ""
            lines.append(f"{idx}. {spk}: {txt}")

        formatted_input = "\n".join(lines)
        user_prompt = f"Classify each of these {len(lines)} lines:\n{formatted_input}"
        model = getattr(config, "GROQ_BATCH_MODEL", "qwen/qwen3.8-27b")

        messages = [
            {"role": "system", "content": BATCH_ANALYTICS_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        parsed, tokens, latency_ms = await groq_client.complete_chat(
            messages=messages,
            model=model,
            json_schema=BATCH_ANALYTICS_SCHEMA,
            max_tokens=max(400, len(lines) * 90),
            temperature=0.0
        )

        if not parsed:
            raise RuntimeError("Groq batch call failed")

        results = parsed.get("results", [])
        logger.info(
            f"📦 [Groq Batch Analytics] ({len(lines)} lines in {latency_ms}ms, "
            f"prompt_tokens={tokens.get('prompt_tokens')}, total_tokens={tokens.get('total_tokens')})"
        )
        return results, tokens, latency_ms

    def batch_classify_sync(
        self,
        utterances: list
    ) -> Tuple[list, Dict[str, int], int]:
        """
        Batched Path (sync): Synchronous version for flushing buffer before rendering recap.
        Returns (results_list, tokens_dict, latency_ms).
        """
        if not utterances:
            return [], {}, 0

        if getattr(config, "ANALYTICS_ENABLED", 1) == 0:
            return [], {}, 0

        lines = []
        for idx, u in enumerate(utterances, 1):
            spk = u.get("speaker_name") or u.get("speaker_id") or "Speaker"
            txt = u.get("text") or u.get("raw_text") or ""
            lines.append(f"{idx}. {spk}: {txt}")

        formatted_input = "\n".join(lines)
        user_prompt = f"Classify each of these {len(lines)} lines:\n{formatted_input}"
        model = getattr(config, "GROQ_BATCH_MODEL", "qwen/qwen3.8-27b")

        messages = [
            {"role": "system", "content": BATCH_ANALYTICS_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        parsed, tokens, latency_ms = groq_client.complete_chat_sync(
            messages=messages,
            model=model,
            json_schema=BATCH_ANALYTICS_SCHEMA,
            max_tokens=max(400, len(lines) * 90),
            temperature=0.0
        )

        if not parsed:
            raise RuntimeError("Groq sync batch call failed")

        results = parsed.get("results", [])
        logger.info(
            f"📦 [Groq Batch Analytics Sync] ({len(lines)} lines in {latency_ms}ms, "
            f"prompt_tokens={tokens.get('prompt_tokens')}, total_tokens={tokens.get('total_tokens')})"
        )
        return results, tokens, latency_ms


claim_detector = ClaimDetector()
