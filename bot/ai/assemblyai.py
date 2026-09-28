import time
import asyncio
import logging
from typing import Optional, Tuple, List, Dict, Any
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
    # Tech & Gaming
    "ping", "ranked", "update", "Discord", "Minecraft", "FPS", "packet loss",
    "stream", "lag", "RTX", "VRAM", "5070", "GPU", "bro", "server", "admin", "GTA",
    # Egyptian & Global Football
    "الأهلي", "الزمالك", "ميسي", "صلاح", "كأس", "دوري", "السوبر",
    "ريال مدريد", "برشلونة", "منتخب مصر", "كولر", "جوميز",
    # Movies & Cinema
    "ولاد رزق", "السينما", "فيلم", "مسلسل", "تريند", "عيد الأضحى",
    "تامر حسني", "ماجد الكدواني", "أحمد عز",
    # Music & Rap
    "عمرو دياب", "ويجز", "مكانك", "تراك", "ألبوم", "راب", "مروان بابلو", "حمزة نمرة",
    # Politics & Public Affairs
    "انتخابات", "مجلس النواب", "قانون", "الإيجار القديم", "البرلمان", "الحكومة", "الوزراء", "الدولار",
    # Tech / Gaming transliterations & hardware
    "بينج", "رانكد", "أبديت", "ديسكورد", "ماين كرافت", "فريمات", "باكيت لوس", "ستريم", "لاج",
    "كارت شاشة", "سيرفر", "أدمن", "جي تي إيه", "ستيم", "تويتش", "بلايستيشن", "إكس بوكس",
    "فالورانت", "كاونتر", "فورتنايت", "كول أوف ديوتي", "ببجي", "فيفا", "بروسيسور",
    "رامات", "هارد", "ماذربورد", "شاشة", "مايك", "راوتر", "فايبر", "بوت", "نوب", "كاري",
    # Football entities & competitions
    "بيراميدز", "الإسماعيلي", "الاتحاد السكندري", "المصري", "محمد صلاح", "رونالدو",
    "مبابي", "فينيسيوس", "هالاند", "حسام حسن", "إمام عاشور", "زيزو", "شيكابالا", "الشناوي",
    "كأس مصر", "كأس الأمم الأفريقية", "دوري أبطال أفريقيا", "الدوري المصري", "السوبر المصري",
    "دوري أبطال أوروبا", "كأس العالم", "مانشستر سيتي", "ليفربول", "أرسنال", "بايرن ميونخ",
    # Movies, TV & actors
    "الفيل الأزرق", "كيرة والجن", "بيت الروبي", "الحريفة", "عيد الفطر", "شاهد", "نتفليكس",
    "كريم عبد العزيز", "محمد هنيدي", "أحمد حلمي", "منى زكي", "دينا الشربيني", "بيومي فؤاد",
    "أمير كرارة", "محمد رمضان", "ياسمين عبد العزيز", "محمد إمام",
    # Music & Rap
    "أبيوسف", "مروان موسى", "عفروتو", "شهاب", "ليجي-سي", "محمد منير", "شيرين", "أنغام",
    "تامر عاشور", "بهاء سلطان", "مهرجانات", "حسن شاكوش", "عمر كمال", "رضا البحراوي",
    # Politics, Economy & Public affairs
    "مجلس الشيوخ", "رئيس الوزراء", "مصطفى مدبولي", "التعويم", "البنك المركزي", "التضخم",
    "الفوائد", "صندوق النقد", "رأس الحكمة", "العاصمة الإدارية", "الكهرباء", "تخفيف الأحمال",
    "التموين", "السكر", "البنزين", "السولار"
]

ASSEMBLYAI_CUSTOM_SPELLING = [
    # Latin-from mappings (English / transliteration code-switching)
    {"from": ["uncertain"], "to": "uncertainty"},
    {"from": ["pinging"], "to": "ping"},
    {"from": ["lags", "lagging"], "to": "lag"},
    {"from": ["streaming", "streams"], "to": "stream"},
    {"from": ["discords"], "to": "Discord"},
    {"from": ["rtx"], "to": "RTX"},
    {"from": ["gpus"], "to": "GPU"},
    {"from": ["fpss"], "to": "FPS"},
    {"from": ["vrams"], "to": "VRAM"},
    {"from": ["gta"], "to": "GTA"},
    {"from": ["ranks"], "to": "ranked"},
    {"from": ["servers"], "to": "server"},
    {"from": ["admins"], "to": "admin"},
    {"from": ["updates"], "to": "update"},
    {"from": ["craft"], "to": "Minecraft"},
    {"from": ["headsets"], "to": "headset"},
    {"from": ["routers"], "to": "router"},
    {"from": ["fibers"], "to": "fiber"},
    {"from": ["mics"], "to": "mic"},
    {"from": ["packetloss"], "to": "packet"},
    # Arabic-from mappings (Egyptian colloquial phonetic normalization)
    {"from": ["كثيره", "كثيرة"], "to": "كتيره"},
    {"from": ["كثير"], "to": "كتير"},
    {"from": ["نقص"], "to": "ناقص"},
    {"from": ["يصدق"], "to": "يسبق"},
    {"from": ["بكم"], "to": "بيكم"},
    {"from": ["احلي", "أحلى"], "to": "احلم"},
    {"from": ["هنعيش"], "to": "حنعيش"},
    {"from": ["سنتعرف", "ستعرف"], "to": "حنتعرف"},
    {"from": ["بره"], "to": "برضه"},
    {"from": ["ثلاث", "ثلاثة"], "to": "تلت"},
    {"from": ["ثلاثين"], "to": "تلاتين"},
    {"from": ["بالزعائف", "بالزعينف", "بالزعينب"], "to": "بالزعانف"},
    {"from": ["زعائف", "زعينف", "زعينب"], "to": "زعانف"},
    {"from": ["معدله"], "to": "معضله"},
    {"from": ["لغوايه"], "to": "لغويه"},
    {"from": ["اسباحه"], "to": "سباحه"},
    {"from": ["كموس"], "to": "قاموس"},
    {"from": ["هيلقي", "هيلقى"], "to": "حيلاقي"},
    {"from": ["الحوزه"], "to": "ملحوظه"},
    {"from": ["البرانويا"], "to": "البارانويا"},
    {"from": ["كالشيزوفرانيا"], "to": "الشيزوفرانيا"},
    {"from": ["تسبحها"], "to": "سباحه"},
    {"from": ["قليلي"], "to": "قوليلي"},
    {"from": ["اكلمكم"], "to": "حكلمكو"}
]

VALID_ASSEMBLYAI_MODELS = {"universal-3-5-pro", "universal-3-pro", "universal-2"}


def build_keyterms(extra_keyterms: Optional[List[str]] = None) -> List[str]:
    """
    Constructs the keyterms_prompt list for AssemblyAI Universal-3.5 Pro.
    Prioritizes dynamically discovered session entities (extra_keyterms), then fills
    the remaining slots from ASSEMBLYAI_KEYTERMS up to the official 100-term ceiling.
    Ensures deduplication, whitespace stripping, and length sanity (<= 50 chars).
    """
    combined: List[str] = []
    seen: set = set()
    if extra_keyterms:
        for term in extra_keyterms:
            if not term or not isinstance(term, str):
                continue
            cleaned = term.strip()
            if cleaned and len(cleaned) <= 50 and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                combined.append(cleaned)
            if len(combined) >= 100:
                break
    for term in ASSEMBLYAI_KEYTERMS:
        if len(combined) >= 100:
            break
        if not term or not isinstance(term, str):
            continue
        cleaned = term.strip()
        if cleaned and len(cleaned) <= 50 and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            combined.append(cleaned)
    return combined[:100]


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

    async def transcribe(
        self,
        wav_bytes: bytes,
        speaker_name: str = "unknown",
        extra_keyterms: Optional[List[str]] = None
    ) -> Tuple[Optional[str], int]:
        """Transcribes audio and returns (raw_text, latency_ms)."""
        if not self.api_key or not wav_bytes or len(wav_bytes) < 1000:
            return None, 0

        # Silence trim: energy-trim trailing silence (the 1.5s VAD window) before upload
        from bot.audio.pcm import trim_trailing_silence_wav
        wav_bytes = trim_trailing_silence_wav(wav_bytes, threshold_rms=getattr(config, "SILENCE_THRESHOLD_RMS", 80.0))

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

                # 2. Submit transcription job with code-switching prompts and dynamic keyterms
                job_payload = {
                    "audio_url": upload_url,
                    "language_code": config.SPEECH_LANGUAGE,
                    "speech_models": valid_models,
                    "punctuate": True,
                    "format_text": True,
                    "prompt": ASSEMBLYAI_CONTEXT_PROMPT,
                    "keyterms_prompt": build_keyterms(extra_keyterms),
                    "custom_spelling": ASSEMBLYAI_CUSTOM_SPELLING
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

    async def transcribe_with_pii_redaction(
        self,
        wav_bytes: bytes,
        policies: Optional[list] = None,
        sub: str = "entity_name",
        language_code: str = "ar"
    ) -> Tuple[Optional[str], int]:
        """Submits batch transcription with PII redaction enabled (Card 7 exhibit)."""
        if not self.api_key or not wav_bytes:
            return None, 0

        policies = policies or ["person_name", "phone_number"]
        t0 = time.perf_counter()
        headers = {"Authorization": self.api_key}

        async with httpx.AsyncClient(timeout=30.0) as client:
            upload_resp = await client.post(self.upload_url, headers=headers, content=wav_bytes)
            if upload_resp.status_code != 200:
                logger.error(f"[AssemblyAI PII] Upload failed: {upload_resp.text}")
                return None, 0
            upload_url = upload_resp.json().get("upload_url")

            job_payload = {
                "audio_url": upload_url,
                "language_code": language_code,
                "redact_pii": True,
                "redact_pii_policies": policies,
                "redact_pii_sub": sub
            }
            job_resp = await client.post(self.transcript_url, headers=headers, json=job_payload)
            if job_resp.status_code != 200:
                logger.error(f"[AssemblyAI PII] Job submission failed: {job_resp.text}")
                return None, 0

            job_id = job_resp.json().get("id")
            poll_url = f"{self.transcript_url}/{job_id}"

            attempts = getattr(config, "ASSEMBLYAI_POLL_ATTEMPTS", 40)
            interval = getattr(config, "ASSEMBLYAI_POLL_INTERVAL_SEC", 0.5)
            for _ in range(attempts):
                await asyncio.sleep(interval)
                poll_resp = await client.get(poll_url, headers=headers)
                if poll_resp.status_code == 200:
                    data = poll_resp.json()
                    status = data.get("status")
                    if status == "completed":
                        redacted_text = data.get("text", "").strip()
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        logger.info(f"🛡️ [AssemblyAI PII Redacted] ({latency_ms}ms): {redacted_text}")
                        return redacted_text, latency_ms
                    elif status == "error":
                        logger.error(f"[AssemblyAI PII] Transcription error: {data.get('error')}")
                        return None, 0

            return None, int((time.perf_counter() - t0) * 1000)


assemblyai_client = AssemblyAIClient()
