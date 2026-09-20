import os, sys, io, json, time, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import httpx
from bot.arbitration.claim_detector import CLAIM_DETECTOR_PROMPT

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = "openai/gpt-oss-20b"

def main():
    if not GROQ_API_KEY:
        print("BLOCKED: GROQ_API_KEY not set")
        return

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    user_prompt = 'Utterance: "Bro, RTX 5070 has 16GB VRAM"'

    print("=== T4: Reasoning Effort Probe on openai/gpt-oss-20b ===")
    
    with httpx.Client(timeout=20.0) as client:
        for effort in ["low", "medium", "high", "minimal"]:
            payload = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": CLAIM_DETECTOR_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "reasoning_effort": effort
            }
            resp = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            print(f"\nReasoning effort = '{effort}':")
            print(f"  HTTP Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"  Response: {resp.json()['choices'][0]['message']['content'][:200]}")
                details = resp.json().get("usage", {}).get("completion_tokens_details", {})
                print(f"  Reasoning tokens: {details.get('reasoning_tokens')}")
            else:
                print(f"  Error body: {resp.text}")

        # Latency benchmark: n=5 for low vs medium
        print("\n--- Latency Benchmark: low vs medium (n=5 each) ---")
        for effort in ["low", "medium"]:
            print(f"\nTesting reasoning_effort = '{effort}' (5 runs):")
            latencies = []
            outputs = []
            for i in range(5):
                payload = {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": CLAIM_DETECTOR_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "reasoning_effort": effort
                }
                t0 = time.perf_counter()
                resp = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                dt_ms = int((time.perf_counter() - t0) * 1000)
                latencies.append(dt_ms)
                if resp.status_code == 200:
                    data = resp.json()
                    c = data['choices'][0]['message']['content']
                    rt = data.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                    outputs.append(c)
                    print(f"  Run #{i+1}: {dt_ms}ms (reasoning_tokens={rt}) | {c.strip()[:120]}")
                else:
                    print(f"  Run #{i+1}: HTTP {resp.status_code} - {resp.text[:100]}")
            
            cold = latencies[0]
            warm = latencies[1:]
            warm_sorted = sorted(warm)
            p50 = warm_sorted[len(warm_sorted) // 2]
            p95 = warm_sorted[min(int(len(warm_sorted) * 0.95), len(warm_sorted) - 1)]
            print(f"  Summary for '{effort}': Cold={cold}ms, Warm p50={p50}ms, Warm p95={p95}ms, Mean={statistics.mean(warm):.0f}ms")

if __name__ == "__main__":
    main()
