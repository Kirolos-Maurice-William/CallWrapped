import array
import csv
import json
import math
from pathlib import Path
import sys
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.audio.loudness import (
    SpeakerLoudnessBaseline,
    UtteranceLoudnessAccumulator,
    PCM16Adapter,
    rms_to_db,
)
from bot.audio.fusion import fuse_anger


def parse_score_results(path: Path) -> dict:
    """Extracts text-only predictions and human ground truth from score results markdown."""
    preds = {}
    if not path.exists():
        return preds
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 10 and "clip_" in parts[1]:
                cid = parts[1].strip("`")
                ang_parts = [a.strip() for a in parts[9].split("/")]
                pred_ang = ang_parts[0]
                true_ang = ang_parts[1] if len(ang_parts) > 1 else "none"
                preds[cid] = (pred_ang, true_ang)
    return preds


def replay_session_fusion(folder_name: str, score_md_name: str) -> list:
    session_dir = PROJECT_ROOT / "recordings" / "test_session" / folder_name
    score_path = PROJECT_ROOT / "audit" / score_md_name
    score_preds = parse_score_results(score_path)

    labels_map = {}
    labels_csv = session_dir / "labels_DRAFT.csv"
    if not labels_csv.exists():
        return []

    with open(labels_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cid = r.get("clip_id", "").strip()
            if cid:
                labels_map[cid] = r

    baselines = {}
    results = []

    for cid, r in labels_map.items():
        if cid not in score_preds:
            continue
        text_pred, true_human = score_preds[cid]
        spk = r.get("speaker", "").strip()
        wav_name = r.get("wav_filename", "").strip()
        wav_path = session_dir / wav_name
        if not wav_path.exists():
            continue

        if spk not in baselines:
            baselines[spk] = SpeakerLoudnessBaseline(min_calibration_frames=15)

        with wave.open(str(wav_path), "rb") as wf:
            fr = wf.getframerate()
            frames_bytes = wf.readframes(wf.getnframes())

        sample_bytes_len = int(fr * 0.02) * 2  # 20ms signed 16-bit
        acc = UtteranceLoudnessAccumulator()
        acc.begin(f"utt_{cid}", spk)

        for i in range(0, len(frames_bytes), sample_bytes_len):
            chunk = frames_bytes[i:i + sample_bytes_len]
            if len(chunk) < sample_bytes_len:
                continue
            arr = array.array("h")
            arr.frombytes(chunk)
            rms = math.sqrt(sum(s * s for s in arr) / len(arr))
            db = rms_to_db(rms)
            c, t = PCM16Adapter.count_clipped_samples(chunk)
            clipped = (c / t >= 0.01) if t > 0 else False

            # Observe speech frames into baseline
            if rms >= 80:
                baselines[spk].observe_eligible_frame(db, clipped)

            acc.observe_frame_raw(rms=rms, log_rms_db=db, clipped_samples=c, total_samples=t)

        feat = acc.finalize(baselines[spk])
        fusion = fuse_anger(
            raw_anger=text_pred,
            audio_features=feat,
            has_active_dispute=True,
            text=r.get("asr_text", "")
        )

        results.append({
            "session": folder_name,
            "clip_id": cid,
            "speaker": spk,
            "human": true_human,
            "text_only": text_pred,
            "fused": fusion.final_anger,
            "was_loud": feat.was_loud,
            "peak_z": feat.peak_robust_z,
            "spikes": feat.sustained_spike_count,
            "boost": fusion.acoustic_boost,
            "gate": fusion.gate_reason,
            "agree_text": (text_pred == true_human),
            "agree_fused": (fusion.final_anger == true_human),
            "asr_text": r.get("asr_text", "")
        })

    return results


def main():
    sessions = [
        ("Batch 2 (Movies Dispute)", "2026-09-27_1803", "score_results_batch2.md"),
        ("Batch 3 (World Cup Dispute)", "2026-09-27_1806", "score_results_batch3.md"),
        ("Batch 4 (Real Estate Dispute)", "2026-09-27_1808", "score_results_batch4.md"),
    ]

    all_results = []
    for title, folder, score_file in sessions:
        res = replay_session_fusion(folder, score_file)
        all_results.extend(res)

    # Shouted / documented misses subset: clips where human annotated mild/high
    shouted_subset = [r for r in all_results if r["human"] in ("mild", "high") or r["was_loud"]]

    print("=" * 80)
    print("=== FEATURE B, SESSION 4: PROOF AGAINST LABELED SHOUTING CLIPS ===")
    print("=" * 80)
    print()

    print("### 1. Documented Misses & Shouted Clips Table")
    print()
    print("| Session | Clip ID | Speaker | Human | Text-Only | Fused | Was Loud? | Peak Z | Boost | Agree (Text) | Agree (Fused) | Status |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")

    text_correct = 0
    fused_correct = 0
    total_shouted = len(shouted_subset)

    for r in shouted_subset:
        agr_t = "✅ Yes" if r["agree_text"] else "❌ No"
        agr_f = "✅ Yes" if r["agree_fused"] else "❌ No"

        if r["agree_text"]:
            text_correct += 1
        if r["agree_fused"]:
            fused_correct += 1

        if not r["agree_text"] and r["agree_fused"]:
            status = "🚀 LIFT (Recovered Miss)"
        elif r["agree_text"] and r["agree_fused"]:
            status = "✅ Preserved Match"
        elif r["agree_text"] and not r["agree_fused"]:
            status = "⚠️ Regression"
        else:
            status = "— Remaining Miss"

        s_name = r["session"].split("_")[1]
        print(f"| `{s_name}` | `{r['clip_id']}` | {r['speaker']} | **{r['human']}** | {r['text_only']} | **{r['fused']}** | {r['was_loud']} | {r['peak_z']:.2f} | {r['boost']:.2f} | {agr_t} | {agr_f} | {status} |")

    acc_text = (text_correct / total_shouted * 100.0) if total_shouted > 0 else 0.0
    acc_fused = (fused_correct / total_shouted * 100.0) if total_shouted > 0 else 0.0
    lift = acc_fused - acc_text

    print()
    print("### 2. Agreement Metrics Summary on Shouted / Documented Miss Subset")
    print()
    print(f"- **Total Shouted / Elevated Clips Evaluated:** {total_shouted}")
    print(f"- **Text-Only Agreement:** {text_correct}/{total_shouted} ({acc_text:.1f}%)")
    print(f"- **Fused Agreement:** {fused_correct}/{total_shouted} ({acc_fused:.1f}%)")
    print(f"- **Net Agreement Lift:** {lift:+.1f}% ({fused_correct - text_correct:+d} clips)")

    # Overall dataset agreement
    all_total = len(all_results)
    all_text_corr = sum(1 for r in all_results if r["agree_text"])
    all_fused_corr = sum(1 for r in all_results if r["agree_fused"])
    overall_acc_text = (all_text_corr / all_total * 100.0) if all_total > 0 else 0.0
    overall_acc_fused = (all_fused_corr / all_total * 100.0) if all_total > 0 else 0.0

    print()
    print("### 3. Full Corpus Overall Anger Accuracy (All Clips Across Batches 2, 3, 4)")
    print()
    print(f"- **Total Clips:** {all_total}")
    print(f"- **Text-Only Overall Accuracy:** {all_text_corr}/{all_total} ({overall_acc_text:.1f}%)")
    print(f"- **Fused Overall Accuracy:** {all_fused_corr}/{all_total} ({overall_acc_fused:.1f}%)")
    print(f"- **Net Corpus Lift:** {overall_acc_fused - overall_acc_text:+.1f}%")


if __name__ == "__main__":
    main()
