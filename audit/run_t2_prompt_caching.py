import os, sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import httpx
from bot.arbitration.claim_detector import CLAIM_DETECTOR_PROMPT

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = "openai/gpt-oss-20b"

def send_req(client, system_prompt, user_prompt):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    t0 = time.perf_counter()
    resp = client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=payload
    )
    dt_ms = int((time.perf_counter() - t0) * 1000)
    return resp, dt_ms

def main():
    if not GROQ_API_KEY:
        print("BLOCKED: GROQ_API_KEY not set")
        return

    user_prompt = 'Utterance: "Bro, RTX 5070 has 16GB VRAM"'
    
    with httpx.Client(timeout=15.0) as client:
        # Request 1 (identical)
        print("--- Request 1: Identical prompt (Cold) ---")
        r1, t1 = send_req(client, CLAIM_DETECTOR_PROMPT, user_prompt)
        print(f"Status: {r1.status_code}, Time: {t1}ms")
        if r1.status_code == 200:
            u1 = r1.json().get("usage", {})
            print("Usage 1:", json.dumps(u1, indent=2))
        else:
            print(r1.text)
            return

        time.sleep(1)

        # Request 2 (identical)
        print("\n--- Request 2: Identical prompt (Warm) ---")
        r2, t2 = send_req(client, CLAIM_DETECTOR_PROMPT, user_prompt)
        print(f"Status: {r2.status_code}, Time: {t2}ms")
        if r2.status_code == 200:
            u2 = r2.json().get("usage", {})
            print("Usage 2:", json.dumps(u2, indent=2))
        else:
            print(r2.text)

        time.sleep(1)

        # Request 3 (1 char changed at start of prompt: 'Y' -> 'X')
        mod_prompt = "X" + CLAIM_DETECTOR_PROMPT[1:]
        print("\n--- Request 3: One character changed at start of system prompt ---")
        r3, t3 = send_req(client, mod_prompt, user_prompt)
        print(f"Status: {r3.status_code}, Time: {t3}ms")
        if r3.status_code == 200:
            u3 = r3.json().get("usage", {})
            print("Usage 3:", json.dumps(u3, indent=2))
        else:
            print(r3.text)

if __name__ == "__main__":
    main()
