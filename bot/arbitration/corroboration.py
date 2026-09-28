"""
Corroboration & Source Independence Filter.

Deduplicates syndicated/co-dependent search results so the verifier
counts INDEPENDENT sources only.  Pipeline position:

  fan-out RRF results  →  independence_filter()  →  synthesize_verdict()

Three stages:
1. Domain extraction   — tldextract registered-domain grouping
2. Near-duplicate det. — 5-gram character-shingle Jaccard on title+snippet
3. Corroboration score — independent_count → verdict trust tier
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple

import tldextract

from bot.ai.tavily import classify_domain_tier

logger = logging.getLogger("Corroboration")


# ---------------------------------------------------------------------------
# 1. Domain extraction
# ---------------------------------------------------------------------------

def extract_registered_domain(url: str) -> str:
    """Return the registered domain for a URL (e.g. news.bbc.co.uk → bbc.co.uk)."""
    ext = tldextract.extract(url)
    reg = (
        getattr(ext, "top_domain_under_public_suffix", None)
        or getattr(ext, "registered_domain", "")
    )
    return (reg or "").lower()


# ---------------------------------------------------------------------------
# 2. Near-duplicate detection — character 5-gram Jaccard
# ---------------------------------------------------------------------------

def _char_shingles(text: str, n: int = 5) -> Set[str]:
    """Generate character n-gram shingles from text."""
    text = text.lower().strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def jaccard_char_ngram(text_a: str, text_b: str, n: int = 5) -> float:
    """Jaccard similarity on character n-gram shingles."""
    sa = _char_shingles(text_a, n)
    sb = _char_shingles(text_b, n)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------------------
# 3. Corroboration result
# ---------------------------------------------------------------------------

@dataclass
class CorroborationResult:
    """Output of the independence filter."""
    independent_sources: List[Dict[str, Any]]
    independent_count: int
    total_before_filter: int
    duplicate_clusters: List[List[Dict[str, Any]]] = field(default_factory=list)
    has_official_source: bool = False
    verdict_tier: str = "confident"  # "confident" | "hedged_single" | "abstain"

    # Arabic hedged-plus text for single-source verdicts
    HEDGED_SINGLE_AR = (
        "المعلومة دي لقيتها في مصدر واحد بس — مش متأكد منها أوي، "
        "الرابط على الداشبورد"
    )


# ---------------------------------------------------------------------------
# 4. Independence filter
# ---------------------------------------------------------------------------

# Jaccard threshold above which two results are considered co-dependent
DUPLICATE_THRESHOLD = 0.45


def _source_text(src: Dict[str, Any]) -> str:
    """Combine title+snippet for duplicate comparison."""
    return f"{src.get('title', '')} {src.get('snippet', '')}".strip()


def _is_official(src: Dict[str, Any], target_domains: Optional[List[str]] = None) -> bool:
    """Check whether a source is Tier-1 (official/primary).

    Mirrors compute_authority_bonus logic: classify_domain_tier +
    hardcoded official domains (fifa.com, etc.) + .gov/.edu.
    """
    url = src.get("url", "")
    tier = src.get("source_tier")
    if tier is None:
        tier = classify_domain_tier(url, target_domains=target_domains)
    if tier == 1:
        return True
    # Fallback: registered domain check for known official orgs
    # (same list as compute_authority_bonus in query_planner.py)
    domain = extract_registered_domain(url)
    if domain in _OFFICIAL_DOMAINS:
        return True
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return True
    return False


# Official org domains not in TIER_1_DOMAINS but recognized as authoritative
_OFFICIAL_DOMAINS = {
    "fifa.com", "uefa.com", "olympics.com",
    "nvidia.com", "apple.com", "amd.com", "intel.com", "microsoft.com",
    "sony.com", "google.com",
}


def independence_filter(
    sources: List[Dict[str, Any]],
    target_domains: Optional[List[str]] = None,
) -> CorroborationResult:
    """
    Filter fan-out search results for source independence.

    Algorithm:
    1. Group sources by registered domain.
    2. Within each domain group keep only the highest-ranked result
       (first in list, which is already sorted by RRF score).
    3. Across domain-deduplicated results, pairwise Jaccard 5-gram
       similarity check.  Pairs above DUPLICATE_THRESHOLD are clustered;
       only the strongest source per cluster survives.
    4. Score: independent_count + official-source flag → verdict_tier.
    """
    total = len(sources)
    if not sources:
        return CorroborationResult(
            independent_sources=[],
            independent_count=0,
            total_before_filter=0,
            verdict_tier="abstain",
        )

    # ---- Stage A: domain dedup ----
    domain_best: Dict[str, Dict[str, Any]] = {}
    domain_dupes: Dict[str, List[Dict[str, Any]]] = {}
    for src in sources:
        dom = extract_registered_domain(src.get("url", ""))
        if not dom:
            dom = "__unknown__"
        if dom not in domain_best:
            domain_best[dom] = src
            domain_dupes[dom] = []
        else:
            domain_dupes[dom].append(src)

    domain_unique = list(domain_best.values())
    logger.debug(
        f"[Corroboration] Domain dedup: {total} → {len(domain_unique)} "
        f"(domains: {list(domain_best.keys())})"
    )

    # ---- Stage B: cross-domain near-duplicate clustering ----
    n = len(domain_unique)
    parent = list(range(n))  # union-find

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            sim = jaccard_char_ngram(
                _source_text(domain_unique[i]),
                _source_text(domain_unique[j]),
            )
            if sim > DUPLICATE_THRESHOLD:
                union(i, j)
                logger.debug(
                    f"[Corroboration] Near-dup cluster: "
                    f"{extract_registered_domain(domain_unique[i].get('url',''))} ↔ "
                    f"{extract_registered_domain(domain_unique[j].get('url',''))} "
                    f"(Jaccard={sim:.3f})"
                )

    # Collect clusters — keep the best (first by list order = highest RRF) per cluster
    clusters: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    independent: List[Dict[str, Any]] = []
    duplicate_clusters: List[List[Dict[str, Any]]] = []
    for members in clusters.values():
        # Best = first member (lowest index = highest RRF rank)
        best_idx = min(members)
        independent.append(domain_unique[best_idx])
        if len(members) > 1:
            duplicate_clusters.append([domain_unique[m] for m in members])

    # ---- Stage C: verdict tier ----
    has_official = any(_is_official(s, target_domains) for s in independent)
    ind_count = len(independent)

    if ind_count >= 2 or (ind_count >= 1 and has_official):
        tier = "confident"
    elif ind_count == 1:
        tier = "hedged_single"
    else:
        tier = "abstain"

    logger.info(
        f"[Corroboration] {total} sources → {ind_count} independent | "
        f"official={has_official} | tier={tier} | "
        f"clusters_merged={len(duplicate_clusters)}"
    )

    return CorroborationResult(
        independent_sources=independent,
        independent_count=ind_count,
        total_before_filter=total,
        duplicate_clusters=duplicate_clusters,
        has_official_source=has_official,
        verdict_tier=tier,
    )
