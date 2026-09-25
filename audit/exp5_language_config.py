import os
import sys
import time
import csv
import io
import wave
import asyncio
import numpy as np
import httpx
import jiwer

# Reconfigure stdout to utf-8 for Windows terminal
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("."))

from audit.cleaner import clean_arabic_text
from audit.run_hearing_test import extract_number_values
from audit.exp1_silence_trim import trim_trailing_silence, check_numbers_match
from bot.ai.assemblyai import (
    assemblyai_client,
    ASSEMBLYAI_CONTEXT_PROMPT,
    ASSEMBLYAI_KEYTERMS,
    ASSEMBLYAI_CUSTOM_SPELLING
)
from bot.config import config

LABELS_CSV = os.path.join("audit", "mgb3_clips", "labels.csv")
OUT_CSV = os.path.join("audit", "mgb3_exp5_lang_detect.csv")
CLIPS_DIR = os.path.join("audit", "mgb3_clips")

async def transcribe_lang_detect(client: httpx.AsyncClient, trimmed_bytes: bytes):
    headers = {"Authorization": assemblyai_client.api_key}
    t0 = time.perf_counter()

    try:
        up_resp = await client.post(assemblyai_client.upload_url, headers=headers, content=trimmed_bytes)
        if up_resp.status_code != 200:
            return None, None, int((time.perf_counter() - t0) * 1000), f"Upload HTTP {up_resp.status_code}"
        upload_url = up_resp.json().get("upload_url")

        job_payload = {
            "audio_url": upload_url,
            "language_detection": True,
            "speech_models": config.SPEECH_MODELS,
            "punctuate": True,
            "format_text": True,
            "prompt": ASSEMBLYAI_CONTEXT_PROMPT,
            "keyterms_prompt": ASSEMBLYAI_KEYTERMS,
            "custom_spelling": ASSEMBLYAI_CUSTOM_SPELLING
        }

        job_resp = await client.post(assemblyai_client.transcript_url, headers=headers, json=job_payload)
        if job_resp.status_code != 200:
            return None, None, int((time.perf_counter() - t0) * 1000), f"Job HTTP {job_resp.status_code}: {job_resp.text}"

        job_id = job_resp.json().get("id")
        poll_url = f"{assemblyai_client.transcript_url}/{job_id}"

        for _ in range(120):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(poll_url, headers=headers)
            if poll_resp.status_code == 200:
                data = poll_resp.json()
                st = data.get("status")
                if st == "completed":
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    text = data.get("text", "").strip()
                    lang = data.get("language_code", "unknown")
                    return text, lang, latency_ms, "completed"
                elif st == "error":
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    err_msg = data.get("error", "Unknown error")
                    return None, None, latency_ms, f"Error: {err_msg}"

        return None, None, int((time.perf_counter() - t0) * 1000), "Timeout (>60s)"

    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return None, None, latency_ms, f"Exception: {str(e)}"

async def main():
    if not assemblyai_client.api_key:
        print("BLOCKED: ASSEMBLYAI_API_KEY is missing or empty.")
        return

    clips = []
    with open(LABELS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clips.append(row)

    print(f"Loaded {len(clips)} clips for EXP 5 (Language Config: language_detection=True).")
    print("Benchmark vs Fixed language_code='ar':\n")

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, clip in enumerate(clips, 1):
            cid = clip["id"]
            genre = clip["genre"]
            ref_raw = clip["reference_text"]
            ref_clean = clean_arabic_text(ref_raw)
            wav_path = os.path.join(CLIPS_DIR, f"{cid}.wav")

            with open(wav_path, "rb") as f:
                raw_bytes = f.read()
            trimmed_bytes, _, _ = trim_trailing_silence(raw_bytes, threshold_rms=80.0, pad_ms=150)

            print(f"[{idx:02d}/20] {cid[:28]}...", end=" ", flush=True)
            heard_raw, detected_lang, latency_ms, status = await transcribe_lang_detect(client, trimmed_bytes)

            if status == "completed" and heard_raw is not None:
                heard_clean = clean_arabic_text(heard_raw)
                try:
                    clip_wer = jiwer.wer(ref_clean, heard_clean)
                except Exception:
                    clip_wer = 1.0 if not heard_clean else 0.0
                print(f"OK {latency_ms}ms (lang={detected_lang}) | WER: {clip_wer:.1%}")
            else:
                heard_clean = ""
                clip_wer = 1.0
                print(f"FAIL ({status})")

            results.append({
                "id": cid,
                "genre": genre,
                "detected_lang": detected_lang or "none",
                "wer": clip_wer,
                "latency_ms": latency_ms,
                "status": status,
                "ref_clean": ref_clean,
                "heard_clean": heard_clean,
                "ref_raw": ref_raw,
                "heard_raw": heard_raw or ""
            })

            if idx < len(clips):
                await asyncio.sleep(2.0)

    # Save CSV
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["id", "genre", "detected_lang", "wer", "latency_ms", "status", "ref_clean", "heard_clean", "ref_raw", "heard_raw"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Metrics
    all_refs = [r["ref_clean"] for r in results]
    all_hyps = [r["heard_clean"] for r in results]
    overall_wer = jiwer.wer(all_refs, all_hyps)

    clean_clips = [r for r in results if r["wer"] < 0.45 and len(r["heard_clean"].split()) >= 0.70 * len(r["ref_clean"].split()) and r["status"] == "completed"]
    clean_wer = jiwer.wer([r["ref_clean"] for r in clean_clips], [r["heard_clean"] for r in clean_clips]) if clean_clips else 0.0

    total_nums = 0
    correct_nums = 0
    for r in results:
        ref_nums = extract_number_values(r["ref_clean"])
        hyp_nums = extract_number_values(r["heard_clean"])
        if ref_nums:
            total_nums += len(ref_nums)
            correct_nums += check_numbers_match(ref_nums, hyp_nums)
    num_acc = correct_nums / max(1, total_nums)
    latencies = [r["latency_ms"] for r in results if r["status"] == "completed"]
    p50_lat = np.percentile(latencies, 50) if latencies else 0

    print("\n" + "=" * 90)
    print("                     EXP 5: LANGUAGE CONFIG COMPARISON")
    print("=" * 90)
    print(f"Fixed language_code='ar':       WER: 22.15% | Clean: 19.40% | Numbers: 90.0% | p50: 3060ms")
    print(f"language_detection=True:        WER: {overall_wer:.2%} | Clean: {clean_wer:.2%} | Numbers: {num_acc:.1%} | p50: {p50_lat:.0f}ms")
    print(f"Delta vs language_code='ar':    WER: {overall_wer - 0.2215:+.2%} | p50: {p50_lat - 3060:+.0f}ms")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
