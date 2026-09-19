import os
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env first if it exists, or local .env
backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
if backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()

class BotConfig:
    """Central configuration for the AI Third Participant Discord Voice Bot."""
    
    # Discord Bot Token (Get from https://discord.com/developers/applications)
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    
    # Command Prefix (e.g. !join, !leave, !status)
    COMMAND_PREFIX: str = "!"
    
    # Intelligence APIs
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Primary Speech-to-Text Provider: "assemblyai" (Primary) -> "groq" (Fallback)
    PRIMARY_STT_PROVIDER: str = os.getenv("PRIMARY_STT_PROVIDER", "assemblyai")
    
    # Whisper STT Model on Groq (Fallback)
    WHISPER_MODEL: str = "whisper-large-v3-turbo"
    SPEECH_LANGUAGE: str = "ar"
    
    # Context prompt to guide Whisper towards Egyptian Arabic and code-switching
    WHISPER_PROMPT: str = (
        "محادثة عفوية باللغة العربية واللهجة المصرية بين شباب، تحتوي على أسماء مشاهير، كورة، أفلام، "
        "ميسي، رونالدو، الأهلي، الزمالك، ومصطلحات إنجليزية مثل bro, actually, basically."
    )
    
    # Audio VAD (Voice Activity Detection) Parameters
    SILENCE_THRESHOLD_RMS: int = 150       # Ignores light breathing/room noise, catches real speech
    SILENCE_DURATION_SEC: float = 0.9      # Natural pause after speaking
    MIN_SPEECH_DURATION_SEC: float = 0.9   # Minimum duration (ignores short clicks/bumps)
    MAX_SPEECH_DURATION_SEC: float = 12.0  # Max utterance duration before auto-transcribing
    
    # TTS Settings
    TTS_VOICE: str = os.getenv("TTS_VOICE_AR", "ar-EG-SalmaNeural")
    
    # Discord Embed Customization
    EMBED_COLOR_INFO: int = 0x5865F2      # Blurple
    EMBED_COLOR_DISPUTE: int = 0xED4245   # Red
    EMBED_COLOR_VERDICT: int = 0x57F287   # Green

config = BotConfig()
