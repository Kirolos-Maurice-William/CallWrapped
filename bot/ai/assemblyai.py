import time
import asyncio
import logging
from typing import Optional, Tuple
import httpx
from bot.config import config

logger = logging.getLogger("AssemblyAI")

HALLUCINATION_BLACKLIST = {
    "شكرا", "شكرا لك", "شكرا لكم", "شكرا جزيلا",
    "thank you", "thanks", "thanks for watching",
    "subscribe", "اشترك", "اشترك في القناة",
    "مع السلامة", "وداعا", "bye", "goodbye",
    "mbc", "alarabiya", "الجزيرة"
}

# Contextual prompts for AssemblyAI Universal-3.5 Pro Code-Switching
ASSEMBLYAI_CONTEXT_PROMPT = (
    "Casual Egyptian Arabic gaming conversation with frequent English gaming, "
    "technology, hardware and internet slang."
)

ASSEMBLYAI_KEYTERMS = [
    "ping", "ranked", "update", "Discord", "Minecraft", "FPS", "packet loss",
    "stream", "lag", "RTX", "VRAM", "5070", "GPU", "bro", "server", "admin"
]


VALID_ASSEMBLYAI_MODELS = {"universal-3-5-pro", "universal-3-pro", "universal-2"}


class AssemblyAIClient:
    """
    AssemblyAI Universal-3.5 Pro Client.
    Captures raw verbatim speech with native Arabic + English code-switching.
    Preserves raw transcript as immutable evidence.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.ASSEMBLYAI_API_KEY
        self.upload_url = "https://api.assemblyai.com/v2/upload"
        self.transcript_url = "https://api.assemblyai.com/v2/transcript"

    async def transcribe(self, wav_bytes: bytes, speaker_name: str = "unknown") -> Tuple[Optional[str], int]:
        """Transcribes audio and returns (raw_text, latency_ms)."""
        if not self.api_key or not wav_bytes or len(wav_bytes) < 1000:
            return None, 0

        t0 = time.perf_counter()
        headers = {"Authorization": self.api_key}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # 1. Fast upload
                upload_resp = await client.post(self.upload_url, headers=headers, content=wav_bytes)
                if upload_resp.status_code != 200:
                    logger.error(f"[AssemblyAI] Upload failed ({upload_resp.status_code}): {upload_resp.text}")
                    return None, 0
                upload_url = upload_resp.json().get("upload_url")

                # Sanitize models list to protect against 400 Bad Request
                valid_models = [m for m in config.SPEECH_MODELS if m in VALID_ASSEMBLYAI_MODELS]
                if not valid_models:
                    valid_models = ["universal-3-5-pro", "universal-2"]

                # 2. Submit transcription job with code-switching prompts
                job_payload = {
                    "audio_url": upload_url,
                    "language_code": config.SPEECH_LANGUAGE,
                    "speech_models": valid_models,
                    "punctuate": True,
                    "format_text": True,
                    "prompt": ASSEMBLYAI_CONTEXT_PROMPT,
                    "keyterms_prompt": ASSEMBLYAI_KEYTERMS
                }
                job_resp = await client.post(self.transcript_url, headers=headers, json=job_payload)
                if job_resp.status_code != 200:
                    logger.error(f"[AssemblyAI] Job submission failed ({job_resp.status_code}) for {speaker_name}: {job_resp.text}")
                    return None, 0

                job_id = job_resp.json().get("id")
                poll_url = f"{self.transcript_url}/{job_id}"

                # 3. Poll for completion (budget from config: default 40 attempts * 0.5s = 20s)
                attempts = getattr(config, "ASSEMBLYAI_POLL_ATTEMPTS", 40)
                interval = getattr(config, "ASSEMBLYAI_POLL_INTERVAL_SEC", 0.5)
                for _ in range(attempts):
                    await asyncio.sleep(interval)
                    poll_resp = await client.get(poll_url, headers=headers)
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        status = data.get("status")
                        if status == "completed":
                            text = data.get("text", "").strip()
                            words = data.get("words", [])
                            latency_ms = int((time.perf_counter() - t0) * 1000)

                            # Filter hallucinations
                            if text.lower().rstrip(".!?،") in HALLUCINATION_BLACKLIST:
                                return None, latency_ms

                            avg_conf = 0.0
                            if words:
                                avg_conf = sum(w.get("confidence", 0) for w in words) / len(words)

                            if text and len(text) <= 5 and avg_conf < 0.55:
                                return None, latency_ms

                            logger.info(f"✅ [AssemblyAI Raw] ({latency_ms}ms, conf={avg_conf:.0%}): {text}")
                            return text, latency_ms
                        elif status == "error":
                            err_msg = data.get("error", "Unknown error")
                            logger.warning(f"[AssemblyAI] Transcription error for {speaker_name}: {err_msg}")
                            return None, 0

                latency_ms = int((time.perf_counter() - t0) * 1000)
                logger.warning(f"[AssemblyAI] STT timeout, utterance dropped for {speaker_name} ({latency_ms}ms, {attempts} attempts)")
                return None, latency_ms
            except Exception as e:
                logger.warning(f"[AssemblyAI] Network error: {e}")
                return None, 0


assemblyai_client = AssemblyAIClient()
