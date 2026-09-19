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

    async def transcribe(self, wav_bytes: bytes) -> Tuple[Optional[str], int]:
        """Transcribes audio and returns (raw_text, latency_ms)."""
        if not self.api_key or not wav_bytes or len(wav_bytes) < 1000:
            return None, 0

        t0 = time.perf_counter()
        headers = {"Authorization": self.api_key}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # 1. Fast upload
                upload_resp = await client.post(self.upload_url, headers=headers, content=wav_bytes)
                if upload_resp.status_code != 200:
                    return None, 0
                upload_url = upload_resp.json().get("upload_url")

                # 2. Submit transcription job with code-switching prompts
                job_payload = {
                    "audio_url": upload_url,
                    "language_code": config.SPEECH_LANGUAGE,
                    "speech_models": config.SPEECH_MODELS,
                    "punctuate": True,
                    "format_text": True,
                    "prompt": ASSEMBLYAI_CONTEXT_PROMPT,
                    "keyterms_prompt": ASSEMBLYAI_KEYTERMS
                }
                job_resp = await client.post(self.transcript_url, headers=headers, json=job_payload)
                if job_resp.status_code != 200:
                    return None, 0

                job_id = job_resp.json().get("id")
                poll_url = f"{self.transcript_url}/{job_id}"

                # 3. Poll for completion (responsive 0.25s intervals)
                for _ in range(24):
                    await asyncio.sleep(0.25)
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
                            return None, 0

                return None, 0
            except Exception as e:
                logger.warning(f"[AssemblyAI] Network error: {e}")
                return None, 0


assemblyai_client = AssemblyAIClient()
