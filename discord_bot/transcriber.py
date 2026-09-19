import logging
import io
import httpx
from typing import Optional
from .config import config

logger = logging.getLogger(__name__)

class GroqWhisperTranscriber:
    """
    Ultra-Fast Egyptian Arabic / Multilingual Speech-to-Text via Groq Whisper.
    Sub-200ms latency, high dialect accuracy, robust to colloquial terms and slang.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"
        self.model = config.WHISPER_MODEL
        self.language = config.SPEECH_LANGUAGE
        self.prompt = config.WHISPER_PROMPT

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        """Transcribes in-memory WAV audio bytes and returns the recognized text."""
        if not self.api_key:
            logger.warning("[Transcriber] No GROQ_API_KEY configured. Skipping STT.")
            return None

        if len(wav_bytes) < 1000:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }

        data = {
            "model": self.model,
            "language": self.language,
            "prompt": self.prompt,
            "response_format": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    self.url,
                    headers=headers,
                    files=files,
                    data=data
                )

                if response.status_code == 200:
                    result = response.json()
                    text = result.get("text", "").strip()
                    if text:
                        return text
                    return None
                else:
                    logger.error(f"[Transcriber] Groq API returned status {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"[Transcriber] Error during transcription: {e}")
            return None

# Global transcriber instance
transcriber = GroqWhisperTranscriber()
