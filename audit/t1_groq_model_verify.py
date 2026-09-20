"""T1: Verify Groq model ID and measure LLM latency (claim detection prompt)."""
import sys, io, os, time, json, asyncio, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

CLAIM_PROMPT = """You are a fast, lightweight conversational gatekeeper.
Given a single transcript utterance from a casual voice call:
Determine if the sentence contains an OBJECTIVELY VERIFIABLE REAL-WORLD FACTUAL CLAIM.
Respond STRICTLY in JSON:
{"is_factual_claim": true, "claim": "...", "topic": "...", "entity": "...", "metric": "..."}"""

TEST_UTTERANCE = 'Utterance: "Bro, RTX 5070 has 16GB VRAM"'

async def run_test():
    if not GROQ_API_KEY:
        print("BLOCKED: GROQ_API_KEY not set")
        return

    print(f"Model configured: {GROQ_MODEL}")
    print(f"API Key (last 4): ...{GROQ_API_KEY[-4:]}")
    print(f"Endpoint: https://api.groq.com/openai/v1/chat/completions")
    print(f"Test utterance: {TEST_UTTERANCE}")
    print("=" * 60)

    # First list available models
    print("\n--- Listing available Groq models ---")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}
            )
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                model_ids = sorted([m["id"] for m in models])
                print(f"Total models available: {len(model_ids)}")
                # Check if configured model exists
                if GROQ_MODEL in model_ids:
                    print(f"PASS: Model '{GROQ_MODEL}' EXISTS in Groq model list")
                else:
                    print(f"FAIL: Model '{GROQ_MODEL}' NOT FOUND in Groq model list")
                    # Show partial matches
                    partial = [m for m in model_ids if "qwen" in m.lower()]
                    if partial:
                        print(f"  Partial matches for 'qwen': {partial}")
                    partial2 = [m for m in model_ids if "llama" in m.lower()]
                    if partial2:
                        print(f"  Available Llama models: {partial2[:5]}")
            else:
                print(f"Model list request failed: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Model list request error: {e}")

    # Now run latency tests
    print("\n--- Latency Tests (n=6, run #1 = cold) ---")
    latencies = []
    results = []

    for i in range(6):
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": GROQ_MODEL,
                        "messages": [
                            {"role": "system", "content": CLAIM_PROMPT},
                            {"role": "user", "content": TEST_UTTERANCE}
                        ],
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"}
                    }
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    latencies.append(latency_ms)
                    result_str = f"  Run #{i+1}: {latency_ms}ms | is_claim={parsed.get('is_factual_claim')} | entity={parsed.get('entity')}"
                    results.append(result_str)
                    print(result_str)
                    if i == 0:
                        print(f"    [COLD RUN] Raw response: {content[:300]}")
                else:
                    print(f"  Run #{i+1}: HTTP {resp.status_code} - {resp.text[:200]}")
                    latencies.append(latency_ms)
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            print(f"  Run #{i+1}: ERROR after {latency_ms}ms - {e}")

    if len(latencies) >= 2:
        cold = latencies[0]
        warm = latencies[1:]
        warm_sorted = sorted(warm)
        p50_idx = len(warm_sorted) // 2
        p95_idx = min(int(len(warm_sorted) * 0.95), len(warm_sorted) - 1)
        print(f"\n--- Summary ---")
        print(f"n = {len(latencies)} (1 cold + {len(warm)} warm)")
        print(f"Cold run: {cold}ms")
        print(f"Warm p50: {warm_sorted[p50_idx]}ms")
        print(f"Warm p95: {warm_sorted[p95_idx]}ms")
        print(f"Warm mean: {statistics.mean(warm):.0f}ms")

asyncio.run(run_test())
