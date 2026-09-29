import csv
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from bot.config import PROJECT_ROOT

logger = logging.getLogger("MigrateRecordings")

DEFAULT_TARGET_DIR = PROJECT_ROOT / "recordings" / "test_session"


def migrate_recordings_directory(
    target_dir: Optional[Path] = None,
    gap_seconds: float = 600.0
) -> Dict[str, Any]:
    """
    Splits stacked clips in target_dir into per-session folders by timestamp.
    Session boundary: gap > gap_seconds (default 10 minutes / 600s) between consecutive clips.
    Moves each WAV together with its log line and generates a separate labels_DRAFT.csv per folder.
    Preserves pre-existing human labels untouched.
    Deletes nothing that cannot be attributed.
    """
    root = Path(target_dir) if target_dir else DEFAULT_TARGET_DIR
    if not root.exists():
        logger.info(f"Directory {root} does not exist. Nothing to migrate.")
        return {
            "status": "empty",
            "session_count": 0,
            "session_folders": [],
            "preserved_labels_sessions": [],
            "unattributed_files": []
        }

    # 1. Identify direct files (ignore subdirectories)
    direct_files = [f for f in root.iterdir() if f.is_file()]
    wav_files = {f.name: f for f in direct_files if f.suffix.lower() == ".wav"}
    log_file = root / "session_log.jsonl"
    csv_candidates = [root / "labels_DRAFT.csv", root / "labels.csv"]

    if not wav_files and not log_file.exists():
        logger.info(f"No direct stacked WAVs or logs in {root}.")
        return {
            "status": "no_stacked_clips",
            "session_count": 0,
            "session_folders": [d.name for d in root.iterdir() if d.is_dir()],
            "preserved_labels_sessions": [],
            "unattributed_files": [f.name for f in direct_files]
        }

    # 2. Extract existing human annotations from root CSV if present
    existing_human_labels: Dict[str, Dict[str, str]] = {}
    for candidate in csv_candidates:
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        fname = row.get("wav_filename", "")
                        if fname:
                            # Preserve human columns if present
                            existing_human_labels[fname] = {
                                "correct_text": row.get("correct_text", ""),
                                "topic": row.get("topic", ""),
                                "is_claim": row.get("is_claim", ""),
                                "anger": row.get("anger", ""),
                                "loud": row.get("loud", "")
                            }
            except Exception as e:
                logger.warning(f"Could not read annotations from {candidate}: {e}")

    # 3. Parse log lines from session_log.jsonl
    log_entries: Dict[str, Dict[str, Any]] = {}
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    fname = entry.get("wav_filename", "")
                    if fname:
                        log_entries[fname] = entry
                except json.JSONDecodeError:
                    continue

    # 4. Construct clip metadata list
    clips = []
    unattributed_files = []

    for fname, wav_path in wav_files.items():
        if fname in log_entries:
            entry = log_entries[fname]
            raw_ts = float(entry.get("timestamp", wav_path.stat().st_mtime))
            ts = raw_ts / 1000.0 if raw_ts > 1e11 else raw_ts
        else:
            # Fallback: extract timestamp from filename prefix or stat
            try:
                prefix = fname.split("_")[0]
                raw_ts = float(prefix) if prefix.isdigit() else wav_path.stat().st_mtime
                ts = raw_ts / 1000.0 if raw_ts > 1e11 else raw_ts
            except Exception:
                ts = wav_path.stat().st_mtime

            entry = {
                "timestamp": ts,
                "speaker_name": fname.split("_")[1].replace(".wav", "") if "_" in fname else "unknown",
                "wav_filename": fname,
                "asr_text": "",
                "stt_latency_ms": 0.0,
                "ended_by": "unknown"
            }

        clips.append({
            "filename": fname,
            "path": wav_path,
            "timestamp": ts,
            "entry": entry
        })

    # Non-WAV, non-log, non-csv files are unattributed
    known_filenames = set(wav_files.keys()).union({"session_log.jsonl", "labels_DRAFT.csv", "labels.csv"})
    for f in direct_files:
        if f.name not in known_filenames:
            unattributed_files.append(f.name)

    if not clips:
        return {
            "status": "no_clips_to_migrate",
            "session_count": 0,
            "session_folders": [d.name for d in root.iterdir() if d.is_dir()],
            "preserved_labels_sessions": [],
            "unattributed_files": unattributed_files
        }

    # 5. Sort clips chronologically
    clips.sort(key=lambda c: c["timestamp"])

    # 6. Group clips into sessions based on gap > gap_seconds
    sessions: List[List[Dict[str, Any]]] = []
    current_session: List[Dict[str, Any]] = [clips[0]]

    for prev_clip, clip in zip(clips[:-1], clips[1:]):
        if clip["timestamp"] - prev_clip["timestamp"] > gap_seconds:
            sessions.append(current_session)
            current_session = [clip]
        else:
            current_session.append(clip)
    sessions.append(current_session)

    # 7. Migrate each session into its own folder
    created_folders = []
    preserved_label_sessions = []

    fieldnames = [
        "clip_id", "wav_filename", "speaker", "asr_text",
        "correct_text", "topic", "is_claim", "anger", "loud"
    ]

    for s_idx, session_clips in enumerate(sessions):
        start_ts = session_clips[0]["timestamp"]
        dt = datetime.fromtimestamp(start_ts)
        base_folder_name = dt.strftime("%Y-%m-%d_%H%M")
        session_dir = root / base_folder_name

        counter = 1
        while session_dir.exists():
            session_dir = root / f"{base_folder_name}_{counter}"
            counter += 1

        session_dir.mkdir(parents=True, exist_ok=True)
        created_folders.append(session_dir.name)

        session_has_preserved_labels = False
        csv_rows = []

        # Write WAVs & JSONL entries
        session_log_path = session_dir / "session_log.jsonl"
        with open(session_log_path, "w", encoding="utf-8") as log_f:
            for idx, clip in enumerate(session_clips, start=1):
                # Move WAV file
                dest_wav = session_dir / clip["filename"]
                shutil.move(str(clip["path"]), str(dest_wav))

                # Write log line
                log_f.write(json.dumps(clip["entry"], ensure_ascii=False) + "\n")

                # Prepare CSV row
                preserved = existing_human_labels.get(clip["filename"], {})
                has_any_label = any(bool(v.strip()) for v in preserved.values() if isinstance(v, str))
                if has_any_label:
                    session_has_preserved_labels = True

                csv_rows.append({
                    "clip_id": f"clip_{idx:03d}",
                    "wav_filename": clip["filename"],
                    "speaker": clip["entry"].get("speaker_name", ""),
                    "asr_text": clip["entry"].get("asr_text", ""),
                    "correct_text": preserved.get("correct_text", ""),
                    "topic": preserved.get("topic", ""),
                    "is_claim": preserved.get("is_claim", ""),
                    "anger": preserved.get("anger", ""),
                    "loud": preserved.get("loud", "")
                })

        # Write labels_DRAFT.csv
        session_csv_path = session_dir / "labels_DRAFT.csv"
        with open(session_csv_path, "w", newline="", encoding="utf-8-sig") as csv_f:
            writer = csv.DictWriter(csv_f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

        if session_has_preserved_labels:
            preserved_label_sessions.append(session_dir.name)

        logger.info(f"✅ Migrated session {s_idx + 1}/{len(sessions)} -> {session_dir.name} ({len(session_clips)} clips)")

    # 8. Clean up root session_log.jsonl and labels_DRAFT.csv if all clips were migrated
    if log_file.exists():
        log_file.unlink()
    for candidate in csv_candidates:
        if candidate.exists():
            candidate.unlink()

    return {
        "status": "success",
        "session_count": len(sessions),
        "session_folders": created_folders,
        "preserved_labels_sessions": preserved_label_sessions,
        "unattributed_files": unattributed_files
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = migrate_recordings_directory()
    print("\n" + "=" * 60)
    print("=== ONE-TIME RECORDINGS MIGRATION RESULT ===")
    print("=" * 60)
    print(json.dumps(result, indent=2))
