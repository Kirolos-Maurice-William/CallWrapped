import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class StoredClaim:
    claim_id: str
    speaker_name: str
    speaker_id: str
    raw_text: str
    claim_text: str
    entity: Optional[str]
    topic: Optional[str]
    metric: Optional[str]
    timestamp: float = field(default_factory=time.time)


class ClaimMemory:
    """
    Maintains a rolling window of recent verified/candidate claims (up to 30)
    and filters potential conflicts by entity, topic, and metric before calling LLM.
    """

    def __init__(self, capacity: int = 30):
        self.capacity = capacity
        self.claims: List[StoredClaim] = []

    def add_claim(
        self,
        claim_id: str,
        speaker_name: str,
        speaker_id: str,
        raw_text: str,
        claim_text: str,
        entity: Optional[str],
        topic: Optional[str],
        metric: Optional[str]
    ) -> StoredClaim:
        claim = StoredClaim(
            claim_id=claim_id,
            speaker_name=speaker_name,
            speaker_id=str(speaker_id),
            raw_text=raw_text,
            claim_text=claim_text,
            entity=entity,
            topic=topic,
            metric=metric,
            timestamp=time.time()
        )
        self.claims.append(claim)
        if len(self.claims) > self.capacity:
            self.claims.pop(0)
        return claim

    def find_relevant_prior_claim(
        self,
        new_speaker_id: str,
        entity: Optional[str],
        topic: Optional[str],
        metric: Optional[str],
        raw_text: str,
        max_age_seconds: float = 180.0
    ) -> Optional[StoredClaim]:
        """
        Finds the most recent prior claim from a DIFFERENT speaker that shares
        the same entity, topic, metric, or key subjects.
        """
        now = time.time()
        new_entity_lower = (entity or "").lower().strip()
        new_metric_lower = (metric or "").lower().strip()
        new_words = set(raw_text.lower().split())

        for prior in reversed(self.claims):
            # Must be from a different speaker
            if str(prior.speaker_id) == str(new_speaker_id):
                continue

            # Must be within acceptable conversation timeframe
            if (now - prior.timestamp) > max_age_seconds:
                continue

            prior_entity_lower = (prior.entity or "").lower().strip()
            prior_metric_lower = (prior.metric or "").lower().strip()

            # Direct entity match (e.g. both talking about "RTX 5070" or "Minecraft")
            if new_entity_lower and prior_entity_lower:
                if new_entity_lower in prior_entity_lower or prior_entity_lower in new_entity_lower:
                    return prior

            # Metric + Topic match (e.g. both talking about "VRAM" in "hardware")
            if (new_metric_lower and prior_metric_lower and new_metric_lower == prior_metric_lower) and \
               (topic and prior.topic and topic.lower() == prior.topic.lower()):
                return prior

            # Significant keyword overlap (e.g. both mention "5070", "16gb", "vram")
            prior_words = set(prior.raw_text.lower().split())
            shared = new_words.intersection(prior_words)
            # Filter stop words from shared
            meaningful_shared = [w for w in shared if len(w) > 2 and w not in {"the", "and", "that", "this", "with", "have", "from", "مش", "على", "في", "ده", "دي"}]
            if len(meaningful_shared) >= 2:
                return prior

        return None
