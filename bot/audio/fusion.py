from dataclasses import dataclass
from typing import Optional, Any, Dict, Union

# Egyptian and Arabic frustration cues for text-based arousal correlation
FRUSTRATION_KEYWORDS = (
    "زهقت", "بيعصب", "زبالة", "يا عم", "ياعم", "حرام", "مش معقول", "كفاية",
    "غلط", "كذب", "مش صح", "هبد", "يا ابني", "بطل", "يا نهار", "مفيش الكلام",
    "مجانين", "مجنين", "مش فاهيمن", "مش فاهمين", "مستحيل", "على الطلاق",
    "بلا خيبة", "تعبان", "اقعد بقى", "إيه ده", "ايه ده", "هاتهم وانا هشتريهم"
)


@dataclass(frozen=True)
class FusedAngerResult:
    """Outcome of deterministic acoustic-textual anger fusion."""
    raw_anger: str
    p_text: float
    acoustic_boost: float
    p_fused: float
    final_anger: str
    calibrated: bool
    was_loud: bool
    clip_ratio: float
    gate_reason: str


def has_frustration_cues(text: str = "", raw_anger: str = "none") -> bool:
    """
    Checks if text contains frustration keywords or non-none classifier anger.
    """
    if str(raw_anger).lower() in ("mild", "high"):
        return True
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in FRUSTRATION_KEYWORDS)


def fuse_anger(
    raw_anger: str,
    audio_features: Optional[Union[Dict[str, Any], Any]] = None,
    *,
    has_active_dispute: bool = False,
    text: str = ""
) -> FusedAngerResult:
    """
    Deterministic late fusion of classifier anger and acoustic loudness.

    1. Base text probability:
       none -> 0.0, mild -> 0.5, high -> 0.9
    2. Acoustic boost:
       if was_loud AND calibrated AND clip_ratio < 0.05:
           boost = 0.6 * clamp((peak_z - 2.5) / 2.5, 0.0, 1.0)
    3. Fused probability:
       p_fused = 1.0 - (1.0 - p_text) * (1.0 - boost)
    4. Final label:
       p_fused >= 0.8 -> high, >= 0.45 -> mild, else none.

    GATES (deterministic, authoritative):
    - not calibrated -> boost = 0.0 (no acoustic contribution)
    - clip_ratio >= 0.05 -> boost = 0.0 (no acoustic contribution)
    - was_loud with NO frustration text AND NO active dispute -> boost = 0.0 (excitement guard)
    """
    norm_anger = str(raw_anger or "none").lower().strip()
    if norm_anger == "high":
        p_text = 0.9
    elif norm_anger == "mild":
        p_text = 0.5
    else:
        norm_anger = "none"
        p_text = 0.0

    # Extract audio feature attributes defensively
    if audio_features is None:
        calibrated = False
        was_loud = False
        clip_ratio = 0.0
        peak_z = 0.0
    elif isinstance(audio_features, dict):
        calibrated = bool(audio_features.get("calibrated", False))
        was_loud = bool(audio_features.get("was_loud", False))
        clip_ratio = float(audio_features.get("clip_ratio", 0.0))
        peak_z = float(audio_features.get("peak_robust_z", 0.0))
    else:
        calibrated = bool(getattr(audio_features, "calibrated", False))
        was_loud = bool(getattr(audio_features, "was_loud", False))
        clip_ratio = float(getattr(audio_features, "clip_ratio", 0.0))
        peak_z = float(getattr(audio_features, "peak_robust_z", 0.0))

    # Evaluate deterministic gates in priority order
    if not calibrated:
        boost = 0.0
        gate_reason = "uncalibrated"
    elif clip_ratio >= 0.05:
        boost = 0.0
        gate_reason = "clipping_exceeded"
    elif not was_loud:
        boost = 0.0
        gate_reason = "not_loud"
    else:
        # was_loud is True: evaluate excitement guard
        has_frustration = has_frustration_cues(text=text, raw_anger=norm_anger)
        if not has_frustration and not has_active_dispute:
            boost = 0.0
            gate_reason = "excitement_guard"
        else:
            clamp_val = max(0.0, min(1.0, (peak_z - 2.5) / 2.5))
            boost = round(0.6 * clamp_val, 4)
            gate_reason = "boost_applied"

    p_fused = round(1.0 - (1.0 - p_text) * (1.0 - boost), 4)

    if p_fused >= 0.8:
        final_anger = "high"
    elif p_fused >= 0.45:
        final_anger = "mild"
    else:
        final_anger = "none"

    return FusedAngerResult(
        raw_anger=norm_anger,
        p_text=p_text,
        acoustic_boost=boost,
        p_fused=p_fused,
        final_anger=final_anger,
        calibrated=calibrated,
        was_loud=was_loud,
        clip_ratio=round(clip_ratio, 4),
        gate_reason=gate_reason
    )
