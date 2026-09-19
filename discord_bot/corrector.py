import logging
import httpx
from typing import Optional
from .config import config

logger = logging.getLogger("EgyptianCorrector")

CORRECTOR_SYSTEM_PROMPT = (
    "أنت مصحح صوتي ذكي للعامية المصرية والشبابية في محادثات الديسكورد.\n"
    "بيوصلك نص من تفريغ صوتي آلي (ASR) فيه أخطاء سمعية ونطق مسموع غلط.\n"
    "وظيفتك تعدل الكلمات اللي واضحة إنها اتسمعت غلط لمعناها الحقيقي في سياق الكلام المصري:\n"
    "- 'أنا أبط' -> 'أنا البوت'\n"
    "- 'يا زبوي' أو 'يا زمي' -> 'يا صاحبي' أو 'يا زميلي'\n"
    "- 'هوريو' -> 'How are you' أو 'عامل إيه'\n"
    "- 'فيحرف' -> 'فيه حرف'\n"
    "قواعد:\n"
    "1. لا تغير معنى الجملة ولا تضيف كلام من عندك.\n"
    "2. حافظ على الأسلوب المصري العفوي.\n"
    "3. رد بالنص المصحح فقط بدون أي شرح أو علامات تنصيص."
)

class EgyptianCorrector:
    """Uses ultra-fast Groq LPU (~150ms) to polish ASR phonetic slips into natural Egyptian Arabic."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "qwen/qwen3.8-27b"

    async def correct_text(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if not clean or len(clean) < 3 or not self.api_key:
            return clean

        # Only correct sentences with 2 or more words
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
            "max_tokens": 100
        }

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(self.url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    corrected = data["choices"][0]["message"]["content"].strip()
                    # Strip any surrounding quotes if returned
                    corrected = corrected.strip('"\'')
                    if corrected and len(corrected) >= 2:
                        if corrected != clean:
                            logger.info(f"✨ [Groq Dialect Polish] '{clean}' ➔ '{corrected}'")
                        return corrected
        except Exception as e:
            logger.debug(f"[Groq Corrector] Timeout/Error, keeping raw text: {e}")

        return clean

corrector = EgyptianCorrector()
