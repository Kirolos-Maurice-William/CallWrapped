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
        duration_sec = 0.0
        try:
            import wave
            with wave.open(str(wav_path), "rb") as wf:
                duration_sec = wf.getnframes() / float(wf.getframerate())
        except Exception:
            duration_sec = max(0.5, len(wav_bytes) / 32000.0)

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

        # Topic evaluation (Taxonomy v2: Topical vs Null)
        human_is_null = human_topic in ("null_topic", "null", "none", "بدون موضوع", "")
        model_is_null = model_topic in ("null_topic", "null", "none", "بدون موضوع", "")
        null_match = bool(human_is_null and model_is_null)
        topical_match = bool(
            (not human_is_null) and (not model_is_null) and (
                human_topic == model_topic
                or (human_topic in ("sports", "football") and model_topic in ("sports", "football"))
                or (human_topic in ("personal", "personal_life") and model_topic in ("personal", "personal_life"))
            )
        )
        topic_match = null_match if human_is_null else topical_match

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
            "duration_sec": duration_sec,
            "is_claim_detected": is_claim_detected,
            "human_is_claim": human_is_claim,
            "claim_match": claim_match,
            "model_topic": model_topic,
            "human_topic": human_topic,
            "human_is_null": human_is_null,
            "model_is_null": model_is_null,
            "null_match": null_match,
            "topical_match": topical_match,
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

    # Step 1c-ii: Production Batched Classifier for Topic and Anger
    if scored_records:
        try:
            batch_utterances = [
                {"speaker_name": r["speaker"], "text": r["asr_text"]}
                for r in scored_records
            ]
            batch_results, batch_tokens, batch_ms = await claim_detector.batch_classify(batch_utterances)
            for r, b_res in zip(scored_records, batch_results):
                b_topic = (b_res.get("topic") or "other").strip().lower()
                b_anger = (b_res.get("anger") or "none").strip().lower()
                r["model_topic"] = b_topic
                r["model_anger"] = b_anger
                r["anger_evidence"] = b_res.get("anger_evidence", "")
                # Update matches with production predictions
                h_top = r["human_topic"]
                h_null = r["human_is_null"]
                m_null = b_topic in ("null_topic", "null", "none", "بدون موضوع", "")
                r["model_is_null"] = m_null
                null_match = bool(h_null and m_null)
                topical_match = bool(
                    (not h_null) and (not m_null) and (
                        h_top == b_topic
                        or (h_top in ("sports", "football") and b_topic in ("sports", "football"))
                        or (h_top in ("personal", "personal_life") and b_topic in ("personal", "personal_life"))
                    )
                )
                r["null_match"] = null_match
                r["topical_match"] = topical_match
                r["topic_match"] = null_match if h_null else topical_match

                exact_anger = (b_anger == r["human_anger"])
                both_angry = (b_anger in ("mild", "high") and r["human_anger"] in ("mild", "high"))
                r["anger_match"] = exact_anger or both_angry
                r["exact_anger"] = exact_anger
                r["both_angry"] = both_angry
                r["false_anger"] = (r["human_anger"] in ("none", "") and b_anger in ("mild", "high"))
        except Exception as e:
            logger.warning(f"⚠️ [Batch Analytics] Batched classifier unavailable ({e}), using instant/heuristic.")

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
    num_accuracy = (total_matched_nums / total_ref_nums * 100.0) if total_ref_nums > 0 else 0.0

    topic_matches = sum(1 for r in scored_records if r["topic_match"])
    topic_acc = (topic_matches / n_scored * 100.0) if n_scored > 0 else 0.0

    # Phase 2 metrics: Topical Accuracy vs Null Detection Accuracy
    topical_records = [r for r in scored_records if not r["human_is_null"]]
    null_records = [r for r in scored_records if r["human_is_null"]]

    topical_matches = sum(1 for r in topical_records if r["topical_match"])
    topical_acc = (topical_matches / len(topical_records) * 100.0) if topical_records else 0.0

    null_matches = sum(1 for r in null_records if r["null_match"])
    null_acc = (null_matches / len(null_records) * 100.0) if null_records else 0.0

    # Topical Coverage: % of audio duration classified as topical by model vs human
    total_audio_sec = sum(r.get("duration_sec", 0.0) for r in scored_records)
    human_topical_sec = sum(r.get("duration_sec", 0.0) for r in topical_records)
    model_topical_records = [r for r in scored_records if not r["model_is_null"]]
    model_topical_sec = sum(r.get("duration_sec", 0.0) for r in model_topical_records)

    human_topical_coverage_pct = (human_topical_sec / total_audio_sec * 100.0) if total_audio_sec > 0 else 0.0
    model_topical_coverage_pct = (model_topical_sec / total_audio_sec * 100.0) if total_audio_sec > 0 else 0.0

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
        "clean_count": len(clean_records),
        "loud_count": len(loud_records),
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
        "topical_count": len(topical_records),
        "topical_matches": topical_matches,
        "topical_accuracy_pct": topical_acc,
        "null_count": len(null_records),
        "null_matches": null_matches,
        "null_accuracy_pct": null_acc,
        "topic_accuracy_pct": topic_acc,
        "total_audio_sec": total_audio_sec,
        "human_topical_coverage_pct": human_topical_coverage_pct,
        "model_topical_coverage_pct": model_topical_coverage_pct,
        "claim_agreement_pct": claim_acc,
        "anger_agreement_pct": anger_acc,
        "human_none_anger_count": len(human_none_anger),
        "false_anger_count": false_anger_count,
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

    # 0-denominator safe metrics rendering
    if summary["scored_count"] > 0:
        micro_res = f"**{summary['micro_wer'] * 100:.2f}%**"
        micro_status = "✅ PASS" if summary["micro_wer"] < 0.308 else "⚠️ REVIEW"
        macro_res = f"**{summary['macro_wer'] * 100:.2f}%**"
        macro_status = "—"
        claim_res = f"**{summary['claim_agreement_pct']:.1f}%**"
        claim_status = "✅ PASS" if summary["claim_agreement_pct"] >= 75.0 else "⚠️ REVIEW"
        anger_res = f"**{summary['anger_agreement_pct']:.1f}%**"
        anger_status = "✅ PASS" if summary["anger_agreement_pct"] >= 70.0 else "⚠️ REVIEW"
    else:
        micro_res = "n/a (0 samples)"
        micro_status = "—"
        macro_res = "n/a (0 samples)"
        macro_status = "—"
        claim_res = "n/a (0 samples)"
        claim_status = "—"
        anger_res = "n/a (0 samples)"
        anger_status = "—"

    if summary.get("topical_count", 0) > 0:
        topical_res = f"**{summary['topical_accuracy_pct']:.1f}%** ({summary['topical_matches']}/{summary['topical_count']})"
        topical_status = "✅ PASS" if summary["topical_accuracy_pct"] >= 80.0 else "⚠️ REVIEW"
    else:
        topical_res = "n/a (0 samples)"
        topical_status = "—"

    if summary.get("null_count", 0) > 0:
        null_res = f"**{summary['null_accuracy_pct']:.1f}%** ({summary['null_matches']}/{summary['null_count']})"
        null_status = "✅ PASS" if summary["null_accuracy_pct"] >= 80.0 else "⚠️ REVIEW"
    else:
        null_res = "n/a (0 samples)"
        null_status = "—"

    if summary.get("total_audio_sec", 0) > 0:
        cov_res = f"**Model: {summary['model_topical_coverage_pct']:.1f}% / Human: {summary['human_topical_coverage_pct']:.1f}%**"
        cov_status = "ℹ️ REPORTED"
    else:
        cov_res = "n/a (0 samples)"
        cov_status = "—"

    if summary["clean_count"] > 0:
        clean_micro_res = f"**{summary['clean_micro_wer'] * 100:.2f}%**"
        clean_micro_status = "✅ PASS" if summary["clean_micro_wer"] < 0.251 else "⚠️ REVIEW"
        clean_macro_res = f"**{summary['clean_macro_wer'] * 100:.2f}%**"
        clean_macro_status = "—"
    else:
        clean_micro_res = "n/a (0 samples)"
        clean_micro_status = "—"
        clean_macro_res = "n/a (0 samples)"
        clean_macro_status = "—"

    if summary["total_ref_numbers"] > 0:
        num_res = f"**{summary['number_accuracy_pct']:.1f}%** ({summary['matched_numbers']}/{summary['total_ref_numbers']})"
        num_status = "✅ PASS" if summary["number_accuracy_pct"] >= 90.0 else "⚠️ REVIEW"
    else:
        num_res = "n/a (0 samples)"
        num_status = "—"

    if summary["human_none_anger_count"] > 0:
        fa_res = f"**{summary['false_anger_rate_pct']:.1f}%** ({summary['false_anger_count']}/{summary['human_none_anger_count']})"
        fa_status = "✅ PASS" if summary["false_anger_rate_pct"] <= 15.0 else "⚠️ REVIEW"
    else:
        fa_res = "n/a (0 samples)"
        fa_status = "—"

    md.append(f"| **Micro WER (Corpus)** | {micro_res} | Beat 30.8% baseline | {micro_status} |")
    md.append(f"| **Macro WER (Clip Avg)** | {macro_res} | Informational | {macro_status} |")
    md.append(f"| **Clean Audio Micro WER** | {clean_micro_res} | Beat 25.1% baseline | {clean_micro_status} |")
    md.append(f"| **Clean Audio Macro WER** | {clean_macro_res} | Informational | {clean_macro_status} |")
    md.append(f"| **Number Accuracy** | {num_res} | ≥ 90% | {num_status} |")
    md.append(f"| **Topical Accuracy** | {topical_res} | ≥ 80% (topical rows only) | {topical_status} |")
    md.append(f"| **Null Detection Accuracy** | {null_res} | ≥ 80% (null_topic rows only) | {null_status} |")
    md.append(f"| **Topical Coverage** | {cov_res} | Model vs Human audio share | {cov_status} |")
    md.append(f"| **Claim Agreement** | {claim_res} | ≥ 75% | {claim_status} |")
    md.append(f"| **Anger Agreement** | {anger_res} | Tolerance (mild/high) | {anger_status} |")
    md.append(f"| **False-Anger Rate** | {fa_res} | ≤ 15% | {fa_status} |")
    md.append(f"| **Scored Clips** | **{summary['scored_count']}** | Non-empty reference | ✅ COMPLETE |")
    md.append(f"| **Skipped Clips** | **{summary['skipped_count']}** | Empty reference | ℹ️ EXCLUDED |\n")

    # Contradiction Pairs section
    md.append("## 2. Contradiction Pairs & Referee Gate Triggers\n")
    if summary["referee_checks"]:
        md.append("| Pair ID | Speaker A | Claim A | Speaker B | Claim B | Referee Triggered? |")
        md.append("|---|---|---|---|---|---|")
        for p in summary["referee_checks"]:
            trig_icon = "⚔️ **YES (Offer Fired)**" if p["referee_fired"] else "🛑 NO (Filtered/Suppressed)"
            md.append(f"| `{p['pair_id']}` | {p['speaker_a']} | {p['claim_a']} | {p['speaker_b']} | {p['claim_b']} | {trig_icon} |")
        md.append("\n")
    else:
        md.append("*0 pairs evaluated (no contradiction claim_pair labeled in session).*\n")

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
