import logging
import httpx
from typing import Optional
from bot.config import config

logger = logging.getLogger("DialectCorrector")

CORRECTOR_SYSTEM_PROMPT = (
    "أنت مصحح صوتي وخبير لغوي متخصص في اللهجة العامية المصرية والمحادثات الشبابية ثنائية اللغة (Arabic + English Code-Switching) على ديسكورد.\n"
    "المهمة:\n"
    "تستلم نص مفرغ صوتياً فيه تحريفات سمعية أو أخطاء في نطق الكلمات الإنجليزية والعربية المدمجة.\n"
    "صحح فقط الكلمات التي نُطقت أو فُرغت خطأً بما يطابق السياق الطبيعي لمحادثة شباب مصرية/عربية، مثل:\n"
    "- 'أنا أبط' -> 'أنا البوت'\n"
    "- 'يا زبوي' أو 'يا زمي' -> 'يا صاحبي' أو 'يا زميلي'\n"
    "- 'فيحرف' -> 'فيه حرف'\n"
    "- 'هاي هوريو' -> 'هاي How are you'\n"
    "- 'البنج عالي' أو 'البينج' -> 'الـ Ping عالي'\n"
    "- 'عملت ابديت للجم' -> 'عملت Update للـ Game'\n"
    "- 'الرانك' / 'الستريم' / 'الديسكورد' -> الحفاظ على المصطلح الإنجليزي الشائع.\n"
    "\nالقواعد الصارمة:\n"
    "1. لا تغير المعنى الأصلي ولا تحذف كلمات مهمة.\n"
    "2. حافظ على عفوية الكلام المصري والمصطلحات الإنجليزية الدارجة بدون فزلكة.\n"
    "3. أخرج النص المصحح فقط بدون علامات تنصيص وبدون أي مقدمات أو شروحات نهائياً."
)


class DialectCorrector:
    """Uses ultra-fast Groq LPU (~150ms) to polish ASR phonetic slips and bilingual code-switching."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = config.GROQ_MODEL

    async def correct_text(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if not clean or len(clean) < 3 or not self.api_key:
            return clean

        # Skip single very short words
        if len(clean.split()) < 2:
            return clean

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CORRECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": clean}
            ],
            "temperature": 0.1,
            "max_tokens": 120
        }

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(self.url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    corrected = data["choices"][0]["message"]["content"].strip()
                    corrected = corrected.strip('"\'')
                    if corrected and len(corrected) >= 2:
                        if corrected != clean:
                            logger.info(f"✨ [Dialect Polish] '{clean}' ➔ '{corrected}'")
                        return corrected
        except Exception as e:
            logger.debug(f"[DialectCorrector] Timeout/Notice: {e}")

        return clean


dialect_corrector = DialectCorrector()
