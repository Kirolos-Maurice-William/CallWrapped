import logging
import json
from typing import Dict, Any, Optional
import httpx
from bot.config import config

logger = logging.getLogger("DisputeDetector")

EPISTEMIC_DISPUTE_PROMPT = """You are an expert conversational intelligence judge analyzing live spoken dialogue (bilingual Egyptian Arabic and English).
Your sole job is to evaluate if two consecutive speaker turns form an OBJECTIVELY VERIFIABLE FACTUAL DISPUTE about real-world facts (entities, history, release dates, sports scores, birth years, celebrities, science, politics, geography).

CRITICAL RULES:
1. Subjective statements, personal preferences, feelings, or interpersonal conversation management MUST be FALSE (is_verifiable_dispute: false).
   - "أنا بحب اللعبة دي" vs "لا مابتحبهاش" -> FALSE (Subjective preference)
   - "أنت قولتلي كذا" vs "لا مقولتش" -> FALSE (Interpersonal dialogue claim)
   - "أنا هعد من واحد لعشرة" vs "لا عيد عيد من الأول" -> FALSE (Conversational instruction / timing)
   - "أنا مبسوط" vs "لا مش باين عليك" -> FALSE (Personal feelings)
2. Only TRUE if two people contest an objective, verifiable world knowledge fact:
   - "ميسي اتولد سنة 2000" vs "لا يا عم ميسي اتولد سنة 1987" -> TRUE (Subject: Lionel Messi birth year)
   - "فيلم Inception نزل في 2015" vs "لا نزل في 2010" -> TRUE (Subject: Inception release date)
   - "الأهلي كسب 3-0" vs "لا كسب 2-1" -> TRUE (Subject: match score)

Respond STRICTLY in JSON format:
{
  "is_verifiable_dispute": true/false,
  "topic": "football" / "movies" / "music" / "technology" / "politics" / "gaming" / "other",
  "search_query": "concise English/Arabic search query for Google/Wikipedia (or null if false)",
  "dispute_summary": "one clear sentence summarizing the factual conflict (or null if false)"
}"""


class DisputeDetector:
    """Uses high-speed Groq LPU inference (~150ms) to detect objective factual disputes."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = config.GROQ_MODEL

    async def check_dispute(self, speaker_a: str, claim_a: str, speaker_b: str, claim_b: str) -> Optional[Dict[str, Any]]:
        if not self.api_key or not claim_a or not claim_b:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        user_prompt = f'{speaker_a}: "{claim_a}"\n{speaker_b}: "{claim_b}"'
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EPISTEMIC_DISPUTE_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(self.url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    if parsed.get("is_verifiable_dispute"):
                        logger.info(f"⚔️ [Dispute Detected] Topic: {parsed.get('topic')} | Query: {parsed.get('search_query')}")
                    return parsed
        except Exception as e:
            logger.debug(f"[DisputeDetector] Notice: {e}")
        return None


dispute_detector = DisputeDetector()
