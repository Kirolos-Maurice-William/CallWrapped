"""T3: Edge-TTS synthesis latency measurement."""
import sys, io, os, time, asyncio, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import edge_tts

VOICE_AR = "ar-EG-ShakirNeural"
VOICE_EN = "en-US-JennyNeural"
TEST_TEXT_EN = "Correction: The NVIDIA RTX 5070 features 12 gigabytes of GDDR7 memory. Source: nvidia.com."
TEST_TEXT_AR = "The RTX 5070 has 12GB VRAM not 16GB."

async def run_test():
    print(f"Voice AR: {VOICE_AR}")
    print(f"Voice EN: {VOICE_EN}")
    print(f"Test text: {TEST_TEXT_EN[:80]}...")
    print("=" * 60)

    for voice, text, label in [
        (VOICE_AR, TEST_TEXT_AR, "Arabic"),
        (VOICE_EN, TEST_TEXT_EN, "English")
    ]:
        print(f"\n--- {label} Voice ({voice}) ---")
        latencies = []
        for i in range(6):
            t0 = time.perf_counter()
            try:
                communicate = edge_tts.Communicate(text, voice, rate="-3%", pitch="+0Hz")
                output_file = os.path.join(os.path.dirname(__file__), f"tts_test_{label.lower()}_{i}.mp3")
                await communicate.save(output_file)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
                latencies.append(latency_ms)
                print(f"  Run #{i+1}: {latency_ms}ms | File size: {file_size} bytes")
                # Clean up
                if os.path.exists(output_file):
                    os.remove(output_file)
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
            print(f"  Summary: n={len(latencies)}, Cold={cold}ms, Warm p50={warm_sorted[p50_idx]}ms, Warm p95={warm_sorted[p95_idx]}ms, Mean={statistics.mean(warm):.0f}ms")

asyncio.run(run_test())
