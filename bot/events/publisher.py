import logging
import asyncio
import httpx
from bot.config import config
from bot.events.models import VoiceEvent

logger = logging.getLogger("EventPublisher")


class EventPublisher:
    """Dispatches VoiceEvents to the FastAPI Event Hub in the background."""

    def __init__(self, api_url: str = None):
        self.api_url = (api_url or config.BACKEND_API_URL).rstrip("/")

    async def publish(self, event: VoiceEvent):
        if not self.api_url:
            return
        endpoint = f"{self.api_url}/api/events"
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                await client.post(endpoint, json=event.dict())
        except Exception as e:
            logger.debug(f"[EventPublisher] Notice: could not post event to {endpoint} ({e})")

    def publish_sync_task(self, event: VoiceEvent):
        """Dispatches an asynchronous background task without blocking calling thread."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            pass


publisher = EventPublisher()
