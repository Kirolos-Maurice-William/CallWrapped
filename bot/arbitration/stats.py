import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List, Set, Tuple

from bot.arbitration.lexicon import analyze_banter, mask_term

logger = logging.getLogger("TalkStats")

# Taxonomy v3 display name mappings (colloquial Egyptian Arabic)
TOPIC_DISPLAY_NAMES: Dict[str, str] = {
    "food": "أكل",
    "travel": "سفر",
    "study_work": "دراسة وشغل",
    "health": "صحة",
    "cars": "عربيات",
    "money": "فلوس",
}


def format_duration_human(seconds: float, lang: str = "en") -> str:
    """
    Deterministically formats seconds into clean, human-readable strings.
    Transitions:
      <60s   -> 'Xs'   (en) or 'Xث'  (ar)
      <3600s -> 'Xm Ys' or 'Xm' (en) or 'Xد Yث' or 'Xد' (ar)
      >=3600s -> 'Xh Ym' or 'Xh' (en) or 'Xس Yد' or 'Xس' (ar)
    Zero / negative values map safely to '0s' / '0ث'.
    """
    if seconds is None or seconds <= 0:
        return "0ث" if lang == "ar" else "0s"

    total_sec = int(round(seconds))
    if total_sec < 60:
        return f"{total_sec}ث" if lang == "ar" else f"{total_sec}s"

    mins = total_sec // 60
    secs = total_sec % 60
    if mins < 60:
        if secs == 0:
            return f"{mins}د" if lang == "ar" else f"{mins}m"
        return f"{mins}د {secs}ث" if lang == "ar" else f"{mins}m {secs}s"

    hours = mins // 60
    rem_mins = mins % 60
    if rem_mins == 0:
        return f"{hours}س" if lang == "ar" else f"{hours}h"
    return f"{hours}س {rem_mins}د" if lang == "ar" else f"{hours}h {rem_mins}m"


def compute_topic_importance(
    topic_durations: Dict[str, float],
    topic_counts: Dict[str, int],
    intervals: Optional[list] = None,
    total_speakers: int = 1
) -> List[Tuple[str, float, float]]:
    """
    Computes Spotify Wrapped Importance Ranking for discussion topics.
    Formula:
      I(topic) = 0.50 * d_norm + 0.30 * p_ratio + 0.20 * t_norm
    where:
      d_norm = continuous duration of topic / sum(all topical durations)
      p_ratio = unique speakers who engaged in topic / total call speakers
      t_norm = turn count in topic / sum(all topical turns)

    Returns sorted list of (topic_key, importance_score, display_pct).
    """
    ignored = {"null_topic", "null", "none", "بدون موضوع"}
    filtered_durs = {k: v for k, v in topic_durations.items() if k and k not in ignored and v > 0}
    filtered_counts = {k: v for k, v in topic_counts.items() if k and k not in ignored and v > 0}

    all_keys = list(dict.fromkeys(list(filtered_durs.keys()) + list(filtered_counts.keys())))
    if not all_keys:
        return []

    has_durations = bool(filtered_durs)
    tot_dur = sum(filtered_durs.values()) if has_durations else 0.0
    tot_cnt = sum(filtered_counts.get(k, 1) for k in all_keys)

    speakers_per_topic: Dict[str, Set[str]] = {k: set() for k in all_keys}
    turns_per_topic: Dict[str, int] = {k: 0 for k in all_keys}
    if intervals:
        for itv in intervals:
            top = getattr(itv, "macro_topic", None)
            if top in speakers_per_topic:
                spks = getattr(itv, "participating_speakers", set())
                speakers_per_topic[top].update(spks)
                turns_per_topic[top] += getattr(itv, "turn_count", 1)

    scored: List[Tuple[str, float, float]] = []
    for k in all_keys:
        dur = filtered_durs.get(k, 0.0)
        cnt = filtered_counts.get(k, turns_per_topic.get(k, 1))

        if has_durations and tot_dur > 0:
            d_norm = dur / tot_dur
            t_norm = cnt / max(1, tot_cnt)
            spk_set = speakers_per_topic.get(k, set())
            p_ratio = (len(spk_set) / max(1, total_speakers)) if spk_set else d_norm
            importance = 0.50 * d_norm + 0.30 * p_ratio + 0.20 * t_norm
            display_pct = round(d_norm * 100.0, 1)
        else:
            c_norm = cnt / max(1, tot_cnt)
            importance = c_norm
            display_pct = round(c_norm * 100.0, 1)

        scored.append((k, importance, display_pct))

    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return scored


def compute_topic_mvps(intervals: Optional[list] = None) -> Dict[str, Tuple[str, float]]:
    """
    Computes domain dominance (Topic MVP) from conversational discourse intervals.
    Returns: {topic_key: (top_speaker_name, dominance_share_pct)}
    Grounded in conversational analysis (Jurafsky & Martin Ch. 26).
    Only awards badges in multi-party topics (>= 2 participating speakers).
    """
    if not intervals:
        return {}

    topic_speaker_durations: Dict[str, Dict[str, float]] = {}
    ignored = {"null_topic", "null", "none", "بدون موضوع"}

    for itv in intervals:
        topic = getattr(itv, "macro_topic", None)
        if not topic or not str(topic).strip() or str(topic).strip().lower() in ignored:
            continue
        clean_topic = str(topic).strip()
        if clean_topic not in topic_speaker_durations:
            topic_speaker_durations[clean_topic] = {}

        spk_durs = getattr(itv, "speaker_durations", {})
        if spk_durs:
            for spk, dur in spk_durs.items():
                if spk and dur > 0:
                    topic_speaker_durations[clean_topic][spk] = (
                        topic_speaker_durations[clean_topic].get(spk, 0.0) + dur
                    )
        else:
            spks = getattr(itv, "participating_speakers", set())
            valid_spks = [s for s in spks if s]
            dur_per_spk = getattr(itv, "duration_seconds", 1.0) / max(1, len(valid_spks))
            for spk in valid_spks:
                topic_speaker_durations[clean_topic][spk] = (
                    topic_speaker_durations[clean_topic].get(spk, 0.0) + dur_per_spk
                )

    mvps: Dict[str, Tuple[str, float]] = {}
    for topic, spk_map in topic_speaker_durations.items():
        tot = sum(spk_map.values())
        if tot > 0 and len(spk_map) >= 2:
            sorted_spks = sorted(spk_map.items(), key=lambda x: x[1], reverse=True)
            top_spk, top_dur = sorted_spks[0]
            # Honest tie guard: if top two speakers contributed equally (within 0.2s), no solo MVP
            if len(sorted_spks) >= 2 and abs(top_dur - sorted_spks[1][1]) < 0.2:
                continue
            share_pct = round((top_dur / tot) * 100.0, 1)
            mvps[topic] = (top_spk, share_pct)

    return mvps



@dataclass
class SpeakerStats:
    """
    Real-time talk statistics for a single speaker in a voice session.
    Tracks exact speech-window durations and conversational streaks.
    """
    speaker_id: str
    total_speak_seconds: float = 0.0
    utterance_count: int = 0
    longest_streak_seconds: float = 0.0
    current_streak: float = 0.0
    last_utterance_end: float = 0.0
    speaker_name: Optional[str] = None
    angry_episodes: int = 0
    last_anger_time: float = 0.0
    first_anger_quote: Optional[str] = None
    anger_episodes_history: List[Dict[str, Any]] = field(default_factory=list)
    # Topic streak tracking (Taxonomy v2)
    current_topic: Optional[str] = None
    current_topic_streak: float = 0.0
    longest_topic_streak_seconds: float = 0.0
    longest_topic: Optional[str] = None
    topic_streak_count: int = 0
    # Banter & vulgarity tracking (Phase 2 & 3)
    vulgarity_count: int = 0
    vulgarity_terms: List[str] = field(default_factory=list)
    banter_count: int = 0
    banter_terms: List[str] = field(default_factory=list)

    @property
    def current_streak_seconds(self) -> float:
        """Alias for current_streak in seconds."""
        return self.current_streak

    @property
    def topic_streak(self) -> float:
        """Alias for current_topic_streak in seconds."""
        return self.current_topic_streak

    def record_banter(self, terms: Optional[List[str]] = None) -> None:
        """Increments friendly banter interaction count and tracks unique terms."""
        self.banter_count += 1
        if terms:
            for term in terms:
                if term not in self.banter_terms and len(self.banter_terms) < 20:
                    self.banter_terms.append(term)

    def record_anger(
        self,
        timestamp: float,
        anger: Any,
        quote: Optional[str] = None,
        was_loud: bool = False,
        peak_z: float = 0.0,
        context: str = "",
        audio_clip: Optional[str] = None
    ) -> bool:
        """
        Pure Python anger episode counter on top of classifier output.
        RULE: Consecutive angry classifications within a 90-second window per speaker = ONE episode
        (a rant is one episode, not five).
        Returns True if a new episode was triggered, False otherwise.
        """
        is_angry = False
        extracted_quote = quote

        if isinstance(anger, bool):
            is_angry = anger
        elif isinstance(anger, str):
            is_angry = anger.lower() in ("mild", "high", "angry", "true")
        elif isinstance(anger, dict):
            val = anger.get("anger", "none")
            is_angry = str(val).lower() in ("mild", "high", "angry", "true")
            if not extracted_quote:
                extracted_quote = anger.get("anger_evidence") or anger.get("claim")

        if not is_angry:
            return False

        # Strict dual-evidence requirement:
        # An anger episode MUST have verified verbal evidence.
        # If there is no quote or it's empty / placeholder, do NOT record an episode.
        clean_quote = str(extracted_quote).strip() if (extracted_quote and str(extracted_quote).strip()) else ""
        if not clean_quote or clean_quote == "(no verbal evidence captured)":
            return False

        # Consecutive angry classifications within 90s = 1 episode
        is_new_episode = False
        if self.angry_episodes == 0 or (timestamp - self.last_anger_time) > 90.0:
            self.angry_episodes += 1
            is_new_episode = True

        self.last_anger_time = timestamp

        if self.first_anger_quote is None:
            self.first_anger_quote = clean_quote

        if is_new_episode:
            self.anger_episodes_history.append({
                "episode_number": self.angry_episodes,
                "quote": clean_quote,
                "timestamp": round(timestamp, 2),
                "anger": str(anger).lower(),
                "was_loud": bool(was_loud),
                "peak_z": round(float(peak_z), 2),
                "context": str(context),
                "audio_clip": str(audio_clip) if audio_clip else None
            })
            if len(self.anger_episodes_history) > 20:
                self.anger_episodes_history.pop(0)

        return is_new_episode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name or self.speaker_id,
            "total_speak_seconds": round(self.total_speak_seconds, 3),
            "utterance_count": self.utterance_count,
            "longest_streak_seconds": round(self.longest_streak_seconds, 3),
            "current_streak": round(self.current_streak, 3),
            "last_utterance_end": round(self.last_utterance_end, 3),
            "angry_episodes": self.angry_episodes,
            "last_anger_time": round(self.last_anger_time, 3),
            "first_anger_quote": self.first_anger_quote,
            "anger_episodes_history": list(self.anger_episodes_history),
            "current_topic": self.current_topic,
            "current_topic_streak": round(self.current_topic_streak, 3),
            "longest_topic_streak_seconds": round(self.longest_topic_streak_seconds, 3),
            "longest_topic": self.longest_topic,
            "topic_streak_count": self.topic_streak_count,
            "vulgarity_count": self.vulgarity_count,
            "vulgarity_terms": list(self.vulgarity_terms),
            "banter_count": self.banter_count,
            "banter_terms": list(self.banter_terms)
        }


class SessionStatsTracker:
    """
    Tracks per-speaker real-time speech statistics, monologue streaks, and topic streaks.
    STREAK DEFINITION:
    Consecutive utterances by the same speaker where the gap between this utterance's
    start and the speaker's prior utterance end is < 5s AND no other user spoke in between.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or "default"
        self.speakers: Dict[str, SpeakerStats] = {}
        self.last_speaker_id: Optional[str] = None
        self.primary_speaker_id: Optional[str] = None
        self.topic_durations: Dict[str, float] = {}
        self.topic_counts: Dict[str, int] = {}

    def get_speaker(self, speaker_id: str) -> Optional[SpeakerStats]:
        return self.speakers.get(str(speaker_id))

    def get_or_create_speaker(self, speaker_id: str, speaker_name: Optional[str] = None) -> SpeakerStats:
        spk_key = str(speaker_id)
        if spk_key not in self.speakers:
            self.speakers[spk_key] = SpeakerStats(
                speaker_id=spk_key,
                speaker_name=speaker_name or spk_key
            )
        elif speaker_name and (not self.speakers[spk_key].speaker_name or self.speakers[spk_key].speaker_name == spk_key):
            self.speakers[spk_key].speaker_name = speaker_name
        return self.speakers[spk_key]

    def record_utterance(
        self,
        speaker_id: str,
        speech_start: float,
        speech_end: float,
        speaker_name: Optional[str] = None,
        anger: Optional[Any] = None,
        anger_quote: Optional[str] = None,
        classification: Optional[Dict[str, Any]] = None,
        topic: Optional[str] = None,
        text: Optional[str] = None
    ) -> SpeakerStats:
        """
        Records an utterance derived strictly from RMS speech-window timestamps.
        Never infers duration from WAV byte counts or transcript lengths.
        Optionally records anger classification and topic streak bridging.
        """
        spk_key = str(speaker_id)
        duration = max(0.0, speech_end - speech_start)
        stats = self.get_or_create_speaker(spk_key, speaker_name)

        # 1. Update basic totals
        stats.total_speak_seconds += duration
        stats.utterance_count += 1

        # 2. Extract and normalize topic
        extracted_topic = topic
        if extracted_topic is None and classification is not None:
            extracted_topic = classification.get("topic")

        norm_topic = extracted_topic.strip().lower() if extracted_topic is not None else ""
        if extracted_topic is not None:
            self.topic_durations[norm_topic] = self.topic_durations.get(norm_topic, 0.0) + duration
            self.topic_counts[norm_topic] = self.topic_counts.get(norm_topic, 0) + 1

        is_null = (norm_topic in ("null_topic", "null", "none", "بدون موضوع", "")) if norm_topic else False

        # Phase 3: Research-backed Schegloff (1982) listener backchannel rule:
        # A listener's null_topic utterance (< 2.0s duration) is an acknowledgment,
        # not floor-taking, and does NOT break the primary speaker's active monologue or topic streak.
        is_listener_backchannel = (
            self.primary_speaker_id is not None
            and spk_key != self.primary_speaker_id
            and is_null
            and duration < 2.0
        )

        if is_listener_backchannel:
            # Backchannel speaker gets speaker stats recorded, but does not take the floor
            stats.last_utterance_end = speech_end
            stats.current_streak = duration
            if stats.current_streak > stats.longest_streak_seconds:
                stats.longest_streak_seconds = stats.current_streak
            # Primary floor-holder's streaks remain untouched
        else:
            # Floor taken or held by spk_key
            # Break active streaks for all OTHER speakers
            for other_id, other_stats in self.speakers.items():
                if other_id != spk_key:
                    other_stats.current_streak = 0.0
                    other_stats.current_topic = None
                    other_stats.current_topic_streak = 0.0

            another_user_spoke = (self.primary_speaker_id is not None and self.primary_speaker_id != spk_key)
            gap = (speech_start - stats.last_utterance_end) if stats.last_utterance_end > 0 else float('inf')

            # Evaluate monologue streak
            if not another_user_spoke and gap < 5.0 and stats.last_utterance_end > 0:
                stats.current_streak += duration
            else:
                stats.current_streak = duration

            if stats.current_streak > stats.longest_streak_seconds:
                stats.longest_streak_seconds = stats.current_streak

            # Evaluate topic streak (Phase 3: SwDA streak bridging)
            if extracted_topic is not None:
                if is_null:
                    # null_topic does NOT break a speaker's topic streak if gap < 5s and no floor change
                    if another_user_spoke or gap >= 5.0:
                        stats.current_topic = None
                        stats.current_topic_streak = 0.0
                    # Else: bridged! Topic remains unchanged, duration is EXCLUDED from topic streak seconds
                else:
                    if (
                        not another_user_spoke
                        and gap < 5.0
                        and stats.current_topic == norm_topic
                        and stats.current_topic_streak > 0
                    ):
                        # Same topic continued (even if bridged across intervening null_topic)
                        stats.current_topic_streak += duration
                    else:
                        # New topic streak begins
                        stats.current_topic = norm_topic
                        stats.current_topic_streak = duration
                        stats.topic_streak_count += 1

                    if stats.current_topic_streak > stats.longest_topic_streak_seconds:
                        stats.longest_topic_streak_seconds = stats.current_topic_streak
                        stats.longest_topic = norm_topic

            stats.last_utterance_end = speech_end
            self.primary_speaker_id = spk_key
            self.last_speaker_id = spk_key

        # Anger tracking
        if classification is not None:
            stats.record_anger(timestamp=speech_end, anger=classification)
        elif anger is not None:
            stats.record_anger(timestamp=speech_end, anger=anger, quote=anger_quote)

        # Banter & vulgarity tracking (Phase 2)
        utterance_text = text
        if utterance_text is None and classification is not None and isinstance(classification, dict):
            utterance_text = classification.get("text")

        if utterance_text:
            banter_res = analyze_banter(utterance_text)
            if banter_res.has_vulgarity:
                stats.vulgarity_count += banter_res.vulgarity_count
                for term in banter_res.matched_terms:
                    masked = mask_term(term)
                    if len(stats.vulgarity_terms) < 20 and masked not in stats.vulgarity_terms:
                        stats.vulgarity_terms.append(masked)

        logger.debug(
            f"[TalkStats] Speaker {spk_key} ({speaker_name}): dur={duration:.2f}s, "
            f"total={stats.total_speak_seconds:.2f}s, streak={stats.current_streak:.2f}s, "
            f"topic={stats.current_topic}, topic_streak={stats.current_topic_streak:.2f}s"
        )
        return stats

    def get_topic_share(self) -> Dict[str, float]:
        """
        Documented formula (Taxonomy v2):
        topic share = topical time in class k / total topical time.
        null_topic is strictly excluded from the denominator.
        """
        topical_durations = {
            t: d for t, d in self.topic_durations.items()
            if t not in ("null_topic", "null", "none", "بدون موضوع", "")
        }
        total_topical_time = sum(topical_durations.values())
        if total_topical_time <= 0:
            return {}
        return {
            t: round((d / total_topical_time) * 100.0, 1)
            for t, d in topical_durations.items()
        }

    def get_topical_coverage(self) -> float:
        """
        Documented formula (Taxonomy v2):
        Topical coverage = topical_time / total_talk_time.
        """
        total_talk_time = sum(s.total_speak_seconds for s in self.speakers.values())
        if total_talk_time <= 0:
            total_talk_time = sum(self.topic_durations.values())
        if total_talk_time <= 0:
            return 0.0

        topical_time = sum(
            d for t, d in self.topic_durations.items()
            if t not in ("null_topic", "null", "none", "بدون موضوع", "")
        )
        return round(topical_time / total_talk_time, 4)

    def record_anger(
        self,
        speaker_id: str,
        timestamp: float,
        anger: Any,
        anger_quote: Optional[str] = None,
        speaker_name: Optional[str] = None,
        was_loud: bool = False,
        peak_z: float = 0.0,
        context: str = "",
        audio_clip: Optional[str] = None
    ) -> SpeakerStats:
        """
        Records an anger classification for a speaker.
        Consecutive angry classifications within a 90-second window per speaker = ONE episode.
        """
        spk_key = str(speaker_id)
        stats = self.get_or_create_speaker(spk_key, speaker_name)
        stats.record_anger(
            timestamp=timestamp,
            anger=anger,
            quote=anger_quote,
            was_loud=was_loud,
            peak_z=peak_z,
            context=context,
            audio_clip=audio_clip
        )
        return stats

    def get_speaker_talk_shares(self) -> Dict[str, float]:
        """
        Computes zero-division-safe normalized talk share percentage per speaker.
        Formula: (speaker.total_speak_seconds / S_total) * 100.0 where S_total = sum(all speakers).
        """
        total_talk_sec = sum(s.total_speak_seconds for s in self.speakers.values())
        if total_talk_sec <= 0:
            return {spk_id: 0.0 for spk_id in self.speakers}
        return {
            spk_id: round((s.total_speak_seconds / total_talk_sec) * 100.0, 1)
            for spk_id, s in self.speakers.items()
        }

    def get_silent_observer(self) -> Optional[Tuple[str, float, float]]:
        """
        Identifies 'The Silent Observer' (speaker who participated but talked the least).
        Rules:
        - Requires at least 2 active speakers in the session.
        - Requires total call speech > 0.
        - Disqualifies if all speakers spoke virtually identical duration (within 1.0s).
        Returns (speaker_id, total_speak_seconds, talk_share_pct) or None.
        """
        if len(self.speakers) < 2:
            return None

        speakers_list = list(self.speakers.values())
        total_talk_sec = sum(s.total_speak_seconds for s in speakers_list)
        if total_talk_sec <= 0:
            return None

        sorted_by_talk = sorted(speakers_list, key=lambda s: s.total_speak_seconds)
        quietest = sorted_by_talk[0]
        second_quietest = sorted_by_talk[1]

        # Honest tie guard: second quietest speaker must have spoken at least 1.0s more than the quietest.
        # This properly guards both 2-speaker calls (Alice vs Bob) and N-speaker calls where multiple speakers tie for least speech.
        if (second_quietest.total_speak_seconds - quietest.total_speak_seconds) < 1.0:
            return None

        share_pct = round((quietest.total_speak_seconds / total_talk_sec) * 100.0, 1)
        return (quietest.speaker_id, quietest.total_speak_seconds, share_pct)

    def get_most_unfiltered(self) -> Optional[Tuple[str, int, List[str]]]:
        """
        Identifies 'The Most Unfiltered / Spicy Tongue' (speaker with highest vulgarity count > 0).
        Rules:
        - Requires at least 1 speaker with vulgarity_count > 0.
        - Disqualifies if the top two speakers tie for vulgarity count.
        Returns (speaker_id, vulgarity_count, vulgarity_terms) or None.
        """
        if len(self.speakers) < 2:
            return None

        speakers_with_vulgarity = [s for s in self.speakers.values() if s.vulgarity_count > 0]
        if not speakers_with_vulgarity:
            return None

        sorted_by_vulgarity = sorted(speakers_with_vulgarity, key=lambda s: s.vulgarity_count, reverse=True)
        top_speaker = sorted_by_vulgarity[0]

        # Honest tie guard: if 2+ speakers have vulgarity and top 2 are tied, refuse false crown
        if len(sorted_by_vulgarity) >= 2:
            runner_up = sorted_by_vulgarity[1]
            if runner_up.vulgarity_count == top_speaker.vulgarity_count:
                return None

        return (top_speaker.speaker_id, top_speaker.vulgarity_count, list(top_speaker.vulgarity_terms))

    def get_diplomat(self) -> Optional[Tuple[str, float]]:
        """
        Identifies 'The Diplomat' (speaker who participated meaningfully with 0 vulgarity and 0 anger).
        Rules:
        - Requires at least 2 active speakers in the session.
        - Requires total call speech > 0.
        - Speaker must have vulgarity_count == 0 and angry_episodes == 0.
        - Speaker must have substantial talk time (>= 15.0 seconds).
        - If multiple qualify, crowns the one with the most speech.
        - Disqualifies if the top two candidates tie within 1.0 second.
        Returns (speaker_id, total_speak_seconds) or None.
        """
        if len(self.speakers) < 2:
            return None

        total_talk_sec = sum(s.total_speak_seconds for s in self.speakers.values())
        if total_talk_sec <= 0:
            return None

        candidates = [
            s for s in self.speakers.values()
            if s.vulgarity_count == 0 and s.angry_episodes == 0 and s.total_speak_seconds >= 15.0
        ]
        if not candidates:
            return None

        sorted_candidates = sorted(candidates, key=lambda s: s.total_speak_seconds, reverse=True)
        best = sorted_candidates[0]

        # Honest tie guard: if top 2 candidates are within 1.0s of each other, refuse false crown
        if len(candidates) >= 2:
            runner_up = sorted_candidates[1]
            if (best.total_speak_seconds - runner_up.total_speak_seconds) < 1.0:
                return None

        return (best.speaker_id, best.total_speak_seconds)

    def get_total_vulgarity_count(self) -> int:
        """Returns the total number of banter/vulgarity tokens recorded across all speakers."""
        return sum(s.vulgarity_count for s in self.speakers.values())

    def record_banter(self, speaker_ids: List[str], terms: Optional[List[str]] = None) -> None:
        """Records a resolved friendly banter exchange for the participating speakers."""
        for spk_id in speaker_ids:
            spk = self.get_or_create_speaker(str(spk_id))
            spk.record_banter(terms)

    def get_total_banter_count(self) -> int:
        """Returns the total number of friendly banter interactions across all speakers."""
        return sum(s.banter_count for s in self.speakers.values())

    def get_roast_master(self) -> Optional[Tuple[str, int, List[str]]]:
        """
        Identifies 'The Roast Master' (ملك الضحك والمناوشات):
        Speaker with highest banter_count (>0), requiring >= 2 speakers in call,
        with honest tie breaking guard.
        Returns (speaker_id, banter_count, banter_terms) or None.
        """
        if len(self.speakers) < 2:
            return None

        speakers_with_banter = [s for s in self.speakers.values() if s.banter_count > 0]
        if not speakers_with_banter:
            return None

        speakers_with_banter.sort(key=lambda s: s.banter_count, reverse=True)
        top_speaker = speakers_with_banter[0]

        # Honest tie guard: If top 2 tied, refuse to crown a fake winner
        if len(speakers_with_banter) >= 2 and speakers_with_banter[1].banter_count == top_speaker.banter_count:
            return None

        return (top_speaker.speaker_id, top_speaker.banter_count, list(top_speaker.banter_terms))

    def reset(self):
        """Clears all session statistics."""
        self.speakers.clear()
        self.last_speaker_id = None
        self.primary_speaker_id = None
        self.topic_durations.clear()
        self.topic_counts.clear()
