"""
Benchmark script: 10 sequential synthesis runs of a 15-word Arabic sentence via Edge-TTS.
Measures Time-To-First-Byte (TTFB) and full synthesis latency with 2s pacing between runs.
"""
import sys
import io
import time
import asyncio
import statistics
from typing import List, Dict, Any

# Ensure UTF-8 output in Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import edge_tts

VOICE = "ar-EG-ShakirNeural"
RATE = "-3%"
PITCH = "+0Hz"
TEST_TEXT = "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16"

NUM_RUNS = 10
SLEEP_BETWEEN_RUNS = 2.0


async def benchmark_run(run_idx: int) -> Dict[str, Any]:
    t0 = time.perf_counter()
    communicate = edge_tts.Communicate(TEST_TEXT, VOICE, rate=RATE, pitch=PITCH)
    
    t_first_event: float = 0.0
    t_first_audio: float = 0.0
    first_event_type: str = ""
    first_audio_bytes: int = 0
    total_audio_bytes: int = 0
    audio_chunks_count: int = 0
    all_chunks_count: int = 0
    
    stream_gen = communicate.stream()
    async for chunk in stream_gen:
        now = time.perf_counter()
        all_chunks_count += 1
        ctype = chunk.get("type", "")
        
        if t_first_event == 0.0:
            t_first_event = now
            first_event_type = ctype
            
        if ctype == "audio":
            audio_chunks_count += 1
            data = chunk.get("data", b"")
            total_audio_bytes += len(data)
            if t_first_audio == 0.0:
                t_first_audio = now
                first_audio_bytes = len(data)

    t_end = time.perf_counter()
    
    ttfb_ms = (t_first_audio - t0) * 1000.0 if t_first_audio > 0 else 0.0
    first_event_ms = (t_first_event - t0) * 1000.0 if t_first_event > 0 else 0.0
    total_ms = (t_end - t0) * 1000.0
    
    return {
        "run": run_idx,
        "ttfb_ms": ttfb_ms,
        "first_event_ms": first_event_ms,
        "first_event_type": first_event_type,
        "first_audio_bytes": first_audio_bytes,
        "total_ms": total_ms,
        "total_audio_bytes": total_audio_bytes,
        "audio_chunks": audio_chunks_count,
        "all_chunks": all_chunks_count,
    }


def compute_percentile(sorted_list: List[float], p: float) -> float:
    """Calculates percentile p in [0, 100] using standard linear interpolation."""
    if not sorted_list:
        return 0.0
    if len(sorted_list) == 1:
        return sorted_list[0]
    k = (len(sorted_list) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_list) - 1)
    d = k - f
    return sorted_list[f] + d * (sorted_list[c] - sorted_list[f])


async def main():
    words = TEST_TEXT.split()
    print("=" * 75)
    print("=== EDGE-TTS CONNECT & TTFB BENCHMARK (10 RUNS) ===")
    print("=" * 75)
    print(f"Target Voice:        {VOICE}")
    print(f"Rate / Pitch:        rate={RATE}, pitch={PITCH}")
    print(f"Sentence Word Count: {len(words)} words")
    print(f"Test Sentence:       '{TEST_TEXT}'")
    print(f"Number of Runs:      {NUM_RUNS} (pacing: {SLEEP_BETWEEN_RUNS}s)")
    print("=" * 75)
    print(f"{'Run':<5} | {'TTFB (ms)':<10} | {'1st Event':<10} | {'Type':<8} | {'1st Chunk':<10} | {'Total (ms)':<10} | {'Total Bytes':<12}")
    print("-" * 75)
    
    results: List[Dict[str, Any]] = []
    
    for i in range(1, NUM_RUNS + 1):
        try:
            res = await benchmark_run(i)
            results.append(res)
            print(
                f"#{res['run']:<4} | "
                f"{res['ttfb_ms']:<10.2f} | "
                f"{res['first_event_ms']:<10.2f} | "
                f"{res['first_event_type']:<8} | "
                f"{res['first_audio_bytes']:<10} | "
                f"{res['total_ms']:<10.2f} | "
                f"{res['total_audio_bytes']:<12}"
            )
        except Exception as e:
            print(f"#{i:<4} | ERROR: {e}")
        
        if i < NUM_RUNS:
            await asyncio.sleep(SLEEP_BETWEEN_RUNS)
            
    print("=" * 75)
    
    if results:
        ttfbs = [r["ttfb_ms"] for r in results]
        sorted_ttfbs = sorted(ttfbs)
        
        min_ttfb = sorted_ttfbs[0]
        max_ttfb = sorted_ttfbs[-1]
        p50_ttfb = compute_percentile(sorted_ttfbs, 50.0)
        p95_ttfb = compute_percentile(sorted_ttfbs, 95.0)
        mean_ttfb = statistics.mean(ttfbs)
        stdev_ttfb = statistics.stdev(ttfbs) if len(ttfbs) > 1 else 0.0
        
        totals = [r["total_ms"] for r in results]
        mean_total = statistics.mean(totals)
        
        print("\n=== SUMMARY STATISTICS ===")
        print(f"Runs Completed:      {len(results)}/{NUM_RUNS}")
        print(f"TTFB Min:            {min_ttfb:.2f} ms")
        print(f"TTFB P50 (Median):   {p50_ttfb:.2f} ms")
        print(f"TTFB P95:            {p95_ttfb:.2f} ms")
        print(f"TTFB Max:            {max_ttfb:.2f} ms")
        print(f"TTFB Mean:           {mean_ttfb:.2f} ms")
        print(f"TTFB Std Dev:        {stdev_ttfb:.2f} ms")
        print(f"Mean Full Synthesis: {mean_total:.2f} ms")
        print("=" * 75)
        
        # Diagnosis
        print("\n=== CAIRO TO MICROSOFT ENDPOINT PATTERN DIAGNOSIS ===")
        if max_ttfb > 5000.0:
            print("⚠️  Pattern observed: Severe connection latency spikes (>5000ms) reproduced during testing.")
        elif max_ttfb > 1500.0:
            print("⚠️  Pattern observed: Moderate jitter/latency spikes (>1500ms) observed.")
        else:
            print("✅  Normal latency profile: All TTFB measurements remained well under 1500ms.")
            print("    The prior 8021ms TTFB was likely an isolated network/TCP stall or Azure endpoint throttle.")


if __name__ == "__main__":
    asyncio.run(main())
