"""T4: AssemblyAI batch transcription latency with synthetic audio."""
import sys, io, os, time, asyncio, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx
import edge_tts

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
SPEECH_MODELS = ["universal-3-5-pro", "universal-2"]
TEST_TEXT = "The RTX 5070 has 12 gigabytes of GDDR7 memory and costs around 549 dollars."

async def generate_test_audio():
    """Generate synthetic test audio using Edge-TTS."""
    output_path = os.path.join(os.path.dirname(__file__), "test_audio.mp3")
    communicate = edge_tts.Communicate(TEST_TEXT, "en-US-JennyNeural")
    await communicate.save(output_path)
    with open(output_path, "rb") as f:
        audio_bytes = f.read()
    os.remove(output_path)
    return audio_bytes

async def run_test():
    if not ASSEMBLYAI_API_KEY:
        print("BLOCKED: ASSEMBLYAI_API_KEY not set")
        return

    print(f"API Key (last 4): ...{ASSEMBLYAI_API_KEY[-4:]}")
    print(f"Speech Models: {SPEECH_MODELS}")
    print(f"Test text: {TEST_TEXT}")
    print("=" * 60)

    # Generate test audio
    print("\nGenerating synthetic test audio via Edge-TTS...")
    audio_bytes = await generate_test_audio()
    print(f"Audio size: {len(audio_bytes)} bytes")

    headers = {"Authorization": ASSEMBLYAI_API_KEY}
    latencies = []

    for i in range(6):
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Upload
                upload_resp = await client.post(
                    "https://api.assemblyai.com/v2/upload",
                    headers=headers,
                    content=audio_bytes
                )
                upload_ms = int((time.perf_counter() - t0) * 1000)
                if upload_resp.status_code != 200:
                    print(f"  Run #{i+1}: Upload failed HTTP {upload_resp.status_code}")
                    continue
                upload_url = upload_resp.json().get("upload_url")

                # Submit transcription job
                job_resp = await client.post(
                    "https://api.assemblyai.com/v2/transcript",
                    headers=headers,
                    json={
                        "audio_url": upload_url,
                        "speech_models": SPEECH_MODELS,
                        "punctuate": True,
                        "format_text": True
                    }
                )
                if job_resp.status_code != 200:
                    print(f"  Run #{i+1}: Job submit failed HTTP {job_resp.status_code} - {job_resp.text[:200]}")
                    continue

                job_id = job_resp.json().get("id")
                poll_url = f"https://api.assemblyai.com/v2/transcript/{job_id}"

                # Poll for completion
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    poll_resp = await client.get(poll_url, headers=headers)
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        status = data.get("status")
                        if status == "completed":
                            total_ms = int((time.perf_counter() - t0) * 1000)
                            text = data.get("text", "")
                            words = data.get("words", [])
                            avg_conf = sum(w.get("confidence", 0) for w in words) / len(words) if words else 0
                            latencies.append(total_ms)
                            print(f"  Run #{i+1}: {total_ms}ms (upload={upload_ms}ms) | conf={avg_conf:.0%} | \"{text[:100]}\"")
                            if i == 0:
                                print(f"    [COLD RUN] Full text: {text}")
                            break
                        elif status == "error":
                            error = data.get("error", "unknown")
                            print(f"  Run #{i+1}: Transcription error: {error}")
                            break
                else:
                    print(f"  Run #{i+1}: Polling timeout after 30s")
        except Exception as e:
            print(f"  Run #{i+1}: ERROR - {e}")

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
