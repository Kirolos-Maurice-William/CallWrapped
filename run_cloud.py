import os
import sys
import signal
import subprocess
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def main():
    print("=" * 60)
    print("  VOICE ARBITRATOR — CLOUD RUNNER")
    print("  AssemblyAI Voice Agent Hackathon (lablab.ai)")
    print("=" * 60)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    # 1. Start FastAPI Backend (Serves static Next.js frontend + WebSockets)
    print("[1/2] Starting FastAPI Backend on port 8000...")
    backend_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--app-dir", "backend",
        "--host", "0.0.0.0",
        "--port", "8000"
    ]
    backend_proc = subprocess.Popen(backend_cmd, env=env)

    # Wait 2 seconds for backend to initialize
    time.sleep(2)

    # 2. Start Discord Voice Arbitrator Bot
    print("[2/2] Starting Discord Voice Arbitrator Bot...")
    bot_cmd = [sys.executable, "bot/main.py"]
    bot_proc = subprocess.Popen(bot_cmd, env=env)

    def cleanup(signum, frame):
        print("\nShutting down services...")
        bot_proc.terminate()
        backend_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Keep alive while both run
    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend exited unexpectedly!")
                bot_proc.terminate()
                break
            if bot_proc.poll() is not None:
                print("Bot exited unexpectedly!")
                backend_proc.terminate()
                break
    except KeyboardInterrupt:
        cleanup(None, None)

if __name__ == "__main__":
    main()
