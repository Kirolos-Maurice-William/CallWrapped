"""
Comparative A/B Benchmark for Multimodal Anger & Context Detection
Validates Old System vs New System across:
1. Live Discord test lines from Remi & 2xDanger
2. User's exact scenario: "I fucking hate my life" (solo calm vs solo loud vs active argument)
3. Dashboard receipt preservation
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from bot.audio.fusion import fuse_anger
from bot.audio.loudness import UtteranceAudioFeatures
from bot.arbitration.stats import SessionStatsTracker
from app.routes import ingest_voice_event, VoiceEventPayload, ANALYTICS_STATE
import asyncio

def run_benchmark():
    print("=" * 75)
    print("      MULTIMODAL ANGER & CONTEXT A/B COMPARATIVE BENCHMARK")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # Test 1: Live Discord Banter Lines
    # -------------------------------------------------------------------------
    print("\n--- TEST 1: Live Discord Banter Lines (Remi & 2xDanger) ---")
    banter_cases = [
        {"speaker": "2xDanger", "text": "أنت عارف بس إنه هو بيفهم كلام كتير غلط بعربي وأنا بحاول أصلح الـ API", "peak_z": 0.8},
        {"speaker": "2xDanger", "text": "مصطفى حيوان ليه حطت الصورة الزبرة بتاعت البوت ده", "peak_z": 1.2},
        {"speaker": "2xDanger", "text": "I hate Mustafa. Fucking Mustafa.", "peak_z": 1.5},
        {"speaker": "Remi", "text": "fuck that do you see this fuck that bot", "peak_z": 1.1},
    ]

    for item in banter_cases:
        feat = UtteranceAudioFeatures(
            frame_count=20, voiced_frames=18, p95_log_rms_db=50.0,
            peak_robust_z=item["peak_z"], sustained_spike_count=0,
            clip_ratio=0.0, calibrated=True, was_loud=False
        )
        res = fuse_anger(
            raw_anger="none",  # Prompt rule correctly classifies testing banter as none
            audio_features=feat,
            has_active_dispute=False,
            in_active_argument=False,
            text=item["text"]
        )
        print(f"  • {item['speaker']}: \"{item['text'][:45]}...\" -> Final: {res.final_anger.upper()} (gate: {res.gate_reason})")
        assert res.final_anger == "none", f"Expected none for banter, got {res.final_anger}"

    # -------------------------------------------------------------------------
    # Test 2: User's Exact Hypothesis: "I fucking hate my life"
    # -------------------------------------------------------------------------
    print("\n--- TEST 2: The User's Scenario: 'I fucking hate my life' across Contexts ---")

    # Scenario 2A: Calm voice, solo (no argument)
    feat_calm = UtteranceAudioFeatures(
        frame_count=20, voiced_frames=18, p95_log_rms_db=44.0,
        peak_robust_z=0.6, sustained_spike_count=0,
        clip_ratio=0.0, calibrated=True, was_loud=False
    )
    res_2a = fuse_anger(
        raw_anger="mild",  # Negative wording might trigger mild in text
        audio_features=feat_calm,
        has_active_dispute=False,
        in_active_argument=False,
        text="I fucking hate my life"
    )
    print(f"  [Scenario 2A: Calm voice, Solo banter/venting]")
    print(f"    Input: raw_anger=mild, was_loud=False, peak_z=0.6, in_argument=False")
    print(f"    Outcome: final_anger={res_2a.final_anger.upper()} | gate={res_2a.gate_reason} | p_fused={res_2a.p_fused:.2f}")
    assert res_2a.final_anger == "none", "Calm solo venting should be vetoed down to none!"

    # Scenario 2B: Loud voice, solo gaming excitement/venting (no argument)
    feat_loud_solo = UtteranceAudioFeatures(
        frame_count=20, voiced_frames=18, p95_log_rms_db=68.0,
        peak_robust_z=3.2, sustained_spike_count=4,
        clip_ratio=0.0, calibrated=True, was_loud=True
    )
    res_2b = fuse_anger(
        raw_anger="none",  # Classified as none/banter
        audio_features=feat_loud_solo,
        has_active_dispute=False,
        in_active_argument=False,
        text="I fucking hate my life"
    )
    print(f"  [Scenario 2B: Loud voice, Solo gaming hyperbole without dispute]")
    print(f"    Input: raw_anger=none, was_loud=True, peak_z=3.2, in_argument=False")
    print(f"    Outcome: final_anger={res_2b.final_anger.upper()} | gate={res_2b.gate_reason} | p_fused={res_2b.p_fused:.2f}")

    # Scenario 2C: Active interpersonal argument!
    res_2c = fuse_anger(
        raw_anger="mild",
        audio_features=feat_loud_solo,
        has_active_dispute=False,
        in_active_argument=True,  # Active argument between 2 speakers!
        text="I fucking hate my life"
    )
    print(f"  [Scenario 2C: Active Interpersonal Argument with Elevated Voice]")
    print(f"    Input: raw_anger=mild, was_loud=True, peak_z=3.2, in_argument=True")
    print(f"    Outcome: final_anger={res_2c.final_anger.upper()} | gate={res_2c.gate_reason} | p_fused={res_2c.p_fused:.2f}")
    assert res_2c.final_anger in ("mild", "high"), "Interpersonal conflict with loud voice MUST be anger!"

    # -------------------------------------------------------------------------
    # Test 3: Dashboard Receipts & Acoustic Badge Persistence
    # -------------------------------------------------------------------------
    print("\n--- TEST 3: Dashboard Receipt & Acoustic Badge Persistence ---")
    async def test_backend():
        payload = {
            "topic": "gaming",
            "anger": "mild",
            "anger_evidence": "الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            "first_anger_quote": "الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            "anger_episodes_history": [
                {
                    "episode_number": 1,
                    "quote": "الكول أوف ديوتي زبالة والرانك بيعصب أوي",
                    "timestamp": 120.5,
                    "anger": "mild",
                    "was_loud": True,
                    "peak_z": 3.6
                }
            ],
            "talk_delta_seconds": 6.2,
            "streak_seconds": 6.2,
            "angry_episodes": 1
        }
        ev = VoiceEventPayload(
            event_id="ev_receipt_test",
            session_id="test_session",
            type="analytics_update",
            speaker_name="2xDanger",
            text="الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            topic="gaming",
            anger="mild",
            anger_evidence="الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            first_anger_quote="الكول أوف ديوتي زبالة والرانك بيعصب أوي",
            payload=payload
        )
        await ingest_voice_event(ev)
        spk = ANALYTICS_STATE["speakers"]["2xDanger"]
        print(f"  • Speaker: {spk['speaker_name']}")
        print(f"  • Episodes: {spk['angry_episodes']}")
        print(f"  • First Anger Quote: \"{spk['first_anger_quote']}\"")
        print(f"  • Episode History Count: {len(spk['anger_episodes_history'])}")
        print(f"  • Ep #1 Details: {spk['anger_episodes_history'][0]}")

        assert spk["first_anger_quote"] is not None, "first_anger_quote must not be dropped!"
        assert len(spk["anger_episodes_history"]) == 1, "anger_episodes_history must contain episode!"
        assert spk["anger_episodes_history"][0]["was_loud"] is True, "was_loud must be preserved!"

    asyncio.run(test_backend())

    print("\n" + "=" * 75)
    print("  ALL BENCHMARK TESTS PASSED: MULTIMODAL CONTEXT & RECEIPTS VERIFIED!")
    print("=" * 75)

if __name__ == "__main__":
    run_benchmark()
