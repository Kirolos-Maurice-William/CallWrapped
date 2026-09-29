import os
import csv
import json
import time
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from bot.config import config, PROJECT_ROOT

logger = logging.getLogger("CaptureMode")

DEFAULT_RECORDINGS_ROOT = PROJECT_ROOT / "recordings" / "test_session"
DEFAULT_RECORDINGS_DIR = DEFAULT_RECORDINGS_ROOT

_active_session_dir: Optional[Path] = None


def get_active_session_dir() -> Optional[Path]:
    """Returns the current in-memory active session directory, if any."""
    return _active_session_dir


def create_session_dir(base_dir: Optional[Path] = None, timestamp: Optional[float] = None) -> Path:
    """
    Creates a new timestamped session directory: recordings/test_session/<YYYY-MM-DD_HHMM>/
    Disambiguates if a directory with the same minute already exists (_1, _2, etc.).
    """
    root = Path(base_dir) if base_dir else DEFAULT_RECORDINGS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    dt = datetime.fromtimestamp(timestamp) if timestamp is not None else datetime.now()
    folder_name = dt.strftime("%Y-%m-%d_%H%M")
    session_dir = root / folder_name

    counter = 1
    while session_dir.exists():
        session_dir = root / f"{folder_name}_{counter}"
        counter += 1

    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def start_capture_session(base_dir: Optional[Path] = None, timestamp: Optional[float] = None) -> Path:
    """
    Starts an isolated capture session:
    - Creates a new timestamped folder recordings/test_session/<YYYY-MM-DD_HHMM>/
    - Sets _active_session_dir to that folder
    - Toggles config.TEST_CAPTURE_MODE = 1
    """
    global _active_session_dir
    session_dir = create_session_dir(base_dir=base_dir, timestamp=timestamp)
    _active_session_dir = session_dir
    config.TEST_CAPTURE_MODE = 1
    logger.info(f"🎙️ [Capture] Started new capture session in: {session_dir}")
    return session_dir


def stop_capture_session(recordings_dir: Optional[Path] = None, grace_seconds: float = 2.0) -> Tuple[Path, Path]:
    """
    Stops the active capture session:
    - Waits for grace_seconds (default 2.0s) so in-flight STT utterances complete and save
    - Sets config.TEST_CAPTURE_MODE = 0
    - Generates labels_DRAFT.csv inside the session folder (including in-flight utterances)
    - Clears _active_session_dir
    - Returns (csv_path, session_dir)
    """
    global _active_session_dir
    session_dir = Path(recordings_dir) if recordings_dir else (_active_session_dir or DEFAULT_RECORDINGS_ROOT)

    if grace_seconds > 0:
        logger.info(f"⏳ [Capture] Stopping capture session with {grace_seconds:.1f}s grace period for in-flight utterances: {session_dir}")
        time.sleep(grace_seconds)

    config.TEST_CAPTURE_MODE = 0
    csv_file = generate_labels_draft_csv(recordings_dir=session_dir)
    _active_session_dir = None
    logger.info(f"🛑 [Capture] Stopped capture session: {session_dir}")
    return csv_file, session_dir


def is_capture_active() -> bool:
    """Returns True if test capture mode is enabled or an active session directory exists."""
    return bool(getattr(config, "TEST_CAPTURE_MODE", 0) or _active_session_dir is not None)


async def finalize_capture_if_active_async() -> Optional[Tuple[Path, Path]]:
    """Non-blocking async version of finalize_capture_if_active via asyncio.to_thread."""
    if is_capture_active():
        return await asyncio.to_thread(stop_capture_session)
    return None


def _clean_speaker_name(speaker_name: str) -> str:
    """Sanitizes speaker name for filesystem safety while preserving Arabic and alphanumeric chars."""
    cleaned = "".join(c for c in speaker_name if c.isalnum() or c in ("-", "_", " ")).strip()
    return cleaned.replace(" ", "_") or "speaker"


def save_captured_utterance_sync(
    speaker_name: str,
    wav_bytes: bytes,
    asr_text: str,
    stt_latency_ms: float,
    ended_by: str = "silence",
    timestamp: Optional[float] = None,
    recordings_dir: Optional[Path] = None,
    audio_features: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Synchronous filesystem save for a finalized utterance:
    - Writes 16kHz mono WAV to <session_dir>/<timestamp>_<speaker>.wav
    - Appends metadata JSON line to <session_dir>/session_log.jsonl
    Returns metadata dict if saved, None if TEST_CAPTURE_MODE is off.
    """
    if not getattr(config, "TEST_CAPTURE_MODE", 0):
        return None

    # Priority: explicit recordings_dir > active session dir > auto-created session dir
    if recordings_dir:
        target_dir = Path(recordings_dir)
    elif _active_session_dir:
        target_dir = _active_session_dir
    else:
        target_dir = start_capture_session()

    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        ts = timestamp if timestamp is not None else time.time()
        safe_speaker = _clean_speaker_name(speaker_name)
        base_filename = f"{int(ts)}_{safe_speaker}.wav"
        wav_path = target_dir / base_filename

        counter = 1
        while wav_path.exists():
            base_filename = f"{int(ts)}_{safe_speaker}_{counter}.wav"
            wav_path = target_dir / base_filename
            counter += 1

        # Write WAV audio
        with open(wav_path, "wb") as f:
            f.write(wav_bytes)

        log_entry = {
            "timestamp": ts,
            "speaker_name": speaker_name,
            "wav_filename": base_filename,
            "asr_text": asr_text,
            "stt_latency_ms": stt_latency_ms,
            "ended_by": ended_by
        }
        if audio_features:
            from dataclasses import is_dataclass, asdict
            log_entry["audio_features"] = asdict(audio_features) if is_dataclass(audio_features) else audio_features

        # Append JSONL log in the session directory ONLY
        log_file = target_dir / "session_log.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        logger.info(f"🎙️ [Capture] Saved utterance clip: {base_filename} ({ended_by}) in {target_dir.name}")
        return log_entry
    except OSError as e:
        logger.error(f"❌ [Capture Failed] Filesystem error saving utterance to {target_dir}: {e}")
        # Degrade gracefully: pipeline continues, utterance recorded as capture_failed
        return {
            "timestamp": timestamp if timestamp is not None else time.time(),
            "speaker_name": speaker_name,
            "wav_filename": None,
            "asr_text": asr_text,
            "stt_latency_ms": stt_latency_ms,
            "ended_by": ended_by,
            "capture_status": "capture_failed",
            "error": str(e)
        }


async def save_captured_utterance_async(
    speaker_name: str,
    wav_bytes: bytes,
    asr_text: str,
    stt_latency_ms: float,
    ended_by: str = "silence",
    timestamp: Optional[float] = None,
    recordings_dir: Optional[Path] = None,
    audio_features: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Non-blocking async wrapper that delegates disk writes to a worker thread
    via asyncio.to_thread, ensuring no event loop or audio stream stalls.
    """
    if not getattr(config, "TEST_CAPTURE_MODE", 0):
        return None

    return await asyncio.to_thread(
        save_captured_utterance_sync,
        speaker_name=speaker_name,
        wav_bytes=wav_bytes,
        asr_text=asr_text,
        stt_latency_ms=stt_latency_ms,
        ended_by=ended_by,
        timestamp=timestamp,
        recordings_dir=recordings_dir,
        audio_features=audio_features
    )


def generate_labels_draft_csv(recordings_dir: Optional[Path] = None) -> Path:
    """
    Generates labels_DRAFT.csv pre-filled from session_log.jsonl INSIDE the session folder:
    Columns: clip_id, wav_filename, speaker, asr_text, correct_text, topic, is_claim, anger, loud
    Pre-fills clip_id, wav_filename, speaker, asr_text from log;
    Preserves existing human annotations if row was already filled.
    """
    target_dir = Path(recordings_dir) if recordings_dir else (_active_session_dir or DEFAULT_RECORDINGS_ROOT)
    target_dir.mkdir(parents=True, exist_ok=True)

    log_file = target_dir / "session_log.jsonl"
    csv_file = target_dir / "labels_DRAFT.csv"

    fieldnames = [
        "clip_id",
        "wav_filename",
        "speaker",
        "asr_text",
        "correct_text",
        "topic",
        "is_claim",
        "anger",
        "loud"
    ]

    # Check for existing human labels to preserve
    existing_human_labels: Dict[str, Dict[str, str]] = {}
    if csv_file.exists():
        try:
            with open(csv_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fname = row.get("wav_filename", "")
                    if fname:
                        existing_human_labels[fname] = {
                            "correct_text": row.get("correct_text", ""),
                            "topic": row.get("topic", ""),
                            "is_claim": row.get("is_claim", ""),
                            "anger": row.get("anger", ""),
                            "loud": row.get("loud", "")
                        }
        except Exception as e:
            logger.warning(f"Failed to read existing labels_DRAFT.csv for preservation: {e}")

    rows = []
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    wav_fname = data.get("wav_filename", "")
                    preserved = existing_human_labels.get(wav_fname, {})
                    rows.append({
                        "clip_id": f"clip_{idx:03d}",
                        "wav_filename": wav_fname,
                        "speaker": data.get("speaker_name", ""),
                        "asr_text": data.get("asr_text", ""),
                        "correct_text": preserved.get("correct_text", ""),
                        "topic": preserved.get("topic", ""),
                        "is_claim": preserved.get("is_claim", ""),
                        "anger": preserved.get("anger", ""),
                        "loud": preserved.get("loud", "")
                    })
                except json.JSONDecodeError:
                    continue

    tmp_csv = csv_file.with_suffix(".csv.tmp")
    with open(tmp_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_csv, csv_file)

    logger.info(f"📋 [Capture] Generated draft labels CSV with {len(rows)} clips: {csv_file}")
    return csv_file
