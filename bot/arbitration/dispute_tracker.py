import time
from typing import Callable, Optional, Dict, List, Any, Set
from bot.arbitration.dispute_models import (
    ThreadState,
    ClaimEvent,
    DisputeThread,
    TrackerDecision,
)

FEATURE_WEIGHTS: Dict[str, float] = {
    "repetition": 0.32,
    "speaker_diversity": 0.25,
    "stability": 0.18,
    "checkability": 0.15,
    "escalation": 0.10,
}


class DisputeTracker:
    """
    Pure Python synchronous dispute tracker and finite-state machine.
    Tracks competing claims on proposition families, computes multi-feature
    confidence with missing-feature normalization, and handles decay and eviction.

    Zero network, zero LLM calls, zero I/O, zero awaits.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        decay_seconds: float = 150.0,
        max_threads: int = 8,
        offer_threshold: float = 0.72,
    ):
        self.clock: Callable[[], float] = clock
        self.decay_seconds: float = float(decay_seconds)
        self.max_threads: int = int(max_threads)
        self.offer_threshold: float = float(offer_threshold)
        self.threads: Dict[str, DisputeThread] = {}
        self._thread_counter: int = 0

    def _next_thread_id(self) -> str:
        self._thread_counter += 1
        return f"th_{self._thread_counter:04d}"

    def get_thread(self, proposition_key: str) -> Optional[DisputeThread]:
        """Lookup a thread by normalized proposition family key."""
        return self.threads.get(proposition_key)

    def has_conflict(self, proposition_key: str) -> bool:
        """Returns True if proposition key exists and has at least two competing sides."""
        thread = self.get_thread(proposition_key)
        return bool(thread and thread.is_conflict)

    def get_conflict_threads(self) -> List[DisputeThread]:
        """Returns all threads that currently represent competing positions."""
        return [t for t in self.threads.values() if t.is_conflict]

    def _evict_if_needed(self) -> Optional[DisputeThread]:
        """
        Evict a thread if at max capacity (max_threads).
        Priority:
          1. Oldest EXPIRED or DECAY first (sorted by last_activity ascending)
          2. Lowest-score WATCHING (sorted by peak_score ascending, then last_activity)
          3. Lowest-score TRACKING (if not offered)
          4. Never evict OFFERED.
        """
        if len(self.threads) < self.max_threads:
            return None

        # 1. Oldest EXPIRED or DECAY
        expired_or_decay = [
            t for t in self.threads.values()
            if t.state in (ThreadState.EXPIRED, ThreadState.DECAY)
        ]
        if expired_or_decay:
            expired_or_decay.sort(key=lambda t: t.last_activity)
            victim = expired_or_decay[0]
            del self.threads[victim.proposition_key]
            return victim

        # 2. Lowest-score WATCHING
        watching = [
            t for t in self.threads.values()
            if t.state == ThreadState.WATCHING and not t.offered
        ]
        if watching:
            watching.sort(key=lambda t: (t.peak_score, t.last_activity))
            victim = watching[0]
            del self.threads[victim.proposition_key]
            return victim

        # 3. Lowest-score non-offered TRACKING
        tracking = [
            t for t in self.threads.values()
            if t.state == ThreadState.TRACKING and not t.offered
        ]
        if tracking:
            tracking.sort(key=lambda t: (t.peak_score, t.last_activity))
            victim = tracking[0]
            del self.threads[victim.proposition_key]
            return victim

        # Never evict OFFERED
        return None

    def compute_confidence(
        self,
        thread: DisputeThread,
        event: Optional[ClaimEvent] = None,
        custom_features: Optional[Dict[str, Optional[float]]] = None,
    ) -> float:
        """
        Computes dispute confidence score:
          C = weighted(repetition 0.32, speaker-diversity 0.25, stability 0.18,
                       checkability 0.15, escalation 0.10)
        with missing-feature normalization (unknown/missing features are excluded
        from both numerator and denominator, NOT zeroed).
        """
        features: Dict[str, Optional[float]] = {}

        if custom_features is not None:
            # Map aliases and copy
            for k, v in custom_features.items():
                norm_k = k.replace("-", "_")
                features[norm_k] = v
        else:
            # Automatic computation from thread & event
            # 1. Repetition: how many times competing claims were reiterated
            competing_events = len(thread.events)
            if competing_events >= 4:
                rep_score = 1.0
            elif competing_events == 3:
                rep_score = 0.65
            elif competing_events == 2:
                rep_score = 0.35
            else:
                rep_score = 0.0
            features["repetition"] = rep_score

            # 2. Speaker Diversity
            distinct_spks = thread.distinct_speakers
            total_speakers = len(distinct_spks)
            active_sides = [s for s in thread.sides.values() if len(s) > 0]
            min_spk_per_side = min((len(s) for s in active_sides), default=0)

            if total_speakers <= 1:
                # Single speaker repeating alone
                spk_score = 0.0
            elif min_spk_per_side >= 2:
                # >=2 distinct speakers per side
                spk_score = 1.0
            elif total_speakers >= 3:
                spk_score = 0.65
            else:
                # 1 speaker vs 1 speaker
                spk_score = 0.35
            features["speaker_diversity"] = spk_score

            # 3. Check for caller-provided stability, checkability, escalation in event
            if event and event.features:
                for feat in ("stability", "checkability", "escalation"):
                    if feat in event.features:
                        features[feat] = event.features[feat]

        # Calculate weighted sum with missing-feature normalization
        numerator = 0.0
        denominator = 0.0

        for feat_name, weight in FEATURE_WEIGHTS.items():
            val = features.get(feat_name)
            if val is not None:
                # Feature is known and present
                clamped_val = max(0.0, min(1.0, float(val)))
                numerator += weight * clamped_val
                denominator += weight

        if denominator <= 0.0:
            return 0.0

        return numerator / denominator

    def ingest(self, event: ClaimEvent) -> TrackerDecision:
        """
        Pure synchronous ingestion of a claim event.
        Routes by proposition_key. Updates FSM states and evaluates offer eligibility.
        """
        now = self.clock()
        prop_key = (event.proposition_key or "").strip()
        val_key = (event.value_key or "").strip().lower()

        if not prop_key or not val_key:
            return TrackerDecision(
                action="none",
                thread_id=None,
                state=None,
                confidence=0.0,
                reason="non_claim_event",
                thread=None,
            )

        thread = self.threads.get(prop_key)

        if thread is None:
            # Evict if capacity reached before creating new thread
            self._evict_if_needed()

            thread_id = self._next_thread_id()
            thread = DisputeThread(
                thread_id=thread_id,
                proposition_key=prop_key,
                state=ThreadState.WATCHING,
                sides={val_key: {event.speaker_id}},
                events=[event],
                created_at=now,
                last_activity=now,
                peak_score=0.0,
                offered=False,
            )
            self.threads[prop_key] = thread
            return TrackerDecision(
                action="watching",
                thread_id=thread.thread_id,
                state=thread.state,
                confidence=0.0,
                reason="first_claim_watching",
                thread=thread,
            )

        # Thread exists: update activity and record event
        thread.last_activity = now
        thread.events.append(event)

        # Revive thread if it had decayed or expired
        if thread.state in (ThreadState.DECAY, ThreadState.EXPIRED):
            thread.state = ThreadState.TRACKING if thread.is_conflict else ThreadState.WATCHING

        # Record speaker in sides
        if val_key not in thread.sides:
            thread.sides[val_key] = set()
        thread.sides[val_key].add(event.speaker_id)

        # Evaluate sides
        active_sides = [spks for spks in thread.sides.values() if len(spks) > 0]

        if len(active_sides) <= 1:
            # Same side / agreement (both say 16GB) -> NO conflict
            thread.state = ThreadState.WATCHING
            return TrackerDecision(
                action="none",
                thread_id=thread.thread_id,
                state=thread.state,
                confidence=0.0,
                reason="agreement_same_side",
                thread=thread,
            )

        # Competing values exist (at least 2 sides)
        min_speakers_per_side = min(len(s) for s in active_sides)
        is_multi_speaker = min_speakers_per_side >= 2
        is_repeated = len(thread.events) >= 3

        if is_repeated or is_multi_speaker:
            # Offer eligibility criteria met -> transition to TRACKING and compute confidence
            thread.state = ThreadState.TRACKING
            c_score = self.compute_confidence(thread, event)
            thread.peak_score = max(thread.peak_score, c_score)

            if not thread.offered and c_score >= self.offer_threshold:
                # C >= 0.72 -> PEAK -> decision "request_offer" (OFFERED)
                thread.state = ThreadState.OFFERED
                thread.offered = True
                return TrackerDecision(
                    action="request_offer",
                    thread_id=thread.thread_id,
                    state=thread.state,
                    confidence=c_score,
                    reason="offer_threshold_reached",
                    thread=thread,
                )
            else:
                return TrackerDecision(
                    action="tracking",
                    thread_id=thread.thread_id,
                    state=thread.state,
                    confidence=c_score,
                    reason="tracking_below_threshold" if not thread.offered else "already_offered",
                    thread=thread,
                )
        else:
            # First incompatible pair: watching, not yet repeated and not yet multi-speaker
            thread.state = ThreadState.WATCHING
            return TrackerDecision(
                action="watching",
                thread_id=thread.thread_id,
                state=thread.state,
                confidence=0.0,
                reason="first_incompatible_pair_watching",
                thread=thread,
            )

    def tick(self) -> List[TrackerDecision]:
        """
        Decay/expiry sweep using current clock.
        Sweeps all active threads against decay_seconds.
        """
        now = self.clock()
        decisions: List[TrackerDecision] = []

        for thread in list(self.threads.values()):
            elapsed = now - thread.last_activity
            if elapsed > self.decay_seconds:
                if thread.state != ThreadState.EXPIRED:
                    thread.state = ThreadState.EXPIRED
                    decisions.append(
                        TrackerDecision(
                            action="expired",
                            thread_id=thread.thread_id,
                            state=thread.state,
                            confidence=thread.peak_score,
                            reason="inactivity_exceeded_decay_seconds",
                            thread=thread,
                        )
                    )
            elif elapsed > (self.decay_seconds * 0.6):
                if thread.state in (ThreadState.WATCHING, ThreadState.TRACKING):
                    thread.state = ThreadState.DECAY
                    decisions.append(
                        TrackerDecision(
                            action="decay",
                            thread_id=thread.thread_id,
                            state=thread.state,
                            confidence=thread.peak_score,
                            reason="inactivity_decay",
                            thread=thread,
                        )
                    )

        return decisions

    def snapshot(self) -> Dict[str, Any]:
        """
        Exports tracker state to a plain dictionary (no pickled objects).
        Safe for JSON serialization.
        """
        return {
            "decay_seconds": self.decay_seconds,
            "max_threads": self.max_threads,
            "offer_threshold": self.offer_threshold,
            "thread_counter": self._thread_counter,
            "threads": {
                prop_key: {
                    "thread_id": t.thread_id,
                    "proposition_key": t.proposition_key,
                    "state": str(t.state.value),
                    "sides": {k: sorted(list(v)) for k, v in t.sides.items()},
                    "events": [
                        {
                            "event_id": e.event_id,
                            "timestamp": e.timestamp,
                            "speaker_id": e.speaker_id,
                            "proposition_key": e.proposition_key,
                            "value_key": e.value_key,
                            "confidence": e.confidence,
                            "text": e.text,
                            "features": e.features,
                            "metadata": e.metadata,
                        }
                        for e in t.events
                    ],
                    "created_at": t.created_at,
                    "last_activity": t.last_activity,
                    "peak_score": t.peak_score,
                    "offered": t.offered,
                }
                for prop_key, t in self.threads.items()
            },
        }

    def restore(self, data: Dict[str, Any]) -> None:
        """
        Restores tracker state from a plain dictionary.
        """
        self.decay_seconds = float(data.get("decay_seconds", self.decay_seconds))
        self.max_threads = int(data.get("max_threads", self.max_threads))
        self.offer_threshold = float(data.get("offer_threshold", self.offer_threshold))
        self._thread_counter = int(data.get("thread_counter", 0))
        self.threads.clear()

        threads_data = data.get("threads", {})
        for prop_key, td in threads_data.items():
            sides = {k: set(v) for k, v in td.get("sides", {}).items()}
            events = [
                ClaimEvent(
                    event_id=ed["event_id"],
                    timestamp=float(ed["timestamp"]),
                    speaker_id=ed["speaker_id"],
                    proposition_key=ed["proposition_key"],
                    value_key=ed["value_key"],
                    confidence=float(ed["confidence"]),
                    text=ed["text"],
                    features=ed.get("features"),
                    metadata=ed.get("metadata"),
                )
                for ed in td.get("events", [])
            ]
            thread = DisputeThread(
                thread_id=td["thread_id"],
                proposition_key=td["proposition_key"],
                state=ThreadState(td["state"]),
                sides=sides,
                events=events,
                created_at=float(td.get("created_at", 0.0)),
                last_activity=float(td.get("last_activity", 0.0)),
                peak_score=float(td.get("peak_score", 0.0)),
                offered=bool(td.get("offered", False)),
            )
            self.threads[prop_key] = thread
