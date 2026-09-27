import csv
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from bot.arbitration.dispute_models import (
    PropositionFamily,
    ClaimEvent,
    TrackerDecision,
)
from bot.arbitration.dispute_tracker import DisputeTracker

logger = logging.getLogger("DisputeReplay")


class ReplayClock:
    """Settable deterministic clock satisfying the DisputeTracker clock interface."""

    def __init__(self, initial_time: float = 0.0):
        self._time: float = float(initial_time)

    def set(self, timestamp: float) -> None:
        self._time = float(timestamp)

    def advance(self, seconds: float) -> None:
        self._time += float(seconds)

    def __call__(self) -> float:
        return self._time


def extract_claim_from_row(row: Dict[str, str]) -> Tuple[str, str, float, Dict[str, float]]:
    """
    Extracts proposition_key and value_key deterministically from human labeled row.
    Uses the owner's labels EXACTLY without generating synthetic labels.
    Returns (proposition_key, value_key, confidence, features).
    Non-claims return ("", "", 0.0, features).
    """
    is_claim = (row.get("is_claim") or "").strip().lower() in ("yes", "true", "1")
    topic = (row.get("topic") or "").strip().lower()
    text = (row.get("correct_text") or row.get("asr_text") or "").strip()

    anger_val = (row.get("anger") or "none").strip().lower()
    escalation_val = 1.0 if anger_val == "high" else (0.5 if anger_val == "mild" else 0.0)
    features: Dict[str, float] = {"escalation": escalation_val}

    if not is_claim or topic in ("null_topic", "null", "none", "") or not text:
        return "", "", 0.0, features

    # Domain 1: Football / World Cup dispute
    if topic in ("football", "sports") or any(k in text for k in ["كاس العالم", "كأس العالم", "كاس عالم", "كسر عالم"]):
        family = PropositionFamily("كاس العالم", "winner", "2022")
        prop_key = family.proposition_key()
        t_low = text.lower()

        if "اسبانيا" in t_low or "أسبانيا" in t_low:
            return prop_key, "spain", 0.95, features
        if "استراليا" in t_low or "السرالية" in t_low:
            return prop_key, "australia", 0.95, features
        if "ارجنتين" in t_low or "أرجنتين" in t_low:
            return prop_key, "argentina", 0.95, features
        if "مصر" in t_low:
            return prop_key, "egypt", 0.95, features
        if "برازيل" in t_low or "برزيل" in t_low:
            return prop_key, "brazil", 0.95, features
        if "وليم" in t_low or "ويليام" in t_low:
            return prop_key, "williams", 0.95, features

        return "", "", 0.0, features

    # Domain 2: Movies / Spider-Man memory erasure dispute
    if topic == "movies" or any(k in text for k in ["سبايدر", "سبايدرمان", "سترنج", "ذاكرة", "ذاكرت", "مسح"]):
        family = PropositionFamily("سبايدرمان", "memory_erasure")
        prop_key = family.proposition_key()
        t_low = text.lower()

        if any(w in t_low for w in ["دكتور", "سترنج", "strange"]):
            if any(neg in t_low for neg in ["مش هو", "مش دكتور", "مش الدكتور", "مش هو اللي"]):
                # Negating doctor strange -> asserting spider-man himself
                return prop_key, "spiderman_self", 0.95, features
            return prop_key, "doctor_strange", 0.95, features
        if any(w in t_low for w in ["صاحب", "صديق"]):
            return prop_key, "friend", 0.95, features
        if any(w in t_low for w in ["سبايدر", "نفسه", "هو المسح", "هوالمسح"]):
            return prop_key, "spiderman_self", 0.95, features

        return "", "", 0.0, features

    # Domain 3: Real estate land prices (Batch 4)
    if topic in ("other", "real_estate") and any(k in text for k in ["فدان", "أرض", "سعر", "مليون", "ألف"]):
        family = PropositionFamily("فدان زراعي", "price")
        prop_key = family.proposition_key()
        t_low = text.lower()

        if any(m in t_low for m in ["مليون", "ملايين", "2-3", "تلاتة مليون"]):
            return prop_key, "millions", 0.95, features
        if any(k in t_low for k in ["ألف", "الف", "50", "80", "قيراط"]):
            return prop_key, "thousands", 0.95, features

        return "", "", 0.0, features

    return "", "", 0.0, features


def load_session_events(session_folder: str | Path) -> List[ClaimEvent]:
    """
    Reads session_log.jsonl + labels_DRAFT.csv from a captured session folder
    and converts each clip into a deterministic ClaimEvent.
    """
    folder = Path(session_folder)
    log_path = folder / "session_log.jsonl"
    labels_path = folder / "labels_DRAFT.csv"

    if not labels_path.exists():
        raise FileNotFoundError(f"labels_DRAFT.csv not found in {session_folder}")

    # Map wav_filename -> timestamp from session_log.jsonl
    timestamps: Dict[str, float] = {}
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    wname = data.get("wav_filename")
                    ts = data.get("timestamp")
                    if wname and ts is not None:
                        timestamps[wname] = float(ts)
                except Exception as e:
                    logger.warning(f"Skipping malformed session_log.jsonl line: {e}")
                    continue

    events: List[ClaimEvent] = []
    current_time = 0.0
    last_time: Optional[float] = None

    with open(labels_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            clip_id = row.get("clip_id") or f"clip_{idx:03d}"
            wname = row.get("wav_filename", "").strip()
            speaker = (row.get("speaker") or "unknown").strip()
            correct_text = (row.get("correct_text") or "").strip()
            asr_text = (row.get("asr_text") or "").strip()

            # Skip empty trailing rows
            if not clip_id and not wname and not correct_text and not asr_text:
                continue

            # Determine timestamp
            if wname in timestamps:
                raw_ts = timestamps[wname]
                if last_time is not None and (raw_ts - last_time > 60.0):
                    logger.warning(
                        f"Clamping large replay clock jump from {last_time:.1f}s to {raw_ts:.1f}s "
                        f"(jump of {raw_ts - last_time:.1f}s > 60s) for {wname}"
                    )
                    current_time = last_time + 1.0
                else:
                    current_time = raw_ts
            else:
                current_time = (last_time + 1.0) if last_time is not None else 1.0
            last_time = current_time

            text = correct_text or asr_text
            prop_key, val_key, conf, features = extract_claim_from_row(row)

            event = ClaimEvent(
                event_id=clip_id,
                timestamp=current_time,
                speaker_id=speaker,
                proposition_key=prop_key,
                value_key=val_key,
                confidence=conf,
                text=text,
                features=features,
                metadata={
                    "wav_filename": wname,
                    "topic": row.get("topic", ""),
                    "anger": row.get("anger", ""),
                    "loud": row.get("loud", ""),
                    "is_claim": row.get("is_claim", ""),
                },
            )
            events.append(event)

    return events


def replay_session(
    events: List[ClaimEvent],
    tracker: Optional[DisputeTracker] = None,
    shadow_log_path: Optional[str | Path] = None,
) -> Tuple[DisputeTracker, List[TrackerDecision]]:
    """
    Feeds events sequentially to DisputeTracker, advancing the clock per event timestamp,
    collecting all decisions and optionally logging to shadow logger JSONL.
    """
    clock = ReplayClock(events[0].timestamp if events else 0.0)

    if tracker is None:
        tracker = DisputeTracker(
            clock=clock,
            decay_seconds=150.0,
            max_threads=8,
            offer_threshold=0.72,
        )
    else:
        tracker.clock = clock

    decisions: List[TrackerDecision] = []

    shadow_file = None
    if shadow_log_path:
        p = Path(shadow_log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        shadow_file = open(p, "a", encoding="utf-8")

    try:
        for ev in events:
            clock.set(ev.timestamp)
            decision = tracker.ingest(ev)
            decisions.append(decision)

            if shadow_file:
                log_entry = {
                    "event_id": ev.event_id,
                    "timestamp": ev.timestamp,
                    "speaker_id": ev.speaker_id,
                    "proposition_key": ev.proposition_key or None,
                    "value_key": ev.value_key or None,
                    "thread_state": str(decision.state.value) if decision.state else "NONE",
                    "action": decision.action,
                    "offer_score": round(float(decision.confidence or 0.0), 4),
                    "reasons": decision.reason,
                }
                shadow_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                shadow_file.flush()
    finally:
        if shadow_file:
            shadow_file.close()

    return tracker, decisions


def format_decision_timeline(events: List[ClaimEvent], decisions: List[TrackerDecision]) -> str:
    """Renders an ASCII / Markdown decision timeline table."""
    lines = [
        "| Event ID | Speaker | Value Key | Anger | State | Action | Confidence | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ev, dec in zip(events, decisions):
        state_str = str(dec.state.value) if dec.state else "—"
        conf_str = f"{dec.confidence:.3f}" if dec.confidence else "0.000"
        val_str = ev.value_key or "—"
        anger_str = (ev.metadata or {}).get("anger", "—") if ev.metadata else "—"
        action_str = f"**{dec.action}**" if dec.action == "request_offer" else dec.action
        lines.append(
            f"| `{ev.event_id}` | {ev.speaker_id} | `{val_str}` | {anger_str} | `{state_str}` | {action_str} | {conf_str} | {dec.reason} |"
        )
    return "\n".join(lines)
