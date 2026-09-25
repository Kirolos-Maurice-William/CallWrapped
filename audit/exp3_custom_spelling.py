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
    ASSEMBLYAI_KEYTERMS
)
from bot.config import config

LABELS_CSV = os.path.join("audit", "mgb3_clips", "labels.csv")
CLIPS_DIR = os.path.join("audit", "mgb3_clips")

# 1. Latin-from mappings (20 mappings, single-word 'to')
LATIN_FROM_SPELLINGS = [
    {"from": ["uncertain"], "to": "uncertainty"},
    {"from": ["pinging"], "to": "ping"},
    {"from": ["lags", "lagging"], "to": "lag"},
    {"from": ["streaming", "streams"], "to": "stream"},
    {"from": ["discords"], "to": "Discord"},
    {"from": ["rtx"], "to": "RTX"},
    {"from": ["gpus"], "to": "GPU"},
    {"from": ["fpss"], "to": "FPS"},
    {"from": ["vrams"], "to": "VRAM"},
    {"from": ["gta"], "to": "GTA"},
    {"from": ["ranks"], "to": "ranked"},
    {"from": ["servers"], "to": "server"},
    {"from": ["admins"], "to": "admin"},
    {"from": ["updates"], "to": "update"},
    {"from": ["craft"], "to": "Minecraft"},
    {"from": ["headsets"], "to": "headset"},
    {"from": ["routers"], "to": "router"},
    {"from": ["fibers"], "to": "fiber"},
    {"from": ["mics"], "to": "mic"},
    {"from": ["packetloss"], "to": "packet"}
]

# 2. Arabic-script-from mappings (24 mappings, single-word 'to')
ARABIC_FROM_SPELLINGS = [
    {"from": ["كثيره", "كثيرة"], "to": "كتيره"},
    {"from": ["كثير"], "to": "كتير"},
    {"from": ["نقص"], "to": "ناقص"},
    {"from": ["يصدق"], "to": "يسبق"},
    {"from": ["بكم"], "to": "بيكم"},
    {"from": ["احلي", "أحلى"], "to": "احلم"},
    {"from": ["هنعيش"], "to": "حنعيش"},
    {"from": ["سنتعرف", "ستعرف"], "to": "حنتعرف"},
    {"from": ["بره"], "to": "برضه"},
    {"from": ["ثلاث", "ثلاثة"], "to": "تلت"},
    {"from": ["ثلاثين"], "to": "تلاتين"},
    {"from": ["بالزعائف", "بالزعينف", "بالزعينب"], "to": "بالزعانف"},
    {"from": ["زعائف", "زعينف", "زعينب"], "to": "زعانف"},
    {"from": ["معدله"], "to": "معضله"},
    {"from": ["لغوايه"], "to": "لغويه"},
    {"from": ["اسباحه"], "to": "سباحه"},
    {"from": ["كموس"], "to": "قاموس"},
    {"from": ["هيلقي", "هيلقى"], "to": "حيلاقي"},
    {"from": ["الحوزه"], "to": "ملحوظه"},
    {"from": ["البرانويا"], "to": "البارانويا"},
    {"from": ["كالشيزوفرانيا"], "to": "الشيزوفرانيا"},
    {"from": ["تسبحها"], "to": "سباحه"},
    {"from": ["قليلي"], "to": "قوليلي"},
    {"from": ["اكلمكم"], "to": "حكلمكو"}
]

async def transcribe_with_custom_spelling(client: httpx.AsyncClient, trimmed_bytes: bytes, custom_spelling: list):
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
            "keyterms_prompt": ASSEMBLYAI_KEYTERMS,
            "custom_spelling": custom_spelling
        }

        job_resp = await client.post(assemblyai_client.transcript_url, headers=headers, json=job_payload)
        if job_resp.status_code != 200:
            return None, int((time.perf_counter() - t0) * 1000), f"Job HTTP {job_resp.status_code}: {job_resp.text}"

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

async def run_probe(probe_name: str, spellings: list, clips: list, trimmed_cache: dict, client: httpx.AsyncClient):
    print(f"\n=======================================================")
    print(f"Running Custom Spelling Probe: {probe_name} ({len(spellings)} mappings)")
    print(f"=======================================================")
    results = []

    for idx, clip in enumerate(clips, 1):
        cid = clip["id"]
        genre = clip["genre"]
        ref_raw = clip["reference_text"]
        ref_clean = clean_arabic_text(ref_raw)
        trimmed_bytes = trimmed_cache[cid]

        print(f"[{idx:02d}/20] {cid[:28]}...", end=" ", flush=True)
        heard_raw, latency_ms, status = await transcribe_with_custom_spelling(client, trimmed_bytes, spellings)

        if status == "completed" and heard_raw is not None:
            heard_clean = clean_arabic_text(heard_raw)
            try:
                clip_wer = jiwer.wer(ref_clean, heard_clean)
            except Exception:
                clip_wer = 1.0 if not heard_clean else 0.0
            print(f"OK {latency_ms}ms | WER: {clip_wer:.1%}")
        else:
            heard_clean = ""
            clip_wer = 1.0
            print(f"FAIL ({status})")

        results.append({
            "id": cid,
            "genre": genre,
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
    out_csv = os.path.join("audit", f"mgb3_exp3_{probe_name}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "genre", "wer", "latency_ms", "status", "ref_clean", "heard_clean", "ref_raw", "heard_raw"])
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

    return {
        "probe": probe_name,
        "mappings_count": len(spellings),
        "corpus_wer": overall_wer,
        "clean_wer": clean_wer,
        "num_acc": num_acc,
        "p50_ms": p50_lat
    }

async def main():
    if not assemblyai_client.api_key:
        print("BLOCKED: ASSEMBLYAI_API_KEY is missing or empty.")
        return

    clips = []
    with open(LABELS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clips.append(row)

    print(f"Pre-caching and energy-trimming {len(clips)} audio clips...")
    trimmed_cache = {}
    for clip in clips:
        cid = clip["id"]
        wav_path = os.path.join(CLIPS_DIR, f"{cid}.wav")
        with open(wav_path, "rb") as f:
            raw = f.read()
        tb, _, _ = trim_trailing_silence(raw, threshold_rms=80.0, pad_ms=150)
        trimmed_cache[cid] = tb

    target_probe = sys.argv[1] if len(sys.argv) > 1 else None

    probes = {
        "latin_from": LATIN_FROM_SPELLINGS,
        "arabic_from": ARABIC_FROM_SPELLINGS,
        "combined_best": LATIN_FROM_SPELLINGS + ARABIC_FROM_SPELLINGS
    }


    summary = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for name, spellings in probes.items():
            if target_probe and name != target_probe:
                continue
            metrics = await run_probe(name, spellings, clips, trimmed_cache, client)
            summary.append(metrics)
            print(f"Result for {name}: WER={metrics['corpus_wer']:.2%} | Numbers={metrics['num_acc']:.1%} | p50={metrics['p50_ms']:.0f}ms")
            await asyncio.sleep(10.0)

    print("\n" + "=" * 90)
    print("                     EXP 3: CUSTOM SPELLING PROBE SUMMARY")
    print("=" * 90)
    print(f"{'Probe':<20} {'Mappings':<10} {'Corpus WER':<12} {'Clean WER':<12} {'Numbers':<12} {'p50 Latency'}")
    print("-" * 90)
    for s in summary:
        print(f"{s['probe']:<20} {s['mappings_count']:<10} {s['corpus_wer']:<12.2%} {s['clean_wer']:<12.2%} {s['num_acc']:<12.1%} {s['p50_ms']:.0f}ms")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
