import re
from enum import StrEnum
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List, Any
from bot.arbitration.claim_memory import canonicalize_entity, _STRIP_PREFIXES_AR


def normalize_family_entity(raw: Optional[str]) -> str:
    """
    Canonicalizes and normalizes an entity for proposition family keying.
    Strips tatweel, Arabic and English articles (including 'الـ' with tatweel),
    noun prefixes, and redundant spacing.
    """
    if not raw:
        return ""
    s = raw.lower().strip()
    # Strip tatweel/kashida
    s = re.sub(r'[\u0640]', '', s)
    # Strip common noun prefixes
    for prefix in _STRIP_PREFIXES_AR:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Strip Arabic article ال / الـ at word boundary
    s = re.sub(r'\bال[ـ\-_]?', '', s)
    # Strip English articles
    for art in ["the ", "a ", "an "]:
        if s.startswith(art):
            s = s[len(art):]
    # Clean non-alphanumeric leading/trailing artifacts
    s = s.strip(" \t\n\r-_")
    return s


class ThreadState(StrEnum):
    WATCHING = "WATCHING"
    TRACKING = "TRACKING"
    PEAK = "PEAK"
    OFFERED = "OFFERED"
    DECAY = "DECAY"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class PropositionFamily:
    """
    Represents a normalized semantic family of claims.
    The disputed value is intentionally NOT part of the family key,
    allowing opposing values on the same family to form a dispute.
    """
    entity: str
    dimension: str
    temporal_anchor: Optional[str] = None
    value_type: str = "categorical"

    def proposition_key(self) -> str:
        ent = normalize_family_entity(self.entity)
        dim = (self.dimension or "").lower().strip()
        anchor = (self.temporal_anchor or "").lower().strip()
        vtype = (self.value_type or "categorical").lower().strip()
        return f"{ent}|{dim}|{anchor}|{vtype}"


@dataclass(frozen=True)
class ClaimEvent:
    """
    Represents an atomic, immutable claim event emitted by the pipeline.
    """
    event_id: str
    timestamp: float
    speaker_id: str
    proposition_key: str
    value_key: str
    confidence: float
    text: str
    features: Optional[Dict[str, float]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class DisputeThread:
    """
    Mutable state container for an active dispute thread.
    Uses slots for fast synchronous in-memory tracking.
    """
    thread_id: str
    proposition_key: str
    state: ThreadState
    sides: Dict[str, Set[str]] = field(default_factory=dict)
    events: List[ClaimEvent] = field(default_factory=list)
    created_at: float = 0.0
    last_activity: float = 0.0
    peak_score: float = 0.0
    offered: bool = False

    @property
    def is_conflict(self) -> bool:
        """Returns True if there are at least 2 distinct competing sides with speakers."""
        active_sides = [spks for spks in self.sides.values() if len(spks) > 0]
        return len(active_sides) >= 2

    @property
    def distinct_speakers(self) -> Set[str]:
        """Returns all distinct speaker IDs across all sides."""
        result: Set[str] = set()
        for spks in self.sides.values():
            result.update(spks)
        return result


@dataclass
class TrackerDecision:
    """
    Decision produced synchronously by DisputeTracker on ingest or tick.
    """
    action: str  # "watching", "tracking", "request_offer", "expired", "decay", "none"
    thread_id: Optional[str] = None
    state: Optional[ThreadState] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    thread: Optional[DisputeThread] = None
