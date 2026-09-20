"""T5: End-to-end pipeline simulation (Groq claim detect -> conflict detect -> Tavily search -> Groq verify)."""
import sys, io, os, time, json, asyncio, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Reproduce the exact prompts from the codebase
CLAIM_DETECTOR_PROMPT = """You are a fast, lightweight conversational gatekeeper.
Given a single transcript utterance from a casual voice call (bilingual Egyptian Arabic + English):
Determine if the sentence contains an OBJECTIVELY VERIFIABLE REAL-WORLD FACTUAL CLAIM.
Respond STRICTLY in JSON:
{"is_factual_claim": true, "claim": "concise extracted claim statement", "topic": "hardware", "entity": "concise subject entity name", "metric": "property being asserted"}"""

CONFLICT_PROMPT = """You are a precision conversational intelligence arbitrator analyzing two opposing statements in a live voice call.
Your job is to determine if the two statements present an OBJECTIVE, MUTUALLY EXCLUSIVE FACTUAL CONTRADICTION.
Respond STRICTLY in JSON:
{"has_conflict": true, "conflict_type": "numeric_spec", "disputed_aspect": "...", "search_query": "...", "target_domains": ["domain1.com"]}"""

VERIFICATION_PROMPT = """You are an objective evidence-based fact-checking engine.
Evaluate two conversational statements against the retrieved ground-truth web search snippets.
Respond STRICTLY in JSON:
{"speaker_a_status": "CONTRADICTED", "speaker_b_status": "SUPPORTED", "evidence_strength": "HIGH", "confidence": 95, "correct_fact": "...", "selected_source_url": "...", "selected_source_title": "..."}"""

CLAIM_A = "RTX 5070 has 16GB VRAM"
CLAIM_B = "RTX 5070 has 12GB GDDR7, not 16GB"

async def groq_call(system_prompt, user_prompt):
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content), latency_ms
        else:
            return None, latency_ms

async def tavily_search(query, target_domains=None):
    t0 = time.perf_counter()
    body = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "max_results": 5, "include_answer": True}
    if target_domains:
        body["include_domains"] = target_domains
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=body)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return resp.json().get("results", []), latency_ms
        return [], latency_ms

async def run_pipeline():
    if not GROQ_API_KEY or not TAVILY_API_KEY:
        print(f"BLOCKED: GROQ_API_KEY={'set' if GROQ_API_KEY else 'MISSING'}, TAVILY_API_KEY={'set' if TAVILY_API_KEY else 'MISSING'}")
        return

    print("=== Full Pipeline Simulation ===")
    print(f"Claim A (Ahmed): {CLAIM_A}")
    print(f"Claim B (Omar): {CLAIM_B}")
    print("=" * 60)

    pipeline_latencies = []

    for i in range(6):
        t_total_start = time.perf_counter()

        # Step 1: Claim Detection on Claim B
        claim_data, claim_ms = await groq_call(CLAIM_DETECTOR_PROMPT, f'Utterance: "{CLAIM_B}"')

        # Step 2: Conflict Detection
        conflict_data, conflict_ms = await groq_call(
            CONFLICT_PROMPT,
            f'Speaker A (Ahmed): "{CLAIM_A}"\nSpeaker B (Omar): "{CLAIM_B}"'
        )

        # Step 3: Tavily Search
        search_query = conflict_data.get("search_query", "RTX 5070 VRAM specs") if conflict_data else "RTX 5070 VRAM specs"
        target_domains = conflict_data.get("target_domains", []) if conflict_data else []
        sources, search_ms = await tavily_search(search_query, target_domains)

        # Step 4: Verification synthesis
        evidence_snippets = "\n".join([
            f"[Source {j+1}] {s.get('title', '')} ({s.get('url', '')}):\n{s.get('content', s.get('snippet', ''))[:200]}"
            for j, s in enumerate(sources[:4])
        ])
        verify_prompt = (
            f"Conversation Context:\n- Ahmed claimed: \"{CLAIM_A}\"\n- Omar claimed: \"{CLAIM_B}\"\n\n"
            f"Authoritative Web Evidence:\n{evidence_snippets}"
        )
        verdict, verify_ms = await groq_call(VERIFICATION_PROMPT, verify_prompt)

        total_ms = int((time.perf_counter() - t_total_start) * 1000)
        pipeline_latencies.append(total_ms)

        print(f"\n  Run #{i+1}: Total={total_ms}ms")
        print(f"    Claim detect:  {claim_ms}ms | is_claim={claim_data.get('is_factual_claim') if claim_data else 'N/A'}")
        print(f"    Conflict:      {conflict_ms}ms | has_conflict={conflict_data.get('has_conflict') if conflict_data else 'N/A'}")
        print(f"    Tavily search: {search_ms}ms | {len(sources)} sources")
        print(f"    Verification:  {verify_ms}ms | verdict={verdict.get('speaker_b_status') if verdict else 'N/A'}")
        if i == 0 and verdict:
            print(f"    [COLD RUN] Correct fact: {verdict.get('correct_fact', 'N/A')}")
            print(f"    [COLD RUN] Confidence: {verdict.get('confidence', 'N/A')}%")

    if len(pipeline_latencies) >= 2:
        cold = pipeline_latencies[0]
        warm = pipeline_latencies[1:]
        warm_sorted = sorted(warm)
        p50_idx = len(warm_sorted) // 2
        p95_idx = min(int(len(warm_sorted) * 0.95), len(warm_sorted) - 1)
        print(f"\n--- Full Pipeline Summary ---")
        print(f"n = {len(pipeline_latencies)} (1 cold + {len(warm)} warm)")
        print(f"Cold run: {cold}ms")
        print(f"Warm p50: {warm_sorted[p50_idx]}ms")
        print(f"Warm p95: {warm_sorted[p95_idx]}ms")
        print(f"Warm mean: {statistics.mean(warm):.0f}ms")

asyncio.run(run_pipeline())
