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

def check_numbers_match(ref_nums, hyp_nums):
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

from bot.ai.assemblyai import (
    assemblyai_client,
    ASSEMBLYAI_CONTEXT_PROMPT,
    ASSEMBLYAI_KEYTERMS
)
from bot.config import config

LABELS_CSV = os.path.join("audit", "mgb3_clips", "labels.csv")
RESULTS_CSV = os.path.join("audit", "mgb3_exp1_silence_results.csv")
CLIPS_DIR = os.path.join("audit", "mgb3_clips")

def trim_trailing_silence(wav_bytes: bytes, threshold_rms: float = 80.0, frame_ms: int = 20, pad_ms: int = 150) -> tuple:
    """Trims trailing silence from 16kHz 16-bit mono WAV bytes."""
    with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    samples = np.frombuffer(frames, dtype=np.int16)
    orig_dur = len(samples) / rate
    frame_samples = int(rate * (frame_ms / 1000.0))
    pad_samples = int(rate * (pad_ms / 1000.0))

    num_frames = len(samples) // frame_samples
    last_active_sample = len(samples)

    for i in range(num_frames - 1, -1, -1):
        chunk = samples[i * frame_samples : (i + 1) * frame_samples]
        chunk_rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))
        if chunk_rms >= threshold_rms:
            last_active_sample = min(len(samples), (i + 1) * frame_samples + pad_samples)
            break
    else:
        last_active_sample = len(samples)

    trimmed_samples = samples[:last_active_sample]
    trimmed_dur = len(trimmed_samples) / rate

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(trimmed_samples.tobytes())
    return buf.getvalue(), orig_dur, trimmed_dur

async def transcribe_trimmed_clip(client: httpx.AsyncClient, trimmed_bytes: bytes):
    headers = {"Authorization": assemblyai_client.api_key}
    t0 = time.perf_counter()

    try:
        up_resp = await client.post(assemblyai_client.upload_url, headers=headers, content=trimmed_bytes)
        if up_resp.status_code != 200:
            return None, int((time.perf_counter() - t0) * 1000), f"Upload HTTP {up_resp.status_code}"
        upload_url = up_resp.json().get("upload_url")

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

    clips = []
    with open(LABELS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clips.append(row)

    print(f"Loaded {len(clips)} clips from {LABELS_CSV} for EXP 1 (Silence Trim).")
    print("Baseline: Corpus WER: 30.8% | Clean WER: 25.1% | Numbers: 90.0% | p50: 3326ms\n")

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, clip in enumerate(clips, 1):
            cid = clip["id"]
            genre = clip["genre"]
            dur = float(clip["duration_s"])
            ref_raw = clip["reference_text"]
            ref_clean = clean_arabic_text(ref_raw)
            wav_path = os.path.join(CLIPS_DIR, f"{cid}.wav")

            with open(wav_path, "rb") as f:
                raw_bytes = f.read()

            trimmed_bytes, orig_dur, trimmed_dur = trim_trailing_silence(raw_bytes, threshold_rms=80.0, pad_ms=150)
            diff_s = orig_dur - trimmed_dur

            print(f"[{idx:02d}/{len(clips):02d}] Transcribing {cid} (trimmed: {trimmed_dur:.2f}s, -{diff_s:.2f}s)...", end=" ", flush=True)

            heard_raw, latency_ms, status = await transcribe_trimmed_clip(client, trimmed_bytes)
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
                "orig_duration_s": orig_dur,
                "trimmed_duration_s": trimmed_dur,
                "latency_ms": latency_ms,
                "exceeded_6s": exceeded_6s,
                "wer": clip_wer,
                "status": status,
                "ref_clean": ref_clean,
                "heard_clean": heard_clean,
                "ref_raw": ref_raw,
                "heard_raw": heard_raw or ""
            })

            if idx < len(clips):
                await asyncio.sleep(2.0)

    # Save results
    fieldnames = [
        "id", "genre", "orig_duration_s", "trimmed_duration_s", "latency_ms",
        "exceeded_6s", "wer", "status", "ref_clean", "heard_clean", "ref_raw", "heard_raw"
    ]
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Calculate metrics
    successful = [r for r in results if r["status"] == "completed"]
    latencies = [r["latency_ms"] for r in successful]

    all_refs = [r["ref_clean"] for r in results]
    all_hyps = [r["heard_clean"] for r in results]
    overall_wer = jiwer.wer(all_refs, all_hyps)

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

    total_number_tokens = 0
    correct_number_tokens = 0
    for r in results:
        ref_nums = extract_number_values(r["ref_clean"])
        hyp_nums = extract_number_values(r["heard_clean"])
        if ref_nums:
            total_number_tokens += len(ref_nums)
            correct_number_tokens += check_numbers_match(ref_nums, hyp_nums)

    num_acc = correct_number_tokens / max(1, total_number_tokens)
    p50_lat = np.percentile(latencies, 50) if latencies else 0

    print("\n" + "=" * 90)
    print("                     EXP 1 (SILENCE TRIM) FINAL METRICS")
    print("=" * 90)
    print(f"Overall Corpus WER:          {overall_wer:.2%} (Baseline: 30.8% | Delta: {overall_wer - 0.307692:+.2%})")
    print(f"Clean Clips Group WER:       {clean_wer:.2%} (Baseline: 25.1% | Delta: {clean_wer - 0.251462:+.2%})")
    print(f"Number Recognition Accuracy: {num_acc:.1%} ({correct_number_tokens}/{total_number_tokens}) (Baseline: 90.0% | Delta: {num_acc - 0.90:+.1%})")
    print(f"Latency p50:                 {p50_lat:.0f} ms (Baseline: 3326 ms | Delta: {p50_lat - 3326:+.0f} ms)")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
