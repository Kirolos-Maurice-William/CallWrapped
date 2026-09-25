import os
import sys
import time
import csv
import json
import asyncio
import numpy as np
import httpx
import jiwer

# Reconfigure stdout to utf-8 for Windows terminal
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("."))

from audit.cleaner import clean_arabic_text
from audit.run_hearing_test import extract_number_values
from audit.exp1_silence_trim import check_numbers_match
from bot.ai.groq import groq_client
from bot.config import config

RESULTS_CSV_EXP3 = os.path.join("audit", "mgb3_exp3_combined_best.csv")
OUT_CSV = os.path.join("audit", "mgb3_exp4_groq_correction.csv")

CORRECTION_SYSTEM_PROMPT = (
    "You are an Egyptian Arabic display-layer speech text polisher.\n"
    "Fix minor phonetic ASR slips in casual Egyptian Arabic speech.\n"
    "CRITICAL RULES:\n"
    "1. NEVER alter, remove, add, or transpose ANY numbers or quantities (e.g., 1, 10, 11, 30, 70, 99, 100, واحد, تلاتين).\n"
    "2. NEVER alter English words or hardware models (e.g. uncertainty, RTX, VRAM, Discord).\n"
    "3. Keep Egyptian vernacular natural; do not translate to Modern Standard Arabic.\n"
    "4. If no obvious typo exists, return the exact original text.\n"
    "5. Return strictly valid JSON: {\"corrected_text\": \"...\"}"
)

async def correct_display_text(raw_asr_text: str) -> tuple[str, bool, str]:
    """
    Applies selective Groq correction with protected spans.
    Guarantees 0 number corruption by validating numbers before and after.
    Returns: (final_text, was_corrected, reason)
    """
    if not raw_asr_text or len(raw_asr_text.strip()) < 3:
        return raw_asr_text, False, "too_short"

    orig_numbers = extract_number_values(clean_arabic_text(raw_asr_text))

    messages = [
        {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
        {"role": "user", "content": f'{{"input_text": "{raw_asr_text}"}}'}
    ]

    try:
        parsed, _, _ = await groq_client.complete_chat(
            messages=messages,
            model=config.GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=150
        )
        if not parsed or not isinstance(parsed, dict):
            return raw_asr_text, False, "empty_response"

        cand_text = parsed.get("corrected_text", "").strip()
        if not cand_text:
            return raw_asr_text, False, "empty_corrected_text"

        # Validation 1: Protected numbers check (Zero number corruption constraint)
        cand_numbers = extract_number_values(clean_arabic_text(cand_text))
        if orig_numbers != cand_numbers:
            return raw_asr_text, False, f"rejected_number_mismatch: {orig_numbers} vs {cand_numbers}"

        # Validation 2: Length sanity check (should not radically shrink or expand)
        orig_words = raw_asr_text.split()
        cand_words = cand_text.split()
        if abs(len(cand_words) - len(orig_words)) > max(2, len(orig_words) * 0.3):
            return raw_asr_text, False, "rejected_length_drift"

        return cand_text, (cand_text != raw_asr_text), "accepted"

    except Exception as e:
        return raw_asr_text, False, f"exception: {str(e)}"


async def main():
    if not os.path.exists(RESULTS_CSV_EXP3):
        print(f"ERROR: {RESULTS_CSV_EXP3} not found. Run EXP 3 first.")
        return

    with open(RESULTS_CSV_EXP3, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} clips from EXP 3 (combined_best).")
    print("Testing Selective Groq Correction for display layer...\n")

    results = []
    number_corruptions = 0
    total_numbers_checked = 0
    total_corrections_made = 0

    for idx, r in enumerate(rows, 1):
        cid = r["id"]
        ref_clean = r["ref_clean"]
        heard_clean = r["heard_clean"]
        heard_raw = r.get("heard_raw", heard_clean)

        orig_wer = float(r["wer"])
        orig_nums = extract_number_values(heard_clean)

        print(f"[{idx:02d}/20] Processing {cid[:28]}...", end=" ", flush=True)

        t0 = time.perf_counter()
        corrected_text, was_corrected, reason = await correct_display_text(heard_raw)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        corrected_clean = clean_arabic_text(corrected_text)
        try:
            new_wer = jiwer.wer(ref_clean, corrected_clean)
        except Exception:
            new_wer = 1.0

        corr_nums = extract_number_values(corrected_clean)

        if orig_nums:
            total_numbers_checked += len(orig_nums)
            if orig_nums != corr_nums:
                number_corruptions += 1
                print(f"CORRUPT NUMS! {orig_nums} -> {corr_nums}")

        if was_corrected:
            total_corrections_made += 1
            delta = new_wer - orig_wer
            print(f"MODIFIED in {elapsed_ms}ms | WER: {orig_wer:.1%} -> {new_wer:.1%} (delta: {delta:+.1%})")
            print(f"   Orig: '{heard_clean}'")
            print(f"   Corr: '{corrected_clean}'")
        else:
            print(f"UNCHANGED ({reason}) in {elapsed_ms}ms | WER: {orig_wer:.1%}")

        results.append({
            "id": cid,
            "genre": r["genre"],
            "ref_clean": ref_clean,
            "heard_clean_orig": heard_clean,
            "heard_clean_corrected": corrected_clean,
            "orig_wer": orig_wer,
            "new_wer": new_wer,
            "was_corrected": was_corrected,
            "reason": reason,
            "orig_nums": json.dumps(orig_nums),
            "corr_nums": json.dumps(corr_nums)
        })

        # Pacing to protect Groq quota
        await asyncio.sleep(1.0)

    # Save CSV
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["id", "genre", "ref_clean", "heard_clean_orig", "heard_clean_corrected", "orig_wer", "new_wer", "was_corrected", "reason", "orig_nums", "corr_nums"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            writer.writerow(res)

    # Overall metrics
    all_refs = [r["ref_clean"] for r in results]
    orig_hyps = [r["heard_clean_orig"] for r in results]
    corr_hyps = [r["heard_clean_corrected"] for r in results]

    orig_overall_wer = jiwer.wer(all_refs, orig_hyps)
    corr_overall_wer = jiwer.wer(all_refs, corr_hyps)

    # Numbers accuracy vs ground truth references
    ref_total_nums = 0
    ref_correct_orig = 0
    ref_correct_corr = 0
    for r in results:
        ref_nums = extract_number_values(r["ref_clean"])
        orig_nums = extract_number_values(r["heard_clean_orig"])
        corr_nums = extract_number_values(r["heard_clean_corrected"])
        if ref_nums:
            ref_total_nums += len(ref_nums)
            ref_correct_orig += check_numbers_match(ref_nums, orig_nums)
            ref_correct_corr += check_numbers_match(ref_nums, corr_nums)

    print("\n" + "=" * 90)
    print("                EXP 4: SELECTIVE GROQ CORRECTION METRICS")
    print("=" * 90)
    print(f"Total Clips Tested:           {len(results)}")
    print(f"Corrections Applied:          {total_corrections_made} of {len(results)} clips")
    print(f"Number Corruptions:           {number_corruptions} (STRICTLY 0 REQUIRED)")
    print(f"Display Corpus WER (Before):  {orig_overall_wer:.2%}")
    print(f"Display Corpus WER (After):   {corr_overall_wer:.2%} (Delta: {corr_overall_wer - orig_overall_wer:+.2%})")
    print(f"Number Accuracy (Before):     {ref_correct_orig}/{ref_total_nums} ({ref_correct_orig/max(1, ref_total_nums):.1%})")
    print(f"Number Accuracy (After):      {ref_correct_corr}/{ref_total_nums} ({ref_correct_corr/max(1, ref_total_nums):.1%})")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
