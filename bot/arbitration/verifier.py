import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from bot.config import config

logger = logging.getLogger("FactVerifier")

ARBITRATION_PROMPT = """You are an authoritative real-time fact-checking arbitrator.
Given two disputed claims from a voice call and authoritative web evidence snippets:
Determine:
1. Is the fact conclusively confirmed or contradicted? ('supported' if evidence proves one speaker right, 'inconclusive' if web snippets don't clearly prove either).
2. Confidence score (0 to 100).
3. Factual truth statement: A concise, natural Egyptian Arabic sentence (under 12 words) stating the exact verified fact.
4. Correct speaker: 'speaker_a', 'speaker_b', or 'neither'.
5. Short 1-sentence explanation of evidence.

Respond STRICTLY in JSON format:
{
  "status": "supported" / "inconclusive",
  "confidence": 95,
  "factual_truth": "ميسي اتولد سنة 1987 في الأرجنتين",
  "correct_speaker": "speaker_a" / "speaker_b" / "neither",
  "explanation": "Official FIFA and biographical records confirm Lionel Messi's birth date as June 24, 1987."
}"""


class FactVerifier:
    """Queries live web sources (Tavily / DuckDuckGo) and synthesizes verified verdicts via Groq LPU."""

    def __init__(self):
        self.tavily_key = config.TAVILY_API_KEY
        self.groq_key = config.GROQ_API_KEY

    async def search_evidence(self, query: str) -> List[Dict[str, str]]:
        if not query:
            return []

        # 1. Try Tavily API if key exists
        if self.tavily_key:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": self.tavily_key,
                            "query": query,
                            "search_depth": "basic",
                            "max_results": 3
                        }
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")} for r in results]
            except Exception as e:
                logger.debug(f"[Tavily] Notice: {e}")

        # 2. Free DuckDuckGo instant fallback (zero key needed)
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
                resp = await client.get(ddg_url)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = data.get("AbstractText", "")
                    src_url = data.get("AbstractURL", "")
                    if abstract:
                        return [{"title": data.get("Heading", "Wikipedia"), "url": src_url, "snippet": abstract}]
        except Exception as e:
            logger.debug(f"[DDG] Notice: {e}")

        return []

    async def verify_and_arbitrate(
        self,
        speaker_a: str,
        claim_a: str,
        speaker_b: str,
        claim_b: str,
        search_query: str
    ) -> Optional[Dict[str, Any]]:
        evidence = await self.search_evidence(search_query)
        if not evidence or not self.groq_key:
            return None

        evidence_text = "\n".join([f"- [{e['title']}]: {e['snippet']}" for e in evidence])
        user_prompt = (
            f'Speaker A ({speaker_a}): "{claim_a}"\n'
            f'Speaker B ({speaker_b}): "{claim_b}"\n\n'
            f'Search Evidence for "{search_query}":\n{evidence_text}'
        )

        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": ARBITRATION_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                if resp.status_code == 200:
                    verdict = json.loads(resp.json()["choices"][0]["message"]["content"])
                    verdict["sources"] = evidence
                    return verdict
        except Exception as e:
            logger.error(f"[FactVerifier] Error: {e}")
        return None


fact_verifier = FactVerifier()
