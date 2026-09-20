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

    @property
    def current_streak_seconds(self) -> float:
        """Alias for current_streak in seconds."""
        return self.current_streak

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name or self.speaker_id,
            "total_speak_seconds": round(self.total_speak_seconds, 3),
            "utterance_count": self.utterance_count,
            "longest_streak_seconds": round(self.longest_streak_seconds, 3),
            "current_streak": round(self.current_streak, 3),
            "last_utterance_end": round(self.last_utterance_end, 3)
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
        speaker_name: Optional[str] = None
    ) -> SpeakerStats:
        """
        Records an utterance derived strictly from RMS speech-window timestamps.
        Never infers duration from WAV byte counts or transcript lengths.
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

        logger.debug(
            f"[TalkStats] Speaker {spk_key} ({speaker_name}): dur={duration:.2f}s, "
            f"total={stats.total_speak_seconds:.2f}s, streak={stats.current_streak:.2f}s, "
            f"longest={stats.longest_streak_seconds:.2f}s"
        )
        return stats

    def reset(self):
        """Clears all session statistics."""
        self.speakers.clear()
        self.last_speaker_id = None
