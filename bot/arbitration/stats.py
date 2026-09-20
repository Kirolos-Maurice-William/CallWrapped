import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

logger = logging.getLogger("TalkStats")


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

    @property
    def current_streak_seconds(self) -> float:
        """Alias for current_streak in seconds."""
        return self.current_streak

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
            "first_anger_quote": self.first_anger_quote
        }


class SessionStatsTracker:
    """
    Tracks per-speaker real-time speech statistics and monologue streaks.
    STREAK DEFINITION:
    Consecutive utterances by the same speaker where the gap between this utterance's
    start and the speaker's prior utterance end is < 5s AND no other user spoke in between.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or "default"
        self.speakers: Dict[str, SpeakerStats] = {}
        self.last_speaker_id: Optional[str] = None

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
        classification: Optional[Dict[str, Any]] = None
    ) -> SpeakerStats:
        """
        Records an utterance derived strictly from RMS speech-window timestamps.
        Never infers duration from WAV byte counts or transcript lengths.
        Optionally records anger classification.
        """
        spk_key = str(speaker_id)
        duration = max(0.0, speech_end - speech_start)
        stats = self.get_or_create_speaker(spk_key, speaker_name)

        # 1. Update basic totals
        stats.total_speak_seconds += duration
        stats.utterance_count += 1

        # 2. Break active streaks for all OTHER speakers since this speaker spoke
        for other_id, other_stats in self.speakers.items():
            if other_id != spk_key:
                other_stats.current_streak = 0.0

        # 3. Evaluate streak for the active speaker
        another_user_spoke = (self.last_speaker_id is not None and self.last_speaker_id != spk_key)
        gap = (speech_start - stats.last_utterance_end) if stats.last_utterance_end > 0 else float('inf')

        if not another_user_spoke and gap < 5.0 and stats.last_utterance_end > 0:
            # Streak continues (e.g. 15s force-split continuation or short pause < 5s)
            stats.current_streak += duration
        else:
            # New streak begins
            stats.current_streak = duration

        # Update high-water mark
        if stats.current_streak > stats.longest_streak_seconds:
            stats.longest_streak_seconds = stats.current_streak

        stats.last_utterance_end = speech_end
        self.last_speaker_id = spk_key

        # 4. Pure Python anger episode tracking on top of classifier output
        if classification is not None:
            stats.record_anger(timestamp=speech_end, anger=classification)
        elif anger is not None:
            stats.record_anger(timestamp=speech_end, anger=anger, quote=anger_quote)

        logger.debug(
            f"[TalkStats] Speaker {spk_key} ({speaker_name}): dur={duration:.2f}s, "
            f"total={stats.total_speak_seconds:.2f}s, streak={stats.current_streak:.2f}s, "
            f"longest={stats.longest_streak_seconds:.2f}s, angry_episodes={stats.angry_episodes}"
        )
        return stats

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

    def record_classification(
        self,
        speaker_id: str,
        timestamp: float,
        classification: Dict[str, Any],
        speaker_name: Optional[str] = None
    ) -> SpeakerStats:
        """
        Convenience method to record classifier output directly.
        """
        spk_key = str(speaker_id)
        stats = self.get_or_create_speaker(spk_key, speaker_name)
        stats.record_anger(timestamp=timestamp, anger=classification)
        return stats

    def reset(self):
        """Clears all session statistics."""
        self.speakers.clear()
        self.last_speaker_id = None
