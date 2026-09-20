import time
import json
import asyncio
import logging
from typing import Optional, Dict, Any, Tuple
import httpx
from bot.config import config

logger = logging.getLogger("ClaimDetector")

# Compact Every-Utterance Classifier Prompt (<= 350 tokens)
# Contains 2 Egyptian-Arabic example sentences PER topic, plus banter mapping to personal_life or other.
CLASSIFIER_PROMPT = """Classify voice chat (Egyptian Arabic/English).
JSON fields:
- is_factual_claim: true ONLY for verifiable facts (opinions/banter=false)
- claim: concise fact or ""
- entity: subject or ""
- metric: asserted spec or ""
- topic: football|politics|music|movies|gaming|tech|personal_life|other
- anger: none|mild|high
- anger_evidence: quote or ""
Write claim, entity, metric, and anger_evidence in the SAME language as the input utterance.

ANGER RULE (check in order):
1. Joking markers present: "هههه", "LOL", "😂", playful teasing, exaggeration for laughs -> anger: none
2. No joking markers AND negative/frustrated words: ranting, complaining, "زهقت", "بيعصب", cursing at the game/server/situation -> anger: mild (high if intense, e.g. "أووووي", CAPS)
3. Calm neutral talk -> none
When unsure: laughter present = none. No laughter + negative words = mild.

Examples:
football: "الأهلي كسب 2-1"(true), "صلاح أحسن لاعب"(false)
politics: "الانتخابات في 6"(true), "الوزير فاشل"(false)
music: "ألبوم ويجز في 2024"(true), "صوته تحفة"(false)
movies: "ولاد رزق في سينما"(true), "الفيلم وحش"(false)
gaming: "تحديث 1.21 نزل"(true), "لعبة زبالة"(false)
tech: "كارت 5070 بـ 12 جيجا"(true), "أبل أحسن"(false)
personal_life: "أنا مطبق من الصبح"(false), "رايح الجيم"(false)
other: "الجو حر النهارده"(false), "سامعني؟"(false)

Twin-pair examples:
"الكول أوف ديوتي زبالة والرانك بيعصب أوي"->mild (rant, no laughter)
"انت زبالة يا عم ههههه ضحكتني"->none (same insult + laughter)
"زهقت من السيرفر ده بجد"->mild
"زهقت منك يا وحوش هههه"->none
banter: "يا نوب ضيعتنا"->personal_life, anger: none; "بطل هبد وروح نام"->other, anger: none"""

# Backwards-compatibility alias
CLAIM_DETECTOR_PROMPT = CLASSIFIER_PROMPT

# Strict JSON Schema for Groq API
CLASSIFIER_SCHEMA = {
    "name": "utterance_classifier",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "is_factual_claim": {"type": "boolean"},
            "claim": {"type": "string"},
            "entity": {"type": "string"},
            "metric": {"type": "string"},
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
        "required": ["is_factual_claim", "claim", "entity", "metric", "topic", "anger", "anger_evidence"],
        "additionalProperties": False
    }
}


def parse_reset_time(reset_header: Optional[str]) -> float:
    """Parses rate-limit reset duration from Groq response headers."""
    if not reset_header:
        return 1.0
    val = reset_header.strip().lower()
    try:
        if val.endswith("ms"):
            return max(0.1, float(val[:-2]) / 1000.0)
        elif val.endswith("s"):
            return max(0.1, float(val[:-1]))
        elif val.endswith("m"):
            return max(1.0, float(val[:-1]) * 60.0)
        return max(0.1, float(val))
    except Exception:
        return 1.0


class ClaimDetector:
    """
    Every-utterance classifier using Groq LPU with strict json_schema.
    Classifies topic, anger, and verifies factual claims on every utterance.
    """

    async def check_claim(self, text: str) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        """
        Classifies an utterance.
        Returns (is_factual_claim, data_dict, latency_ms).
        """
        if not text or len(text.strip()) == 0:
            return False, None, 0

        # Feature flag: if ANALYTICS_ENABLED is 0, skip classification entirely
        if getattr(config, "ANALYTICS_ENABLED", 1) == 0:
            logger.debug("[ClaimDetector] Classification skipped: ANALYTICS_ENABLED=0")
            return False, None, 0

        if not config.GROQ_API_KEY:
            logger.warning("[ClaimDetector] GROQ_API_KEY is missing, skipping classification")
            return False, None, 0

        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": f'Utterance: "{text.strip()}"'}
            ],
            "response_format": {"type": "json_schema", "json_schema": CLASSIFIER_SCHEMA},
            "max_tokens": 200,
            "temperature": 0.0
        }

        t0 = time.perf_counter()
        resp = None

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)

                # HTTP 429: Retry ONCE after x-ratelimit-reset-tokens wait
                if resp.status_code == 429:
                    reset_header = resp.headers.get("x-ratelimit-reset-tokens") or resp.headers.get("x-ratelimit-reset-requests")
                    wait_sec = parse_reset_time(reset_header)
                    logger.warning(f"⚠️ [ClaimDetector 429] Rate limit hit. Waiting {wait_sec:.3f}s for 1x retry...")
                    await asyncio.sleep(wait_sec)
                    resp = await client.post(endpoint, headers=headers, json=payload)
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(f"[ClaimDetector] Network error during classification: {e}")
            fallback = {
                "is_factual_claim": False,
                "claim": None,
                "entity": None,
                "metric": None,
                "topic": "other",
                "anger": "none",
                "anger_evidence": None
            }
            return False, fallback, latency_ms

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Handle non-200 responses gracefully
        if not resp or resp.status_code != 200:
            err_msg = resp.text[:200] if resp else "No response"
            logger.warning(f"[ClaimDetector] Groq returned HTTP {resp.status_code if resp else 'N/A'}: {err_msg}")
            fallback = {
                "is_factual_claim": False,
                "claim": None,
                "entity": None,
                "metric": None,
                "topic": "other",
                "anger": "none",
                "anger_evidence": None
            }
            return False, fallback, latency_ms

        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        logger.info(
            f"📊 [Groq Utterance Classifier] ({latency_ms}ms, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}, total={total_tokens})"
        )

        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            parsed = json.loads(raw_content)
            parsed["_tokens"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
            # Normalize empty strings to None
            if parsed.get("claim") == "":
                parsed["claim"] = None
            if parsed.get("entity") == "":
                parsed["entity"] = None
            if parsed.get("metric") == "":
                parsed["metric"] = None
            if parsed.get("anger_evidence") == "":
                parsed["anger_evidence"] = None

            is_claim = bool(parsed.get("is_factual_claim", False))
            logger.info(
                f"💡 [Classifier Result] topic={parsed.get('topic')} | anger={parsed.get('anger')} | "
                f"claim={is_claim} | entity={parsed.get('entity')}"
            )
            return is_claim, parsed, latency_ms
        except Exception as e:
            logger.warning(f"⚠️ [ClaimDetector] JSON parse failed: {e}. Raw response: '{raw_content}'")
            fallback = {
                "is_factual_claim": False,
                "claim": None,
                "entity": None,
                "metric": None,
                "topic": "other",
                "anger": "none",
                "anger_evidence": None
            }
            return False, fallback, latency_ms


claim_detector = ClaimDetector()
