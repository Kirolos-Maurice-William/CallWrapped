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
1. 'speaker_a_status' and 'speaker_b_status': Must each be 'SUPPORTED', 'CONTRADICTED', or 'UNVERIFIABLE'.
2. 'evidence_strength': 'HIGH' (official manufacturer/gov/peer-reviewed docs), 'MEDIUM' (reputable tech media/encyclopedia), or 'LOW' (indirect/sparse).
3. 'correct_fact': Exactly 1 objective, concise factual sentence drawn directly from the evidence snippets.
4. 'selected_source_url': The most authoritative source URL from the provided evidence list.
5. 'selected_source_title': Title of that source.

Respond STRICTLY in JSON:
{
  "speaker_a_status": "CONTRADICTED" | "SUPPORTED" | "UNVERIFIABLE",
  "speaker_b_status": "CONTRADICTED" | "SUPPORTED" | "UNVERIFIABLE",
  "evidence_strength": "HIGH" | "MEDIUM" | "LOW",
  "confidence": 95,
  "correct_fact": "NVIDIA RTX 5070 has 12GB of GDDR7 memory, while the RTX 5070 Ti has 16GB.",
  "selected_source_url": "https://www.nvidia.com/...",
  "selected_source_title": "NVIDIA Official Product Specifications"
}"""


class ArbitrationVerifier:
    """Queries Tavily and synthesizes evidence into an objective verdict without hallucination."""

    def format_intervention_template(
        self,
        assessment: Dict[str, Any],
        is_arabic: bool = False
    ) -> str:
        """
        Builds a strict template-based spoken intervention:
        CONTRADICTED: 'Correction: {fact}. Source: {domain}'
        SUPPORTED: 'That claim is verified: {fact}. Source: {domain}'
        UNVERIFIABLE: 'I could not verify that claim from a reliable source.'
        """
        fact = assessment.get("correct_fact", "").strip()
        url = assessment.get("selected_source_url", "")
        domain = urlparse(url).netloc.replace("www.", "") if url else "Official Documentation"

        a_status = assessment.get("speaker_a_status")
        b_status = assessment.get("speaker_b_status")

        has_contradiction = "CONTRADICTED" in (a_status, b_status)
        has_supported = "SUPPORTED" in (a_status, b_status)

        if has_contradiction:
            return f"Correction: {fact} Source: {domain}."
        elif has_supported:
            return f"That claim is verified: {fact} Source: {domain}."
        else:
            return "Unable to verify this claim from reliable sources."

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
        Returns (assessment_dict, search_ms, llm_ms, sources).
        """
        # Step 1: Search using Tiered Source Policy
        sources, search_ms = await tavily_client.search(search_query, target_domains=target_domains)
        if not sources:
            return None, search_ms, 0, []

        # Format Evidence Snippets
        evidence_snippets = "\n".join([
            f"[Source {i+1} - Tier {s.get('source_tier', 3)}] {s['title']} ({s['domain']}):\n{s['snippet']}\nURL: {s['url']}"
            for i, s in enumerate(sources[:4])
        ])

        user_prompt = (
            f"Conversation Context:\n"
            f"- {speaker_a} claimed: \"{claim_a}\"\n"
            f"- {speaker_b} claimed: \"{claim_b}\"\n\n"
            f"Authoritative Web Evidence (Sorted by Trust Tier):\n{evidence_snippets}"
        )

        # Step 2: Groq LPU evaluates evidence
        assessment, llm_ms = await groq_client.complete_json(VERIFICATION_SYNTHESIS_PROMPT, user_prompt)
        if assessment:
            assessment["sources"] = sources
            if not assessment.get("selected_source_url") and sources:
                assessment["selected_source_url"] = sources[0].get("url")
                assessment["selected_source_title"] = sources[0].get("title", "Official Source")

            # Check if conversation has Arabic characters
            has_arabic = any("\u0600" <= c <= "\u06FF" for c in (claim_a + claim_b))

            # Step 3: Enforce template-based intervention
            spoken_text = self.format_intervention_template(assessment, is_arabic=has_arabic)
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


arbitration_verifier = ArbitrationVerifier()
