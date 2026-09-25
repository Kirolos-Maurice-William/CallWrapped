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

KEYTERMS_54 = list(ASSEMBLYAI_KEYTERMS)

KEYTERMS_150 = list(KEYTERMS_54) + [
    # Tech / Gaming transliterations & hardware
    "بينج", "رانكد", "أبديت", "ديسكورد", "ماين كرافت", "فريمات", "باكيت لوس", "ستريم", "لاج",
    "كارت شاشة", "سيرفر", "أدمن", "جي تي إيه", "ستيم", "تويتش", "بلايستيشن", "إكس بوكس",
    "فالورانت", "كاونتر", "فورتنايت", "كول أوف ديوتي", "ببجي", "فيفا", "بروسيسور",
    "رامات", "هارد", "ماذربورد", "شاشة", "مايك", "راوتر", "فايبر", "بوت", "نوب", "كاري",
    # Football entities & competitions
    "بيراميدز", "الإسماعيلي", "الاتحاد السكندري", "المصري", "محمد صلاح", "رونالدو",
    "مبابي", "فينيسيوس", "هالاند", "حسام حسن", "إمام عاشور", "زيزو", "شيكابالا", "الشناوي",
    "كأس مصر", "كأس الأمم الأفريقية", "دوري أبطال أفريقيا", "الدوري المصري", "السوبر المصري",
    "دوري أبطال أوروبا", "كأس العالم", "مانشستر سيتي", "ليفربول", "أرسنال", "بايرن ميونخ",
    # Movies, TV & actors
    "الفيل الأزرق", "كيرة والجن", "بيت الروبي", "الحريفة", "عيد الفطر", "شاهد", "نتفليكس",
    "كريم عبد العزيز", "محمد هنيدي", "أحمد حلمي", "منى زكي", "دينا الشربيني", "بيومي فؤاد",
    "أمير كرارة", "محمد رمضان", "ياسمين عبد العزيز", "محمد إمام",
    # Music & Rap
    "أبيوسف", "مروان موسى", "عفروتو", "شهاب", "ليجي-سي", "محمد منير", "شيرين", "أنغام",
    "تامر عاشور", "بهاء سلطان", "مهرجانات", "حسن شاكوش", "عمر كمال", "رضا البحراوي",
    # Politics, Economy & Public affairs
    "مجلس الشيوخ", "رئيس الوزراء", "مصطفى مدبولي", "التعويم", "البنك المركزي", "التضخم",
    "الفوائد", "صندوق النقد", "رأس الحكمة", "العاصمة الإدارية", "الكهرباء", "تخفيف الأحمال",
    "التموين", "السكر", "البنزين", "السولار"
]

KEYTERMS_GROUPED = [
    # Multi-word Tech & Hardware
    "RTX 5070", "packet loss", "VRAM", "Discord", "Minecraft", "Counter-Strike", "League of Legends",
    "كارت شاشة", "باكيت لوس", "جي تي إيه",
    # Multi-word Football Entities & Tournaments
    "النادي الأهلي", "نادي الزمالك", "محمد صلاح", "ريال مدريد", "مانشستر سيتي", "دوري أبطال أفريقيا",
    "دوري أبطال أوروبا", "كأس الأمم الأفريقية", "الدوري المصري", "السوبر المصري",
    # Multi-word Movies, Series & Cultural Entities
    "ولاد رزق", "الفيل الأزرق", "كيرة والجن", "بيت الروبي", "تامر حسني", "ماجد الكدواني", "أحمد عز",
    "كريم عبد العزيز", "محمد هنيدي", "أحمد حلمي",
    # Multi-word Music & Rap
    "عمرو دياب", "مروان بابلو", "حمزة نمرة", "مروان موسى", "تامر عاشور", "بهاء سلطان", "حسن شاكوش",
    # Specific Politics, Law & Economy
    "مجلس النواب", "قانون الإيجار القديم", "رئيس الوزراء", "البنك المركزي", "صندوق النقد", "رأس الحكمة",
    "العاصمة الإدارية", "تخفيف الأحمال"
]

CONFIGS = {
    "a_no_keyterms": [],
    "b_current_54": KEYTERMS_54,
    "c_expanded_150": KEYTERMS_150,
    "d_best_of_grouped": KEYTERMS_GROUPED
}

async def transcribe_with_keyterms(client: httpx.AsyncClient, trimmed_bytes: bytes, keyterms: list):
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
        }
        if keyterms:
            job_payload["keyterms_prompt"] = keyterms

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

async def run_config(config_name: str, keyterms: list, clips: list, trimmed_cache: dict, client: httpx.AsyncClient):
    print(f"\n=======================================================")
    print(f"Running Config: {config_name} ({len(keyterms)} keyterms)")
    print(f"=======================================================")
    results = []

    for idx, clip in enumerate(clips, 1):
        cid = clip["id"]
        genre = clip["genre"]
        ref_raw = clip["reference_text"]
        ref_clean = clean_arabic_text(ref_raw)
        trimmed_bytes = trimmed_cache[cid]

        print(f"[{idx:02d}/20] {cid[:28]}...", end=" ", flush=True)
        heard_raw, latency_ms, status = await transcribe_with_keyterms(client, trimmed_bytes, keyterms)

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
    out_csv = os.path.join("audit", f"mgb3_exp2_{config_name}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "genre", "wer", "latency_ms", "status", "ref_clean", "heard_clean", "ref_raw", "heard_raw"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Compute metrics
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
        "config": config_name,
        "keyterms_count": len(keyterms),
        "corpus_wer": overall_wer,
        "clean_wer": clean_wer,
        "num_acc": num_acc,
        "correct_nums": correct_nums,
        "total_nums": total_nums,
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

    summary = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check if user passed specific config as sys.argv[1]
        target_config = sys.argv[1] if len(sys.argv) > 1 else None

        for name, kts in CONFIGS.items():
            if target_config and name != target_config:
                continue
            metrics = await run_config(name, kts, clips, trimmed_cache, client)
            summary.append(metrics)
            print(f"Result for {name}: WER={metrics['corpus_wer']:.2%} | Numbers={metrics['num_acc']:.1%} | p50={metrics['p50_ms']:.0f}ms")
            # Wait 10s between config runs to be gentle on API
            await asyncio.sleep(10.0)

    print("\n" + "=" * 90)
    print("                     EXP 2: KEYTERMS ABLATION SUMMARY")
    print("=" * 90)
    print(f"{'Config':<20} {'Terms':<7} {'Corpus WER':<12} {'Clean WER':<12} {'Numbers':<12} {'p50 Latency'}")
    print("-" * 90)
    for s in summary:
        print(f"{s['config']:<20} {s['keyterms_count']:<7} {s['corpus_wer']:<12.2%} {s['clean_wer']:<12.2%} {s['num_acc']:<12.1%} {s['p50_ms']:.0f}ms")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
