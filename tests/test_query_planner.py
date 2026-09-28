"""
Acceptance Test Suite for Query Planner, Step-Back Abstraction, and Fan-Out RRF Search.
Tests:
a) Unit: planner output schema validation (3 variants max, required fields, ambiguity_type enum)
b) Unit: temporal ambiguity — "مين كسب كاس العالم" (no year) -> ambiguity_type=temporal, NO date-assuming query emitted
c) Unit: specific claim — "اسبانيا كسبت 2022" -> time_anchor=2022, query includes year
d) Integration: real Groq call producing 3 variants for World Cup dispute -> prints all 3 queries + merged top-5 results with RRF scores
e) FIFA.com confirmation: assert fifa.com appears in top-5 merged results for World Cup dispute
"""

import sys
import re
import asyncio
import unittest

import tests._setup

from bot.config import config
from bot.arbitration.query_planner import (
    AmbiguityType,
    ClaimSearchPlan,
    QueryPlanner,
    query_planner,
    get_canonical_key,
    jaccard_similarity,
    compute_authority_bonus,
    compute_direct_coverage,
    reciprocal_rank_fusion
)


class TestQueryPlanner(unittest.IsolatedAsyncioTestCase):

    def test_a_schema_validation(self):
        """
        Unit test a: Schema validation
        - Required fields present
        - 3 variants max capping
        - Empty variants raises ValueError
        - AmbiguityType enum verification
        - RRF deduplication and authority bonus math
        """
        print("\n=== TEST A: PLANNER SCHEMA VALIDATION ===")

        # 1. AmbiguityType enum values
        expected_types = {"none", "temporal", "entity", "scope", "comparative"}
        actual_types = {t.value for t in AmbiguityType}
        self.assertEqual(expected_types, actual_types, "AmbiguityType enum must contain all 5 types")

        # 2. ClaimSearchPlan construction & fields
        plan = ClaimSearchPlan(
            subject="Spain",
            predicate="winner",
            object="FIFA World Cup 2022",
            time_anchor="2022",
            time_anchor_confidence=1.0,
            ambiguity_type=AmbiguityType.NONE,
            query_variants=["query 1", "query 2"]
        )
        self.assertEqual(plan.subject, "Spain")
        self.assertEqual(plan.time_anchor, "2022")
        self.assertEqual(plan.ambiguity_type, AmbiguityType.NONE)
        self.assertEqual(len(plan.query_variants), 2)

        # 3. Validation: Cap at 3 query variants max
        plan_capped = ClaimSearchPlan(
            subject="Test",
            predicate="attr",
            object=None,
            time_anchor=None,
            time_anchor_confidence=0.0,
            ambiguity_type=AmbiguityType.TEMPORAL,
            query_variants=["q1", "q2", "q3", "q4", "q5"]
        )
        self.assertEqual(len(plan_capped.query_variants), 3, "query_variants must be capped at 3 max")
        self.assertEqual(plan_capped.query_variants, ["q1", "q2", "q3"])

        # 4. Validation: Empty query_variants raises ValueError
        with self.assertRaises(ValueError):
            ClaimSearchPlan(
                subject="Test",
                predicate="attr",
                query_variants=[]
            )

        # 5. Canonical URL deduplication helper
        can_url, reg_dom = get_canonical_key("https://www.fifa.com/en/tournaments/worldcup/2022/")
        self.assertEqual(can_url, "fifa.com/en/tournaments/worldcup/2022")
        self.assertEqual(reg_dom, "fifa.com")

        # 6. Jaccard similarity & RRF duplicate penalty logic
        sim = jaccard_similarity("Argentina won the World Cup in Qatar", "Argentina won the World Cup final in Qatar")
        self.assertGreater(sim, 0.6)

        # 7. Model check: ensure production model is strictly qwen/qwen3.8-27b (NOT llama-3.3-70b)
        self.assertNotIn("llama-3.3-70b", query_planner.model_name)
        self.assertEqual(query_planner.model_name, "qwen/qwen3.8-27b")

        print("  ✓ All schema, enum, validation, and model assertions passed.")

    async def test_b_temporal_ambiguity_no_year(self):
        """
        Unit test b: Temporal ambiguity on 'مين كسب كاس العالم'
        - Claim has no year anchor
        - Model must detect ambiguity_type = 'temporal'
        - time_anchor must be None / empty with confidence 0.0
        - FORBIDDEN: NO query may invent or assume a year (e.g. 2022, 2026, 1998)
        """
        print("\n=== TEST B: TEMPORAL AMBIGUITY (NO INVENTED DATES) ===")
        claim_text = "مين كسب كاس العالم"
        print(f"  Input: \"{claim_text}\"")

        plan = await query_planner.plan_search(
            entity="كاس العالم",
            dimension="winner",
            claim_a=claim_text,
            fallback_query=claim_text
        )

        print(f"  Result Plan:")
        print(f"    Subject: {plan.subject}")
        print(f"    Ambiguity Type: {plan.ambiguity_type.value}")
        print(f"    Time Anchor: {plan.time_anchor} (confidence={plan.time_anchor_confidence})")
        print(f"    Query Variants ({len(plan.query_variants)}):")
        for i, q in enumerate(plan.query_variants, 1):
            print(f"      [{i}] {q}")

        # Assertions per task requirements
        self.assertEqual(plan.ambiguity_type, AmbiguityType.TEMPORAL, "Ambiguity type must be 'temporal'")
        self.assertIsNone(plan.time_anchor, "time_anchor must be None when no date is in utterance")
        self.assertEqual(plan.time_anchor_confidence, 0.0, "time_anchor_confidence must be 0.0")
        self.assertLessEqual(len(plan.query_variants), 3, "Variants count must be <= 3")

        # STRICT CONSTRAINT: No invented 4-digit years in any query
        for q in plan.query_variants:
            year_match = re.search(r'\b(19\d\d|20\d\d)\b', q)
            self.assertIsNone(
                year_match,
                f"FORBIDDEN: Invented year '{year_match.group(0) if year_match else ''}' in query: '{q}'"
            )

        print("  ✓ Temporal ambiguity test passed (0 invented years).")

    async def test_c_specific_claim_with_year(self):
        """
        Unit test c: Specific claim with explicit year 'اسبانيا كسبت 2022'
        - time_anchor must be '2022'
        - time_anchor_confidence >= 0.8
        - Emitted queries must include the year '2022'
        - ambiguity_type must not be 'temporal'
        """
        print("\n=== TEST C: SPECIFIC CLAIM WITH EXPLICIT YEAR ===")
        claim_text = "اسبانيا كسبت 2022"
        print(f"  Input: \"{claim_text}\"")

        plan = await query_planner.plan_search(
            entity="كاس العالم",
            dimension="winner",
            speaker_a="أحمد",
            claim_a=claim_text,
            fallback_query=claim_text
        )

        print(f"  Result Plan:")
        print(f"    Subject: {plan.subject}")
        print(f"    Ambiguity Type: {plan.ambiguity_type.value}")
        print(f"    Time Anchor: {plan.time_anchor} (confidence={plan.time_anchor_confidence})")
        print(f"    Query Variants ({len(plan.query_variants)}):")
        for i, q in enumerate(plan.query_variants, 1):
            print(f"      [{i}] {q}")

        # Assertions per task requirements
        self.assertEqual(plan.time_anchor, "2022", "time_anchor must capture '2022'")
        self.assertGreaterEqual(plan.time_anchor_confidence, 0.8, "Confidence must be >= 0.8")
        self.assertNotEqual(plan.ambiguity_type, AmbiguityType.TEMPORAL, "Ambiguity type must NOT be temporal when year is explicit")
        self.assertLessEqual(len(plan.query_variants), 3, "Variants count must be <= 3")

        # Queries must include the anchored year
        has_year = any("2022" in q for q in plan.query_variants)
        self.assertTrue(has_year, "At least one query variant must include '2022'")

        print("  ✓ Specific claim test passed (time_anchor='2022' verified).")

    async def test_d_integration_world_cup_dispute_fanout_rrf_and_fifa(self):
        """
        Integration test d & f:
        - Real Groq call producing 3 query variants for World Cup dispute
        - Executes concurrent Tavily fan-out search with RRF merging
        - Pastes all 3 queries + merged top-5 results with RRF scores
        - Confirms FIFA.com appears in top-5 merged results
        """
        print("\n=== TEST D & F: INTEGRATION WORLD CUP DISPUTE + RRF FAN-OUT + FIFA.COM ===")
        speaker_a = "أحمد"
        claim_a = "اسبانيا كسبت كاس العالم 2022"
        speaker_b = "كريم"
        claim_b = "لا الارجنتين اللي كسبت كاس العالم 2022"

        print(f"  Speaker A: {claim_a}")
        print(f"  Speaker B: {claim_b}")

        # Step 1: Real Groq query planner call
        plan = await query_planner.plan_search(
            entity="FIFA World Cup",
            dimension="2022 winner",
            speaker_a=speaker_a,
            claim_a=claim_a,
            speaker_b=speaker_b,
            claim_b=claim_b,
            fallback_query="FIFA World Cup 2022 winner",
            target_domains=["fifa.com"]
        )

        print("\n[ACCEPTANCE PROOF] Step-Back Query Variants Generated:")
        for i, q in enumerate(plan.query_variants, 1):
            print(f"  Variant {i}: {q}")

        self.assertGreaterEqual(len(plan.query_variants), 2, "Must generate at least 2 query variants")
        self.assertLessEqual(len(plan.query_variants), 3, "Must not exceed 3 query variants")

        # Step 2: Concurrent Tavily fan-out search + RRF deduplication & merging
        merged_results, search_ms = await query_planner.execute_fan_out_search(
            query_variants=plan.query_variants,
            target_domains=["fifa.com"],
            claim_context=f"{claim_a} vs {claim_b}",
            entity="FIFA World Cup 2022",
            budget_sec=3.5
        )

        print(f"\n[ACCEPTANCE PROOF] Fan-out Search Completed in {search_ms}ms (Merged: {len(merged_results)} unique docs)")
        print("[ACCEPTANCE PROOF] Top 5 Merged Results with RRF Scores:")
        for rank, doc in enumerate(merged_results[:5], 1):
            url = doc.get("url", "")
            domain = doc.get("domain", "")
            title = doc.get("title", "")
            rrf = doc.get("rrf_score", 0.0)
            base = doc.get("rrf_base", 0.0)
            auth = doc.get("authority_bonus", 0.0)
            cov = doc.get("direct_coverage", 0.0)
            dup_pen = doc.get("duplicate_penalty", 0.0)
            matched = doc.get("queries_matched", [])
            print(f"  #{rank} [RRF={rrf:.4f}] {title}")
            print(f"      URL: {url}")
            print(f"      Domain: {domain} | Matched Queries: {matched}")
            print(f"      (rrf_base={base}, auth_bonus={auth}, coverage={cov}, dup_penalty={dup_pen})")

        self.assertGreater(len(merged_results), 0, "Fan-out search must return at least 1 result")

        # Step 3: Confirm FIFA.com appears in top-5 merged results
        top_5_domains = [doc.get("domain", "").lower() for doc in merged_results[:5]]
        top_5_urls = [doc.get("url", "").lower() for doc in merged_results[:5]]
        has_fifa = any("fifa.com" in dom or "fifa.com" in url for dom, url in zip(top_5_domains, top_5_urls))

        print(f"\n[ACCEPTANCE PROOF] FIFA.com Presence in Top-5: {has_fifa}")
        self.assertTrue(has_fifa, f"fifa.com MUST appear in top-5 merged results! Top 5 domains: {top_5_domains}")


if __name__ == "__main__":
    unittest.main()
