import asyncio
import json
import logging
import websockets
import time
from typing import Callable, Optional
from app.config import settings

try:
    import orjson
    def fast_json_dumps(obj): return orjson.dumps(obj).decode("utf-8")
    def fast_json_loads(s): return orjson.loads(s)
except ImportError:
    def fast_json_dumps(obj): return json.dumps(obj)
    def fast_json_loads(s): return json.loads(s)

logger = logging.getLogger(__name__)

EGYPTIAN_ARABIC_CONTEXT_PROMPT = (
    "This is a casual spoken conversation between two Egyptian speakers who naturally mix Egyptian Arabic "
    "and English (code-switching). Topics include movies, football, music, technology, politics, and gaming. "
    "Egyptian slang expressions, Arabic names, foreign celebrity names, and English terminology are expected."
)

DEFAULT_KEYTERMS = [
    "بص يا عم", "يا راجل", "حبيبي", "كورة", "الأهلي", "الزمالك",
    "Messi", "Ronaldo", "Inception", "Inter Miami", "basically", "actually", "bro"
]

class AssemblyAIRealtimeSession:
    """
    Ultra-Low Latency AssemblyAI Streaming Session (V3 Protocol).
    - Global Anycast edge routing: wss://streaming.assemblyai.com/v3/ws
    - Zero-copy raw binary PCM16 frames directly over WebSocket
    - Egyptian Arabic + English contextual prompt & dynamic keyterm boosting
    - Periodic heartbeat ping to eliminate socket idle latency
    """
    def __init__(
        self,
        call_id: str,
        speaker_id: str,
        speaker_name: str,
        on_partial: Callable[[dict], None],
        on_final: Callable[[dict], None],
        sample_rate: int = 16000
    ):
        self.call_id = call_id
        self.speaker_id = speaker_id
        self.speaker_name = speaker_name
        self.on_partial = on_partial
        self.on_final = on_final
        self.sample_rate = sample_rate
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.use_raw_binary = True

    async def connect(self):
        if not settings.ASSEMBLYAI_API_KEY or settings.ASSEMBLYAI_API_KEY == "your_assemblyai_api_key_here":
            logger.warning("[AssemblyAI] No API key provided. Simulated mode active.")
            self.is_running = True
            return

        # V3 Global Edge Endpoint locked to Arabic
        model = (settings.ASSEMBLYAI_MODEL or "universal-3-5-pro").replace(".", "-")
        url = f"wss://streaming.assemblyai.com/v3/ws?sample_rate={self.sample_rate}&speech_model={model}&language_codes=ar&language_code=ar"
        headers = {
            "Authorization": settings.ASSEMBLYAI_API_KEY
        }

        try:
            try:
                self.ws = await websockets.connect(
                    url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**24
                )
            except TypeError:
                self.ws = await websockets.connect(
                    url,
                    extra_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**24
                )
            self.is_running = True
            self.use_raw_binary = True
            logger.info(f"[AssemblyAI V3] Connected to Anycast Edge STT for {self.speaker_name}")

            # Send agent context configuration for bilingual Egyptian Arabic / English
            try:
                config_msg = {
                    "type": "UpdateConfiguration",
                    "agent_context": EGYPTIAN_ARABIC_CONTEXT_PROMPT
                }
                await self.ws.send(fast_json_dumps(config_msg))
            except Exception:
                pass

            self._receive_task = asyncio.create_task(self._listen())
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            return
        except Exception as e_v3:
            logger.error(f"[AssemblyAI V3] Connection failed for {self.speaker_name}: {e_v3}")
            self.is_running = False

    async def send_audio(self, audio_chunk: bytes):
        """Sends raw 16kHz PCM audio chunk with zero buffering delay."""
        if not self.ws or not self.is_running:
            return

        try:
            if self.use_raw_binary:
                # V3 accepts direct binary frame
                await self.ws.send(audio_chunk)
            else:
                import base64
                b64_audio = base64.b64encode(audio_chunk).decode("utf-8")
                await self.ws.send(fast_json_dumps({"audio_data": b64_audio}))
        except Exception as e:
            logger.error(f"[AssemblyAI] Error transmitting audio frame: {e}")

    async def _heartbeat(self):
        """Maintains socket hot and prevents TCP timeouts."""
        while self.is_running and self.ws:
            try:
                await asyncio.sleep(15)
                if self.ws and not self.ws.closed:
                    await self.ws.ping()
            except Exception:
                break

    async def _listen(self):
        """Receives partial and final transcripts from AssemblyAI WebSocket."""
        try:
            async for message in self.ws:
                t_recv = time.perf_counter()
                if isinstance(message, bytes):
                    message = message.decode("utf-8")

                data = fast_json_loads(message)
                msg_type = data.get("message_type") or data.get("type")

                # 1. Handle AssemblyAI V3 'Turn' messages
                if msg_type == "Turn":
                    text = (data.get("transcript") or data.get("text") or "").strip()
                    end_of_turn = data.get("end_of_turn", False)
                    if text:
                        # Discard noise turns with foreign scripts (CJK, Hebrew, Cyrillic, etc.)
                        has_cjk = any('\u4e00' <= char <= '\u9fff' or '\u3040' <= char <= '\u30ff' for char in text)
                        has_hebrew = any('\u0590' <= char <= '\u05ff' for char in text)
                        has_cyrillic = any('\u0400' <= char <= '\u04ff' for char in text)
                        if has_cjk or has_hebrew or has_cyrillic:
                            logger.debug(f"[AssemblyAI] Discarded foreign script hallucination: {text}")
                            continue

                        words = data.get("words", [])
                        start_ms = words[0]["start"] if (words and "start" in words[0]) else 0
                        end_ms = words[-1]["end"] if (words and "end" in words[-1]) else 0

                        # Language detection
                        has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
                        has_english = any('a' <= char.lower() <= 'z' for char in text)
                        lang = "mixed" if (has_arabic and has_english) else ("ar" if has_arabic else "en")

                        if end_of_turn:
                            logger.info(f"[AssemblyAI Turn Final] ({self.speaker_name}): {text}")
                            self.on_final({
                                "call_id": self.call_id,
                                "speaker_id": self.speaker_id,
                                "speaker_name": self.speaker_name,
                                "start_ms": start_ms,
                                "end_ms": end_ms,
                                "text": text,
                                "language": lang,
                                "is_final": True,
                                "t_stt_recv": t_recv
                            })
                        else:
                            self.on_partial({
                                "call_id": self.call_id,
                                "speaker_id": self.speaker_id,
                                "speaker_name": self.speaker_name,
                                "text": text,
                                "is_final": False,
                                "t_stt_recv": t_recv
                            })

                # 2. Backwards compatibility with V2 PartialTranscript
                elif msg_type in ("PartialTranscript", "partial"):
                    text = (data.get("text") or data.get("transcript") or "").strip()
                    if text:
                        self.on_partial({
                            "call_id": self.call_id,
                            "speaker_id": self.speaker_id,
                            "speaker_name": self.speaker_name,
                            "text": text,
                            "is_final": False,
                            "t_stt_recv": t_recv
                        })

                # 3. Backwards compatibility with V2 FinalTranscript
                elif msg_type in ("FinalTranscript", "final"):
                    text = (data.get("text") or data.get("transcript") or "").strip()
                    if text:
                        words = data.get("words", [])
                        start_ms = words[0]["start"] if (words and "start" in words[0]) else 0
                        end_ms = words[-1]["end"] if (words and "end" in words[-1]) else 0

                        has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
                        has_english = any('a' <= char.lower() <= 'z' for char in text)
                        lang = "mixed" if (has_arabic and has_english) else ("ar" if has_arabic else "en")

                        self.on_final({
                            "call_id": self.call_id,
                            "speaker_id": self.speaker_id,
                            "speaker_name": self.speaker_name,
                            "start_ms": start_ms,
                            "end_ms": end_ms,
                            "text": text,
                            "language": lang,
                            "is_final": True,
                            "t_stt_recv": t_recv
                        })

                elif msg_type in ("Begin", "SessionBegins"):
                    logger.info(f"[AssemblyAI] Session started for {self.speaker_name}: {data.get('id') or data.get('session_id')}")

                elif msg_type in ("Termination", "SessionTerminated"):
                    logger.info(f"[AssemblyAI] Session terminated for {self.speaker_name}")
                    break

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[AssemblyAI] WebSocket closed for {self.speaker_name}")
        except Exception as e:
            logger.error(f"[AssemblyAI] Listen loop error: {e}")
        finally:
            self.is_running = False

    async def close(self):
        self.is_running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            try:
                await self.ws.send(fast_json_dumps({"type": "Terminate"}))
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
