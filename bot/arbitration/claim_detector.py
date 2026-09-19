import logging
from typing import Optional, Dict, Any, Tuple
from bot.ai.groq import groq_client
from bot.arbitration.fast_gate import fast_gate

logger = logging.getLogger("ClaimDetector")

CLAIM_DETECTOR_PROMPT = """You are a fast, lightweight conversational gatekeeper.
Given a single transcript utterance from a casual voice call (bilingual Egyptian Arabic + English):
Determine if the sentence contains an OBJECTIVELY VERIFIABLE REAL-WORLD FACTUAL CLAIM (e.g. computer hardware specs, release dates, video game versions, sports results, celebrity ages, science/geography).

STRICT CRITERIA:
1. Casual chat, opinions, subjective feelings, greetings, questions, banter MUST be false:
   - "ألو سامعني؟" -> false
   - "أنا عملت update للـ game والـ ping عالي" -> false (personal gameplay experience)
   - "الفيلم ده جامد أوي" -> false (opinion)
2. Only TRUE if it asserts an objective, verifiable world fact:
   - "Bro, RTX 5070 has 16GB VRAM" -> true (Entity: "RTX 5070", Topic: "hardware", Metric: "VRAM")
   - "Minecraft 1.21 نزلت قبل 1.20" -> true (Entity: "Minecraft", Topic: "gaming", Metric: "release order")
   - "ميسي اتولد سنة 2000" -> true (Entity: "Lionel Messi", Topic: "sports", Metric: "birth year")

Respond STRICTLY in JSON:
{
  "is_factual_claim": true,
  "claim": "concise extracted claim statement",
  "topic": "hardware" | "gaming" | "sports" | "tech" | "movies" | "general" | null,
  "entity": "concise subject entity name" | null,
  "metric": "property being asserted (e.g. VRAM, release_date, age, price)" | null
}"""


class ClaimDetector:
    """Two-tier claim detector: Local FastGate -> Groq LPU (~150ms)."""

    async def check_claim(self, text: str) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        """
        Returns (is_claim, claim_data, latency_ms).
        FastGate filters out non-candidates before hitting Groq API.
        """
        if not text or len(text.strip()) < 4:
            return False, None, 0

        # Tier 1: Local Fast Gate
        is_candidate, reason = fast_gate.is_candidate(text)
        if not is_candidate:
            logger.debug(f"🛑 [FastGate Rejected] '{text}' ({reason})")
            return False, None, 0

        # Tier 2: Groq LPU Structured Extraction
        user_prompt = f'Utterance: "{text.strip()}"'
        data, latency_ms = await groq_client.complete_json(CLAIM_DETECTOR_PROMPT, user_prompt)
        if data and data.get("is_factual_claim"):
            logger.info(
                f"💡 [Factual Claim Detected] ({latency_ms}ms) "
                f"Entity: {data.get('entity')} | Metric: {data.get('metric')}"
            )
            return True, data, latency_ms

        return False, None, latency_ms


claim_detector = ClaimDetector()
