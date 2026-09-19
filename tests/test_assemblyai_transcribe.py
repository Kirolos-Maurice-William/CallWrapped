import asyncio
import os
import sys
import time
import io
import edge_tts
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.ai.assemblyai import assemblyai_client

async def generate_test_audio(text: str, output_path: str):
    """Generates an Arabic/English speech sample using Edge-TTS."""
    communicate = edge_tts.Communicate(text, "ar-EG-ShakirNeural", rate="+0%", pitch="+0Hz")
    await communicate.save(output_path)
    print(f"Generated test audio at {output_path}")

async def main():
    print("=== AssemblyAI Transcription Benchmark Test ===")
    test_phrase = "يا شباب كارت الـ RTX 5070 نزل رسمي بـ 12GB VRAM"
    audio_file = "test_sample.wav"

    print(f"Original Text: {test_phrase}")
    await generate_test_audio(test_phrase, audio_file)

    with open(audio_file, "rb") as f:
        audio_bytes = f.read()

    print(f"Audio size: {len(audio_bytes)} bytes. Submitting to AssemblyAI...")
    t0 = time.perf_counter()
    transcription, latency_ms = await assemblyai_client.transcribe(audio_bytes)
    total_ms = (time.perf_counter() - t0) * 1000

    print(f"\n--- Benchmark Results ---")
    print(f"Result Transcription: {transcription}")
    print(f"AssemblyAI Latency: {latency_ms} ms")
    print(f"Total Test Time: {total_ms:.1f} ms")

    # Clean up test file
    try:
        os.remove(audio_file)
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(main())
