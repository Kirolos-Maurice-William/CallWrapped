import unittest
import io
import wave
import numpy as np
from bot.audio.pcm import trim_trailing_silence_wav, convert_discord_pcm_to_wav
from bot.config import config

class TestSilenceTrim(unittest.TestCase):
    def _generate_wav(self, duration_s: float, freq: float = 440.0, silence_s: float = 1.0, sample_rate: int = 16000) -> bytes:
        total_samples = int(duration_s * sample_rate)
        tone_samples = int((duration_s - silence_s) * sample_rate)
        
        t = np.linspace(0, (duration_s - silence_s), tone_samples, endpoint=False)
        tone = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
        silence = np.zeros(total_samples - tone_samples, dtype=np.int16)
        samples = np.concatenate([tone, silence])
        
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
        return buf.getvalue()

    def test_trim_trailing_silence_removes_silence(self):
        # 3.0s total: 2.0s tone + 1.0s silence
        wav_with_silence = self._generate_wav(duration_s=3.0, freq=440.0, silence_s=1.0)
        with wave.open(io.BytesIO(wav_with_silence), "rb") as wf:
            orig_frames = wf.getnframes()
        
        trimmed = trim_trailing_silence_wav(wav_with_silence, threshold_rms=80.0, pad_ms=150)
        with wave.open(io.BytesIO(trimmed), "rb") as wf:
            trimmed_frames = wf.getnframes()
        
        orig_sec = orig_frames / 16000.0
        trimmed_sec = trimmed_frames / 16000.0
        
        self.assertAlmostEqual(orig_sec, 3.0, delta=0.05)
        # Tone is 2.0s, pad is 150ms -> ~2.15s
        self.assertLess(trimmed_sec, 2.3)
        self.assertGreater(trimmed_sec, 2.0)

    def test_trim_trailing_silence_pure_tone_intact(self):
        # 2.0s tone, 0s silence
        wav_pure = self._generate_wav(duration_s=2.0, freq=440.0, silence_s=0.0)
        trimmed = trim_trailing_silence_wav(wav_pure, threshold_rms=80.0, pad_ms=150)
        with wave.open(io.BytesIO(trimmed), "rb") as wf:
            trimmed_frames = wf.getnframes()
        self.assertAlmostEqual(trimmed_frames / 16000.0, 2.0, delta=0.05)

    def test_trim_edge_cases(self):
        self.assertEqual(trim_trailing_silence_wav(b""), b"")
        self.assertEqual(trim_trailing_silence_wav(b"too_short"), b"too_short")
        corrupt = b"RIFF____WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00corrupt"
        # Should not crash on invalid data
        res = trim_trailing_silence_wav(corrupt)
        self.assertTrue(len(res) > 0)

    def test_convert_discord_pcm_trims_trailing_silence(self):
        # 20ms frame = 960 samples stereo = 3840 bytes
        frame_tone = (np.ones(960 * 2, dtype=np.int16) * 5000).tobytes()
        frame_silence = (np.zeros(960 * 2, dtype=np.int16)).tobytes()
        
        # 10 frames tone (200ms) + 10 frames silence (200ms)
        chunks = [frame_tone] * 10 + [frame_silence] * 10
        wav_bytes = convert_discord_pcm_to_wav(chunks)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            dur = wf.getnframes() / 16000.0
        
        # Original was 400ms, tone was 200ms + 150ms pad = 350ms
        self.assertLess(dur, 0.40)
        self.assertGreaterEqual(dur, 0.20)

if __name__ == "__main__":
    unittest.main()
