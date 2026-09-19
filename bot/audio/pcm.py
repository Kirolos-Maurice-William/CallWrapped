import io
import wave
from typing import List
import numpy as np
from bot.config import config


def convert_discord_pcm_to_wav(pcm_chunks: List[bytes]) -> bytes:
    """
    Converts a list of Discord 48kHz stereo 16-bit PCM frames into a clean 16kHz mono WAV.
    Uses numpy 3-sample boxcar anti-aliasing filter for maximum clarity and sub-5ms performance.
    """
    if not pcm_chunks:
        return b""
    raw_bytes = b"".join(pcm_chunks)
    stereo_data = np.frombuffer(raw_bytes, dtype=np.int16)
    if stereo_data.size < 2:
        return b""

    # Reshape to (N, 2) and average stereo to mono
    stereo_matrix = stereo_data.reshape(-1, 2)
    mono_48k = stereo_matrix.mean(axis=1).astype(np.int16)

    # Downsample 48kHz -> 16kHz (3:1 integer decimation with anti-aliasing averaging)
    remainder = mono_48k.size % 3
    if remainder != 0:
        mono_48k = mono_48k[:-remainder]
    mono_16k = mono_48k.reshape(-1, 3).mean(axis=1).astype(np.int16)

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(mono_16k.tobytes())
    return wav_buf.getvalue()


class UserSpeechBuffer:
    """Tracks active speaking state, PCM frame buffer, and silence timing for a specific user.
    Includes a pre-roll ring buffer (~100ms) so speech onset is never clipped."""
    PRE_ROLL_FRAMES = 5

    def __init__(self, user_id: int, user_name: str):
        self.user_id = user_id
        self.user_name = user_name
        self.pcm_chunks: List[bytes] = []
        self.speech_start_time: float = 0.0
        self.last_speech_time: float = 0.0
        self.is_speaking: bool = False
        self._pre_roll: List[bytes] = []

    def add_frame(self, pcm_bytes: bytes, rms: float, now: float):
        if rms >= config.SILENCE_THRESHOLD_RMS:
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_start_time = now
                if self._pre_roll:
                    self.pcm_chunks.extend(self._pre_roll)
                    self._pre_roll.clear()
            self.last_speech_time = now
            self.pcm_chunks.append(pcm_bytes)
        elif self.is_speaking:
            self.pcm_chunks.append(pcm_bytes)
        else:
            self._pre_roll.append(pcm_bytes)
            if len(self._pre_roll) > self.PRE_ROLL_FRAMES:
                self._pre_roll.pop(0)

    def duration(self) -> float:
        return (len(self.pcm_chunks) * 3840) / (48000 * 4)

    def reset(self):
        self.pcm_chunks = []
        self.is_speaking = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self._pre_roll.clear()
