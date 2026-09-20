import os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

def main():
    if not GROQ_API_KEY:
        print("BLOCKED: GROQ_API_KEY not set")
        return

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }

    with httpx.Client(timeout=10.0) as client:
        resp = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        print(f"HTTP Status: {resp.status_code}")
        print("\nALL HEADERS:")
        for k, v in sorted(resp.headers.items()):
            print(f"{k}: {v}")

        print("\nALL x-ratelimit-* HEADERS VERBATIM:")
        for k, v in sorted(resp.headers.items()):
            if k.lower().startswith("x-ratelimit-"):
                print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
