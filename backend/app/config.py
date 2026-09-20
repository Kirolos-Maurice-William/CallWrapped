from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List
import os
from dotenv import load_dotenv

# Explicit path to unified root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ROOT_ENV = PROJECT_ROOT / ".env"

if ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)
else:
    load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Third Participant"
    VERSION: str = "0.1.0"
    
    # AssemblyAI
    ASSEMBLYAI_API_KEY: str = ""
    ASSEMBLYAI_MODEL: str = (os.getenv("SPEECH_MODELS") or os.getenv("ASSEMBLYAI_MODEL") or "universal-3-6-pro").split(",")[0].strip()
    
    # LLM Settings
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    
    # Search API
    TAVILY_API_KEY: str = ""
    
    # TTS Settings
    TTS_PROVIDER: str = "edge-tts"
    TTS_VOICE_AR: str = "ar-EG-ShakirNeural"
    TTS_VOICE_EN: str = "en-US-JennyNeural"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./call_intelligence.db"
    
    # Network & CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Discord Bot & Invite Link
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "1550926707517558864")
    DISCORD_INVITE_PERMISSIONS: str = os.getenv("DISCORD_INVITE_PERMISSIONS", "36718592")

    @property
    def discord_invite_url(self) -> str:
        cid = self.DISCORD_CLIENT_ID
        if (not cid or cid == "1550926707517558864") and self.DISCORD_BOT_TOKEN:
            try:
                import base64
                part = self.DISCORD_BOT_TOKEN.split('.')[0]
                padded = part + '=' * (-len(part) % 4)
                decoded = base64.b64decode(padded).decode('utf-8')
                if decoded.isdigit():
                    cid = decoded
            except Exception:
                pass
        return f"https://discord.com/oauth2/authorize?client_id={cid}&permissions={self.DISCORD_INVITE_PERMISSIONS}&scope=bot%20applications.commands"
    
    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = str(ROOT_ENV) if ROOT_ENV.exists() else ".env"
        extra = "ignore"

settings = Settings()
