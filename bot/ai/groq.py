import time
import json
import logging
from typing import Dict, Any, Optional, Tuple
import httpx
from bot.config import config

logger = logging.getLogger("GroqClient")


class GroqClient:
    """High-speed Groq LPU client for real-time arbitration and claim reasoning (~150ms)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = config.GROQ_MODEL

    async def complete_json(self, system_prompt: str, user_prompt: str) -> Tuple[Optional[Dict[str, Any]], int]:
        """Runs JSON-mode completion and returns (parsed_json, latency_ms)."""
        if not self.api_key:
            return None, 0

        t0 = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(self.url, headers=headers, json=payload)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return parsed, latency_ms
        except Exception as e:
            logger.debug(f"[GroqClient] Notice: {e}")

        return None, 0


groq_client = GroqClient()
