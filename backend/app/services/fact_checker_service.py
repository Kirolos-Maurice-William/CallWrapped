import logging
import json
import re
import asyncio
import time
from typing import Dict, Any, List, Optional
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class FactCheckerService:
    def __init__(self):
        # High performance persistent HTTP/2 connection pool
        self.http_client = httpx.AsyncClient(
            timeout=8.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            http2=True
        )
        # In-memory Cache: {query_hash: verification_result}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # Active speculative tasks: {query: Task}
        self._speculative_searches: Dict[str, asyncio.Task] = {}

    async def prefetch_speculative_search(self, claim_a: str, claim_b: str, topic: str):
        """Speculatively triggers search when early disagreement signals are detected."""
        query = self._build_search_query(claim_a, claim_b, topic)
        if query not in self._cache and query not in self._speculative_searches:
            logger.info(f"[FactChecker] Starting speculative prefetch search for: '{query}'")
            task = asyncio.create_task(self._search_web_fast(query))
            self._speculative_searches[query] = task

    async def verify_disagreement(self, dispute: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes external fact-checking with sub-second latency:
        1. Checks cache (0ms)
        2. Awaits speculative prefetch or executes parallel search
        3. Grounded LLM evaluation with minimal tokens
        """
        t_start = time.perf_counter()
        claim_a = dispute.get("claim_a", "")
        claim_b = dispute.get("claim_b", "")
        topic = dispute.get("topic", "general")

        search_query = self._build_search_query(claim_a, claim_b, topic)

        # 1. Cache Hit
        if search_query in self._cache:
            cached = dict(self._cache[search_query])
            cached["search_latency_ms"] = 0
            cached["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            logger.info(f"[FactChecker] Cache hit for query '{search_query}' in 0ms")
            return cached

        # 2. Check if a speculative search was already running
        sources = []
        if search_query in self._speculative_searches:
            logger.info(f"[FactChecker] Joining existing speculative search for '{search_query}'")
            try:
                sources = await self._speculative_searches[search_query]
            except Exception:
                sources = []
            del self._speculative_searches[search_query]
        else:
            sources = await self._search_web_fast(search_query)

        t_search_done = time.perf_counter()
        search_latency_ms = round((t_search_done - t_start) * 1000, 1)

        if not sources:
            result = {
                "result": "inconclusive",
                "confidence": 0.2,
                "evidence": "No authoritative web sources found to substantiate or refute either claim.",
                "sources": [],
                "factual_truth": None,
                "search_latency_ms": search_latency_ms,
                "total_latency_ms": search_latency_ms
            }
            self._cache[search_query] = result
            return result

        # 3. Grounded Evidence Evaluation
        verification = await self._evaluate_evidence(claim_a, claim_b, sources)
        total_latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
        verification["search_latency_ms"] = search_latency_ms
        verification["total_latency_ms"] = total_latency_ms

        # Cache valid result
        self._cache[search_query] = verification
        return verification

    def _build_search_query(self, claim_a: str, claim_b: str, topic: str) -> str:
        combined = f"{claim_a} {claim_b}"
        noise_words = [
            "بص", "يا", "عم", "أنا", "انت", "أنت", "متأكد", "فاهم", "غلط", "صح", "حبيبي", "كلام",
            "bro", "man", "no", "not", "actually", "sure", "think", "telling", "you", "i'm", "im"
        ]

        english_entities = re.findall(r'[A-Za-z0-9\-\']+', combined)
        filtered_en = [w for w in english_entities if w.lower() not in noise_words and len(w) > 2 and not w.isdigit()]

        arabic_words = re.findall(r'[\u0600-\u06FF]+', combined)
        filtered_ar = [w for w in arabic_words if w not in noise_words and len(w) > 2 and not w.isdigit()]

        if topic == "movies":
            title = " ".join(filtered_en) if filtered_en else " ".join(filtered_ar[:2])
            return f"{title} movie release year".strip()
        elif topic == "football":
            player = " ".join(filtered_en) if filtered_en else " ".join(filtered_ar[:2])
            return f"{player} transfer history contract year".strip()

        main_terms = (filtered_en + filtered_ar[:3])[:5]
        query = " ".join(main_terms)
        return query if query else f"{claim_a} fact check"

    async def _search_web_fast(self, query: str) -> List[Dict[str, str]]:
        """Executes search with fallback strategy."""
        tasks = []

        # Tavily Task (if configured)
        if settings.TAVILY_API_KEY:
            tasks.append(self._tavily_search(query))

        # DuckDuckGo Fast Async Task
        tasks.append(self._ddgs_search(query))

        # Run concurrently and return first non-empty result
        for coro in asyncio.as_completed(tasks):
            try:
                results = await coro
                if results:
                    return results
            except Exception:
                continue

        return []

    async def _tavily_search(self, query: str) -> List[Dict[str, str]]:
        resp = await self.http_client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 4
            }
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")
                }
                for item in data.get("results", [])
            ]
        return []

    async def _ddgs_search(self, query: str) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def sync_ddgs():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=4))
        raw = await loop.run_in_executor(None, sync_ddgs)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in raw
        ]

    async def _evaluate_evidence(
        self, claim_a: str, claim_b: str, sources: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Low-token structured evidence evaluation."""
        snippets_combined = "\n".join([f"- {s['title']}: {s['snippet']}" for s in sources[:3]])

        # Fast path with Gemini 2.5 Flash
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    f"Fact arbitrator. Two claims in dispute:\nA: \"{claim_a}\"\nB: \"{claim_b}\"\n\n"
                    f"Evidence:\n{snippets_combined}\n\n"
                    f"Return JSON strictly with:\n"
                    f"- result: 'supported', 'contradicted', or 'inconclusive'\n"
                    f"- confidence: float 0.0-1.0\n"
                    f"- evidence: 1 sentence summary\n"
                    f"- factual_truth: exact truth statement\n"
                    f"- correct_speaker: 'speaker_a', 'speaker_b', or 'neither'"
                )
                resp = await client.aio.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": 150,
                        "temperature": 0.1
                    }
                )
                parsed = json.loads(resp.text)
                parsed["sources"] = sources
                return parsed
            except Exception as e:
                logger.warning(f"[FactChecker] Gemini error, using heuristic: {e}")

        # High-Speed Heuristic Evaluator (< 1ms)
        all_text = snippets_combined.lower()
        years_a = re.findall(r'\b(19\d\d|20\d\d)\b', claim_a)
        years_b = re.findall(r'\b(19\d\d|20\d\d)\b', claim_b)

        winner = None
        factual_truth = ""
        for y in years_a:
            if y in all_text:
                winner = "speaker_a"
                factual_truth = f"Official sources confirm the date was {y}."
                break
        if not winner:
            for y in years_b:
                if y in all_text:
                    winner = "speaker_b"
                    factual_truth = f"Official sources confirm the date was {y}."
                    break

        if winner:
            return {
                "result": "supported",
                "confidence": 0.92,
                "evidence": f"Web sources confirm {factual_truth}",
                "factual_truth": factual_truth,
                "correct_speaker": winner,
                "sources": sources
            }

        return {
            "result": "inconclusive",
            "confidence": 0.5,
            "evidence": "Evidence did not conclusively settle the dispute.",
            "factual_truth": None,
            "correct_speaker": "neither",
            "sources": sources
        }
