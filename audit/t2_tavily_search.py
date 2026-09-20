"""T2: Tavily search latency and source tier classification."""
import sys, io, os, time, json, asyncio, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

TEST_QUERY = "NVIDIA RTX 5070 VRAM specifications official"

async def run_test():
    if not TAVILY_API_KEY:
        print("BLOCKED: TAVILY_API_KEY not set")
        return

    print(f"API Key (last 4): ...{TAVILY_API_KEY[-4:]}")
    print(f"Test query: {TEST_QUERY}")
    print("=" * 60)

    latencies = []

    for i in range(6):
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": TAVILY_API_KEY,
                        "query": TEST_QUERY,
                        "search_depth": "basic",
                        "max_results": 5,
                        "include_answer": True
                    }
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                latencies.append(latency_ms)

                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    answer = data.get("answer", "")
                    print(f"  Run #{i+1}: {latency_ms}ms | {len(results)} results")
                    if i == 0:
                        print(f"    [COLD RUN] Answer snippet: {answer[:200]}")
                        for j, r in enumerate(results[:3]):
                            from urllib.parse import urlparse
                            domain = urlparse(r.get("url", "")).netloc
                            print(f"    Result {j+1}: [{domain}] {r.get('title', '')[:80]}")
                else:
                    print(f"  Run #{i+1}: HTTP {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            print(f"  Run #{i+1}: ERROR after {latency_ms}ms - {e}")
            latencies.append(latency_ms)

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
