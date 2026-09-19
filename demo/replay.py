import os
import sys
import json
import time
import asyncio
from pathlib import Path
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_PATH = PROJECT_ROOT / "demo" / "sessions" / "rtx5070_dispute.json"
BACKEND_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")


async def replay_session(file_path: Path = DEFAULT_SESSION_PATH, target_url: str = BACKEND_URL):
    """
    Replays a recorded session step-by-step through the VoiceEvent pipeline.
    Preserves exact timing so the judge can observe the real-time arbitration lifecycle.
    """
    if not file_path.exists():
        print(f"Error: Session file {file_path} does not exist.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    session_id = data.get("session_id", "demo_session")
    events = data.get("events", [])
    print(f"\n========================================================")
    print(f"  Starting Demo Replay: {data.get('title')}")
    print(f"  Target Hub: {target_url}/api/events")
    print(f"  Total events to stream: {len(events)}")
    print(f"========================================================\n")

    # Reset backend state first
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{target_url}/api/reset")
            print("  🔄 Backend state reset for clean demo.")
        except Exception as e:
            print(f"  ⚠️ Note: Could not reset backend state: {e}")

        for i, step in enumerate(events, 1):
            delay = step.get("delay_seconds", 1.0)
            event_data = step.get("event", {})
            event_type = event_data.get("type")
            speaker = event_data.get("speaker_name", "Unknown")
            text = event_data.get("text", "")

            print(f"[{i}/{len(events)}] Waiting {delay:.1f}s...")
            await asyncio.sleep(delay)

            # Update event timestamp to current time for live accuracy
            event_data["timestamp"] = time.time()

            try:
                resp = await client.post(f"{target_url}/api/events", json=event_data)
                if resp.status_code == 200:
                    print(f"  ➡️ [{event_type.upper()}] {speaker}: \"{text[:45]}...\" -> Dispatched OK")
                else:
                    print(f"  ❌ Error {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"  ❌ Failed to post event: {e}")

    print("\n========================================================")
    print("  ✅ Demo Replay Completed successfully!")
    print("========================================================\n")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else BACKEND_URL
    asyncio.run(replay_session(target_url=url))
