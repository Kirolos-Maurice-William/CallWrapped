import os
import sys
import time
import csv
import asyncio
import numpy as np
import httpx
import jiwer

# Reconfigure stdout to utf-8 for Windows terminal
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("."))

from audit.cleaner import clean_arabic_text
from bot.ai.assemblyai import (
    assemblyai_client,
    ASSEMBLYAI_CONTEXT_PROMPT,
    ASSEMBLYAI_KEYTERMS
)
from bot.config import config

LABELS_CSV = os.path.join("audit", "mgb3_clips", "labels.csv")
RESULTS_CSV = os.path.join("audit", "mgb3_results.csv")
CLIPS_DIR = os.path.join("audit", "mgb3_clips")

NUMBER_MAP = {
    'صفر': 0, '0': 0,
    'واحد': 1, 'واحده': 1, '1': 1,
    'اتنين': 2, 'تنين': 2, 'سنتين': 2, '2': 2,
    'تلاته': 3, 'تلات': 3, 'تلت': 3, 'ثلاثه': 3, 'ثلاث': 3, '3': 3,
    'اربعه': 4, 'اربع': 4, '4': 4,
    'خمسه': 5, 'خمس': 5, '5': 5,
    'سته': 6, 'ست': 6, '6': 6,
    'سبعه': 7, 'سبع': 7, '7': 7,
    'تمانيه': 8, 'تمن': 8, 'ثمانيه': 8, '8': 8,
    'تسعه': 9, 'تسع': 9, '9': 9,
    'عشره': 10, 'عشر': 10, '10': 10,
    'احداشر': 11, 'احد عشر': 11, '11': 11,
    'اتناشر': 12, 'اثنا عشر': 12, '12': 12,
    'تلاتاشر': 13, '13': 13,
    'اربعتاشر': 14, '14': 14,
    'خمستاشر': 15, '15': 15,
    'ستاشر': 16, '16': 16,
    'سبعتاشر': 17, '17': 17,
    'تمنتاشر': 18, '18': 18,
    'تسعتاشر': 19, '19': 19,
    'عشرين': 20, '20': 20,
    'تلاتين': 30, 'ثلاثين': 30, '30': 30,
    'اربعين': 40, '40': 40,
    'خمسين': 50, '50': 50,
    'ستين': 60, '60': 60,
    'سبعين': 70, '70': 70,
    'تمانين': 80, 'ثمانين': 80, '80': 80,
    'تسعين': 90, '90': 90,
    'ميه': 100, 'مائه': 100, '100': 100,
    'ميتين': 200, '200': 200,
    'الف': 1000, '1000': 1000,
    'الفين': 2000, '2000': 2000,
    'مليون': 1000000
}

def extract_number_values(text: str):
    tokens = text.split()
    nums = []
    for t in tokens:
        if t.isdigit():
            nums.append(int(t))
        elif t in NUMBER_MAP:
            nums.append(NUMBER_MAP[t])
        elif t.startswith('و') and len(t) > 1 and t[1:] in NUMBER_MAP:
            nums.append(NUMBER_MAP[t[1:]])
    return nums

async def transcribe_clip(client: httpx.AsyncClient, wav_path: str):
    """Transcribes a single clip using production AssemblyAI settings and measures latency."""
    with open(wav_path, "rb") as f:
        wav_bytes = f.read()

    headers = {"Authorization": assemblyai_client.api_key}
    t0 = time.perf_counter()

    try:
        # Step 1: Upload
        up_resp = await client.post(assemblyai_client.upload_url, headers=headers, content=wav_bytes)
        if up_resp.status_code != 200:
            return None, int((time.perf_counter() - t0) * 1000), f"Upload HTTP {up_resp.status_code}"
        upload_url = up_resp.json().get("upload_url")

        # Step 2: Submit job with production parameters
        job_payload = {
            "audio_url": upload_url,
            "language_code": config.SPEECH_LANGUAGE,
            "speech_models": config.SPEECH_MODELS,
            "punctuate": True,
            "format_text": True,
            "prompt": ASSEMBLYAI_CONTEXT_PROMPT,
            "keyterms_prompt": ASSEMBLYAI_KEYTERMS
        }
        job_resp = await client.post(assemblyai_client.transcript_url, headers=headers, json=job_payload)
        if job_resp.status_code != 200:
            return None, int((time.perf_counter() - t0) * 1000), f"Job HTTP {job_resp.status_code}"

        job_id = job_resp.json().get("id")
        poll_url = f"{assemblyai_client.transcript_url}/{job_id}"

        # Step 3: Poll up to 60s (120 * 0.5s)
        for _ in range(120):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(poll_url, headers=headers)
            if poll_resp.status_code == 200:
                data = poll_resp.json()
                st = data.get("status")
                if st == "completed":
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    text = data.get("text", "").strip()
                    return text, latency_ms, "completed"
                elif st == "error":
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    err_msg = data.get("error", "Unknown error")
                    return None, latency_ms, f"Error: {err_msg}"

        return None, int((time.perf_counter() - t0) * 1000), "Timeout (>60s)"

    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return None, latency_ms, f"Exception: {str(e)}"

async def main():
    if not assemblyai_client.api_key:
        print("BLOCKED: ASSEMBLYAI_API_KEY is missing or empty.")
        return

    # Read clips from labels.csv
    clips = []
    with open(LABELS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clips.append(row)

    print(f"Loaded {len(clips)} clips from {LABELS_CSV}.")
    print(f"AssemblyAI Production Settings:")
    print(f"  Speech Language: {config.SPEECH_LANGUAGE}")
    print(f"  Speech Models:   {config.SPEECH_MODELS}")
    print(f"  Context Prompt:  {ASSEMBLYAI_CONTEXT_PROMPT}")
    print(f"  Keyterms:        {ASSEMBLYAI_KEYTERMS}")
    print(f"  Polling Budget:  6000ms\n")

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, clip in enumerate(clips, 1):
            cid = clip["id"]
            genre = clip["genre"]
            dur = float(clip["duration_s"])
            ref_raw = clip["reference_text"]
            ref_clean = clean_arabic_text(ref_raw)
            wav_path = os.path.join(CLIPS_DIR, f"{cid}.wav")

            print(f"[{idx:02d}/{len(clips):02d}] Transcribing {cid} ({genre}, {dur:.2f}s)...", end=" ", flush=True)

            heard_raw, latency_ms, status = await transcribe_clip(client, wav_path)
            exceeded_6s = latency_ms > 6000

            if status == "completed" and heard_raw is not None:
                heard_clean = clean_arabic_text(heard_raw)
                try:
                    clip_wer = jiwer.wer(ref_clean, heard_clean)
                except Exception:
                    clip_wer = 1.0 if not heard_clean else 0.0
                print(f"DONE in {latency_ms}ms (exceeded 6s: {exceeded_6s}) | WER: {clip_wer:.1%}")
            else:
                heard_clean = ""
                clip_wer = 1.0
                print(f"FAILED ({status}) in {latency_ms}ms")

            results.append({
                "id": cid,
                "genre": genre,
                "duration_s": dur,
                "ref_raw": ref_raw,
                "ref_clean": ref_clean,
                "heard_raw": heard_raw or "",
                "heard_clean": heard_clean,
                "latency_ms": latency_ms,
                "exceeded_6s": exceeded_6s,
                "status": status,
                "wer": clip_wer
            })

            # Sleep 2s between clips
            if idx < len(clips):
                await asyncio.sleep(2.0)

    # Save results to audit/mgb3_results.csv
    fieldnames = [
        "id", "genre", "duration_s", "latency_ms", "exceeded_6s",
        "wer", "status", "ref_clean", "heard_clean", "ref_raw", "heard_raw"
    ]
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    print(f"\nSaved detailed results to {RESULTS_CSV}")

    # ==================== SCORING & METRICS ====================
    successful = [r for r in results if r["status"] == "completed"]
    latencies = [r["latency_ms"] for r in successful]

    # Overall WER
    all_refs = [r["ref_clean"] for r in results]
    all_hyps = [r["heard_clean"] for r in results]
    overall_wer = jiwer.wer(all_refs, all_hyps)

    # Clean vs Noisy split
    # Criterion: A clip is NOISY if heard word count < 70% of ref count or clip WER >= 45%
    clean_clips = []
    noisy_clips = []
    for r in results:
        ref_words = r["ref_clean"].split()
        hyp_words = r["heard_clean"].split()
        ratio = len(hyp_words) / max(1, len(ref_words))
        if ratio < 0.70 or r["wer"] >= 0.45 or r["status"] != "completed":
            noisy_clips.append(r)
        else:
            clean_clips.append(r)

    clean_wer = jiwer.wer([r["ref_clean"] for r in clean_clips], [r["heard_clean"] for r in clean_clips]) if clean_clips else 0.0
    noisy_wer = jiwer.wer([r["ref_clean"] for r in noisy_clips], [r["heard_clean"] for r in noisy_clips]) if noisy_clips else 0.0

    # Top 10 Most Misheard Words
    from collections import Counter
    misheard_words = Counter()
    for r in results:
        ref_tokens = r["ref_clean"].split()
        hyp_tokens = r["heard_clean"].split()
        if not ref_tokens:
            continue
        try:
            alignments = jiwer.process_words(r["ref_clean"], r["heard_clean"]).alignments[0]
            for chunk in alignments:
                if chunk.type in ("substitute", "delete"):
                    for w in ref_tokens[chunk.ref_start_idx : chunk.ref_end_idx]:
                        misheard_words[w] += 1
        except Exception:
            for w in ref_tokens:
                misheard_words[w] += 1

    top_10_misheard = misheard_words.most_common(10)

    # Number Recognition
    total_number_tokens = 0
    correct_number_tokens = 0
    clips_with_numbers = []

    def check_numbers_match(ref_nums, hyp_nums):
        """Checks how many ref numbers are found in hyp numbers, accounting for compound numbers like 99 = 90 + 9."""
        expanded_hyp = []
        for h in hyp_nums:
            expanded_hyp.append(h)
            if 20 <= h <= 99 and h % 10 != 0:
                expanded_hyp.extend([h % 10, (h // 10) * 10])
        
        matched = 0
        for r in ref_nums:
            if r in expanded_hyp:
                matched += 1
                expanded_hyp.remove(r)
        return matched

    for r in results:
        ref_nums = extract_number_values(r["ref_clean"])
        hyp_nums = extract_number_values(r["heard_clean"])
        if ref_nums:
            clips_with_numbers.append(r)
            total_number_tokens += len(ref_nums)
            correct_number_tokens += check_numbers_match(ref_nums, hyp_nums)

    # Latency p50 and p95 and budget overruns
    p50_lat = np.percentile(latencies, 50) if latencies else 0
    p95_lat = np.percentile(latencies, 95) if latencies else 0
    budget_overruns = sum(1 for r in results if r["exceeded_6s"])

    # ==================== OUTPUT ACCEPTANCE REPORT ====================
    print("\n" + "=" * 90)
    print("                      ASSEMBLYAI STT HEARING TEST SUMMARY TABLE")
    print("=" * 90)
    print(f"{'#':<3} {'ID':<38} {'Genre':<12} {'Dur(s)':<7} {'Latency':<9} {'>6s':<5} {'WER':<7} {'Status'}")
    print("-" * 90)
    for idx, r in enumerate(results, 1):
        cid_short = r["id"][:36]
        print(f"{idx:<3} {cid_short:<38} {r['genre']:<12} {r['duration_s']:<7.2f} {r['latency_ms']}ms{'':<3} {str(r['exceeded_6s']):<5} {r['wer']:<7.1%} {r['status']}")
    print("-" * 90)

    print("\n" + "=" * 90)
    print("                              EXAMPLE AUDIT ROWS")
    print("=" * 90)
    
    # 1. Clean clip
    best_clean = min(clean_clips, key=lambda x: x["wer"]) if clean_clips else results[0]
    print("\n[EXAMPLE 1: CLEAN CLIP]")
    print(f"ID:        {best_clean['id']} ({best_clean['genre']}, {best_clean['duration_s']:.2f}s)")
    print(f"WER:       {best_clean['wer']:.1%} | Latency: {best_clean['latency_ms']}ms")
    print(f"REF (RAW): {best_clean['ref_raw']}")
    print(f"REF (CLN): {best_clean['ref_clean']}")
    print(f"HEARD:     {best_clean['heard_clean']}")

    # 2. Noisy clip
    worst_noisy = max(noisy_clips, key=lambda x: x["wer"]) if noisy_clips else results[-1]
    print("\n[EXAMPLE 2: NOISY CLIP]")
    print(f"ID:        {worst_noisy['id']} ({worst_noisy['genre']}, {worst_noisy['duration_s']:.2f}s)")
    print(f"WER:       {worst_noisy['wer']:.1%} | Latency: {worst_noisy['latency_ms']}ms")
    print(f"REF (RAW): {worst_noisy['ref_raw']}")
    print(f"REF (CLN): {worst_noisy['ref_clean']}")
    print(f"HEARD:     {worst_noisy['heard_clean']}")

    # 3. Clip with numbers
    num_clip = clips_with_numbers[0] if clips_with_numbers else results[0]
    # If comedy_09... with multiple numbers exists, prefer it
    for c in clips_with_numbers:
        if len(extract_number_values(c["ref_clean"])) >= 3:
            num_clip = c
            break
    ref_nums = extract_number_values(num_clip["ref_clean"])
    hyp_nums = extract_number_values(num_clip["heard_clean"])
    print("\n[EXAMPLE 3: CLIP WITH NUMBERS]")
    print(f"ID:        {num_clip['id']} ({num_clip['genre']}, {num_clip['duration_s']:.2f}s)")
    print(f"WER:       {num_clip['wer']:.1%} | Latency: {num_clip['latency_ms']}ms")
    print(f"REF (RAW): {num_clip['ref_raw']}")
    print(f"REF (CLN): {num_clip['ref_clean']}")
    print(f"HEARD:     {num_clip['heard_clean']}")
    print(f"Ref Numbers:   {ref_nums}")
    print(f"Heard Numbers: {hyp_nums}")

    print("\n" + "=" * 90)
    print("                                FINAL METRICS")
    print("=" * 90)
    print(f"Total Clips Tested:           {len(results)}")
    print(f"Completed Successfully:       {len(successful)} / {len(results)}")
    print(f"Overall Corpus WER:           {overall_wer:.2%}")
    print(f"Clean Clips Group WER:        {clean_wer:.2%} (n={len(clean_clips)})")
    print(f"Noisy Clips Group WER:        {noisy_wer:.2%} (n={len(noisy_clips)})")
    print(f"Number Recognition Accuracy:  {correct_number_tokens} of {total_number_tokens} numbers heard correctly ({correct_number_tokens/max(1, total_number_tokens):.1%})")
    print(f"Latency p50:                  {p50_lat:.0f} ms")
    print(f"Latency p95:                  {p95_lat:.0f} ms")
    print(f"Exceeded 6s Polling Budget:   {budget_overruns} of {len(results)} clips ({budget_overruns/len(results):.1%})")
    print("\nTop 10 Most Misheard Words:")
    for rank, (word, count) in enumerate(top_10_misheard, 1):
        print(f"  {rank:2d}. {word:<15} ({count} occurrences)")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
