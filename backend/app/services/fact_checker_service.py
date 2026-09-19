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
        """Dynamically builds search query from contested claims without topic hardcoding."""
        from app.services.analyzer_service import normalize_conversational_text
        norm_a = normalize_conversational_text(claim_a)
        norm_b = normalize_conversational_text(claim_b)

        noise_words = {
            "بص", "يا", "عم", "أنا", "انا", "انت", "أنت", "متأكد", "فاهم", "غلط", "صح", "لا", "مش", "في", "من", "على",
            "هو", "هي", "ده", "دي", "حبيبي", "كلام", "فارغ", "عارف", "شايف", "يعني", "أصلا", "اصلا", "بقى",
            "bro", "man", "no", "not", "wrong", "actually", "sure", "think", "telling", "you", "i'm", "im", "the",
            "is", "was", "are", "were", "that", "this", "it", "they", "in", "on", "at", "to", "for", "with"
        }

        tokens_a = [w for w in re.findall(r'[\w\d]+', norm_a) if w.lower() not in noise_words and len(w) > 1]
        tokens_b = [w for w in re.findall(r'[\w\d]+', norm_b) if w.lower() not in noise_words and len(w) > 1]

        # Extract asserted numbers & expand 2-digit years
        nums_a = re.findall(r'\d+', norm_a)
        nums_b = re.findall(r'\d+', norm_b)
        all_nums: List[str] = []
        for n in nums_a + nums_b:
            if n not in all_nums:
                all_nums.append(n)
                if len(n) == 2 and n.isdigit():
                    val = int(n)
                    century = f"19{n}" if val >= 35 else f"20{n}"
                    if century not in all_nums:
                        all_nums.append(century)

        subjs_a = [w for w in tokens_a if not w.isdigit()]
        subjs_b = [w for w in tokens_b if not w.isdigit()]

        # Combine subject words preserving order
        unique_subjs: List[str] = []
        for w in subjs_a + subjs_b:
            if w.lower() not in [s.lower() for s in unique_subjs]:
                unique_subjs.append(w)

        query_tokens = unique_subjs[:4] + all_nums[:4]
        if query_tokens:
            return " ".join(query_tokens).strip()

        return f"{norm_a} {norm_b}".strip()

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
        """Grounded evidence evaluation across any domain with semantic proximity arbitration."""
        snippets_combined = "\n".join([f"- {s['title']}: {s['snippet']}" for s in sources[:4]])

        # Fast path with Gemini if available and has active quota
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
                    f"- factual_truth: exact truth statement (<= 12 words)\n"
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
                logger.warning(f"[FactChecker] Gemini unavailable, using linguistic arbitrator: {e}")

        # High-Speed Linguistic & Proximity Arbitrator (Universal, zero-dependency)
        def normalize_w(w: str) -> str:
            w = w.lower()
            w = re.sub(r'[أإآ]', 'ا', w)
            w = re.sub(r'ة', 'ه', w)
            w = re.sub(r'ى', 'ي', w)
            if w.startswith('ال') and len(w) > 3:
                w = w[2:]
            return w

        noise = {
            "بص", "يا", "عم", "أنا", "انا", "انت", "أنت", "متأكد", "فاهم", "غلط", "صح", "لا", "مش", "في", "من", "على",
            "هو", "هي", "ده", "دي", "bro", "no", "not", "wrong", "the", "is", "was", "in", "at", "that", "actually"
        }

        raw_a = [w for w in re.findall(r'[\w\d]+', claim_a) if len(w) > 1 and w.lower() not in noise]
        raw_b = [w for w in re.findall(r'[\w\d]+', claim_b) if len(w) > 1 and w.lower() not in noise]

        norm_a = {normalize_w(w): w for w in raw_a}
        norm_b = {normalize_w(w): w for w in raw_b}

        diff_a_norm = set(norm_a.keys()) - set(norm_b.keys())
        diff_b_norm = set(norm_b.keys()) - set(norm_a.keys())
        common_norm = set(norm_a.keys()) & set(norm_b.keys())

        from app.services.analyzer_service import normalize_conversational_text
        norm_a_str = normalize_conversational_text(claim_a)
        norm_b_str = normalize_conversational_text(claim_b)

        # Detect numbers explicitly negated with 'مش' or 'not'
        neg_a = set(re.findall(r'(?:مش|not)\s*(\d+)', norm_a_str))
        neg_b = set(re.findall(r'(?:مش|not)\s*(\d+)', norm_b_str))

        numbers_a = (set(re.findall(r'\d+', norm_a_str)) - neg_a) | neg_b
        numbers_b = (set(re.findall(r'\d+', norm_b_str)) - neg_b) | neg_a

        score_a = 0
        score_b = 0
        best_sentence = ""

        def num_matches_text(n: str, text: str) -> bool:
            if n in text:
                return True
            if len(n) == 2 and n.isdigit():
                val = int(n)
                century = f"19{n}" if val >= 35 else f"20{n}"
                return century in text
            return False

        for s in sources:
            full_text = f"{s.get('title', '')}. {s.get('snippet', '')}"
            sentences = re.split(r'[\.\!\?\n\r]+', full_text)
            for sentence in sentences:
                sent_clean = sentence.strip()
                if not sent_clean:
                    continue
                tokens = [normalize_w(w) for w in re.findall(r'[\w\d]+', sent_clean)]
                sent_norm = set(tokens)

                # 1. Number & Year matching with 2-to-4 digit expansion
                has_num_a = any(num_matches_text(n, sent_clean) for n in numbers_a)
                has_num_b = any(num_matches_text(n, sent_clean) for n in numbers_b)
                if has_num_a and not has_num_b:
                    score_a += 6
                    best_sentence = sent_clean
                elif has_num_b and not has_num_a:
                    score_b += 6
                    best_sentence = sent_clean

                # 2. Proximity scoring between common subject and contested targets
                if common_norm and (diff_a_norm or diff_b_norm):
                    sub_pos = [i for i, w in enumerate(tokens) if w in common_norm]
                    tar_pos_a = [i for i, w in enumerate(tokens) if w in diff_a_norm]
                    tar_pos_b = [i for i, w in enumerate(tokens) if w in diff_b_norm]

                    if sub_pos and tar_pos_a:
                        min_dist_a = min(abs(sp - tp) for sp in sub_pos for tp in tar_pos_a)
                        score_a += max(1, 10 - min_dist_a)
                        if not best_sentence or score_a > score_b:
                            best_sentence = sent_clean

                    if sub_pos and tar_pos_b:
                        min_dist_b = min(abs(sp - tp) for sp in sub_pos for tp in tar_pos_b)
                        score_b += max(1, 10 - min_dist_b)
                        if not best_sentence or score_b > score_a:
                            best_sentence = sent_clean

        # Clean best sentence to concise snippet
        if len(best_sentence) > 130:
            best_sentence = best_sentence[:130].rsplit(' ', 1)[0] + "..."

        winner = None
        factual_truth = ""
        if score_a > score_b and score_a >= 4:
            winner = "speaker_a"
            factual_truth = best_sentence or f"تأكيد صحة كلام الطرف الأول: {claim_a}"
        elif score_b > score_a and score_b >= 4:
            winner = "speaker_b"
            factual_truth = best_sentence or f"تأكيد صحة كلام الطرف الثاني: {claim_b}"

        if winner:
            return {
                "result": "supported",
                "confidence": min(0.96, 0.80 + (0.02 * max(score_a, score_b))),
                "evidence": f"المصادر الرسمية تؤكد: {factual_truth}",
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
