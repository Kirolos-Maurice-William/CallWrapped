import logging
import json
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

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

ARBITRATION_PROMPT = """You are a grounded fact-checking arbitrator.
Given two disputed claims from a call and authoritative web evidence snippets:
Determine:
1. Is the fact conclusively confirmed or contradicted? ('supported' if evidence proves one speaker right, 'inconclusive' if web snippets don't clearly prove either).
2. Confidence score (0.0 to 1.0).
3. Factual truth statement: A concise, natural Egyptian Arabic sentence (under 12 words) stating the exact verified fact.
4. Correct speaker: 'speaker_a', 'speaker_b', or 'neither'.
5. Short 1-sentence explanation of evidence.

Respond STRICTLY in JSON format:
{
  "result": "supported" / "contradicted" / "inconclusive",
  "confidence": 0.95,
  "factual_truth": "ولد ليونيل ميسي في 24 يونيو 1987",
  "correct_speaker": "speaker_a" / "speaker_b" / "neither",
  "evidence": "تؤكد المصادر الرسمية وويكيبيديا أن ميسي وُلد في 24 يونيو 1987."
}"""

class GroqService:
    def __init__(self):
        self.model = "qwen/qwen3.8-27b"
        self.client = httpx.AsyncClient(
            timeout=6.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=30),
            http2=True
        )

    async def classify_epistemic_dispute(self, speaker_a: str, claim_a: str, speaker_b: str, claim_b: str) -> Optional[Dict[str, Any]]:
        """
        Uses high-speed Groq LPU inference (~200ms) to evaluate if two statements
        form a verifiable real-world dispute vs subjective/casual banter.
        """
        if not settings.GROQ_API_KEY:
            return None

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
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
            resp = await self.client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                logger.warning(f"[Groq] Dispute classification error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Groq] Error calling dispute classifier: {e}")

        return None

    async def arbitrate_facts(self, claim_a: str, claim_b: str, sources: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        Reads web search snippets and uses Groq LPU inference (~250ms) to verify truth
        and eliminate hallucinated answers.
        """
        if not settings.GROQ_API_KEY or not sources:
            return None

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        snippets_combined = "\n".join([f"- {s.get('title', '')}: {s.get('snippet', '')}" for s in sources[:4]])
        user_content = f"Disputed Claims:\nSpeaker A: \"{claim_a}\"\nSpeaker B: \"{claim_b}\"\n\nAuthoritative Evidence Snippets:\n{snippets_combined}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": ARBITRATION_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = await self.client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["sources"] = sources
                return parsed
            else:
                logger.warning(f"[Groq] Fact arbitration error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Groq] Error calling fact arbitrator: {e}")

        return None

groq_service = GroqService()
