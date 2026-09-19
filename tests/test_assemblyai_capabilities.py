import asyncio
import os
import json
import time
import websockets
from dotenv import load_dotenv

load_dotenv()

async def test_streaming_model(model_name: str, language_code: str = "ar"):
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("ERROR: ASSEMBLYAI_API_KEY is not set.")
        return None

    # AssemblyAI v3 websocket URL
    url = f"wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&speech_model={model_name}"
    if language_code:
        url += f"&language_code={language_code}"

    print(f"Testing AssemblyAI model: '{model_name}' with language_code='{language_code}'...")
    t0 = time.perf_counter()
    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": api_key},
            open_timeout=8
        ) as ws:
            connect_latency = (time.perf_counter() - t0) * 1000
            print(f"  Connected in {connect_latency:.1f}ms")
            
            # Read first message (session start / configuration)
            raw_msg = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw_msg)
            print(f"  Handshake Received: type={msg.get('type')}")
            config = msg.get("configuration", {})
            print(f"  Negotiated Model: {config.get('model', 'N/A')}")
            print(f"  Config Details: {json.dumps(config, indent=2)}")

            # Test termination
            await ws.send(json.dumps({"type": "Terminate"}))
            try:
                term_raw = await asyncio.wait_for(ws.recv(), timeout=3)
                term_msg = json.loads(term_raw)
                print(f"  Termination: {term_msg.get('type')}")
            except Exception:
                pass

            return {
                "model_tested": model_name,
                "negotiated_model": config.get("model"),
                "status": "success",
                "connect_latency_ms": round(connect_latency, 1),
                "config": config
            }
    except Exception as e:
        print(f"  FAILED for {model_name}: {e}")
        return {
            "model_tested": model_name,
            "status": "error",
            "error": str(e)
        }

async def main():
    print("=== AssemblyAI Capability & Model Probe ===")
    candidates = [
        ("universal-3-5-pro", "ar"),
        ("universal-3-5-pro", None),
        ("u3-rt-pro", "ar"),
        ("u3-rt-pro", None),
        ("universal-2", "ar"),
    ]

    results = []
    for model, lang in candidates:
        res = await test_streaming_model(model, lang)
        results.append(res)
        await asyncio.sleep(1)

    print("\n=== Summary of Results ===")
    print(json.dumps(results, indent=2))

    # Save results to a file for README integration
    with open("assemblyai_capability_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved report to assemblyai_capability_report.json")

if __name__ == "__main__":
    asyncio.run(main())
