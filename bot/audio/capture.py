import os
import sys
import csv
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from bot.config import config, PROJECT_ROOT

logger = logging.getLogger("CaptureMode")

DEFAULT_RECORDINGS_DIR = PROJECT_ROOT / "recordings" / "test_session"


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
    recordings_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Synchronous filesystem save for a finalized utterance:
    - Writes 16kHz mono WAV to recordings/test_session/<timestamp>_<speaker>.wav
    - Appends metadata JSON line to recordings/test_session/session_log.jsonl
    Returns metadata dict if saved, None if TEST_CAPTURE_MODE is off.
    """
    if not getattr(config, "TEST_CAPTURE_MODE", 0):
        return None

    target_dir = Path(recordings_dir) if recordings_dir else DEFAULT_RECORDINGS_DIR
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

    # Append JSONL log
    log_file = target_dir / "session_log.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    logger.info(f"🎙️ [Capture] Saved utterance clip: {base_filename} ({ended_by})")
    return log_entry


async def save_captured_utterance_async(
    speaker_name: str,
    wav_bytes: bytes,
    asr_text: str,
    stt_latency_ms: float,
    ended_by: str = "silence",
    timestamp: Optional[float] = None,
    recordings_dir: Optional[Path] = None
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
        recordings_dir=recordings_dir
    )


def generate_labels_draft_csv(recordings_dir: Optional[Path] = None) -> Path:
    """
    Generates recordings/test_session/labels_DRAFT.csv pre-filled from session_log.jsonl:
    Columns: clip_id, wav_filename, speaker, asr_text, correct_text, topic, is_claim, anger, loud
    Pre-fills clip_id, wav_filename, speaker, asr_text from log; human columns remain empty.
    """
    target_dir = Path(recordings_dir) if recordings_dir else DEFAULT_RECORDINGS_DIR
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

    rows = []
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rows.append({
                        "clip_id": f"clip_{idx:03d}",
                        "wav_filename": data.get("wav_filename", ""),
                        "speaker": data.get("speaker_name", ""),
                        "asr_text": data.get("asr_text", ""),
                        "correct_text": "",
                        "topic": "",
                        "is_claim": "",
                        "anger": "",
                        "loud": ""
                    })
                except json.JSONDecodeError:
                    continue

    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"📋 [Capture] Generated draft labels CSV with {len(rows)} clips: {csv_file}")
    return csv_file
