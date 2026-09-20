import os, sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import httpx
from bot.arbitration.claim_detector import CLAIM_DETECTOR_PROMPT

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PROD_MODEL = "qwen/qwen3.8-27b"
TEST_MODEL = "openai/gpt-oss-20b"

CLAIM_SCHEMA = {
    "name": "claim_detection_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "is_factual_claim": {"type": "boolean"},
            "claim": {"type": "string"},
            "topic": {
                "type": "string",
                "enum": ["hardware", "gaming", "sports", "tech", "movies", "general", "null"]
            },
            "entity": {"type": "string"},
            "metric": {"type": "string"}
        },
        "required": ["is_factual_claim", "claim", "topic", "entity", "metric"],
        "additionalProperties": False
    }
}

def validate_schema(data):
    if not isinstance(data, dict):
        return False, "Not a dict"
    required = ["is_factual_claim", "claim", "topic", "entity", "metric"]
    for r in required:
        if r not in data:
            return False, f"Missing {r}"
    if not isinstance(data["is_factual_claim"], bool):
        return False, "is_factual_claim is not bool"
    if not isinstance(data["claim"], str):
        return False, "claim is not str"
    if not isinstance(data["entity"], str):
        return False, "entity is not str"
    if not isinstance(data["metric"], str):
        return False, "metric is not str"
    return True, "Valid"

def test_model(model_name):
    print(f"\n=======================================================")
    print(f"TESTING MODEL: {model_name}")
    print(f"=======================================================")
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    user_prompt = 'Utterance: "Bro, RTX 5070 has 16GB VRAM"'
    
    # (a) json_schema stream=false
    print(f"\n--- (a) json_schema strict, stream=false ---")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": CLAIM_DETECTOR_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": CLAIM_SCHEMA
        },
        "stream": False
    }
    
    with httpx.Client(timeout=15.0) as client:
        r = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            print("Content:", content)
            try:
                parsed = json.loads(content)
                val, reason = validate_schema(parsed)
                print(f"Schema validation: {val} ({reason})")
            except Exception as e:
                print(f"JSON parse error: {e}")
        else:
            print(f"Error body: {r.text}")

        # (b) Same request stream=true
        print(f"\n--- (b) json_schema strict, stream=true ---")
        payload_stream = dict(payload)
        payload_stream["stream"] = True
        r_stream = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload_stream)
        print(f"Stream status code: {r_stream.status_code}")
        print(f"Stream response excerpt: {r_stream.text[:300]}")

        # (c) Repeat (a) 5 times
        print(f"\n--- (c) Repeat (a) 5 times validation count ---")
        valid_count = 0
        latencies = []
        for i in range(5):
            t0 = time.perf_counter()
            r_rep = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            dt_ms = int((time.perf_counter() - t0) * 1000)
            latencies.append(dt_ms)
            if r_rep.status_code == 200:
                try:
                    c = r_rep.json()["choices"][0]["message"]["content"]
                    p = json.loads(c)
                    val, _ = validate_schema(p)
                    if val:
                        valid_count += 1
                        print(f"  Run #{i+1}: {dt_ms}ms -> VALID")
                    else:
                        print(f"  Run #{i+1}: {dt_ms}ms -> INVALID SCHEMA: {p}")
                except Exception as e:
                    print(f"  Run #{i+1}: {dt_ms}ms -> PARSE ERROR: {e}")
            else:
                print(f"  Run #{i+1}: HTTP {r_rep.status_code} - {r_rep.text[:150]}")
        print(f"Total Schema-Valid Outputs: {valid_count}/5")

def main():
    if not GROQ_API_KEY:
        print("BLOCKED: GROQ_API_KEY not set")
        return
    test_model(TEST_MODEL)
    test_model(PROD_MODEL)

if __name__ == "__main__":
    main()
