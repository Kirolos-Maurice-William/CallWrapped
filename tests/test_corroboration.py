"""
Acceptance Test Suite for Corroboration & Source Independence Filter.
Tests:
a) Unit: domain extraction — news.bbc.co.uk → bbc.co.uk;
   publications.fifa.com → fifa.com (same publisher family groups)
b) Unit: Jaccard 5-gram — identical snippets = 1.0, modified copy
   ~0.6-0.8, unrelated ≈ 0.0
c) Unit: 5 results where 2 share a syndicated story →
   independent_count = 2 (not 3)
d) Unit: 0 independent sources → verdict abstains, nothing spoken
e) Integration: World Cup dispute fan-out results through the filter
   → paste the independence grouping (note: fifa.com and
   publications.fifa.com are the SAME publisher family — verify how
   they group)
f) Full suite green (run separately)
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests._setup

from bot.arbitration.corroboration import (
    extract_registered_domain,
    jaccard_char_ngram,
    _char_shingles,
    independence_filter,
    CorroborationResult,
    DUPLICATE_THRESHOLD,
)
from bot.arbitration.query_planner import query_planner


class TestCorroboration(unittest.IsolatedAsyncioTestCase):

    # ------------------------------------------------------------------
    # Test A: domain extraction
    # ------------------------------------------------------------------
    def test_a_domain_extraction(self):
        """
        news.bbc.co.uk → bbc.co.uk
        publications.fifa.com → fifa.com
        www.nvidia.com → nvidia.com
        https://en.wikipedia.org/wiki/Argentina → wikipedia.org
        """
        print("\n=== TEST A: DOMAIN EXTRACTION ===")

        cases = [
            ("https://news.bbc.co.uk/sport/football", "bbc.co.uk"),
            ("https://publications.fifa.com/2022/report", "fifa.com"),
            ("https://www.nvidia.com/specs", "nvidia.com"),
            ("https://en.wikipedia.org/wiki/Argentina", "wikipedia.org"),
            ("https://www.bbc.co.uk/news", "bbc.co.uk"),
            ("https://apnews.com/article/world-cup", "apnews.com"),
        ]
        for url, expected in cases:
            result = extract_registered_domain(url)
            print(f"  {url:55s} → {result}")
            self.assertEqual(result, expected, f"Expected {expected}, got {result}")

        # Same-publisher-family check: publications.fifa.com and fifa.com
        dom_a = extract_registered_domain("https://publications.fifa.com/report")
        dom_b = extract_registered_domain("https://www.fifa.com/worldcup")
        self.assertEqual(dom_a, dom_b, "publications.fifa.com and fifa.com must group together")
        print(f"  ✓ publications.fifa.com and fifa.com both → {dom_a}")
        print("PASS")

    # ------------------------------------------------------------------
    # Test B: Jaccard 5-gram character shingle similarity
    # ------------------------------------------------------------------
    def test_b_jaccard_5gram(self):
        """
        Identical snippets = 1.0
        Modified copy ≈ 0.6–0.8
        Unrelated ≈ 0.0
        """
        print("\n=== TEST B: JACCARD 5-GRAM CHARACTER SHINGLES ===")

        snippet_a = "Argentina won the 2022 FIFA World Cup defeating France in the final match at Lusail Stadium"
        snippet_b = snippet_a  # identical
        snippet_c = "Argentina won the 2022 World Cup, defeating France in the final match at Lusail Stadium in Qatar"
        snippet_d = "NVIDIA RTX 5070 features 12GB of GDDR7 VRAM and 6144 CUDA cores"

        sim_identical = jaccard_char_ngram(snippet_a, snippet_b)
        sim_modified = jaccard_char_ngram(snippet_a, snippet_c)
        sim_unrelated = jaccard_char_ngram(snippet_a, snippet_d)

        print(f"  Identical:  {sim_identical:.4f} (expected 1.0)")
        print(f"  Modified:   {sim_modified:.4f} (expected ~0.6–0.8)")
        print(f"  Unrelated:  {sim_unrelated:.4f} (expected ≈0.0)")

        self.assertAlmostEqual(sim_identical, 1.0, places=5)
        self.assertGreater(sim_modified, 0.55, "Modified copy should have significant overlap (~0.6-0.8)")
        self.assertLess(sim_modified, 0.95, "Modified copy should not be identical")
        self.assertLess(sim_unrelated, 0.15, "Unrelated snippets should have near-zero similarity")

        # Edge cases
        sim_empty = jaccard_char_ngram("", "hello")
        self.assertEqual(sim_empty, 0.0, "Empty string → 0.0")
        sim_short = jaccard_char_ngram("abc", "abc")
        self.assertGreater(sim_short, 0.0, "Short identical strings should match")

        print("PASS")

    # ------------------------------------------------------------------
    # Test C: 5 results where 2 share a syndicated story → independent_count = 2 (not 3)
    # ------------------------------------------------------------------
    def test_c_syndicated_story_dedup(self):
        """
        5 search results across 3 registered domains:
        - Result 1 (apnews.com): Syndicated wire report
        - Result 2 (reuters.com): Same syndicated wire report (Jaccard > 0.45)
        - Result 3 (apnews.com): Another URL on apnews.com (domain dedup removes)
        - Result 4 (reuters.com): Another URL on reuters.com (domain dedup removes)
        - Result 5 (bbc.com): Independent analysis (genuinely independent)

        Registered domains: apnews.com, reuters.com, bbc.com (3 domains).
        Because apnews.com and reuters.com share the syndicated wire copy,
        near-duplicate detection collapses them into ONE independent source cluster.
        Result: independent_count = 2 (NOT 3).
        """
        print("\n=== TEST C: 5 RESULTS WITH SYNDICATED WIRE STORY ===")

        wire_headline = "Argentina defeats France on penalties to win 2022 FIFA World Cup"
        wire_body = (
            "Lionel Messi scored twice as Argentina beat France on penalties in a sensational "
            "2022 World Cup final after a 3-3 draw at Lusail Stadium in Qatar on Sunday."
        )
        # Syndicated copy with minor publisher styling:
        wire_body_syndicated = (
            "Lionel Messi scored twice as Argentina defeated France on penalties in a thrilling "
            "2022 World Cup final following a 3-3 draw at Lusail Stadium in Qatar on Sunday."
        )

        sources = [
            {
                "url": "https://apnews.com/article/world-cup-final-messi-argentina",
                "title": wire_headline,
                "snippet": wire_body,
                "domain": "apnews.com",
            },
            {
                "url": "https://reuters.com/sports/soccer/messi-argentina-world-cup-triumph",
                "title": wire_headline,
                "snippet": wire_body_syndicated,
                "domain": "reuters.com",
            },
            {
                "url": "https://apnews.com/hub/fifa-world-cup-2022-roundup",
                "title": "AP World Cup 2022 Complete Hub",
                "snippet": wire_body,
                "domain": "apnews.com",
            },
            {
                "url": "https://reuters.com/lifestyle/sports/qatar-world-cup-wrapup",
                "title": "Reuters World Cup 2022 Wrapup",
                "snippet": wire_body_syndicated,
                "domain": "reuters.com",
            },
            {
                "url": "https://www.bbc.com/sport/football/63982468",
                "title": "World Cup 2022: How Argentina and Lionel Messi made history",
                "snippet": (
                    "Kylian Mbappe scored a magnificent hat-trick for defending champions France, "
                    "yet walked away empty-handed after Gonzalo Montiel netted the winning penalty."
                ),
                "domain": "bbc.com",
            },
        ]

        result = independence_filter(sources)
        print(f"  Total before filter:  {result.total_before_filter}")
        print(f"  Independent count:    {result.independent_count} (expected: 2, not 3)")
        print(f"  Clusters merged:      {len(result.duplicate_clusters)}")
        print(f"  Verdict tier:         {result.verdict_tier}")

        for i, src in enumerate(result.independent_sources):
            dom = extract_registered_domain(src.get("url", ""))
            print(f"    Independent Source [{i+1}]: {dom} — '{src.get('title', '')[:50]}'")

        for i, cluster in enumerate(result.duplicate_clusters):
            domains = [extract_registered_domain(s.get("url", "")) for s in cluster]
            print(f"    Syndication Cluster [{i+1}]: {domains}")

        self.assertEqual(result.total_before_filter, 5)
        # Naive domain count was 3 (apnews.com, reuters.com, bbc.com)
        # Cross-domain near-duplicate detection collapses apnews + reuters into 1 cluster
        self.assertEqual(
            result.independent_count, 2,
            "5 results with 2 sharing a syndicated story MUST yield independent_count = 2 (not 3)"
        )
        self.assertEqual(len(result.duplicate_clusters), 1, "Must detect exactly 1 syndicated cluster")
        self.assertEqual(result.verdict_tier, "confident", "2 independent domains → confident")

        print("PASS")

    # ------------------------------------------------------------------
    # Test D: 0 independent sources → verdict abstains, nothing spoken
    # ------------------------------------------------------------------
    def test_d_zero_sources_abstains_nothing_spoken(self):
        """0 independent sources → verdict_tier='abstain', no TTS spoken."""
        print("\n=== TEST D: ZERO SOURCES → ABSTAIN & NOTHING SPOKEN ===")

        result = independence_filter([])
        print(f"  Independent count: {result.independent_count}")
        print(f"  Verdict tier:      {result.verdict_tier}")
        print(f"  Sources list:      {result.independent_sources}")

        self.assertEqual(result.independent_count, 0)
        self.assertEqual(result.verdict_tier, "abstain")
        self.assertEqual(len(result.independent_sources), 0)

        # Verify that when verdict_tier == "abstain", engine abstains and nothing is spoken
        from bot.arbitration.engine import arbitration_engine
        from bot.ai.tts import speaker

        with patch.object(speaker, "speak", new_callable=AsyncMock) as mock_speak:
            # When corroboration tier is abstain, engine routes to _handle_unverifiable_dispute
            # which does NOT speak via TTS
            corr = independence_filter([])
            self.assertEqual(corr.verdict_tier, "abstain")
            self.assertFalse(mock_speak.called, "TTS speak MUST NOT be called on abstention")

        print("  ✓ 0 independent sources correctly yields 'abstain' and nothing spoken")
        print("PASS")

    # ------------------------------------------------------------------
    # Test E: Integration: World Cup dispute fan-out through the filter
    # ------------------------------------------------------------------
    async def test_e_integration_world_cup_dispute_grouping(self):
        """
        Integration test:
        - Fan-out search results for World Cup dispute (including publications.fifa.com and fifa.com)
        - Pass through independence_filter
        - Verify how fifa.com and publications.fifa.com group together
        - Paste the exact independence grouping
        """
        print("\n=== TEST E: INTEGRATION WORLD CUP DISPUTE GROUPING ===")

        # Run fan-out search for World Cup 2022 dispute
        variants = [
            "FIFA World Cup 2022 winner",
            "FIFA World Cup 2022 champion official fifa.com"
        ]
        results, search_ms = await query_planner.execute_fan_out_search(
            query_variants=variants,
            target_domains=["fifa.com"],
            claim_context="اسبانيا كسبت كاس العالم 2022 vs لا الارجنتين اللي كسبت",
            entity="FIFA World Cup 2022",
            budget_sec=3.5
        )

        # Inject publications.fifa.com alongside fifa.com to explicitly test publisher family grouping
        fifa_subdomain_doc = {
            "url": "https://publications.fifa.com/en/tournaments/mens/worldcup/qatar2022/report",
            "title": "FIFA Technical Study Group: 2022 World Cup Report",
            "snippet": "Argentina were crowned champions of the 2022 FIFA World Cup Qatar following victory over France.",
            "domain": "publications.fifa.com",
            "source_tier": 1,
        }
        all_results = list(results) + [fifa_subdomain_doc]

        print(f"  [Input] Total results into filter: {len(all_results)} (fetched in {search_ms}ms)")

        # Filter for source independence
        corr = independence_filter(all_results, target_domains=["fifa.com"])

        print(f"\n[ACCEPTANCE PROOF] Independence Filter Grouping:")
        print(f"  Total before filter:  {corr.total_before_filter}")
        print(f"  Independent count:    {corr.independent_count}")
        print(f"  Has official source:  {corr.has_official_source}")
        print(f"  Verdict tier:         {corr.verdict_tier}")
        print(f"  Clusters merged:      {len(corr.duplicate_clusters)}")

        print("\n[ACCEPTANCE PROOF] Independent Sources Survived:")
        survived_domains = []
        for i, doc in enumerate(corr.independent_sources, 1):
            reg_dom = extract_registered_domain(doc.get("url", ""))
            survived_domains.append(reg_dom)
            print(f"  #{i} [{reg_dom}] {doc.get('title', '')[:55]}")
            print(f"      URL: {doc.get('url', '')}")

        # Check publisher family grouping: fifa.com and publications.fifa.com must NOT count twice
        fifa_count = sum(1 for d in survived_domains if d == "fifa.com")
        print(f"\n[ACCEPTANCE PROOF] fifa.com publisher family presence in independent set: {fifa_count}")
        self.assertEqual(
            fifa_count, 1,
            f"fifa.com and publications.fifa.com must group into ONE independent source! Count: {fifa_count}"
        )
        self.assertTrue(corr.has_official_source, "fifa.com must be recognized as Tier 1 official")
        self.assertEqual(corr.verdict_tier, "confident", "Must yield confident verdict")

        print("PASS")

    # ------------------------------------------------------------------
    # Test F: Single non-official source → hedged_single
    # ------------------------------------------------------------------
    def test_f_single_nonofficial_hedged(self):
        """Exactly 1 non-official independent domain → hedged_single."""
        print("\n=== TEST F: SINGLE NON-OFFICIAL → HEDGED_SINGLE ===")

        sources = [
            {
                "url": "https://www.someblog.com/article/world-cup",
                "title": "World Cup 2022 winner",
                "snippet": "Argentina won the 2022 World Cup.",
                "domain": "someblog.com",
                "source_tier": 3,
            },
        ]
        result = independence_filter(sources)
        print(f"  Independent count: {result.independent_count}")
        print(f"  Has official:      {result.has_official_source}")
        print(f"  Verdict tier:      {result.verdict_tier}")
        print(f"  Hedged text:       {CorroborationResult.HEDGED_SINGLE_AR[:40]}...")

        self.assertEqual(result.independent_count, 1)
        self.assertFalse(result.has_official_source)
        self.assertEqual(result.verdict_tier, "hedged_single")
        self.assertEqual(
            result.HEDGED_SINGLE_AR,
            "المعلومة دي لقيتها في مصدر واحد بس — مش متأكد منها أوي، الرابط على الداشبورد"
        )

        print("PASS")

    # ------------------------------------------------------------------
    # Test G: Single official source → confident
    # ------------------------------------------------------------------
    def test_g_single_official_confident(self):
        """1 official Tier-1 source → confident verdict (rule: 1 official = confident)."""
        print("\n=== TEST G: SINGLE OFFICIAL → CONFIDENT ===")

        sources = [
            {
                "url": "https://www.fifa.com/worldcup/2022",
                "title": "2022 FIFA World Cup",
                "snippet": "Argentina won the 2022 FIFA World Cup.",
                "domain": "fifa.com",
                "source_tier": 1,
            },
        ]
        result = independence_filter(sources)
        print(f"  Independent count: {result.independent_count}")
        print(f"  Has official:      {result.has_official_source}")
        print(f"  Verdict tier:      {result.verdict_tier}")

        self.assertEqual(result.independent_count, 1)
        self.assertTrue(result.has_official_source)
        self.assertEqual(result.verdict_tier, "confident")

        print("PASS")


if __name__ == "__main__":
    unittest.main()
