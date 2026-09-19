import logging
from typing import Dict, Any, Optional, Tuple
from bot.ai.groq import groq_client

logger = logging.getLogger("ConflictDetector")

CONFLICT_PROMPT = """You are a precision conversational intelligence arbitrator analyzing two opposing statements in a live voice call.
Your job is to determine if the two statements present an OBJECTIVE, MUTUALLY EXCLUSIVE FACTUAL CONTRADICTION that can be verified via authoritative sources.

RULES:
1. Subjective disagreements, opinions, or personal preferences are NOT conflicts:
   - "Apex is better than Warzone" vs "No Warzone is better" -> has_conflict: false
2. Direct factual contradictions on specs, dates, prices, names, version numbers ARE conflicts:
   - "RTX 5070 has 16GB VRAM" vs "No, RTX 5070 has 12GB" -> has_conflict: true
   - "Release date was 2024" vs "It came out in 2023" -> has_conflict: true
3. Formulate an unbiased, high-precision search query that will find official ground-truth documentation.

Respond STRICTLY in JSON:
{
  "has_conflict": true,
  "conflict_type": "numeric_spec" | "release_date" | "existence" | "identity" | "other",
  "disputed_aspect": "concise description of what is disputed",
  "search_query": "specific search terms for official documentation",
  "target_domains": ["domain1.com", "domain2.com"]
}"""


class ConflictDetector:
    """Analyzes opposing speaker claims for factual contradictions using Groq LPU."""

    async def detect_conflict(
        self,
        speaker_a: str,
        claim_a: str,
        speaker_b: str,
        claim_b: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        user_prompt = (
            f"Speaker A ({speaker_a}): \"{claim_a}\"\n"
            f"Speaker B ({speaker_b}): \"{claim_b}\""
        )
        data, latency_ms = await groq_client.complete_json(CONFLICT_PROMPT, user_prompt)
        if data and data.get("has_conflict"):
            logger.info(
                f"⚔️ [Conflict Confirmed] ({latency_ms}ms) Type: {data.get('conflict_type')} | "
                f"Query: '{data.get('search_query')}'"
            )
            return True, data, latency_ms

        return False, None, latency_ms


conflict_detector = ConflictDetector()
