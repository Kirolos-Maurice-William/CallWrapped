import time
import logging
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple, Optional
import httpx
from bot.config import config

logger = logging.getLogger("TavilyClient")

# Source Policy Tiers
TIER_1_DOMAINS = {
    "nvidia.com", "amd.com", "intel.com", "apple.com", "microsoft.com",
    "sony.com", "playstation.com", "xbox.com", "nintendo.com", "google.com",
    "github.com", "pypi.org", "w3.org", "mozilla.org", "kernel.org"
}

TIER_2_DOMAINS = {
    "wikipedia.org", "theverge.com", "tomshardware.com", "anandtech.com",
    "gsmarena.com", "ign.com", "techcrunch.com", "arstechnica.com",
    "reuters.com", "apnews.com", "bbc.com", "bloomberg.com"
}

TIER_4_BLOCKED = {
    "reddit.com", "quora.com", "twitter.com", "x.com", "facebook.com",
    "tiktok.com", "instagram.com", "yahoo.answers.com", "answers.com"
}


def classify_domain_tier(url: str, target_domains: Optional[List[str]] = None) -> int:
    """Classifies a URL into a Source Tier (1 = Highest authority, 4 = Lowest)."""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        if target_domains:
            for td in target_domains:
                if td.lower() in domain:
                    return 1

        if any(domain.endswith(t1) or domain == t1 for t1 in TIER_1_DOMAINS):
            return 1
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return 1

        if any(domain.endswith(t2) or domain == t2 for t2 in TIER_2_DOMAINS):
            return 2

        if any(domain.endswith(t4) or domain == t4 for t4 in TIER_4_BLOCKED):
            return 4

        return 3
    except Exception:
        return 3


class TavilyClient:
    """
    Tavily Search client with an explicit Source Policy:
    Tier 1: Official Documentation & Manufacturers
    Tier 2: Major Technical & Encyclopedic Sources
    Tier 3: General Web Pages
    Tier 4: User-Generated Forums / Social Media (deprioritized/filtered)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.TAVILY_API_KEY

    async def search(
        self,
        query: str,
        target_domains: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Executes a targeted search using Tavily (with DuckDuckGo fallback).
        Returns filtered, sorted results by Source Tier and the latency in ms.
        """
        if not query:
            return [], 0

        t0 = time.perf_counter()

        # 1. Primary: Tavily Search API
        if self.api_key:
            try:
                body: Dict[str, Any] = {
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_answer": True
                }
                if target_domains:
                    body["include_domains"] = target_domains

                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post("https://api.tavily.com/search", json=body)
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    if resp.status_code == 200:
                        raw_results = resp.json().get("results", [])
                        processed = []
                        for r in raw_results:
                            url = r.get("url", "")
                            tier = classify_domain_tier(url, target_domains)
                            if tier == 4:
                                continue  # Ignore unverified forums/social media
                            domain = urlparse(url).netloc.replace("www.", "")
                            processed.append({
                                "title": r.get("title", ""),
                                "url": url,
                                "domain": domain,
                                "snippet": r.get("content", ""),
                                "source_tier": tier
                            })

                        # Sort by source tier (Tier 1 first, then Tier 2, etc.)
                        processed.sort(key=lambda x: x["source_tier"])
                        logger.info(f"🌐 [Tavily Search] ({latency_ms}ms) Found {len(processed)} qualified sources for '{query}'")
                        return processed, latency_ms
            except Exception as e:
                logger.warning(f"[Tavily Search Error] {e}")

        # 2. Fallback: DuckDuckGo Instant Answers
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
                resp = await client.get(ddg_url)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = data.get("AbstractText", "")
                    if abstract:
                        url = data.get("AbstractURL", "https://wikipedia.org")
                        domain = urlparse(url).netloc.replace("www.", "")
                        return [{
                            "title": data.get("Heading", "Wikipedia Reference"),
                            "url": url,
                            "domain": domain,
                            "snippet": abstract,
                            "source_tier": 2
                        }], latency_ms
        except Exception:
            pass

        return [], int((time.perf_counter() - t0) * 1000)


tavily_client = TavilyClient()
