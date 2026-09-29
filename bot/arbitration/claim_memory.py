import re
import time
from typing import List, Optional
from dataclasses import dataclass, field

# Prefixes to strip for entity normalization
_STRIP_PREFIXES_AR = ["كارت", "لعبة", "فيلم", "مسلسل", "أغنية", "ألبوم"]
_STRIP_ARTICLES = ["ال", "the", "a", "an"]


def canonicalize_entity(raw: Optional[str]) -> str:
    """
    Normalize an entity for comparison: lowercase, strip Arabic/English articles
    and common noun prefixes (كارت، لعبة، فيلم...).
    """
    if not raw:
        return ""
    s = raw.lower().strip()
    # Strip Arabic article ال at the start of each word
    s = re.sub(r'\bال', '', s)
    # Strip English articles
    for art in ["the ", "a ", "an "]:
        if s.startswith(art):
            s = s[len(art):]
    # Strip common Arabic noun prefixes
    for prefix in _STRIP_PREFIXES_AR:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip()


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

    def clear(self):
        """Clears all stored claims."""
        self.claims.clear()

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
        Entity comparison uses canonicalize_entity() for normalized matching.
        """
        now = time.time()
        new_entity_canon = canonicalize_entity(entity)
        new_metric_lower = (metric or "").lower().strip()
        new_words = set(raw_text.lower().split())

        for prior in reversed(self.claims):
            # Must be from a different speaker
            if str(prior.speaker_id) == str(new_speaker_id):
                continue

            # Must be within acceptable conversation timeframe
            if (now - prior.timestamp) > max_age_seconds:
                continue

            prior_entity_canon = canonicalize_entity(prior.entity)
            prior_metric_lower = (prior.metric or "").lower().strip()

            # Direct entity match (canonicalized, e.g. "الكارت RTX 5070" matches "rtx 5070")
            if new_entity_canon and prior_entity_canon:
                if new_entity_canon in prior_entity_canon or prior_entity_canon in new_entity_canon:
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

