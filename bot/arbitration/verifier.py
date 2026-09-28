import re
import logging
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Tuple, List
from bot.ai.tavily import tavily_client
from bot.ai.groq import groq_client

logger = logging.getLogger("ArbitrationVerifier")

VERIFICATION_SYNTHESIS_PROMPT = """You are an objective evidence-based fact-checking engine.
Evaluate two conversational statements against the retrieved ground-truth web search snippets.
Do NOT guess or hallucinate facts not supported by the evidence.

RULES:
1. FAST-PATH GROUNDING: If Tavily's 'include_answer' field is present and consistent with the retrieved snippets, GROUND your verdict in it (validate-and-format into the required JSON schema rather than re-reasoning from scratch). If include_answer is absent or conflicts with snippets, fall back to normal evidence reading.
2. 'speaker_a_status' and 'speaker_b_status': Must each be 'SUPPORTED', 'CONTRADICTED', or 'UNVERIFIABLE'.
3. 'evidence_strength': 'HIGH' (official manufacturer/gov/peer-reviewed docs), 'MEDIUM' (reputable tech media/encyclopedia), or 'LOW' (indirect/sparse).
4. 'correct_fact': Exactly 1 objective factual sentence, strictly 6 to 12 words in colloquial phrasing.
   - MANDATORY CONCISENESS & SHORTHAND: State ONLY the verified fact itself. Do NOT include comparison clauses, side-by-side specs, or extra commentary (e.g. state 'كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM' instead of comparing it with other models). Always use common shorthand/product names (e.g. 'RTX 5070' NOT 'NVIDIA GeForce RTX 5070').
   - LANGUAGE RULE (MANDATORY): 'correct_fact' MUST be written in the SAME LANGUAGE as the speakers' utterances. If the speakers' utterances are in Arabic, 'correct_fact' MUST be written in natural, fluent Arabic (translate from English evidence snippets as necessary; keep model names, numbers, and technical terms in Latin/digits as-is). Never output an English correct_fact for Arabic claims.
5. 'comparison_details': Put any comparison details, secondary model specs, or additional context here for the dashboard embed (e.g. 'RTX 5070 Ti features 16GB VRAM'). If no comparison, leave empty string.
6. 'selected_source_url': The most authoritative source URL from the provided evidence list.
7. 'selected_source_title': Title of that source.

Respond STRICTLY in JSON:
{
  "speaker_a_status": "CONTRADICTED" | "SUPPORTED" | "UNVERIFIABLE",
  "speaker_b_status": "CONTRADICTED" | "SUPPORTED" | "UNVERIFIABLE",
  "evidence_strength": "HIGH" | "MEDIUM" | "LOW",
  "confidence": 95,
  "correct_fact": "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16",
  "comparison_details": "RTX 5070 Ti features 16GB VRAM",
  "selected_source_url": "https://www.nvidia.com/...",
  "selected_source_title": "NVIDIA Official Product Specifications"
}"""


class ArbitrationVerifier:
    """Queries Tavily and synthesizes evidence into an objective verdict without hallucination."""

    def format_intervention_clauses(
        self,
        assessment: Dict[str, Any],
        is_arabic: bool = False
    ) -> Tuple[str, str]:
        """
        Builds two separate clauses for two-stage streaming:
        1. fact_clause (<= 12 words): Anchor and objective fact without comparison.
        2. hedge_clause: Social hedge and dashboard reference.
        Strips doubled punctuation to ensure clean spoken synthesis.
        """
        fact = assessment.get("correct_fact", "").strip()
        # Clean up any doubled punctuation inside and strip trailing punctuation
        fact = re.sub(r'([.،,:؛!?]){2,}', r'\1', fact)
        fact = fact.rstrip(" .،,:؛!?")

        a_status = assessment.get("speaker_a_status")
        b_status = assessment.get("speaker_b_status")

        has_contradiction = "CONTRADICTED" in (a_status, b_status)
        has_supported = "SUPPORTED" in (a_status, b_status)

        if is_arabic:
            if has_contradiction:
                fact_clause = f"تصحيح سريع: المصدر اللي لقيته بيقول {fact}."
                hedge_clause = "ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد."
            elif has_supported:
                fact_clause = f"تأكيد سريع: المصدر اللي لقيته بيقول {fact}."
                hedge_clause = "المصدر ظاهر في الداشبورد."
            else:
                fact_clause = "تعذر التحقق من المعلومة من مصادر موثوقة."
                hedge_clause = ""
        else:
            if has_contradiction:
                fact_clause = f"Quick fact check: the source I found says {fact}."
                hedge_clause = "I may have missed context — source is on the dashboard."
            elif has_supported:
                fact_clause = f"Quick fact check: the source I found confirms {fact}."
                hedge_clause = "Source is on the dashboard."
            else:
                fact_clause = "Unable to verify this claim from reliable sources."
                hedge_clause = ""

        return fact_clause, hedge_clause

    def format_intervention_template(
        self,
        assessment: Dict[str, Any],
        is_arabic: bool = False
    ) -> str:
        """
        Builds a hedged social template-based spoken intervention.
        Combines fact_clause and hedge_clause for backward compatibility.
        """
        fact_clause, hedge_clause = self.format_intervention_clauses(assessment, is_arabic=is_arabic)
        if hedge_clause:
            return f"{fact_clause} {hedge_clause}"
        return fact_clause

    async def search_evidence(
        self,
        search_query: str,
        target_domains: Optional[List[str]] = None,
        query_variants: Optional[List[str]] = None,
        claim_context: Optional[str] = None,
        entity: Optional[str] = None,
        dimension: Optional[str] = None,
        speaker_a: Optional[str] = None,
        claim_a: Optional[str] = None,
        speaker_b: Optional[str] = None,
        claim_b: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Queries Tavily using Step-Back Query Planning and Fan-out Search with RRF.
        If query planning fails or only 1 query is available, falls back to single-query search.
        """
        # 1. If explicit query_variants provided (>1), fan out directly
        if query_variants and len(query_variants) > 1:
            from bot.arbitration.query_planner import query_planner
            return await query_planner.execute_fan_out_search(
                query_variants=query_variants,
                target_domains=target_domains,
                claim_context=claim_context or (f"{claim_a} vs {claim_b}" if claim_a else None),
                entity=entity
            )

        # 2. If conversational context is available, run QueryPlanner for Step-Back fan-out
        if (claim_a and claim_b) or entity:
            try:
                from bot.arbitration.query_planner import query_planner
                plan = await query_planner.plan_search(
                    entity=entity,
                    dimension=dimension,
                    speaker_a=speaker_a,
                    claim_a=claim_a,
                    speaker_b=speaker_b,
                    claim_b=claim_b,
                    fallback_query=search_query,
                    target_domains=target_domains
                )
                if plan and plan.query_variants and len(plan.query_variants) > 1:
                    return await query_planner.execute_fan_out_search(
                        query_variants=plan.query_variants,
                        target_domains=target_domains,
                        claim_context=claim_context or f"{claim_a} vs {claim_b}",
                        entity=entity or plan.subject
                    )
                elif plan and plan.query_variants:
                    search_query = plan.query_variants[0]
            except Exception as e:
                logger.warning(f"⚠️ [SearchEvidence] Query planning failed, using single search: {e}")

        # 3. Single-query fallback
        return await tavily_client.search(search_query, target_domains=target_domains)

    async def search_evidence_fanout(
        self,
        query_variants: List[str],
        target_domains: Optional[List[str]] = None,
        claim_context: Optional[str] = None,
        entity: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Direct fan-out search helper with Reciprocal Rank Fusion."""
        from bot.arbitration.query_planner import query_planner
        return await query_planner.execute_fan_out_search(
            query_variants=query_variants,
            target_domains=target_domains,
            claim_context=claim_context,
            entity=entity
        )

    async def synthesize_verdict(
        self,
        speaker_a: str,
        claim_a: str,
        speaker_b: str,
        claim_b: str,
        sources: List[Dict[str, Any]],
        search_ms: int = 0
    ) -> Tuple[Optional[Dict[str, Any]], int, int, List[Dict[str, Any]]]:
        """Evaluates retrieved web evidence snippets and synthesizes a structured verdict."""
        if not sources:
            return None, search_ms, 0, []

        evidence_snippets = "\n".join([
            f"[Source {i+1} - Tier {s.get('source_tier', 3)}] {s.get('title', '')} ({s.get('domain', '')}):\n{s.get('snippet', '')[:350]}\nURL: {s.get('url', '')}"
            for i, s in enumerate(sources[:3])
        ])

        has_arabic = any("\u0600" <= c <= "\u06FF" for c in (claim_a + claim_b))
        lang_note = (
            "\nLanguage Note: The claims are in Arabic. 'correct_fact' MUST be written in natural Arabic (translate facts from English evidence as needed)."
            if has_arabic else ""
        )

        # Check for Tavily include_answer in retrieved search evidence
        include_answer = ""
        for s in sources:
            if s.get("answer"):
                include_answer = str(s["answer"]).strip()
                break
            elif s.get("include_answer"):
                include_answer = str(s["include_answer"]).strip()
                break

        answer_section = f"Tavily include_answer (Fast-Path):\n{include_answer}\n\n" if include_answer else ""

        user_prompt = (
            f"Conversation Context:\n"
            f"- {speaker_a} claimed: \"{claim_a}\"\n"
            f"- {speaker_b} claimed: \"{claim_b}\"{lang_note}\n\n"
            f"{answer_section}"
            f"Authoritative Web Evidence (Sorted by Trust Tier):\n{evidence_snippets}"
        )

        # Step 2: Groq LPU evaluates evidence with tightened token budget (~180 tokens)
        messages = [
            {"role": "system", "content": VERIFICATION_SYNTHESIS_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        assessment, tokens, llm_ms = await groq_client.complete_chat(
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=180,
            temperature=0.0
        )
        if not assessment:
            assessment, llm_ms = await groq_client.complete_json(VERIFICATION_SYNTHESIS_PROMPT, user_prompt)
        if assessment:
            assessment["sources"] = sources
            if not assessment.get("selected_source_url") and sources:
                assessment["selected_source_url"] = sources[0].get("url")
                assessment["selected_source_title"] = sources[0].get("title", "Official Source")

            # Check if conversation has Arabic characters
            has_arabic = any("\u0600" <= c <= "\u06FF" for c in (claim_a + claim_b))

            # Step 3: Enforce template-based intervention
            fact_clause, hedge_clause = self.format_intervention_clauses(assessment, is_arabic=has_arabic)
            spoken_text = self.format_intervention_template(assessment, is_arabic=has_arabic)
            assessment["fact_clause"] = fact_clause
            assessment["hedge_clause"] = hedge_clause
            assessment["comparison_details"] = assessment.get("comparison_details", "")
            assessment["spoken_intervention"] = spoken_text

            # Map status for backward/frontend compatibility
            if "CONTRADICTED" in (assessment.get("speaker_a_status"), assessment.get("speaker_b_status")):
                assessment["status"] = "CONTRADICTED"
            elif "SUPPORTED" in (assessment.get("speaker_a_status"), assessment.get("speaker_b_status")):
                assessment["status"] = "SUPPORTED"
            else:
                assessment["status"] = "UNVERIFIABLE"

            logger.info(f"🏆 [Verdict] ({search_ms}ms search, {llm_ms}ms LLM): {spoken_text}")
            return assessment, search_ms, llm_ms, sources

        return None, search_ms, llm_ms, sources

    async def verify_dispute(
        self,
        speaker_a: str,
        claim_a: str,
        speaker_b: str,
        claim_b: str,
        search_query: str,
        target_domains: Optional[List[str]] = None
    ) -> Tuple[Optional[Dict[str, Any]], int, int, List[Dict[str, Any]]]:
        """
        Backward-compatible wrapper: searches evidence and synthesizes verdict.
        Returns (assessment_dict, search_ms, llm_ms, sources).
        """
        sources, search_ms = await self.search_evidence(search_query, target_domains=target_domains)
        if not sources:
            return None, search_ms, 0, []
        return await self.synthesize_verdict(
            speaker_a=speaker_a,
            claim_a=claim_a,
            speaker_b=speaker_b,
            claim_b=claim_b,
            sources=sources,
            search_ms=search_ms
        )


arbitration_verifier = ArbitrationVerifier()
