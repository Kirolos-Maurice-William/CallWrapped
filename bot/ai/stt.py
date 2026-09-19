import time
import asyncio
import logging
from typing import Optional
import httpx
from bot.config import config
from bot.ai.dialect import dialect_corrector

logger = logging.getLogger("STT")

# Common hallucination phrases from background silence
HALLUCINATION_BLACKLIST = {
    "شكرا", "شكرا لك", "شكرا لكم", "شكرا جزيلا",
    "thank you", "thanks", "thanks for watching",
    "subscribe", "اشترك", "اشترك في القناة",
    "مع السلامة", "وداعا", "bye", "goodbye",
    "mbc", "alarabiya", "الجزيرة"
}


def is_hallucination(text: str) -> bool:
    clean = text.strip().lower().rstrip(".!?،")
    return clean in HALLUCINATION_BLACKLIST


class AssemblyAITranscriber:
    """Asynchronous client for AssemblyAI's flagship Universal-3.5 Pro Arabic/English STT."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.ASSEMBLYAI_API_KEY
        self.upload_url = "https://api.assemblyai.com/v2/upload"
        self.transcript_url = "https://api.assemblyai.com/v2/transcript"

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not self.api_key or not wav_bytes or len(wav_bytes) < 1000:
            return None

        t0 = time.perf_counter()
        headers = {"Authorization": self.api_key}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # 1. Upload audio
                upload_resp = await client.post(
                    self.upload_url,
                    headers=headers,
                    content=wav_bytes
                )
                if upload_resp.status_code != 200:
                    logger.warning(f"[AssemblyAI] Upload failed {upload_resp.status_code}: {upload_resp.text}")
                    return None

                upload_url = upload_resp.json().get("upload_url")
                if not upload_url:
                    return None

                # 2. Submit transcription job with Universal-3.5 Pro model
                job_payload = {
                    "audio_url": upload_url,
                    "language_code": config.SPEECH_LANGUAGE,
                    "speech_models": config.SPEECH_MODELS,
                    "punctuate": True,
                    "format_text": True
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

                # 3. Poll for completion (responsive 0.25s intervals, up to 6s)
                for _ in range(24):
                    await asyncio.sleep(0.25)
                    poll_resp = await client.get(poll_url, headers=headers)
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        status = data.get("status")
                        if status == "completed":
                            text = data.get("text", "").strip()
                            words = data.get("words", [])
                            duration = data.get("audio_duration", 0)
                            elapsed = (time.perf_counter() - t0) * 1000

                            avg_conf = 0.0
                            if words:
                                avg_conf = sum(w.get("confidence", 0) for w in words) / len(words)

                            logger.info(
                                f"✅ [AssemblyAI API] Transcribed {duration}s in {elapsed:.0f}ms "
                                f"(Confidence: {avg_conf:.0%}, Words: {len(words)}): {text}"
                            )

                            # Filter out low-confidence short noise artifacts
                            if text and len(text) <= 5 and avg_conf < 0.55:
                                logger.info(f"🛡️ [Low Confidence Filter] Rejected '{text}' (conf={avg_conf:.0%})")
                                return ""

                            return text
                        elif status == "error":
                            logger.error(f"[AssemblyAI] Transcription error: {data.get('error')}")
                            return None

                logger.warning("[AssemblyAI] Transcription timed out.")
                return None
            except Exception as e:
                logger.warning(f"[AssemblyAI] Network/HTTP Exception: {e}")
                return None


class GroqWhisperTranscriber:
    """Fallback high-speed STT via Groq Cloud Whisper API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not self.api_key or not wav_bytes or len(wav_bytes) < 1000:
            return None

        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "model": "whisper-large-v3-turbo",
            "language": config.SPEECH_LANGUAGE,
            "response_format": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(self.url, headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    logger.info(f"⚡ [Groq Whisper Fallback] Transcribed: {text}")
                    return text
        except Exception as e:
            logger.error(f"[Groq Whisper] Exception: {e}")
        return None


class UnifiedTranscriber:
    """Orchestrates primary AssemblyAI STT + Groq dialect correction + Fallback."""

    def __init__(self):
        self.assemblyai = AssemblyAITranscriber()
        self.groq = GroqWhisperTranscriber()

    async def transcribe_wav(self, wav_bytes: bytes) -> Optional[str]:
        if not wav_bytes or len(wav_bytes) < 1000:
            return None

        text = None

        # 1. Primary: AssemblyAI (Consumes user credits with Universal-3.5 Pro)
        if config.PRIMARY_STT_PROVIDER == "assemblyai" and config.ASSEMBLYAI_API_KEY:
            try:
                res = await self.assemblyai.transcribe_wav(wav_bytes)
                if res is not None:
                    clean = res.strip()
                    if clean and not is_hallucination(clean):
                        text = clean
            except Exception as e:
                logger.warning(f"AssemblyAI exception: {e}")

        # 2. Fallback to Groq Whisper only if AssemblyAI had an outage
        if text is None:
            res = await self.groq.transcribe_wav(wav_bytes)
            if res and not is_hallucination(res):
                text = res.strip()

        if not text:
            return None

        # 3. Post-process with Groq Dialect Corrector for Egyptian & English loanwords
        polished = await dialect_corrector.correct_text(text)
        return polished


transcriber = UnifiedTranscriber()
