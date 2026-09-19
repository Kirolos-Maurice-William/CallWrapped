import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ClaimDetectorService:
    def __init__(self):
        # Rolling recent claims per call_id: list of claims
        self._recent_claims: Dict[str, List[Dict[str, Any]]] = {}

    def register_turn(self, turn: Dict[str, Any], analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluates whether a turn represents a new factual claim or creates a factual disagreement
        with a recently uttered claim.
        """
        call_id = turn.get("call_id")
        speaker_name = turn.get("speaker_name")
        text = turn.get("text", "")
        topic = analysis.get("topic", "other")
        is_claim = analysis.get("is_claim", False)
        is_disagreement = analysis.get("is_disagreement", False)

        if call_id not in self._recent_claims:
            self._recent_claims[call_id] = []

        history = self._recent_claims[call_id]

        # Case 1: Speaker states a factual claim
        current_claim = None
        if is_claim:
            current_claim = {
                "speaker_name": speaker_name,
                "text": text,
                "topic": topic,
                "start_ms": turn.get("start_ms", 0),
                "end_ms": turn.get("end_ms", 0)
            }
            history.append(current_claim)
            if len(history) > 10:
                history.pop(0)

        # Case 2: Speaker disagrees with a previous speaker's recent factual claim or states a conflicting claim
        if history:
            import re
            for prev_claim in reversed(history):
                if prev_claim["speaker_name"] != speaker_name:
                    dispute_found = False
                    # Condition A: Explicit disagreement marker
                    if is_disagreement:
                        dispute_found = True
                    # Condition B: Overlapping subject entities with conflicting asserted details
                    elif current_claim:
                        words_prev = set(re.findall(r'[\w\d]+', prev_claim["text"].lower()))
                        words_curr = set(re.findall(r'[\w\d]+', text.lower()))
                        noise = {'في', 'من', 'على', 'هو', 'هي', 'ده', 'دي', 'the', 'is', 'was', 'in', 'at', 'a', 'an'}
                        common = (words_prev & words_curr) - noise
                        diff_prev = (words_prev - words_curr) - noise
                        diff_curr = (words_curr - words_prev) - noise
                        if len(common) >= 2 and diff_prev and diff_curr:
                            dispute_found = True

                    if dispute_found:
                        logger.info(f"[ClaimDetector] Factual disagreement detected! Claim A: '{prev_claim['text']}', Speaker B: '{text}'")
                        return {
                            "type": "disagreement",
                            "topic": topic if topic != "other" else prev_claim["topic"],
                            "speaker_a": prev_claim["speaker_name"],
                            "claim_a": prev_claim["text"],
                            "speaker_b": speaker_name,
                            "claim_b": text,
                            "start_ms": prev_claim["start_ms"],
                            "end_ms": turn.get("end_ms", 0),
                            "fact_check_required": True
                        }

        # If it's a stand-alone claim without disagreement yet
        if current_claim:
            return {
                "type": "factual_claim",
                "topic": topic,
                "speaker": speaker_name,
                "claim": text,
                "fact_check_required": False
            }

        return None
