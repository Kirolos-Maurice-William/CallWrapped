from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Third Participant"
    VERSION: str = "0.1.0"
    
    # AssemblyAI
    ASSEMBLYAI_API_KEY: str = ""
    ASSEMBLYAI_MODEL: str = "universal-3-5-pro"
    
    # LLM Settings
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    # Search API
    TAVILY_API_KEY: str = ""
    
    # TTS Settings
    TTS_PROVIDER: str = "edge-tts"
    TTS_VOICE_AR: str = "ar-EG-SalmaNeural"
    TTS_VOICE_EN: str = "en-US-JennyNeural"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./call_intelligence.db"
    
    # Network & CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
