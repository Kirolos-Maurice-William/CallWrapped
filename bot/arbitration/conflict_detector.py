import logging
from typing import Dict, Any, Optional, Tuple
from bot.ai.groq import groq_client

logger = logging.getLogger("ConflictDetector")

CONFIDENCE_THRESHOLD = 70

CONFLICT_PROMPT = """You are a precision conversational intelligence arbitrator analyzing statements in a live voice call.
Your job is to determine if two opposing statements present an OBJECTIVE, MUTUALLY EXCLUSIVE FACTUAL CONTRADICTION on a verifiable public topic.

=== CRITICAL EVALUATION RULES ===

1. CONFLICT AUTHENTICITY GATE:
   - 'has_conflict' is TRUE ONLY IF two different speakers assert INCOMPATIBLE, MUTUALLY EXCLUSIVE factual values for the same objective fact (e.g., specs, numbers, scores, dates, official names).
   - CASUAL MENTIONS / UNRELATED: If one speaker states a fact and another makes a casual comment or mentions an unrelated aspect, there is NO conflict:
     * "Ronaldo scored 2 goals" vs "ماتش امبارح كان وحش" -> has_conflict: false, rejection_reason: "casual_mention"
   - AGREEMENT: If both speakers state or agree on the same value, there is NO conflict:
     * Speaker A: "16 جيجا" vs Speaker B: "16 جيجا" (or "أيوة 16 جيجا") -> has_conflict: false, rejection_reason: "agreement"
   - OPINIONS / SUBJECTIVE CLAIMS: Value judgments, tastes, quality assessments, or subjective rankings are NEVER factual conflicts:
     * "صلاح أحسن لاعب" vs "لأ ميسي أحسن" -> has_conflict: false, rejection_reason: "opinion"
     * "Apex is better than Warzone" vs "No Warzone is better" -> has_conflict: false, rejection_reason: "opinion"

2. PRIVATE-ENTITY REFUSAL GATE:
   - Before any fact-checking or web lookup, classify the subject entity as 'PUBLIC' or 'PRIVATE'.
   - 'PRIVATE' ENTITIES: Bare first names, nicknames, call participants, friends, family, or private personal events that cannot be verified on the public web.
     * Egyptian bare first names without celebrity/public context: محمد, أحمد, مصطفى, عمر, محمود, علي, سارة, كريم, طارق, etc.
     * Examples:
       - "محمد قال الماتش الساعة 8" vs "لا هو قال 9" -> entity_type: "PRIVATE", entity_name: "محمد", has_conflict: false, rejection_reason: "private_entity"
       - "أحمد اشترى العربية ب 200 ألف" vs "لا جابها ب 180" -> entity_type: "PRIVATE", entity_name: "أحمد", has_conflict: false, rejection_reason: "private_entity"
       - "مصطفى نجح بامتياز" vs "لا جاب جيد جدا" -> entity_type: "PRIVATE", entity_name: "مصطفى", has_conflict: false, rejection_reason: "private_entity"
     * ANY private entity claim MUST be REFUSED: set entity_type: "PRIVATE", has_conflict: false, rejection_reason: "private_entity".
   - 'PUBLIC' ENTITIES: Internationally or nationally known celebrities, public figures, professional athletes, companies, hardware, games, or public events.
     * Famous public footballer Mohamed Salah referred to simply as "صلاح" or "محمد صلاح" in sports context is PUBLIC:
       - "صلاح سجل هدفين" vs "لا هدف واحد" -> entity_type: "PUBLIC", entity_name: "Mohamed Salah", has_conflict: true, conflict_type: "sports_stat"
     * Hardware / products / games / teams are PUBLIC:
       - "فيها 16 جيجا" vs "لا هي 12 بس" (e.g. RTX 5070) -> entity_type: "PUBLIC", entity_name: "Hardware Spec", has_conflict: true, conflict_type: "numeric_spec"

3. CONFIDENCE SCORE (0 to 100):
   - Score your confidence in this decision from 0 to 100.
   - Clear, unambiguous contradictions on public facts should have confidence >= 90.
   - Ambiguous, vague, or borderline statements should have confidence < 70.

4. SEARCH QUERY:
   - If has_conflict is true and entity_type is 'PUBLIC', formulate an unbiased, high-precision search query in English (Latin alphabet) to find official ground-truth documentation.
   - If has_conflict is false or entity_type is 'PRIVATE', leave search_query empty ("").

Respond STRICTLY in JSON:
{
  "has_conflict": true,
  "confidence": 95,
  "entity_type": "PUBLIC",
  "entity_name": "Name of entity",
  "conflict_type": "numeric_spec",
  "disputed_aspect": "concise description of what is disputed",
  "search_query": "English search query or empty string",
  "target_domains": ["domain1.com"],
  "rejection_reason": "none"
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
        if not data:
            return False, None, latency_ms

        entity_type = data.get("entity_type", "PUBLIC")
        entity_name = data.get("entity_name", "unknown")
        confidence = int(data.get("confidence") or 0)
        has_conflict = bool(data.get("has_conflict"))
        disputed_aspect = data.get("disputed_aspect", "")
        rejection_reason = data.get("rejection_reason", "none")

        # 1. Private Entity Refusal Gate
        if entity_type == "PRIVATE":
            data["is_refused_private"] = True
            data["dashboard_label"] = "Private claim — no lookup performed"
            logger.info(
                f"🚫 [Referee Refusal] Private entity detected ('{entity_name}'): "
                f"Private claim — no lookup performed (confidence {confidence})"
            )
            return False, data, latency_ms

        # 2. Confidence Threshold Gate
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                f"[Referee] Rejected: low confidence on '{disputed_aspect or rejection_reason}' "
                f"(confidence {confidence})"
            )
            return False, data, latency_ms

        # 3. Authenticity Conflict Gate
        if not has_conflict:
            logger.info(
                f"[Referee] Rejected: {rejection_reason} - '{disputed_aspect}' "
                f"(confidence {confidence})"
            )
            return False, data, latency_ms

        # 4. Verified Public Conflict
        logger.info(
            f"⚔️ [Referee Approved] Public conflict confirmed on '{entity_name}' "
            f"({latency_ms}ms, confidence {confidence}%) Type: {data.get('conflict_type')} | "
            f"Query: '{data.get('search_query')}'"
        )
        return True, data, latency_ms


conflict_detector = ConflictDetector()
