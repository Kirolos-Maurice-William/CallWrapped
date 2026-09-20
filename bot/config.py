import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load unified root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
root_env = PROJECT_ROOT / ".env"

if root_env.exists():
    load_dotenv(root_env)
else:
    load_dotenv()


class BotConfig:
    """Central configuration for the AssemblyAI Third Participant Voice Agent."""

    # Discord Bot Token
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")

    # AssemblyAI Speech-to-Text (tied to .env: SPEECH_MODELS or ASSEMBLYAI_MODEL)
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    PRIMARY_STT_PROVIDER: str = os.getenv("PRIMARY_STT_PROVIDER", "assemblyai")
    SPEECH_LANGUAGE: str = os.getenv("SPEECH_LANGUAGE", "ar")
    raw_speech_models = os.getenv("SPEECH_MODELS") or os.getenv("ASSEMBLYAI_MODEL", "universal-3-6-pro,universal-3-5-pro,universal-2")
    SPEECH_MODELS: list = [m.strip() for m in raw_speech_models.split(",") if m.strip()]
    SPEECH_MODEL_NAME: str = os.getenv("SPEECH_MODEL_NAME", SPEECH_MODELS[0] if SPEECH_MODELS else "universal-3-6-pro")
    ASSEMBLYAI_POLL_ATTEMPTS: int = int(os.getenv("ASSEMBLYAI_POLL_ATTEMPTS", "40"))
    ASSEMBLYAI_POLL_INTERVAL_SEC: float = float(os.getenv("ASSEMBLYAI_POLL_INTERVAL_SEC", "0.5"))

    # Intelligence & Fact-Checking APIs
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    GROQ_INSTANT_MODEL: str = os.getenv("GROQ_INSTANT_MODEL", os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    GROQ_BATCH_MODEL: str = os.getenv("GROQ_BATCH_MODEL", "qwen/qwen3.8-27b")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    ANALYTICS_ENABLED: int = int(os.getenv("ANALYTICS_ENABLED", "1"))
    default_window = "0" if any("test_fanout" in a for a in sys.argv) else "75"
    ANALYTICS_WINDOW_SEC: float = float(os.getenv("ANALYTICS_WINDOW_SEC", default_window))

    # Live Web Dashboard Integration URL
    BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")

    # Audio VAD (Voice Activity Detection) Parameters
    SILENCE_DURATION_SEC: float = float(os.getenv("SILENCE_DURATION_SEC", "1.5"))
    SILENCE_THRESHOLD_RMS: int = int(os.getenv("SILENCE_THRESHOLD_RMS", "80"))
    MIN_SPEECH_DURATION_SEC: float = float(os.getenv("MIN_SPEECH_DURATION_SEC", "0.5"))
    MAX_SPEECH_DURATION_SEC: float = float(os.getenv("MAX_SPEECH_DURATION_SEC", "15.0"))

    # Natural Neural TTS Voice
    TTS_VOICE: str = os.getenv("TTS_VOICE_AR", os.getenv("TTS_VOICE", "ar-EG-ShakirNeural"))
    TTS_RATE: str = os.getenv("TTS_RATE", "-3%")
    TTS_PITCH: str = os.getenv("TTS_PITCH", "+0Hz")

    # Discord Embed Styling
    EMBED_COLOR_INFO: int = int(str(os.getenv("EMBED_COLOR_INFO", "0x5865F2")), 16)
    EMBED_COLOR_DISPUTE: int = int(str(os.getenv("EMBED_COLOR_DISPUTE", "0xED4245")), 16)
    EMBED_COLOR_VERDICT: int = int(str(os.getenv("EMBED_COLOR_VERDICT", "0x57F287")), 16)
    EMBED_COLOR_ECHO: int = int(str(os.getenv("EMBED_COLOR_ECHO", "0xFEE75C")), 16)

    @property
    def speech_model_display(self) -> str:
        name = self.SPEECH_MODELS[0] if self.SPEECH_MODELS else "universal-3-6-pro"
        parts = name.split("-")
        if len(parts) >= 3 and parts[0] == "universal":
            version = f"{parts[1]}.{parts[2]}" if len(parts) >= 3 and parts[2].isdigit() else parts[1]
            rest = " ".join(p.capitalize() for p in parts[3:]) if len(parts) >= 4 else ("Pro" if "pro" in parts else "")
            return f"Universal-{version} {rest}".strip()
        return name.replace("-", " ").title()


config = BotConfig()
