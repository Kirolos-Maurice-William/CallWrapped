"""
Conversational Pragmatics & Multi-Turn Discourse Trajectory Engine.
Implements interactional sociolinguistics and conversational emotion recognition (CER):
1. Symmetrical Acoustic/Linguistic Entrainment (Mutual Teasing / Roasting).
2. Prosodic & Lexical Rebound (Resolution Window: Greetings, Laughter, Collaborative Shift).
3. Asymmetric SLA: Arousal candidate emission with retrospective resolution
   (friendly_banter vs hostile_escalation vs isolated_shout).
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set

from bot.arbitration.lexicon import analyze_banter, normalize_bilingual_text

logger = logging.getLogger("DiscoursePragmatics")

# ---------------------------------------------------------------------------
# Interactional Sociolinguistic Dictionaries
# ---------------------------------------------------------------------------

REBOUND_GREETING_TOKENS = (
    # Egyptian / Arabic greetings, warmth, and affiliative address
    "ازيك", "ازيك يا", "عامل ايه", "اخبارك", "يا صاحبي", "صاحبي", "اخويا",
    "حبيبي", "يا حبيبي", "منور", "وحشني", "صباح الفل", "مساء الورد",
    "كيفك", "شلونك", "يا بطل", "يا غالي",
    # English greetings, camaraderie, and affiliative address
    "how are you", "how r u", "how you doing", "what's up", "whats up",
    "what's good", "whats good", "good to see you", "my man", "my friend",
    "bro", "welcome", "sup", "how's it going"
)

REBOUND_COLLABORATIVE_TOKENS = (
    "تعال ندخل", "يلا ندخل", "يلا نلعب", "تعال نلعب", "يلا بينا", "جاهز",
    "شفت الماتش", "let's play", "lets play", "let's go", "lets go",
    "hop on", "ready", "wanna play", "start the match"
)

PLAYFUL_INSULT_TOKENS = (
    # Common gaming and colloquial teasing words that are not full slurs
    "حمار", "غبي", "حيوان", "فاشل", "نوب", "يا نوب",
    "noob", "loser", "bot", "trash", "dummy", "stupid", "idiot"
)

DEFENSE_WITHDRAWAL_TOKENS = (
    # Arabic defensive or hurt reactions indicating unilateral attack
    "مالك", "في ايه", "براحة عليا", "براحة يا عم", "اهدى", "اهدا",
    "خلاص يا عم", "سيبني", "كفاية كدا", "ليه كده", "حرام عليك",
    # English defensive reactions
    "chill", "calm down", "stop it", "relax", "why are you mad",
    "leave me alone", "what's wrong with you", "whats wrong with you",
    "take it easy", "why so aggressive"
)

HOSTILE_FRICTION_TOKENS = (
    # Arabic persistent hostility, contempt, or severe despair
    "زهقت", "زبالة", "مقرف", "مش طايق", "اخرس", "غور", "انقلع",
    "اتكتم", "هقتلك", "عصبتني", "بقولك اخرس", "فاشل ومقرف",
    # English persistent hostility and contempt
    "fucking hate", "fuck you all", "kill yourself", "die", "shut the fuck up",
    "stfu", "piece of shit", "worthless", "hate you"
)

_ARABIC_LAUGHTER_REGEX = re.compile(r"ه{2,}")
_ENGLISH_LAUGHTER_REGEX = re.compile(r"\b(?:lol|lmao|rofl|haha+|lmfao|kek|xd)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DiscourseTurn:
    """Represents a single conversational turn in the sliding discourse window."""
    turn_index: int
    speaker_id: str
    speaker_name: str
    text: str
    timestamp: float
    duration: float = 1.0
    was_loud: bool = False
    peak_z: float = 0.0
    raw_anger: str = "none"
    anger_evidence: str = ""
    audio_clip: Optional[str] = None
    vulgarity_count: int = 0
    vulgarity_terms: List[str] = field(default_factory=list)

    @property
    def normalized_text(self) -> str:
        return normalize_bilingual_text(self.text)

    def has_rebound_cue(self) -> Optional[str]:
        """Checks if utterance contains greetings, laughter, or collaborative shift."""
        # Check raw text for laughter patterns before repetition collapsing
        if _ARABIC_LAUGHTER_REGEX.search(self.text):
            return "laughter_arabic"
        if _ENGLISH_LAUGHTER_REGEX.search(self.text):
            return "laughter_english"

        norm = self.normalized_text
        for tok in REBOUND_GREETING_TOKENS:
            if tok in norm:
                return tok
        for tok in REBOUND_COLLABORATIVE_TOKENS:
            if tok in norm:
                return tok
        if any(w in norm for w in ("ضحكتني", "بتضحك", "ضحك")):
            return "laughter_word"
        return None

    def has_playful_insult(self) -> Optional[str]:
        """Checks if utterance contains common gaming/teasing terms."""
        norm = self.normalized_text
        for tok in PLAYFUL_INSULT_TOKENS:
            if tok in norm:
                return tok
        return None

    def has_defense_cue(self) -> Optional[str]:
        """Checks if utterance contains defensive withdrawal tokens."""
        norm = self.normalized_text
        for tok in DEFENSE_WITHDRAWAL_TOKENS:
            if tok in norm:
                return tok
        return None

    def has_hostile_friction(self) -> Optional[str]:
        """Checks if utterance contains explicit persistent hostility tokens."""
        norm = self.normalized_text
        for tok in HOSTILE_FRICTION_TOKENS:
            if tok in norm:
                return tok
        return None


@dataclass
class ArousalCandidate:
    """An uncommitted high-arousal or friction turn awaiting resolution window."""
    candidate_id: str
    initial_turn: DiscourseTurn
    turns_since: int = 0
    created_at: float = field(default_factory=time.time)
    has_symmetrical_response: bool = False
    responding_speaker_id: Optional[str] = None
    responding_speaker_name: Optional[str] = None
    responding_text: Optional[str] = None
    has_victim_defense: bool = False
    is_resolved: bool = False


@dataclass
class DiscourseResolution:
    """Authoritative outcome of discourse trajectory evaluation."""
    resolution_type: str  # "friendly_banter" | "hostile_escalation" | "isolated_shout"
    speaker_id: str
    speaker_name: str
    timestamp: float
    quote: str
    was_loud: bool
    peak_z: float
    trajectory_context: str
    partner_id: Optional[str] = None
    partner_name: Optional[str] = None
    audio_clip: Optional[str] = None
    terms: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discourse & Pragmatics Tracker
# ---------------------------------------------------------------------------

class DiscourseTracker:
    """
    Maintains a rolling sliding window of conversational turns and tracks
    structural trajectories to separate friendly banter from hostile escalation.
    """

    def __init__(self, session_id: str = "default", max_window_turns: int = 15):
        self.session_id: str = session_id
        self.max_window_turns: int = max_window_turns
        self.turns: List[DiscourseTurn] = []
        self.pending_candidates: List[ArousalCandidate] = []
        self.turn_counter: int = 0
        self.resolved_banter_count: int = 0
        self.resolved_escalation_count: int = 0

    def observe_turn(
        self,
        speaker_id: str,
        speaker_name: str,
        text: str,
        timestamp: float,
        duration: float = 1.0,
        audio_features: Optional[Any] = None,
        raw_anger: str = "none",
        anger_evidence: str = "",
        audio_clip: Optional[str] = None
    ) -> List[DiscourseResolution]:
        """
        Ingests a finalized conversational turn, updates the discourse window,
        evaluates active candidates, and detects trajectories.
        Returns a list of DiscourseResolutions (if any candidate was resolved).
        """
        self.turn_counter += 1

        # Extract audio features defensively
        if audio_features is None:
            was_loud = False
            peak_z = 0.0
        elif isinstance(audio_features, dict):
            was_loud = bool(audio_features.get("was_loud", False))
            peak_z = float(audio_features.get("peak_robust_z", 0.0))
        else:
            was_loud = bool(getattr(audio_features, "was_loud", False))
            peak_z = float(getattr(audio_features, "peak_robust_z", 0.0))

        # Perform lexical banter analysis
        banter_res = analyze_banter(text)

        turn = DiscourseTurn(
            turn_index=self.turn_counter,
            speaker_id=str(speaker_id),
            speaker_name=speaker_name,
            text=text,
            timestamp=timestamp,
            duration=duration,
            was_loud=was_loud,
            peak_z=peak_z,
            raw_anger=str(raw_anger).lower().strip(),
            anger_evidence=anger_evidence or "",
            audio_clip=audio_clip,
            vulgarity_count=banter_res.vulgarity_count,
            vulgarity_terms=banter_res.matched_terms
        )

        resolutions: List[DiscourseResolution] = []

        # -------------------------------------------------------------------
        # Step 1: Update Existing Pending Candidates
        # -------------------------------------------------------------------
        for cand in self.pending_candidates:
            if cand.is_resolved:
                continue

            cand.turns_since += 1
            init_turn = cand.initial_turn

            # Interaction between different speakers
            if turn.speaker_id != init_turn.speaker_id:
                latency = turn.timestamp - init_turn.timestamp

                # A. Check Symmetrical Entrainment (Mutual Arousal / Banter)
                if latency <= 6.0:
                    is_reciprocal_energy = turn.was_loud or turn.peak_z >= 2.2
                    is_reciprocal_lexicon = (
                        turn.vulgarity_count > 0 or
                        turn.has_playful_insult() is not None or
                        turn.raw_anger in ("mild", "high")
                    )
                    if is_reciprocal_energy or is_reciprocal_lexicon:
                        cand.has_symmetrical_response = True
                        cand.responding_speaker_id = turn.speaker_id
                        cand.responding_speaker_name = turn.speaker_name
                        cand.responding_text = turn.text

                # B. Check Defense / Victim Withdrawal
                defense_cue = turn.has_defense_cue()
                if defense_cue:
                    cand.has_victim_defense = True

            # C. Check Prosodic & Lexical Rebound
            rebound_cue = turn.has_rebound_cue()
            is_acoustic_rebound = not turn.was_loud and turn.peak_z <= 1.8

            # Resolution Condition: Symmetrical banter followed by rebound
            if cand.has_symmetrical_response and (rebound_cue or is_acoustic_rebound):
                # Friendly banter confirmed!
                cand.is_resolved = True
                self.resolved_banter_count += 1
                cue_str = rebound_cue or "prosodic_baseline_reset"
                res = DiscourseResolution(
                    resolution_type="friendly_banter",
                    speaker_id=init_turn.speaker_id,
                    speaker_name=init_turn.speaker_name,
                    timestamp=init_turn.timestamp,
                    quote=init_turn.text,
                    was_loud=init_turn.was_loud,
                    peak_z=init_turn.peak_z,
                    trajectory_context=f"symmetrical_banter_with_rebound ('{cue_str}')",
                    partner_id=cand.responding_speaker_id,
                    partner_name=cand.responding_speaker_name,
                    audio_clip=init_turn.audio_clip,
                    terms=init_turn.vulgarity_terms
                )
                resolutions.append(res)
                logger.info(
                    f"🤝 [Discourse] Friendly banter resolved between {init_turn.speaker_name} "
                    f"and {cand.responding_speaker_name} (cue='{cue_str}'). Suppressing false anger."
                )

            # Resolution Condition: Escalation Window Timeout or Persistent Attack
            elif cand.turns_since >= 2 or (timestamp - init_turn.timestamp) >= 15.0:
                if cand.has_victim_defense:
                    # Unilateral hostile escalation confirmed!
                    cand.is_resolved = True
                    self.resolved_escalation_count += 1
                    res = DiscourseResolution(
                        resolution_type="hostile_escalation",
                        speaker_id=init_turn.speaker_id,
                        speaker_name=init_turn.speaker_name,
                        timestamp=init_turn.timestamp,
                        quote=cand.initial_turn.anger_evidence or init_turn.text,
                        was_loud=init_turn.was_loud,
                        peak_z=init_turn.peak_z,
                        trajectory_context=f"hostile_escalation (unilateral attack vs defense, z={init_turn.peak_z:.1f}σ)",
                        partner_id=cand.responding_speaker_id,
                        partner_name=cand.responding_speaker_name,
                        audio_clip=init_turn.audio_clip,
                        terms=init_turn.vulgarity_terms
                    )
                    resolutions.append(res)
                elif init_turn.has_hostile_friction() or init_turn.raw_anger in ("mild", "high"):
                    # Persistent hostile friction without de-escalation
                    cand.is_resolved = True
                    self.resolved_escalation_count += 1
                    traj_desc = (
                        f"sustained_monologue_rant ({cand.turns_since} turns without de-escalation, z={init_turn.peak_z:.1f}σ)"
                        if cand.responding_speaker_id is None
                        else f"hostile_escalation (sustained {cand.turns_since} turns without rebound, z={init_turn.peak_z:.1f}σ)"
                    )
                    res = DiscourseResolution(
                        resolution_type="hostile_escalation",
                        speaker_id=init_turn.speaker_id,
                        speaker_name=init_turn.speaker_name,
                        timestamp=init_turn.timestamp,
                        quote=cand.initial_turn.anger_evidence or init_turn.text,
                        was_loud=init_turn.was_loud,
                        peak_z=init_turn.peak_z,
                        trajectory_context=traj_desc,
                        partner_id=cand.responding_speaker_id,
                        partner_name=cand.responding_speaker_name,
                        audio_clip=init_turn.audio_clip,
                        terms=init_turn.vulgarity_terms
                    )
                    resolutions.append(res)
                else:
                    # Isolated shout or de-escalated arousal without ongoing conflict
                    cand.is_resolved = True
                    res = DiscourseResolution(
                        resolution_type="isolated_shout",
                        speaker_id=init_turn.speaker_id,
                        speaker_name=init_turn.speaker_name,
                        timestamp=init_turn.timestamp,
                        quote=init_turn.text,
                        was_loud=init_turn.was_loud,
                        peak_z=init_turn.peak_z,
                        trajectory_context="isolated_shout_without_conflict",
                        audio_clip=init_turn.audio_clip,
                        terms=init_turn.vulgarity_terms
                    )
                    resolutions.append(res)

        # Prune resolved candidates
        self.pending_candidates = [c for c in self.pending_candidates if not c.is_resolved]

        # -------------------------------------------------------------------
        # Step 2: Multi-Turn Rant Check (Single Speaker Sustained Toxicity)
        # -------------------------------------------------------------------
        recent_speaker_turns = [
            t for t in self.turns
            if t.speaker_id == turn.speaker_id and (timestamp - t.timestamp) <= 30.0
        ]
        all_speaker_turns = recent_speaker_turns + [turn]
        if len(all_speaker_turns) >= 3:
            hostile_count = sum(
                1 for t in all_speaker_turns
                if t.has_hostile_friction() or t.raw_anger in ("mild", "high") or (t.was_loud and t.vulgarity_count > 0)
            )
            # 3 consecutive hostile complaints/rants = guaranteed hostile escalation
            if hostile_count >= 3:
                # Avoid duplicate emission if a resolution was already added in Step 1
                already_escalated = any(r.speaker_id == turn.speaker_id and r.resolution_type == "hostile_escalation" for r in resolutions)
                if not already_escalated:
                    self.resolved_escalation_count += 1
                    res = DiscourseResolution(
                        resolution_type="hostile_escalation",
                        speaker_id=turn.speaker_id,
                        speaker_name=turn.speaker_name,
                        timestamp=turn.timestamp,
                        quote=turn.anger_evidence or turn.text,
                        was_loud=turn.was_loud,
                        peak_z=turn.peak_z,
                        trajectory_context=f"sustained_monologue_rant ({hostile_count} consecutive turns)",
                        audio_clip=turn.audio_clip,
                        terms=turn.vulgarity_terms
                    )
                    resolutions.append(res)
                    logger.info(f"🔥 [Discourse] Sustained monologue rant confirmed for {turn.speaker_name}.")

        # -------------------------------------------------------------------
        # Step 3: Register New Candidate Arousal Turn (If Applicable)
        # -------------------------------------------------------------------
        is_banter_cue = turn.vulgarity_count > 0 or turn.has_playful_insult() is not None
        needs_candidate = (
            is_banter_cue or
            (turn.was_loud and any(t.speaker_id != turn.speaker_id for t in self.turns[-3:]))
        )

        if needs_candidate:
            # If the utterance itself contains explicit laughter or greeting, resolve immediately as banter
            rebound_in_turn = turn.has_rebound_cue()
            if rebound_in_turn:
                self.resolved_banter_count += 1
                res = DiscourseResolution(
                    resolution_type="friendly_banter",
                    speaker_id=turn.speaker_id,
                    speaker_name=turn.speaker_name,
                    timestamp=turn.timestamp,
                    quote=turn.text,
                    was_loud=turn.was_loud,
                    peak_z=turn.peak_z,
                    trajectory_context=f"self_contained_banter ('{rebound_in_turn}')",
                    audio_clip=turn.audio_clip,
                    terms=turn.vulgarity_terms
                )
                resolutions.append(res)
                logger.info(f"🤝 [Discourse] Self-contained banter in turn '{turn.text}' for {turn.speaker_name}.")
            else:
                cand_id = f"cand_{turn.speaker_id}_{turn.turn_index}_{int(timestamp)}"
                new_cand = ArousalCandidate(
                    candidate_id=cand_id,
                    initial_turn=turn,
                    turns_since=0,
                    created_at=timestamp
                )
                # Link reciprocity: If another speaker has an active candidate within 6s, link both
                for prior_cand in self.pending_candidates:
                    if prior_cand.initial_turn.speaker_id != turn.speaker_id:
                        if (timestamp - prior_cand.initial_turn.timestamp) <= 6.0:
                            new_cand.has_symmetrical_response = True
                            new_cand.responding_speaker_id = prior_cand.initial_turn.speaker_id
                            new_cand.responding_speaker_name = prior_cand.initial_turn.speaker_name
                            break
                self.pending_candidates.append(new_cand)
                logger.debug(f"⏳ [Discourse] Registered arousal candidate: {cand_id} ({turn.speaker_name}: '{turn.text}')")

        # -------------------------------------------------------------------
        # Step 4: Maintain Sliding Window
        # -------------------------------------------------------------------
        self.turns.append(turn)
        if len(self.turns) > self.max_window_turns:
            self.turns.pop(0)

        return resolutions

    def flush_pending(self) -> List[DiscourseResolution]:
        """
        Flushes and resolves any lingering candidates at call end / recap time.
        Any candidate with insufficient evidence of ongoing hostility is cleared.
        """
        resolutions: List[DiscourseResolution] = []
        for cand in self.pending_candidates:
            if cand.is_resolved:
                continue
            cand.is_resolved = True
            init_turn = cand.initial_turn

            # If it had confirmed victim defense, count as escalation
            if cand.has_victim_defense and init_turn.has_hostile_friction():
                self.resolved_escalation_count += 1
                res = DiscourseResolution(
                    resolution_type="hostile_escalation",
                    speaker_id=init_turn.speaker_id,
                    speaker_name=init_turn.speaker_name,
                    timestamp=init_turn.timestamp,
                    quote=init_turn.anger_evidence or init_turn.text,
                    was_loud=init_turn.was_loud,
                    peak_z=init_turn.peak_z,
                    trajectory_context="hostile_escalation_at_session_end",
                    audio_clip=init_turn.audio_clip,
                    terms=init_turn.vulgarity_terms
                )
                resolutions.append(res)
            elif cand.has_symmetrical_response:
                # Symmetrical exchange without further escalation -> friendly banter
                self.resolved_banter_count += 1
                res = DiscourseResolution(
                    resolution_type="friendly_banter",
                    speaker_id=init_turn.speaker_id,
                    speaker_name=init_turn.speaker_name,
                    timestamp=init_turn.timestamp,
                    quote=init_turn.text,
                    was_loud=init_turn.was_loud,
                    peak_z=init_turn.peak_z,
                    trajectory_context="symmetrical_banter_flushed_at_end",
                    partner_id=cand.responding_speaker_id,
                    partner_name=cand.responding_speaker_name,
                    audio_clip=init_turn.audio_clip,
                    terms=init_turn.vulgarity_terms
                )
                resolutions.append(res)
            else:
                # Isolated unresolved shout -> suppressed
                res = DiscourseResolution(
                    resolution_type="isolated_shout",
                    speaker_id=init_turn.speaker_id,
                    speaker_name=init_turn.speaker_name,
                    timestamp=init_turn.timestamp,
                    quote=init_turn.text,
                    was_loud=init_turn.was_loud,
                    peak_z=init_turn.peak_z,
                    trajectory_context="unresolved_shout_flushed_at_end",
                    audio_clip=init_turn.audio_clip,
                    terms=init_turn.vulgarity_terms
                )
                resolutions.append(res)

        self.pending_candidates.clear()
        return resolutions
