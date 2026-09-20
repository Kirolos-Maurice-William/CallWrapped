import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in root or backend/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
root_env = PROJECT_ROOT / ".env"
backend_env = PROJECT_ROOT / "backend" / ".env"

if root_env.exists():
    load_dotenv(root_env)
elif backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()


class BotConfig:
    """Central configuration for the AssemblyAI Third Participant Voice Agent."""

    # Discord Bot Token
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    COMMAND_PREFIX: str = "!"

    # AssemblyAI Speech-to-Text
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    PRIMARY_STT_PROVIDER: str = os.getenv("PRIMARY_STT_PROVIDER", "assemblyai")
    SPEECH_LANGUAGE: str = "ar"
    SPEECH_MODELS: list = ["universal-3-5-pro", "universal-2"]
    ASSEMBLYAI_POLL_ATTEMPTS: int = int(os.getenv("ASSEMBLYAI_POLL_ATTEMPTS", "40"))
    ASSEMBLYAI_POLL_INTERVAL_SEC: float = float(os.getenv("ASSEMBLYAI_POLL_INTERVAL_SEC", "0.5"))

    # Intelligence & Fact-Checking APIs
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    ANALYTICS_ENABLED: int = int(os.getenv("ANALYTICS_ENABLED", "1"))

    # Live Web Dashboard Integration URL
    BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")

    # Audio VAD (Voice Activity Detection) Parameters
    SILENCE_DURATION_SEC: float = float(os.getenv("SILENCE_DURATION_SEC", "1.5"))
    SILENCE_THRESHOLD_RMS: int = int(os.getenv("SILENCE_THRESHOLD_RMS", "80"))
    MIN_SPEECH_DURATION_SEC: float = float(os.getenv("MIN_SPEECH_DURATION_SEC", "0.5"))
    MAX_SPEECH_DURATION_SEC: float = float(os.getenv("MAX_SPEECH_DURATION_SEC", "15.0"))

    # Natural Neural TTS Voice
    TTS_VOICE: str = os.getenv("TTS_VOICE_AR", "ar-EG-ShakirNeural")
    TTS_RATE: str = os.getenv("TTS_RATE", "-3%")
    TTS_PITCH: str = os.getenv("TTS_PITCH", "+0Hz")

    # Discord Embed Styling
    EMBED_COLOR_INFO: int = 0x5865F2       # Blurple
    EMBED_COLOR_DISPUTE: int = 0xED4245    # Red
    EMBED_COLOR_VERDICT: int = 0x57F287    # Green
    EMBED_COLOR_ECHO: int = 0xFEE75C       # Yellow


config = BotConfig()
