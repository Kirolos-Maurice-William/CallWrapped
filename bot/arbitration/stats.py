import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

logger = logging.getLogger("TalkStats")

# Taxonomy v3 display name mappings (colloquial Egyptian Arabic)
TOPIC_DISPLAY_NAMES: Dict[str, str] = {
    "food": "أكل",
    "travel": "سفر",
    "study_work": "دراسة وشغل",
    "health": "صحة",
    "cars": "عربيات",
    "money": "فلوس",
    "football": "كورة",
    "politics": "سياسة",
    "music": "مزيكا",
    "movies": "أفلام",
    "gaming": "ألعاب",
    "tech": "تكنولوجيا",
    "personal": "شخصي",
    "personal_life": "شخصي",
    "other": "أخرى",
    "null_topic": "بدون موضوع",
}


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
    # Topic streak tracking (Taxonomy v2)
    current_topic: Optional[str] = None
    current_topic_streak: float = 0.0
    longest_topic_streak_seconds: float = 0.0
    longest_topic: Optional[str] = None
    topic_streak_count: int = 0

    @property
    def current_streak_seconds(self) -> float:
        """Alias for current_streak in seconds."""
        return self.current_streak

    @property
    def topic_streak(self) -> float:
        """Alias for current_topic_streak in seconds."""
        return self.current_topic_streak

    def record_anger(
        self,
        timestamp: float,
        anger: Any,
        quote: Optional[str] = None
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

        # Consecutive angry classifications within 90s = 1 episode
        is_new_episode = False
        if self.angry_episodes == 0 or (timestamp - self.last_anger_time) > 90.0:
            self.angry_episodes += 1
            is_new_episode = True

        self.last_anger_time = timestamp

        if self.first_anger_quote is None and extracted_quote:
            self.first_anger_quote = extracted_quote

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
            "current_topic": self.current_topic,
            "current_topic_streak": round(self.current_topic_streak, 3),
            "longest_topic_streak_seconds": round(self.longest_topic_streak_seconds, 3),
            "longest_topic": self.longest_topic,
            "topic_streak_count": self.topic_streak_count
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
        topic: Optional[str] = None
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
        speaker_name: Optional[str] = None
    ) -> SpeakerStats:
        """
        Records an anger classification for a speaker.
        Consecutive angry classifications within a 90-second window per speaker = ONE episode.
        """
        spk_key = str(speaker_id)
        stats = self.get_or_create_speaker(spk_key, speaker_name)
        stats.record_anger(timestamp=timestamp, anger=anger, quote=anger_quote)
        return stats

    def reset(self):
        """Clears all session statistics."""
        self.speakers.clear()
        self.last_speaker_id = None
        self.primary_speaker_id = None
        self.topic_durations.clear()
        self.topic_counts.clear()
