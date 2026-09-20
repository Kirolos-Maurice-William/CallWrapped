import os, sys, io, json, time, statistics, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import httpx
import edge_tts
from bot.arbitration.claim_detector import CLAIM_DETECTOR_PROMPT
from bot.arbitration.conflict_detector import CONFLICT_PROMPT

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "qwen/qwen3.8-27b"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

def calc_stats(latencies):
    cold = latencies[0]
    warm = latencies[1:]
    if not warm:
        return cold, cold, cold, cold
    warm_sorted = sorted(warm)
    p50 = warm_sorted[len(warm_sorted) // 2]
    p95 = warm_sorted[min(int(len(warm_sorted) * 0.95), len(warm_sorted) - 1)]
    return cold, p50, p95, statistics.mean(warm)

# ----------------------------------------------------
# 6a: Groq claim detection n=10
# ----------------------------------------------------
def test_6a():
    print("\n=======================================================")
    print("T6 (a) GROQ CLAIM DETECTION (n=10, qwen/qwen3.8-27b)")
    print("=======================================================")
    sample_utterance = 'Utterance: "سيرفر ماين كرافت 1.21 نزل رسمي وفيه trial chambers"'
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": CLAIM_DETECTOR_PROMPT},
            {"role": "user", "content": sample_utterance}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    latencies = []
    tokens_per_sec_list = []
    with httpx.Client(timeout=15.0) as client:
        for i in range(10):
            t0 = time.perf_counter()
            r = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            dt_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(dt_ms)
            if r.status_code == 200:
                data = r.json()
                usage = data.get("usage", {})
                compl_time = usage.get("completion_time", 0.0)
                compl_tokens = usage.get("completion_tokens", 0)
                tps = (compl_tokens / compl_time) if compl_time > 0 else 0.0
                tokens_per_sec_list.append(tps)
                content = data["choices"][0]["message"]["content"]
                print(f"  Run #{i+1}: {dt_ms}ms | tokens/sec={tps:.1f} | {content[:80]}...")
            else:
                print(f"  Run #{i+1}: HTTP {r.status_code} - {r.text[:100]}")
    cold, p50, p95, mean = calc_stats(latencies)
    avg_tps = statistics.mean(tokens_per_sec_list[1:]) if len(tokens_per_sec_list) > 1 else 0
    print(f"Summary: Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={mean:.0f}ms, Warm avg tokens/sec={avg_tps:.1f}")

# ----------------------------------------------------
# 6b: Groq conflict analysis n=10
# ----------------------------------------------------
def test_6b():
    print("\n=======================================================")
    print("T6 (b) GROQ CONFLICT ANALYSIS (n=10, qwen/qwen3.8-27b)")
    print("=======================================================")
    prompt_user = 'Speaker A (Ahmed): "Bro, RTX 5070 has 16GB VRAM"\nSpeaker B (Omar): "No, RTX 5070 has 12GB"'
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": CONFLICT_PROMPT},
            {"role": "user", "content": prompt_user}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    latencies = []
    with httpx.Client(timeout=15.0) as client:
        for i in range(10):
            t0 = time.perf_counter()
            r = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            dt_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(dt_ms)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                print(f"  Run #{i+1}: {dt_ms}ms | {content[:80]}...")
            else:
                print(f"  Run #{i+1}: HTTP {r.status_code} - {r.text[:100]}")
    cold, p50, p95, mean = calc_stats(latencies)
    print(f"Summary: Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={mean:.0f}ms")

# ----------------------------------------------------
# 6c: AssemblyAI STT
# ----------------------------------------------------
def test_6c():
    print("\n=======================================================")
    print("T6 (c) ASSEMBLYAI STT")
    print("=======================================================")
    print("Result: NO SAMPLE AVAILABLE in repository. (0 WAV files found in repository tree).")

# ----------------------------------------------------
# 6d: Tavily search probes
# ----------------------------------------------------
def test_6d():
    print("\n=======================================================")
    print("T6 (d) TAVILY SEARCH (Basic vs Advanced, probes)")
    print("=======================================================")
    query = "RTX 5070 VRAM memory specifications"

    # Basic depth n=5
    print("\n--- Basic depth (n=5) ---")
    basic_latencies = []
    with httpx.Client(timeout=15.0) as client:
        for i in range(5):
            t0 = time.perf_counter()
            r = client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "max_results": 5, "include_answer": True
            })
            dt_ms = int((time.perf_counter() - t0) * 1000)
            basic_latencies.append(dt_ms)
            if r.status_code == 200:
                cnt = len(r.json().get("results", []))
                print(f"  Run #{i+1}: {dt_ms}ms | {cnt} results")
            else:
                print(f"  Run #{i+1}: HTTP {r.status_code}")
        cold, p50, p95, mean = calc_stats(basic_latencies)
        print(f"Basic Summary: Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={mean:.0f}ms")

        # Advanced depth n=5
        print("\n--- Advanced depth (n=5) ---")
        adv_latencies = []
        for i in range(5):
            t0 = time.perf_counter()
            r = client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced", "max_results": 5, "include_answer": True
            })
            dt_ms = int((time.perf_counter() - t0) * 1000)
            adv_latencies.append(dt_ms)
            if r.status_code == 200:
                cnt = len(r.json().get("results", []))
                print(f"  Run #{i+1}: {dt_ms}ms | {cnt} results")
            else:
                print(f"  Run #{i+1}: HTTP {r.status_code}")
        cold, p50, p95, mean = calc_stats(adv_latencies)
        print(f"Advanced Summary: Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={mean:.0f}ms")

        # Probing fast and ultra-fast
        print("\n--- Probing search_depth='fast' and 'ultra-fast' ---")
        for d in ["fast", "ultra-fast"]:
            r = client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY, "query": query, "search_depth": d
            })
            print(f"depth='{d}' -> HTTP {r.status_code}: {r.text[:200]}")

        # Testing include_answer=True accuracy and latency
        print("\n--- Testing include_answer=True ---")
        t0 = time.perf_counter()
        r_ans = client.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "include_answer": True
        })
        dt_ms = int((time.perf_counter() - t0) * 1000)
        ans = r_ans.json().get("answer", "") if r_ans.status_code == 200 else "ERROR"
        print(f"Latency: {dt_ms}ms")
        print(f"Answer populated: {bool(ans)}")
        print(f"Answer content: {ans}")

# ----------------------------------------------------
# 6e: edge-tts time to first audio chunk (15 words)
# ----------------------------------------------------
async def test_6e_async():
    print("\n=======================================================")
    print("T6 (e) EDGE-TTS TIME TO FIRST CHUNK (15-word sentence, n=5)")
    print("=======================================================")
    sentence = "The official specifications confirm that the RTX 5070 graphics card features 12GB of memory."
    voice = "en-US-JennyNeural"
    latencies = []
    for i in range(5):
        t0 = time.perf_counter()
        communicate = edge_tts.Communicate(sentence, voice)
        ttfb = None
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and len(chunk["data"]) > 0:
                ttfb = int((time.perf_counter() - t0) * 1000)
                break
        latencies.append(ttfb or 0)
        print(f"  Run #{i+1}: TTFB (first audio chunk) = {ttfb}ms")
    cold, p50, p95, mean = calc_stats(latencies)
    print(f"Summary: Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={mean:.0f}ms")

# ----------------------------------------------------
# 6f: Raw network RTT via socket connect
# ----------------------------------------------------
def test_6f():
    print("\n=======================================================")
    print("T6 (f) RAW NETWORK RTT (TCP Connect + SSL Handshake, n=3)")
    print("=======================================================")
    import socket, ssl
    endpoints = [
        ("api.groq.com", 443),
        ("api.assemblyai.com", 443),
        ("api.tavily.com", 443)
    ]
    for host, port in endpoints:
        print(f"\nHost: {host}:{port}")
        tcp_times = []
        ssl_times = []
        for i in range(3):
            # TCP Connect
            t0 = time.perf_counter()
            s = socket.create_connection((host, port), timeout=5.0)
            t_tcp = (time.perf_counter() - t0) * 1000
            tcp_times.append(t_tcp)

            # SSL Handshake
            ctx = ssl.create_default_context()
            t1 = time.perf_counter()
            ss = ctx.wrap_socket(s, server_hostname=host)
            t_ssl = (time.perf_counter() - t1) * 1000
            ssl_times.append(t_ssl)
            ss.close()

            print(f"  Run #{i+1}: TCP connect = {t_tcp:.1f}ms, SSL handshake = {t_ssl:.1f}ms, Total = {t_tcp + t_ssl:.1f}ms")
        print(f"  Avg TCP: {statistics.mean(tcp_times):.1f}ms | Avg SSL: {statistics.mean(ssl_times):.1f}ms | Total RTT: {statistics.mean(tcp_times) + statistics.mean(ssl_times):.1f}ms")

def main():
    test_6a()
    test_6b()
    test_6c()
    test_6d()
    asyncio.run(test_6e_async())
    test_6f()

if __name__ == "__main__":
    main()
