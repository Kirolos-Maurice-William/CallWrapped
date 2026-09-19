import asyncio
import os
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

print("=" * 65)
print("         COMPREHENSIVE API HEALTH & DIAGNOSTIC TEST        ")
print("=" * 65)

async def check_assemblyai():
    print("\n[1] CHECKING ASSEMBLYAI API...")
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    model = (os.getenv("ASSEMBLYAI_MODEL") or "universal-3-5-pro").replace(".", "-")
    if not api_key:
        print("  ❌ ASSEMBLYAI_API_KEY is missing!")
        return False

    # 1. Check REST API / Account
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.assemblyai.com/v2/transcript?limit=1", headers={"Authorization": api_key})
            if resp.status_code == 200:
                print("  ✅ AssemblyAI REST API: Valid credentials & active account!")
            else:
                print(f"  ❌ AssemblyAI REST API error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  ⚠️ AssemblyAI REST test warning: {e}")

    # 2. Check WebSocket V3 Live Streaming
    import websockets
    url = f"wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&speech_model={model}"
    t0 = time.perf_counter()
    try:
        ws = await websockets.connect(url, additional_headers={"Authorization": api_key}, open_timeout=10)
        t_conn = (time.perf_counter() - t0) * 1000
        print(f"  ✅ AssemblyAI V3 Streaming: Connected in {t_conn:.1f}ms!")

        # Read Begin message
        begin_raw = await asyncio.wait_for(ws.recv(), timeout=5)
        begin_data = json.loads(begin_raw)
        print(f"  ✅ AssemblyAI Handshake: type={begin_data.get('type')}, session_id={begin_data.get('id')}")
        print(f"     Applied Model: {begin_data.get('configuration', {}).get('model')}")

        # Test sending PCM audio frame
        sample_pcm = b"\x00\x05\x00\x02" * 400  # 1600 samples (100ms)
        await ws.send(sample_pcm)
        print("  ✅ AssemblyAI Audio Ingestion: Raw PCM16 frame sent successfully!")

        # Send Terminate
        await ws.send(json.dumps({"type": "Terminate"}))
        async for msg in ws:
            term_data = json.loads(msg)
            if term_data.get("type") == "Termination":
                print("  ✅ AssemblyAI Clean Teardown: Session terminated properly!")
                break
        await ws.close()
        return True
    except Exception as e:
        print(f"  ❌ AssemblyAI Streaming Error: {e}")
        return False

async def check_tavily():
    print("\n[2] CHECKING TAVILY WEB SEARCH API...")
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("  ⚠️ TAVILY_API_KEY not configured.")
        return False
    try:
        t0 = time.perf_counter()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": "Inception movie Christopher Nolan release date", "max_results": 2},
                timeout=10
            )
            lat = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                print(f"  ✅ Tavily Search API: SUCCESS ({lat:.1f}ms) — {len(results)} authoritative sources found!")
                for r in results[:1]:
                    print(f"     Sample Source: \"{r.get('title')}\" -> {r.get('url')}")
                return True
            else:
                print(f"  ❌ Tavily Error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        print(f"  ❌ Tavily Exception: {e}")
        return False

async def check_ddgs():
    print("\n[3] CHECKING DUCKDUCKGO FALLBACK SEARCH...")
    try:
        from ddgs import DDGS
        loop = asyncio.get_running_loop()
        def sync_ddgs():
            with DDGS() as ddgs:
                return list(ddgs.text("Egypt capital Cairo", max_results=1))
        t0 = time.perf_counter()
        res = await loop.run_in_executor(None, sync_ddgs)
        lat = (time.perf_counter() - t0) * 1000
        print(f"  ✅ DuckDuckGo Fallback: SUCCESS ({lat:.1f}ms) — {len(res)} results.")
        return True
    except Exception as e:
        print(f"  ⚠️ DuckDuckGo Notice: {e}")
        return False

async def check_edge_tts():
    print("\n[4] CHECKING NEURAL EDGE-TTS VOICE ENGINE...")
    try:
        import edge_tts
        t0 = time.perf_counter()
        communicate = edge_tts.Communicate("ثواني يا شباب راجعت المعلومة", "ar-EG-SalmaNeural")
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        total_audio = b"".join(audio_chunks)
        lat = (time.perf_counter() - t0) * 1000
        print(f"  ✅ Edge-TTS (Salma Egyptian Neural): Generated {len(total_audio)} audio bytes in {lat:.1f}ms!")
        return True
    except Exception as e:
        print(f"  ❌ Edge-TTS Error: {e}")
        return False

async def check_backend_server():
    print("\n[5] CHECKING LOCAL BACKEND (PORT 8000)...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:8000/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ✅ Backend Server: Status={data.get('status')}, Model={data.get('assemblyai_model')}")
                return True
            else:
                print(f"  ❌ Backend Server Error: {resp.status_code}")
                return False
    except Exception as e:
        print(f"  ❌ Backend Server connection failed: {e}")
        return False

async def main():
    res_aai = await check_assemblyai()
    res_tav = await check_tavily()
    res_ddg = await check_ddgs()
    res_tts = await check_edge_tts()
    res_srv = await check_backend_server()

    print("\n" + "=" * 65)
    print("                      SUMMARY RESULTS                      ")
    print("=" * 65)
    print(f"  AssemblyAI Streaming V3 : {'✅ 100% OPERATIONAL' if res_aai else '❌ FAILED'}")
    print(f"  Tavily Fact Search      : {'✅ 100% OPERATIONAL' if res_tav else '❌ FAILED'}")
    print(f"  DuckDuckGo Backup Search: {'✅ 100% OPERATIONAL' if res_ddg else '⚠️ BACKUP OFFLINE'}")
    print(f"  Neural Edge-TTS Voice   : {'✅ 100% OPERATIONAL' if res_tts else '❌ FAILED'}")
    print(f"  Backend Server          : {'✅ 100% OPERATIONAL' if res_srv else '❌ FAILED'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
