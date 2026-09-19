import io
import time
import asyncio
import logging
import httpx
from typing import Optional
from .config import config

logger = logging.getLogger(__name__)

# Known hallucination patterns Whisper outputs when fed silence / background noise
WHISPER_HALLUCINATIONS = [
    "نانسي", "قنقر", "ترجمة", "اشترك", "قناة", "تحرير من شباب",
    "subtitles", "amara.org", "mbc", "watching", "subscribe", "translated by"
]

def is_hallucination(text: str) -> bool:
    """Detects if Whisper hallucinated subtitle credits on silent audio."""
    text_clean = text.strip()
    if not text_clean or len(text_clean) < 2:
        return True
    for pat in WHISPER_HALLUCINATIONS:
        if pat in text_clean:
            return True
    return False


class AssemblyAITranscriber:
    """
    Primary Speech-to-Text Transcriber using AssemblyAI.
    Uploads audio, requests Arabic transcription, and consumes credits from user's account.
    Returns:
      - str (transcribed text) if speech found
      - "" (empty string) if AssemblyAI successfully analyzed and found silence/no speech
      - None only if network/HTTP error occurred
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
                            words = data.get("words", [])
                            duration = data.get("audio_duration", 0)
                            elapsed = (time.perf_counter() - t0) * 1000

                            # Calculate average word confidence
                            avg_conf = 0.0
                            if words:
                                avg_conf = sum(w.get("confidence", 0) for w in words) / len(words)

                            logger.info(
                                f"✅ [AssemblyAI API] Transcribed {duration}s in {elapsed:.0f}ms "
                                f"(Confidence: {avg_conf:.0%}, Words: {len(words)}): {text}"
                            )

                            # Filter out low-confidence short guesses (noise artifacts like "أنا.")
                            if text and len(text) <= 5 and avg_conf < 0.55:
                                logger.info(
                                    f"🛡️ [Low Confidence Filter] Rejected '{text}' "
                                    f"(conf={avg_conf:.0%}, len={len(text)})"
                                )
                                return ""

                            # Return text (even if empty string) to indicate successful processing!
                            return text
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
    Strictly filters out any silent-frame subtitle hallucinations.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"
        self.model = config.WHISPER_MODEL
        self.language = config.SPEECH_LANGUAGE

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not self.api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }
        # Do not send any hallucination-prone prompt
        data = {
            "model": self.model,
            "language": self.language,
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
                    if is_hallucination(text):
                        logger.info(f"🛡️ [Filtered Hallucination] Ignored Whisper output: '{text}'")
                        return None
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
    Orchestrates transcription:
    1. AssemblyAI is PRIMARY: Consumes account credits.
       - If AssemblyAI completes with text -> Returns speech text.
       - If AssemblyAI completes with empty text -> It was silence, returns None (NO hallucination!).
    2. Groq Whisper is FALLBACK: Only called if AssemblyAI has a network/HTTP outage.
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
                res = await self.assemblyai.transcribe_wav(wav_bytes)
                if res is not None:
                    # AssemblyAI successfully processed the audio
                    clean = res.strip()
                    if clean and not is_hallucination(clean):
                        return clean
                    # If clean is empty, it was pure silence or non-speech noise -> Do NOT hallucinate!
                    return None
            except Exception as e:
                logger.warning(f"AssemblyAI failed with exception: {e}")

        # 2. Fallback to Groq Whisper only if AssemblyAI was unavailable
        res = await self.groq.transcribe_wav(wav_bytes)
        if res and not is_hallucination(res):
            return res.strip()
        return None


# Global transcriber instance
transcriber = UnifiedTranscriber()
