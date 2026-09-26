import sys
import csv
import time
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

import jiwer

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from audit.cleaner import clean_arabic_text
from audit.check_numbers import get_numbers
from bot.ai.assemblyai import assemblyai_client
from bot.arbitration.claim_detector import claim_detector
from bot.arbitration.conflict_detector import conflict_detector
from bot.config import config

logger = logging.getLogger("ScoreTestSession")
DEFAULT_RESULTS_FILE = PROJECT_ROOT / "audit" / "score_results.md"


async def score_session(
    session_dir: Path,
    output_md: Optional[Path] = None,
    pace_delay_sec: float = 2.0
) -> Dict[str, Any]:
    """
    Scores a single test-capture session folder against human annotations in labels_DRAFT.csv / labels.csv:
    1. Reads human labels from CSV.
    2. Filters rows with non-empty correct_text; skips empty ones.
    3. Re-transcribes WAVs with production AssemblyAI settings (with pacing).
    4. Computes WER, Number Accuracy, Topic, Anger, Claim match, and referee conflict trigger.
    5. Writes detailed markdown report to audit/score_results.md.
    6. PRESERVES original CSV unmodified.
    """
    session_path = Path(session_dir)
    if not session_path.exists():
        raise FileNotFoundError(f"Session directory {session_path} does not exist.")

    # Locate labels CSV
    csv_candidates = [session_path / "labels.csv", session_path / "labels_DRAFT.csv"]
    csv_file = next((c for c in csv_candidates if c.exists()), None)
    if not csv_file:
        raise FileNotFoundError(f"No labels CSV found in {session_path}. Expected labels.csv or labels_DRAFT.csv.")

    rows = []
    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    scored_records: List[Dict[str, Any]] = []
    skipped_records: List[Dict[str, Any]] = []

    # Claim pairs map for contradiction check
    claim_pairs: Dict[str, List[Dict[str, Any]]] = {}

    for idx, row in enumerate(rows, start=1):
        clip_id = row.get("clip_id") or f"clip_{idx:03d}"
        wav_fname = row.get("wav_filename", "")
        speaker = row.get("speaker", "unknown")
        correct_text = (row.get("correct_text") or "").strip()

        # Rule 2: Refuse to score rows with EMPTY correct_text
        if not correct_text:
            skipped_records.append({
                "clip_id": clip_id,
                "wav_filename": wav_fname,
                "speaker": speaker,
                "reason": "Empty correct_text (unlabeled by human)"
            })
            continue

        wav_path = session_path / wav_fname
        if not wav_path.exists():
            skipped_records.append({
                "clip_id": clip_id,
                "wav_filename": wav_fname,
                "speaker": speaker,
                "reason": f"WAV file not found on disk ({wav_fname})"
            })
            continue

        wav_bytes = wav_path.read_bytes()

        # Step 1a: Transcribe with production AssemblyAI settings
        raw_asr, stt_ms = await assemblyai_client.transcribe(wav_bytes, speaker_name=speaker)
        raw_asr = raw_asr or ""

        # Pace delay between live API calls
        if pace_delay_sec > 0:
            await asyncio.sleep(pace_delay_sec)

        # Step 1b: Compute WER (jiwer + clean_arabic_text)
        ref_clean = clean_arabic_text(correct_text)
        hyp_clean = clean_arabic_text(raw_asr)

        if not ref_clean:
            wer = 0.0 if not hyp_clean else 1.0
        else:
            wer = float(jiwer.wer(ref_clean, hyp_clean))

        # Number Accuracy calculation
        ref_nums = [val for _, val in get_numbers(ref_clean)]
        hyp_nums = [val for _, val in get_numbers(hyp_clean)]
        num_matches = 0
        hyp_copy = list(hyp_nums)
        for n in ref_nums:
            if n in hyp_copy:
                num_matches += 1
                hyp_copy.remove(n)

        # Step 1c: Classify through real ClaimDetector
        is_claim_detected, parsed, class_ms = await claim_detector.check_claim(raw_asr)
        parsed = parsed or {}

        model_topic = (parsed.get("topic") or "other").strip().lower()
        model_anger = (parsed.get("anger") or "none").strip().lower()
        model_claim_text = parsed.get("claim")

        human_topic = (row.get("topic") or "").strip().lower()
        human_is_claim_raw = (row.get("is_claim") or "").strip().lower()
        human_is_claim = human_is_claim_raw in ("yes", "true", "1")
        human_anger = (row.get("anger") or "none").strip().lower()
        human_loud = (row.get("loud") or "normal").strip().lower()

        # Topic match
        topic_match = bool(human_topic and human_topic == model_topic)

        # Claim match
        claim_match = (is_claim_detected == human_is_claim)

        # Anger match (exact + high vs mild tolerance)
        exact_anger = (model_anger == human_anger)
        both_angry = (model_anger in ("mild", "high") and human_anger in ("mild", "high"))
        anger_match = exact_anger or both_angry
        false_anger = (human_anger in ("none", "") and model_anger in ("mild", "high"))

        record = {
            "clip_id": clip_id,
            "wav_filename": wav_fname,
            "speaker": speaker,
            "loud": human_loud,
            "correct_text": correct_text,
            "ref_clean": ref_clean,
            "asr_text": raw_asr,
            "hyp_clean": hyp_clean,
            "wer": wer,
            "ref_nums": ref_nums,
            "hyp_nums": hyp_nums,
            "num_matches": num_matches,
            "ref_num_count": len(ref_nums),
            "stt_ms": stt_ms,
            "is_claim_detected": is_claim_detected,
            "human_is_claim": human_is_claim,
            "claim_match": claim_match,
            "model_topic": model_topic,
            "human_topic": human_topic,
            "topic_match": topic_match,
            "model_anger": model_anger,
            "human_anger": human_anger,
            "anger_match": anger_match,
            "exact_anger": exact_anger,
            "both_angry": both_angry,
            "false_anger": false_anger,
            "claim_text": model_claim_text,
            "claim_pair": row.get("claim_pair", "").strip()
        }
        scored_records.append(record)

        # Group contradiction pairs if claim_pair column provided
        cp_id = row.get("claim_pair", "").strip()
        if cp_id:
            claim_pairs.setdefault(cp_id, []).append(record)

    # Step 1d: Contradiction pair referee gate firing check
    referee_checks: List[Dict[str, Any]] = []
    for cp_id, pair_records in claim_pairs.items():
        if len(pair_records) >= 2:
            r_a, r_b = pair_records[0], pair_records[1]
            c_a = r_a["claim_text"] or r_a["asr_text"]
            c_b = r_b["claim_text"] or r_b["asr_text"]

            has_conflict, c_data, gate_ms = await conflict_detector.detect_conflict(
                speaker_a=r_a["speaker"],
                claim_a=c_a,
                speaker_b=r_b["speaker"],
                claim_b=c_b
            )
            referee_checks.append({
                "pair_id": cp_id,
                "speaker_a": r_a["speaker"],
                "claim_a": c_a,
                "speaker_b": r_b["speaker"],
                "claim_b": c_b,
                "referee_fired": has_conflict,
                "conflict_data": c_data or {}
            })

    # Aggregate Metrics
    n_scored = len(scored_records)
    macro_wer = (sum(r["wer"] for r in scored_records) / n_scored) if n_scored > 0 else 0.0
    all_refs = [r["ref_clean"] for r in scored_records]
    all_hyps = [r["hyp_clean"] for r in scored_records]
    micro_wer = float(jiwer.wer(all_refs, all_hyps)) if n_scored > 0 else 0.0

    clean_records = [r for r in scored_records if r["loud"] != "loud"]
    loud_records = [r for r in scored_records if r["loud"] == "loud"]
    clean_macro_wer = (sum(r["wer"] for r in clean_records) / len(clean_records)) if clean_records else 0.0
    clean_micro_wer = float(jiwer.wer([r["ref_clean"] for r in clean_records], [r["hyp_clean"] for r in clean_records])) if clean_records else 0.0
    loud_macro_wer = (sum(r["wer"] for r in loud_records) / len(loud_records)) if loud_records else 0.0
    loud_micro_wer = float(jiwer.wer([r["ref_clean"] for r in loud_records], [r["hyp_clean"] for r in loud_records])) if loud_records else 0.0

    total_ref_nums = sum(r["ref_num_count"] for r in scored_records)
    total_matched_nums = sum(r["num_matches"] for r in scored_records)
    num_accuracy = (total_matched_nums / total_ref_nums * 100.0) if total_ref_nums > 0 else 100.0

    topic_matches = sum(1 for r in scored_records if r["topic_match"])
    topic_acc = (topic_matches / n_scored * 100.0) if n_scored > 0 else 0.0

    claim_matches = sum(1 for r in scored_records if r["claim_match"])
    claim_acc = (claim_matches / n_scored * 100.0) if n_scored > 0 else 0.0

    anger_matches = sum(1 for r in scored_records if r["anger_match"])
    anger_acc = (anger_matches / n_scored * 100.0) if n_scored > 0 else 0.0

    human_none_anger = [r for r in scored_records if r["human_anger"] in ("none", "")]
    false_anger_count = sum(1 for r in human_none_anger if r["false_anger"])
    false_anger_rate = (false_anger_count / len(human_none_anger) * 100.0) if human_none_anger else 0.0

    summary = {
        "session_folder": session_path.name,
        "labels_file": csv_file.name,
        "total_rows": len(rows),
        "scored_count": n_scored,
        "skipped_count": len(skipped_records),
        "overall_wer": micro_wer,
        "micro_wer": micro_wer,
        "macro_wer": macro_wer,
        "clean_wer": clean_micro_wer,
        "clean_micro_wer": clean_micro_wer,
        "clean_macro_wer": clean_macro_wer,
        "loud_wer": loud_micro_wer,
        "loud_micro_wer": loud_micro_wer,
        "loud_macro_wer": loud_macro_wer,
        "total_ref_numbers": total_ref_nums,
        "matched_numbers": total_matched_nums,
        "number_accuracy_pct": num_accuracy,
        "topic_accuracy_pct": topic_acc,
        "claim_agreement_pct": claim_acc,
        "anger_agreement_pct": anger_acc,
        "false_anger_rate_pct": false_anger_rate,
        "referee_pairs_evaluated": len(referee_checks),
        "referee_pairs_fired": sum(1 for p in referee_checks if p["referee_fired"]),
        "scored_records": scored_records,
        "skipped_records": skipped_records,
        "referee_checks": referee_checks
    }

    # Step 3: Render audit/score_results.md
    out_file = output_md if output_md else DEFAULT_RESULTS_FILE
    out_file.parent.mkdir(parents=True, exist_ok=True)
    md_content = render_markdown_report(summary)
    out_file.write_text(md_content, encoding="utf-8")
    logger.info(f"✅ Generated Step 9 evaluation report: {out_file}")

    return summary


def render_markdown_report(summary: Dict[str, Any]) -> str:
    """Renders the comprehensive evaluation markdown report."""
    md = []
    md.append(f"# Step 9: Captured Test Session Scoring Report\n")
    md.append(f"**Session Folder:** `{summary['session_folder']}`  ")
    md.append(f"**Source Labels File:** `{summary['labels_file']}`  ")
    md.append(f"**Evaluation Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"**STT Engine:** AssemblyAI Universal-3.5 Pro (Native Code-Switching)  ")
    md.append(f"**Epistemic Engine:** Groq LPU (`{config.GROQ_MODEL}`)  \n")

    md.append("## 1. Executive Metric Summary\n")
    md.append("| Metric | Result | Target Benchmark | Status |")
    md.append("|---|---|---|---|")
    md.append(f"| **Micro WER (Corpus)** | **{summary['micro_wer'] * 100:.2f}%** | Beat 30.8% baseline | {'✅ PASS' if summary['micro_wer'] < 0.308 else '⚠️ REVIEW'} |")
    md.append(f"| **Macro WER (Clip Avg)** | **{summary['macro_wer'] * 100:.2f}%** | Informational | — |")
    md.append(f"| **Clean Audio Micro WER** | **{summary['clean_micro_wer'] * 100:.2f}%** | Beat 25.1% baseline | {'✅ PASS' if summary['clean_micro_wer'] < 0.251 else '⚠️ REVIEW'} |")
    md.append(f"| **Clean Audio Macro WER** | **{summary['clean_macro_wer'] * 100:.2f}%** | Informational | — |")
    md.append(f"| **Number Accuracy** | **{summary['number_accuracy_pct']:.1f}%** ({summary['matched_numbers']}/{summary['total_ref_numbers']}) | ≥ 90% | {'✅ PASS' if summary['number_accuracy_pct'] >= 90.0 else '⚠️ REVIEW'} |")
    md.append(f"| **Topic Classification** | **{summary['topic_accuracy_pct']:.1f}%** | ≥ 80% | {'✅ PASS' if summary['topic_accuracy_pct'] >= 80.0 else '⚠️ REVIEW'} |")
    md.append(f"| **Claim Agreement** | **{summary['claim_agreement_pct']:.1f}%** | ≥ 75% | {'✅ PASS' if summary['claim_agreement_pct'] >= 75.0 else '⚠️ REVIEW'} |")
    md.append(f"| **Anger Agreement** | **{summary['anger_agreement_pct']:.1f}%** | Tolerance (mild/high) | {'✅ PASS' if summary['anger_agreement_pct'] >= 70.0 else '⚠️ REVIEW'} |")
    md.append(f"| **False-Anger Rate** | **{summary['false_anger_rate_pct']:.1f}%** | ≤ 15% | {'✅ PASS' if summary['false_anger_rate_pct'] <= 15.0 else '⚠️ REVIEW'} |")
    md.append(f"| **Scored Clips** | **{summary['scored_count']}** | Non-empty reference | ✅ COMPLETE |")
    md.append(f"| **Skipped Clips** | **{summary['skipped_count']}** | Empty reference | ℹ️ EXCLUDED |\n")

    # Contradiction Pairs section
    if summary["referee_checks"]:
        md.append("## 2. Contradiction Pairs & Referee Gate Triggers\n")
        md.append("| Pair ID | Speaker A | Claim A | Speaker B | Claim B | Referee Triggered? |")
        md.append("|---|---|---|---|---|---|")
        for p in summary["referee_checks"]:
            trig_icon = "⚔️ **YES (Offer Fired)**" if p["referee_fired"] else "🛑 NO (Filtered/Suppressed)"
            md.append(f"| `{p['pair_id']}` | {p['speaker_a']} | {p['claim_a']} | {p['speaker_b']} | {p['claim_b']} | {trig_icon} |")
        md.append("\n")

    # Full Per-Clip Table
    md.append("## 3. Detailed Per-Clip Scoring Table\n")
    md.append("| Clip ID | Speaker | Loud | WER | Human Reference (`correct_text`) | AssemblyAI Raw (`asr_text`) | Topic (Pred/True) | Claim (Pred/True) | Anger (Pred/True) |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in summary["scored_records"]:
        topic_str = f"{r['model_topic']} / {r['human_topic'] or '-'}"
        claim_str = f"{'Yes' if r['is_claim_detected'] else 'No'} / {'Yes' if r['human_is_claim'] else 'No'}"
        anger_str = f"{r['model_anger']} / {r['human_anger'] or '-'}"
        md.append(
            f"| `{r['clip_id']}` | {r['speaker']} | {r['loud']} | **{r['wer']*100:.1f}%** | "
            f"{r['correct_text']} | {r['asr_text']} | {topic_str} | {claim_str} | {anger_str} |"
        )
    md.append("\n")

    # Skipped Clips Table
    if summary["skipped_records"]:
        md.append("## 4. Skipped Clips (Unlabeled by Human)\n")
        md.append("| Clip ID | Filename | Speaker | Reason |")
        md.append("|---|---|---|---|")
        for s in summary["skipped_records"]:
            md.append(f"| `{s['clip_id']}` | `{s['wav_filename']}` | {s['speaker']} | {s['reason']} |")
        md.append("\n")

    return "\n".join(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 9 Captured Test Session Scorer")
    parser.add_argument("session_dir", nargs="?", default=None, help="Path to captured session folder")
    parser.add_argument("--output", "-o", default=None, help="Output markdown path")
    parser.add_argument("--pace", "-p", type=float, default=2.0, help="Pace delay between clips in seconds")
    args = parser.parse_args()

    target = args.session_dir
    if not target:
        # Default: locate latest session directory in recordings/test_session/
        root = PROJECT_ROOT / "recordings" / "test_session"
        sessions = sorted([d for d in root.iterdir() if d.is_dir()])
        if not sessions:
            print(f"❌ No session directories found in {root}.")
            sys.exit(1)
        target = sessions[-1]
        print(f"ℹ️ Auto-selected latest session: {target}")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out_path = Path(args.output) if args.output else DEFAULT_RESULTS_FILE
    result = asyncio.run(score_session(Path(target), output_md=out_path, pace_delay_sec=args.pace))
    print(f"\nReport written to: {out_path}")
