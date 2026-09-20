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

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with httpx.Client(timeout=10.0) as client:
        resp = client.get("https://api.groq.com/openai/v1/models", headers=headers)
        if resp.status_code != 200:
            print(f"FAILED: HTTP {resp.status_code} - {resp.text}")
            return
        data = resp.json()
        models = data.get("data", [])
        model_ids = sorted([m["id"] for m in models])
        
        print(f"Total models returned: {len(model_ids)}")
        print("\nALL MODEL IDS:")
        for mid in model_ids:
            print(f"  - {mid}")
            
        llama_models = [m for m in model_ids if "llama-3" in m.lower() or "llama3" in m.lower()]
        qwen_models = [m for m in model_ids if "qwen" in m.lower()]
        gpt_oss_models = [m for m in model_ids if "gpt" in m.lower() or "oss" in m.lower()]
        whisper_models = [m for m in model_ids if "whisper" in m.lower()]
        
        print("\n(a) LLAMA-3.X CHAT MODELS:")
        for m in llama_models:
            print(f"  - {m}")
        if not llama_models:
            print("  NONE")

        print("\n(b) QWEN MODELS:")
        for m in qwen_models:
            print(f"  - {m}")
        if not qwen_models:
            print("  NONE")

        print("\n(c) GPT-OSS MODELS:")
        for m in gpt_oss_models:
            print(f"  - {m}")
        if not gpt_oss_models:
            print("  NONE")

        print("\n(d) WHISPER / STT MODELS:")
        for m in whisper_models:
            print(f"  - {m}")
        if not whisper_models:
            print("  NONE")

if __name__ == "__main__":
    main()
