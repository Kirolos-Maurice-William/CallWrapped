import io
import base64
import logging
from typing import Optional
import edge_tts
from app.config import settings

logger = logging.getLogger(__name__)

class TTSService:
    @staticmethod
    async def synthesize_speech(text: str) -> Optional[str]:
        """
        Synthesizes text into base64 encoded MP3 audio.
        Supports edge-tts (free, zero API key) and OpenAI TTS.
        """
        # Auto-detect language of interruption
        has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
        voice = settings.TTS_VOICE_AR if has_arabic else settings.TTS_VOICE_EN

        # 1. Edge TTS
        if settings.TTS_PROVIDER == "edge-tts" or not settings.OPENAI_API_KEY:
            try:
                communicate = edge_tts.Communicate(text, voice)
                audio_stream = io.BytesIO()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_stream.write(chunk["data"])
                
                audio_bytes = audio_stream.getvalue()
                if audio_bytes:
                    b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    return f"data:audio/mp3;base64,{b64}"
            except Exception as e:
                logger.error(f"[TTS] Edge-TTS generation error: {e}")

        # 2. OpenAI TTS
        if settings.OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=text
                )
                b64 = base64.b64encode(response.content).decode("utf-8")
                return f"data:audio/mp3;base64,{b64}"
            except Exception as e:
                logger.error(f"[TTS] OpenAI TTS generation error: {e}")

        return None
