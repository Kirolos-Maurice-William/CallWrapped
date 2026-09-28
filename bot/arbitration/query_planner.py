import re
import time
import asyncio
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import tldextract
from pydantic import BaseModel, Field, field_validator

from bot.config import config
from bot.ai.groq import groq_client
from bot.ai.tavily import tavily_client, TIER_1_DOMAINS, TIER_2_DOMAINS, classify_domain_tier

logger = logging.getLogger("QueryPlanner")


class AmbiguityType(str, Enum):
    NONE = "none"
    TEMPORAL = "temporal"
    ENTITY = "entity"
    SCOPE = "scope"
    COMPARATIVE = "comparative"


class ClaimSearchPlan(BaseModel):
    subject: str = Field(description="Subject entity of the claim")
    predicate: str = Field(description="Relation or attribute being claimed")
    object: Optional[str] = Field(default=None, description="Target value, object, or counter-claim")
    time_anchor: Optional[str] = Field(default=None, description="Explicit year, date, or edition mentioned in the claim")
    time_anchor_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in the time anchor from 0.0 to 1.0")
    ambiguity_type: AmbiguityType = Field(default=AmbiguityType.NONE, description="Type of ambiguity detected")
    query_variants: List[str] = Field(default_factory=list, description="1 to 3 search query variants in English")

    @field_validator("query_variants")
    @classmethod
    def validate_query_variants(cls, v: List[str]) -> List[str]:
        cleaned = [q.strip() for q in v if q and q.strip()]
        if not cleaned:
            raise ValueError("query_variants must contain at least 1 non-empty query")
        return cleaned[:3]


STEP_BACK_PROMPT = """You transform a fact-check claim into retrieval planning metadata.
Do not answer the claim. Do not invent facts.
If a date/edition/office is missing, set ambiguity_type and emit NO query that assumes it.

=== RETRIEVAL PLANNING RULES ===
1. TIME ANCHORS & TEMPORAL AMBIGUITY:
   - If the input claim contains an explicit year (4-digit number, Arabic-Indic digits, or written year), you MUST set time_anchor to that year with time_anchor_confidence >= 0.9. Never return time_anchor=null when a year is present in the input.
   - If an explicit year (e.g. 4-digit year like "2022", "2024", "1998") or date appears in the claim text or speaker utterances:
     * You MUST set `time_anchor` = the exact year string (e.g. "2022").
     * Set `time_anchor_confidence` = 1.0.
     * `ambiguity_type` MUST NOT be "temporal" (set to "none" or "comparative").
     * All emitted queries MUST include this explicit year.
   - If the claim is about a tournament, match, election, office, or recurring event, but NO specific year or date is mentioned anywhere in the input:
     * Set `ambiguity_type` = "temporal"
     * Set `time_anchor` = null
     * Set `time_anchor_confidence` = 0.0
     * FORBIDDEN: Do NOT invent, assume, or guess a year (e.g. do NOT inject "2022" or "2026" if not stated in the input).
     * Step-Back Abstraction: Generate queries about the tournament's overall champions / winners history or most recent official list.

2. AMBIGUITY TYPES:
   - "none": Clear, unambiguous claim with all needed anchors.
   - "temporal": Missing year, edition, or time frame for a recurring event.
   - "entity": Ambiguous, vague, or multi-meaning entity.
   - "scope": Regional, platform, or hardware version ambiguity.
   - "comparative": Two speakers assert conflicting opposing values for the same metric/entity.

3. QUERY VARIANT RULES (Strictly 1 to 3 queries in English, Latin alphabet):
   - Variant A (canonical): "{entity}" {relation} {time_anchor} (omit time_anchor if missing).
   - Variant B (authoritative): Same + domain hint (e.g. site:fifa.com for football/sports, site:nvidia.com for hardware specs, etc.).
   - Variant C (Step-Back / comparative paraphrase): When ambiguity is present or two opposing claims are compared, emit this 3rd broader or comparative query.
   - CONSTRAINT: Maximum 3 query variants. Emit all 3 variants whenever a conflict or ambiguity (temporal, comparative, entity, scope) is detected; emit 2 variants if ambiguity is "none".
"""

PLANNER_SCHEMA = {
    "name": "claim_search_planner",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "predicate": {"type": "string"},
            "object": {"type": ["string", "null"]},
            "time_anchor": {"type": ["string", "null"]},
            "time_anchor_confidence": {"type": "number"},
            "ambiguity_type": {
                "type": "string",
                "enum": ["none", "temporal", "entity", "scope", "comparative"]
            },
            "query_variants": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3
            }
        },
        "required": [
            "subject",
            "predicate",
            "object",
            "time_anchor",
            "time_anchor_confidence",
            "ambiguity_type",
            "query_variants"
        ],
        "additionalProperties": False
    }
}
 
 
ARABIC_INDIC_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
YEAR_REGEX = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')


def extract_year_from_text(text: Optional[str]) -> Optional[str]:
    """
    Scans text for 4-digit years (1900-2099), supporting Western and Arabic-Indic digits.
    Returns the first matching year string or None.
    """
    if not text:
        return None
    norm_text = text.translate(ARABIC_INDIC_DIGITS_TRANS)
    match = re.search(r'\b(19|20)\d{2}\b', norm_text) or YEAR_REGEX.search(norm_text)
    if match:
        return match.group(0)
    return None


def get_canonical_key(url: str) -> Tuple[str, str]:
    """Returns (canonical_url, registered_domain) for deduplication."""
    ext = tldextract.extract(url)
    reg_domain = getattr(ext, "top_domain_under_public_suffix", None) or getattr(ext, "registered_domain", "")
    reg_domain = reg_domain.lower() if reg_domain else ""
    p = urlparse(url)
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/")
    canonical_url = f"{netloc}{path}"
    return canonical_url, reg_domain


def jaccard_similarity(s1: str, s2: str) -> float:
    """Computes word-level Jaccard similarity between two text snippets."""
    w1 = set(re.findall(r'\b\w{3,}\b', s1.lower()))
    w2 = set(re.findall(r'\b\w{3,}\b', s2.lower()))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def compute_authority_bonus(doc: Dict[str, Any], target_domains: Optional[List[str]] = None) -> float:
    """Computes authority bonus: 1.0 for Tier 1 / target / official domains, 0.5 for Tier 2, 0.0 otherwise."""
    domain = doc.get("domain", "").lower()
    url = doc.get("url", "").lower()
    tier = doc.get("source_tier")
    if tier is None:
        tier = classify_domain_tier(url, target_domains=target_domains)

    if tier == 1:
        return 1.0
    if target_domains and any(td.lower() in domain for td in target_domains):
        return 1.0
    if any(domain.endswith(t1) or domain == t1 for t1 in TIER_1_DOMAINS):
        return 1.0
    if "fifa.com" in domain or "nvidia.com" in domain or "apple.com" in domain:
        return 1.0
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 1.0
    if tier == 2 or any(domain.endswith(t2) or domain == t2 for t2 in TIER_2_DOMAINS):
        return 0.5
    return 0.0


def compute_direct_coverage(doc: Dict[str, Any], claim_context: Optional[str] = None, entity: Optional[str] = None) -> float:
    """Estimates whether the retrieved snippet directly addresses the entity and claim."""
    text = (doc.get("title", "") + " " + doc.get("snippet", "")).lower()
    if not text.strip():
        return 0.0
    score = 0.0
    if entity and entity.lower() in text:
        score += 0.5
    if claim_context:
        keywords = [w.lower() for w in re.findall(r'\b\w{3,}\b', claim_context)]
        if keywords:
            matches = sum(1 for kw in set(keywords) if kw in text)
            score += 0.5 * min(1.0, matches / max(1, min(len(keywords), 4)))
    return min(1.0, score if (entity or claim_context) else 0.5)


def reciprocal_rank_fusion(
    results_per_query: List[List[Dict[str, Any]]],
    query_variants: List[str],
    target_domains: Optional[List[str]] = None,
    claim_context: Optional[str] = None,
    entity: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Merges multi-query search results using Reciprocal Rank Fusion:
    score(d) = sum(1/(60 + rank_q(d)))
             + 0.15 * authority_bonus(d)
             + 0.10 * direct_coverage(d)
             - 0.20 * duplicate_penalty(d)
    """
    docs: Dict[str, Dict[str, Any]] = {}
    ranks: Dict[str, Dict[int, int]] = {}

    for q_idx, res in enumerate(results_per_query):
        for rank_0, item in enumerate(res):
            rank = rank_0 + 1
            can_url, reg_dom = get_canonical_key(item.get("url", ""))
            if not can_url:
                continue

            if can_url not in docs:
                doc_copy = dict(item)
                doc_copy["canonical_url"] = can_url
                doc_copy["registered_domain"] = reg_dom
                doc_copy["queries_matched"] = [query_variants[q_idx]] if q_idx < len(query_variants) else []
                docs[can_url] = doc_copy
                ranks[can_url] = {q_idx: rank}
            else:
                ranks[can_url][q_idx] = rank
                if q_idx < len(query_variants):
                    docs[can_url]["queries_matched"].append(query_variants[q_idx])

    if not docs:
        return []

    # 1. Preliminary scoring
    scored = []
    for can_url, doc in docs.items():
        rrf_base = sum(1.0 / (60.0 + r) for r in ranks[can_url].values())
        auth_bonus = compute_authority_bonus(doc, target_domains=target_domains)
        cov = compute_direct_coverage(doc, claim_context=claim_context, entity=entity)
        raw_score = rrf_base + 0.15 * auth_bonus + 0.10 * cov
        scored.append((raw_score, rrf_base, auth_bonus, cov, doc))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 2. Duplicate penalty against higher-ranked results
    final_results = []
    selected_snippets: List[str] = []

    for raw_score, rrf_base, auth_bonus, cov, doc in scored:
        snip = doc.get("snippet", "")
        is_dup = any(jaccard_similarity(snip, prev) > 0.65 for prev in selected_snippets)
        dup_penalty = 1.0 if is_dup else 0.0
        final_score = rrf_base + 0.15 * auth_bonus + 0.10 * cov - 0.20 * dup_penalty

        doc["rrf_score"] = round(final_score, 4)
        doc["rrf_base"] = round(rrf_base, 4)
        doc["authority_bonus"] = round(auth_bonus, 2)
        doc["direct_coverage"] = round(cov, 2)
        doc["duplicate_penalty"] = round(dup_penalty, 2)

        final_results.append((final_score, doc))
        selected_snippets.append(snip)

    final_results.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in final_results]


class QueryPlanner:
    """Transforms raw conversational claims into structured Step-Back retrieval plans and fan-out searches."""

    def __init__(self, model_name: Optional[str] = None):
        # Strict constraint: production model qwen/qwen3.8-27b (NOT llama-3.3-70b)
        self.model_name = model_name or config.GROQ_MODEL

    async def plan_search(
        self,
        entity: Optional[str] = None,
        dimension: Optional[str] = None,
        speaker_a: Optional[str] = None,
        claim_a: Optional[str] = None,
        speaker_b: Optional[str] = None,
        claim_b: Optional[str] = None,
        fallback_query: Optional[str] = None,
        target_domains: Optional[List[str]] = None
    ) -> ClaimSearchPlan:
        """
        Generates a ClaimSearchPlan with Step-Back abstraction and 1 to 3 query variants.
        Uses Groq structured output (json_schema) with qwen/qwen3.8-27b.
        """
        user_content_lines = []
        if entity:
            user_content_lines.append(f"Entity: {entity}")
        if dimension:
            user_content_lines.append(f"Dimension / Metric: {dimension}")
        if claim_a:
            spk_label = f"Speaker A ({speaker_a})" if speaker_a else "Claim A"
            user_content_lines.append(f"{spk_label}: \"{claim_a}\"")
        if claim_b:
            spk_label = f"Speaker B ({speaker_b})" if speaker_b else "Claim B"
            user_content_lines.append(f"{spk_label}: \"{claim_b}\"")
        if fallback_query and fallback_query not in (claim_a or "", claim_b or ""):
            user_content_lines.append(f"Search Query / Context: \"{fallback_query}\"")

        user_content = "\n".join(user_content_lines) or "Verify current topic"

        try:
            data, _, latency_ms = await groq_client.complete_chat(
                messages=[
                    {"role": "system", "content": STEP_BACK_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                model=self.model_name,
                json_schema=PLANNER_SCHEMA,
                temperature=0.0
            )
            if data:
                # Deterministic fallback: scan raw claim text for 4-digit years
                raw_inputs = " ".join(filter(None, [claim_a, claim_b, dimension, fallback_query, entity]))
                extracted_year = extract_year_from_text(raw_inputs)
                if not data.get("time_anchor") and extracted_year:
                    data["time_anchor"] = extracted_year
                    data["time_anchor_confidence"] = max(data.get("time_anchor_confidence", 0.0), 1.0)
                    if data.get("ambiguity_type") in ("temporal", AmbiguityType.TEMPORAL.value):
                        data["ambiguity_type"] = AmbiguityType.NONE.value
                    logger.info(f"[QueryPlanner] LLM missed year, deterministic fallback: {extracted_year}")

                # Ensure queries are capped at 3 max
                variants = data.get("query_variants", [])
                if not variants and fallback_query:
                    variants = [fallback_query]
                clean_variants = [q.strip() for q in variants if q and q.strip()]
                # If an explicit time_anchor exists, ensure at least one variant includes it
                anchor = data.get("time_anchor")
                if anchor and clean_variants and not any(anchor in q for q in clean_variants):
                    clean_variants[0] = f"{clean_variants[0]} {anchor}"
                data["query_variants"] = clean_variants[:3]

                plan = ClaimSearchPlan(**data)
                logger.info(
                    f"🗺️ [QueryPlanner] ({latency_ms}ms) Planned {len(plan.query_variants)} queries "
                    f"| ambiguity={plan.ambiguity_type.value} | anchor={plan.time_anchor}"
                )
                return plan
        except Exception as e:
            logger.warning(f"⚠️ [QueryPlanner] Groq planning error: {e}")

        # Fallback single-query plan
        raw_inputs = " ".join(filter(None, [claim_a, claim_b, dimension, fallback_query, entity]))
        fallback_year = extract_year_from_text(raw_inputs)
        canonical = fallback_query or entity or "verifiable fact check"
        if fallback_year and fallback_year not in canonical:
            canonical = f"{canonical} {fallback_year}"
        return ClaimSearchPlan(
            subject=entity or "unknown",
            predicate=dimension or "attribute",
            object=None,
            time_anchor=fallback_year,
            time_anchor_confidence=1.0 if fallback_year else 0.0,
            ambiguity_type=AmbiguityType.NONE,
            query_variants=[canonical]
        )

    async def execute_fan_out_search(
        self,
        query_variants: List[str],
        target_domains: Optional[List[str]] = None,
        claim_context: Optional[str] = None,
        entity: Optional[str] = None,
        budget_sec: float = 3.0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Executes concurrent Tavily searches across 1-3 query variants and merges using RRF.
        Budget: 3.0s max.
        Returns (top_sources, total_search_ms).
        """
        variants = [q.strip() for q in query_variants if q and q.strip()][:3]
        if not variants:
            return [], 0

        t0 = time.perf_counter()

        # If only 1 variant, fast path through single search
        if len(variants) == 1:
            sources, search_ms = await tavily_client.search(variants[0], target_domains=target_domains)
            for s in sources:
                s["rrf_score"] = 1.0
            return sources[:5], search_ms

        # Multi-query fan-out search with budget
        tasks = [asyncio.create_task(tavily_client.search(q, target_domains=target_domains)) for q in variants]
        done, pending = await asyncio.wait(tasks, timeout=budget_sec)
        if pending:
            logger.warning(f"⚠️ [FanOutSearch] {len(pending)} searches exceeded budget of {budget_sec}s")
            for p in pending:
                p.cancel()

        total_search_ms = int((time.perf_counter() - t0) * 1000)

        results_per_query: List[List[Dict[str, Any]]] = []
        valid_queries: List[str] = []

        for i, t in enumerate(tasks):
            if t in done and not t.cancelled() and not t.exception():
                resp = t.result()
                if isinstance(resp, tuple) and len(resp) == 2 and isinstance(resp[0], list):
                    results_per_query.append(resp[0])
                    valid_queries.append(variants[i])
                elif not isinstance(resp, Exception) and isinstance(resp, list):
                    results_per_query.append(resp)
                    valid_queries.append(variants[i])
                else:
                    logger.debug(f"[FanOutSearch] Variant #{i+1} ('{variants[i]}') error: {resp}")

        if not results_per_query:
            # Fallback to single search on variant A
            logger.info("ℹ️ [FanOutSearch] Falling back to primary variant search")
            sources, search_ms = await tavily_client.search(variants[0], target_domains=target_domains)
            for s in sources:
                s["rrf_score"] = 1.0
            return sources[:5], search_ms

        merged = reciprocal_rank_fusion(
            results_per_query=results_per_query,
            query_variants=valid_queries,
            target_domains=target_domains,
            claim_context=claim_context,
            entity=entity
        )

        logger.info(
            f"⚡ [FanOutSearch] ({total_search_ms}ms) Merged {len(merged)} unique docs "
            f"across {len(valid_queries)} queries via RRF"
        )
        return merged[:5], total_search_ms


query_planner = QueryPlanner()
