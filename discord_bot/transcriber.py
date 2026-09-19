import io
import time
import asyncio
import logging
import httpx
from typing import Optional
from .config import config

logger = logging.getLogger(__name__)

class AssemblyAITranscriber:
    """
    Primary Speech-to-Text Transcriber using AssemblyAI.
    Uploads audio, requests Arabic transcription, and consumes credits from user's account.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.ASSEMBLYAI_API_KEY
        self.upload_url = "https://api.assemblyai.com/v2/upload"
        self.transcript_url = "https://api.assemblyai.com/v2/transcript"

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not self.api_key:
            return None

        headers = {
            "Authorization": self.api_key
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Upload audio to AssemblyAI CDN
                t0 = time.perf_counter()
                up_resp = await client.post(
                    self.upload_url,
                    headers=headers,
                    content=wav_bytes
                )
                if up_resp.status_code != 200:
                    logger.warning(f"[AssemblyAI] Upload failed with status {up_resp.status_code}: {up_resp.text}")
                    return None

                upload_url = up_resp.json().get("upload_url")
                if not upload_url:
                    return None

                # 2. Submit transcription job (Arabic speech model)
                job_payload = {
                    "audio_url": upload_url,
                    "language_code": config.SPEECH_LANGUAGE
                }
                job_resp = await client.post(
                    self.transcript_url,
                    headers=headers,
                    json=job_payload
                )
                if job_resp.status_code != 200:
                    logger.warning(f"[AssemblyAI] Job submission failed {job_resp.status_code}: {job_resp.text}")
                    return None

                job_id = job_resp.json().get("id")
                poll_url = f"{self.transcript_url}/{job_id}"

                # 3. Poll for completion (up to 5 seconds max)
                for _ in range(10):
                    await asyncio.sleep(0.5)
                    poll_resp = await client.get(poll_url, headers=headers)
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        status = data.get("status")
                        if status == "completed":
                            text = data.get("text", "").strip()
                            duration = data.get("audio_duration", 0)
                            elapsed = (time.perf_counter() - t0) * 1000
                            logger.info(f"✅ [AssemblyAI API] Transcribed {duration}s in {elapsed:.0f}ms (Credit Consumed): {text}")
                            return text if text else None
                        elif status == "error":
                            logger.error(f"[AssemblyAI API] Transcription error: {data.get('error')}")
                            return None

                logger.warning(f"[AssemblyAI API] Polling timed out for job {job_id}")
                return None

        except Exception as e:
            logger.error(f"[AssemblyAI API] Exception during transcription: {e}")
            return None


class GroqWhisperTranscriber:
    """
    High-Speed Fallback Speech-to-Text using Groq Whisper Large v3 Turbo.
    Sub-200ms latency, high Egyptian Arabic dialect accuracy.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"
        self.model = config.WHISPER_MODEL
        self.language = config.SPEECH_LANGUAGE
        self.prompt = config.WHISPER_PROMPT

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not self.api_key:
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
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    self.url,
                    headers=headers,
                    files=files,
                    data=data
                )
                if response.status_code == 200:
                    text = response.json().get("text", "").strip()
                    logger.info(f"⚡ [Groq Whisper STT] Transcribed: {text}")
                    return text if text else None
                else:
                    logger.warning(f"[Groq Whisper] Returned status {response.status_code}: {response.text}")
                    return None
        except Exception as e:
            logger.error(f"[Groq Whisper] Exception: {e}")
            return None


class UnifiedTranscriber:
    """
    Orchestrates transcription with AssemblyAI as Primary provider to consume account credits,
    with automatic seamless fallback to Groq Whisper if AssemblyAI encounters an issue.
    """
    def __init__(self):
        self.assemblyai = AssemblyAITranscriber()
        self.groq = GroqWhisperTranscriber()

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not wav_bytes or len(wav_bytes) < 1000:
            return None

        # 1. Try AssemblyAI First (Consumes user credits)
        if config.PRIMARY_STT_PROVIDER == "assemblyai" and config.ASSEMBLYAI_API_KEY:
            try:
                text = await self.assemblyai.transcribe_wav(wav_bytes)
                if text:
                    return text
            except Exception as e:
                logger.warning(f"AssemblyAI failed, falling back to Groq: {e}")

        # 2. Fallback to Groq Whisper Large v3
        return await self.groq.transcribe_wav(wav_bytes)


# Global transcriber instance
transcriber = UnifiedTranscriber()
