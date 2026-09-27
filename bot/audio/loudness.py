import array
import collections
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging
import math
from pathlib import Path
import statistics
import time
from typing import Optional, List, Union, Sequence, Tuple, Any, Dict

logger = logging.getLogger("LoudnessTracker")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class CalibrationState(str, Enum):
    """Loudness baseline calibration progression states."""
    COLD = "COLD"          # 0 eligible frames
    LEARNING = "LEARNING"  # 1 to 29 eligible frames
    READY = "READY"        # >= 30 eligible frames


class PCM16Adapter:
    """
    Explicit adapter for 16-bit signed little-endian PCM audio (s16le).
    - Format: signed 16-bit integers, range [-32768, 32767].
    - Clipping sample threshold: 0.999 * 32767 = 32734 (|sample| >= 32734).
    - Frame clipping ratio threshold: 0.01 (>= 1% clipped samples marks frame as clipped).
    - Utterance clipping ratio threshold: 0.05 (>= 5% clipped samples invalidates was_loud).
    """
    FORMAT = "s16le"
    BYTES_PER_SAMPLE = 2
    MIN_INT16 = -32768
    MAX_INT16 = 32767
    CLIPPING_SAMPLE_THRESHOLD = 32734  # int(0.999 * 32767)
    FRAME_CLIP_RATIO_THRESHOLD = 0.01
    UTTERANCE_CLIP_RATIO_THRESHOLD = 0.05

    @classmethod
    def count_clipped_samples(cls, samples: Any) -> Tuple[int, int]:
        """
        Counts clipped samples in a PCM buffer or sequence.
        Returns (clipped_samples_count, total_samples_count).
        """
        if samples is None:
            return 0, 0

        if isinstance(samples, (bytes, bytearray)):
            if len(samples) < 2:
                return 0, 0
            arr = array.array('h')
            arr.frombytes(samples)
            total = len(arr)
            thresh = cls.CLIPPING_SAMPLE_THRESHOLD
            clipped = sum(1 for s in arr if s >= thresh or s <= -thresh)
            return clipped, total

        if isinstance(samples, (list, tuple, array.array)):
            total = len(samples)
            if total == 0:
                return 0, 0
            thresh = cls.CLIPPING_SAMPLE_THRESHOLD
            clipped = sum(1 for s in samples if s >= thresh or s <= -thresh)
            return clipped, total

        # Duck typing for numpy ndarray or other sequence types without importing numpy
        try:
            total = len(samples)
            if total == 0:
                return 0, 0
            thresh = cls.CLIPPING_SAMPLE_THRESHOLD
            clipped = sum(1 for s in samples if s >= thresh or s <= -thresh)
            return clipped, total
        except Exception:
            return 0, 0

    @classmethod
    def compute_clip_ratio(cls, samples: Any) -> float:
        """Calculates clip ratio: clipped_samples / total_samples."""
        clipped, total = cls.count_clipped_samples(samples)
        return (clipped / total) if total > 0 else 0.0

    @classmethod
    def is_frame_clipped(cls, samples: Any) -> bool:
        """Returns True if frame clipping ratio >= 0.01."""
        return cls.compute_clip_ratio(samples) >= cls.FRAME_CLIP_RATIO_THRESHOLD


def rms_to_db(rms: float, eps: float = 1e-9) -> float:
    """Computes log-RMS dB: 20 * log10(max(rms, eps))."""
    safe_rms = max(float(rms), eps)
    return 20.0 * math.log10(safe_rms)


class SpeakerLoudnessBaseline:
    """
    Per-speaker robust acoustic loudness baseline.
    - Window: deque(maxlen=1200) of log-RMS dB values.
    - Calibration: COLD -> LEARNING -> READY (>= 30 eligible frames).
    - Update gate: clipped frames and shouts (z >= 2.5) are excluded from baseline.
    - Robust statistics: Median + MAD (scaled by 1.4826).
    """

    def __init__(self, maxlen: int = 1200, min_calibration_frames: int = 30):
        self.history: collections.deque = collections.deque(maxlen=maxlen)
        self.min_calibration_frames = min_calibration_frames
        self._cached_median: Optional[float] = None
        self._cached_mad: Optional[float] = None
        self._dirty: bool = True

    @property
    def state(self) -> CalibrationState:
        n = len(self.history)
        if n == 0:
            return CalibrationState.COLD
        elif n < self.min_calibration_frames:
            return CalibrationState.LEARNING
        else:
            return CalibrationState.READY

    @property
    def baseline_ready(self) -> bool:
        """True when the baseline has accumulated >= min_calibration_frames eligible frames."""
        return len(self.history) >= self.min_calibration_frames

    @property
    def calibrated(self) -> bool:
        """Alias for baseline_ready."""
        return self.baseline_ready

    def _recompute_stats_if_dirty(self) -> None:
        if self._dirty or self._cached_median is None:
            n = len(self.history)
            if n < 1:
                self._cached_median = None
                self._cached_mad = None
            else:
                hist_list = list(self.history)
                med = float(statistics.median(hist_list))
                self._cached_median = med
                mad = float(statistics.median([abs(x - med) for x in hist_list]))
                self._cached_mad = mad
            self._dirty = False

    @property
    def median(self) -> Optional[float]:
        self._recompute_stats_if_dirty()
        return self._cached_median

    @property
    def mad(self) -> Optional[float]:
        self._recompute_stats_if_dirty()
        return self._cached_mad

    def score(self, log_rms_db: float) -> Optional[float]:
        """
        Computes robust z-score: (log_rms_db - median) / (1.4826 * MAD).
        Returns None if baseline is uncalibrated (< 30 eligible frames).
        """
        if not self.baseline_ready:
            return None

        self._recompute_stats_if_dirty()
        med = self._cached_median
        mad = self._cached_mad
        if med is None or mad is None:
            return None

        diff = float(log_rms_db) - med
        denom = 1.4826 * mad
        if denom < 1e-4:
            # Handle perfectly flat baseline without division by zero
            if abs(diff) < 1e-4:
                return 0.0
            return diff / 1e-4

        return diff / denom

    def observe_eligible_frame(
        self,
        log_rms_db: float,
        clipped: Union[bool, float] = False,
        is_loud: Optional[bool] = None
    ) -> bool:
        """
        Appends log_rms_db to baseline history ONLY if frame is not clipped and not flagged loud.
        Update gate ensures a shout never normalizes itself into the baseline.
        Returns True if appended, False if rejected.
        """
        is_clipped = clipped if isinstance(clipped, bool) else (float(clipped) >= PCM16Adapter.FRAME_CLIP_RATIO_THRESHOLD)
        if is_clipped:
            return False

        if is_loud is True:
            return False

        # When calibrated, score against baseline and gate out loud frames (z >= 2.5)
        if self.baseline_ready:
            z = self.score(log_rms_db)
            if z is not None and z >= 2.5:
                return False

        self.history.append(float(log_rms_db))
        self._dirty = True
        return True

    def reset(self) -> None:
        """Clears baseline history and resets calibration."""
        self.history.clear()
        self._cached_median = None
        self._cached_mad = None
        self._dirty = True


@dataclass(frozen=True)
class UtteranceAudioFeatures:
    """Acoustic loudness features extracted from a finalized utterance."""
    frame_count: int
    voiced_frames: int
    p95_log_rms_db: float
    peak_robust_z: float
    sustained_spike_count: int
    clip_ratio: float
    calibrated: bool
    was_loud: bool

    @property
    def baseline_ready(self) -> bool:
        return self.calibrated


class UtteranceLoudnessAccumulator:
    """
    Accumulator for acoustic loudness features over the duration of an active utterance.
    - Finalize produces an immutable UtteranceAudioFeatures dataclass.
    - Resets cleanly on utterance finalization or force-split without touching the speaker baseline.
    """

    def __init__(self, voiced_threshold_rms: float = 80.0):
        self.voiced_threshold_rms = voiced_threshold_rms
        self.utterance_id: Optional[str] = None
        self.speaker_id: Optional[str] = None
        self.is_active: bool = False

        self.frames_log_rms_db: List[float] = []
        self.voiced_frames: int = 0
        self.total_samples: int = 0
        self.clipped_samples: int = 0

    def begin(self, utterance_id: str, speaker_id: str) -> None:
        """Begins accumulating loudness features for a new utterance."""
        self.utterance_id = utterance_id
        self.speaker_id = speaker_id
        self.is_active = True
        self.frames_log_rms_db.clear()
        self.voiced_frames = 0
        self.total_samples = 0
        self.clipped_samples = 0

    def observe_frame(
        self,
        rms: float,
        samples: Any = None,
        *,
        log_rms_db: Optional[float] = None,
        is_db: bool = False
    ) -> None:
        """
        Observes a single frame of audio during an utterance.
        """
        if not self.is_active:
            self.begin(f"utt_{int(time.time()*1000)}", "speaker")

        if log_rms_db is not None:
            db_val = float(log_rms_db)
        elif is_db or (rms < 0.0):
            db_val = float(rms)
        else:
            db_val = rms_to_db(rms)

        self.frames_log_rms_db.append(db_val)

        # Voiced detection: compare with linear threshold or equivalent dB (80 RMS ≈ 38.06 dB)
        if is_db or log_rms_db is not None or rms < 0.0:
            if db_val >= 38.06:
                self.voiced_frames += 1
        else:
            if rms >= self.voiced_threshold_rms:
                self.voiced_frames += 1

        # Clipping accumulation
        if samples is not None:
            if isinstance(samples, (float, int)) and not isinstance(samples, (bytes, bytearray)):
                if isinstance(samples, float) and 0.0 <= samples <= 1.0:
                    nominal_samples = 1000
                    self.clipped_samples += int(samples * nominal_samples)
                    self.total_samples += nominal_samples
                else:
                    self.total_samples += int(samples)
            else:
                c, t = PCM16Adapter.count_clipped_samples(samples)
                self.clipped_samples += c
                self.total_samples += t

    def observe_frame_raw(
        self,
        rms: float,
        log_rms_db: float,
        clipped_samples: int,
        total_samples: int
    ) -> None:
        """
        Optimized inline observation path for receiver.py with pre-calculated values.
        Guaranteed O(1), no conversions, no allocations.
        """
        if not self.is_active:
            self.begin(f"utt_{int(time.time()*1000)}", "speaker")

        self.frames_log_rms_db.append(log_rms_db)
        if rms >= self.voiced_threshold_rms:
            self.voiced_frames += 1
        self.clipped_samples += clipped_samples
        self.total_samples += total_samples

    def finalize(
        self,
        baseline: Optional[SpeakerLoudnessBaseline] = None
    ) -> UtteranceAudioFeatures:
        """
        Finalizes feature computation against the provided speaker baseline and resets the accumulator.
        """
        frame_count = len(self.frames_log_rms_db)
        voiced_frames = self.voiced_frames
        clip_ratio = (self.clipped_samples / self.total_samples) if self.total_samples > 0 else 0.0

        if frame_count == 0:
            p95_db = 0.0
        elif frame_count == 1:
            p95_db = self.frames_log_rms_db[0]
        else:
            sorted_dbs = sorted(self.frames_log_rms_db)
            k = (frame_count - 1) * 0.95
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                p95_db = sorted_dbs[int(k)]
            else:
                p95_db = sorted_dbs[f] * (c - k) + sorted_dbs[c] * (k - f)

        calibrated = bool(baseline and baseline.baseline_ready)
        peak_robust_z = 0.0
        sustained_spike_count = 0

        if calibrated and baseline is not None:
            for db in self.frames_log_rms_db:
                z = baseline.score(db)
                if z is not None:
                    if z > peak_robust_z:
                        peak_robust_z = z
                    if z >= 2.5:
                        sustained_spike_count += 1

        # Definition: calibrated AND peak_z >= 2.5 AND >= 4 spike frames AND clip_ratio < 0.05
        was_loud = bool(
            calibrated
            and (peak_robust_z >= 2.5)
            and (sustained_spike_count >= 4)
            and (clip_ratio < PCM16Adapter.UTTERANCE_CLIP_RATIO_THRESHOLD)
        )

        features = UtteranceAudioFeatures(
            frame_count=frame_count,
            voiced_frames=voiced_frames,
            p95_log_rms_db=round(p95_db, 3),
            peak_robust_z=round(peak_robust_z, 3),
            sustained_spike_count=sustained_spike_count,
            clip_ratio=round(clip_ratio, 4),
            calibrated=calibrated,
            was_loud=was_loud,
        )

        self.reset()
        return features

    def reset(self) -> None:
        """Resets accumulator state for the next utterance."""
        self.frames_log_rms_db.clear()
        self.voiced_frames = 0
        self.total_samples = 0
        self.clipped_samples = 0
        self.is_active = False


def log_loudness_shadow(
    speaker: str,
    features: UtteranceAudioFeatures,
    shadow_path: Optional[Union[str, Path]] = None,
    timestamp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Appends was_loud events to audit/shadow/loudness_shadow.jsonl.
    Only logs when features.was_loud is True.
    """
    if not features or not features.was_loud:
        return None

    now = timestamp if timestamp is not None else time.time()
    sustain_ms = round(features.sustained_spike_count * 20.0, 1)

    record = {
        "timestamp": now,
        "speaker": speaker,
        "z_peak": round(features.peak_robust_z, 3),
        "sustain_ms": sustain_ms,
        "frame_count": features.frame_count,
        "clip_ratio": round(features.clip_ratio, 4),
    }

    path = Path(shadow_path) if shadow_path else (PROJECT_ROOT / "audit" / "shadow" / "loudness_shadow.jsonl")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to append loudness shadow log: {e}")

    return record
