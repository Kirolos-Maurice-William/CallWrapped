#!/usr/bin/env python3
"""
CallWrapped — Live Readiness Verification Script
Audit Path: audit/live_readiness_check.py

Validates every feature flag, config setting, API pool, model parameter,
referee invariant, TTS pipeline setting, dashboard endpoint, and Discord command
for live call execution readiness. Outputs a unified PASS/FAIL readiness table.
"""

import os
import sys
import time
import inspect
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Ensure project root and backend are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
import websockets
from bot.config import config
from bot.ai.groq import KeyPool
from bot.arbitration.claim_detector import BATCH_ANALYTICS_PROMPT
from bot.arbitration.conflict_detector import CONFIDENCE_THRESHOLD, CONFLICT_PROMPT
from bot.arbitration.verifier import is_private_claim
from bot.arbitration.dispute_tracker import DisputeTracker
from bot.ai.tts import StreamFFmpegPCMAudio, create_streaming_source
from bot.main import bot


class ReadinessAuditor:
    def __init__(self):
        self.results: List[Dict[str, str]] = []
        self.failures: List[str] = []

    def record(self, check: str, current: Any, expected: Any, passed: bool, remediation: str = ""):
        status = "PASS" if passed else "FAIL"
        self.results.append({
            "check": check,
            "current": str(current),
            "expected": str(expected),
            "status": status,
            "remediation": remediation
        })
        if not passed:
            self.failures.append(f"[{check}] Current: {current} | Expected: {expected} -> Fix: {remediation}")

    # -------------------------------------------------------------------------
    # 1. FEATURE FLAGS
    # -------------------------------------------------------------------------
    def check_feature_flags(self):
        # TEST_CAPTURE_MODE: must be 1
        val_capture = getattr(config, "TEST_CAPTURE_MODE", 0)
        self.record(
            "1.1 Feature Flag: TEST_CAPTURE_MODE",
            val_capture,
            1,
            val_capture == 1,
            "Add TEST_CAPTURE_MODE=1 to .env"
        )

        # ACOUSTIC_FUSION_ENABLED: must be 0
        val_fusion = getattr(config, "ACOUSTIC_FUSION_ENABLED", 0)
        self.record(
            "1.2 Feature Flag: ACOUSTIC_FUSION_ENABLED",
            val_fusion,
            0,
            val_fusion == 0,
            "Set ACOUSTIC_FUSION_ENABLED=0 in .env"
        )

        # ANALYTICS_ENABLED: must be 1
        val_analytics = getattr(config, "ANALYTICS_ENABLED", 0)
        self.record(
            "1.3 Feature Flag: ANALYTICS_ENABLED",
            val_analytics,
            1,
            val_analytics == 1,
            "Set ANALYTICS_ENABLED=1 in .env"
        )

        # ANALYTICS_WINDOW_SEC: must be 75
        val_window = int(getattr(config, "ANALYTICS_WINDOW_SEC", 0))
        self.record(
            "1.4 Feature Flag: ANALYTICS_WINDOW_SEC",
            f"{val_window}s",
            "75s",
            val_window == 75,
            "Set ANALYTICS_WINDOW_SEC=75 in .env"
        )

    # -------------------------------------------------------------------------
    # 2. GROQ KEY POOL
    # -------------------------------------------------------------------------
    async def check_groq_pool(self):
        pool = KeyPool()
        pool_size = len(pool.keys)

        self.record(
            "2.1 Groq: Key Pool Size",
            f"{pool_size} keys",
            ">= 4 keys",
            pool_size >= 4,
            "Add GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4 to .env"
        )

        # Query per-key remaining tokens
        key_tokens: Dict[str, int] = {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for k in pool.keys:
                key_id = k["id"]
                raw_key = k["key"]
                try:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {raw_key}", "Content-Type": "application/json"},
                        json={"model": config.GROQ_MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                    )
                    rem = resp.headers.get("x-ratelimit-remaining-tokens")
                    key_tokens[key_id] = int(rem) if rem is not None else 0
                except Exception as e:
                    key_tokens[key_id] = -1

        keys_above_1000 = sum(1 for tok in key_tokens.values() if tok > 1000)
        tokens_summary = ", ".join(f"{k}:{v}" for k, v in key_tokens.items())

        self.record(
            "2.2 Groq: Active Keys (> 1000 tokens)",
            f"{keys_above_1000} keys ({tokens_summary})",
            ">= 2 keys with > 1000 tokens",
            keys_above_1000 >= 2,
            "Refresh exhausted Groq API keys in .env"
        )

    # -------------------------------------------------------------------------
    # 3. ASSEMBLYAI
    # -------------------------------------------------------------------------
    async def check_assemblyai(self):
        key = getattr(config, "ASSEMBLYAI_API_KEY", "")
        key_present = bool(key and len(key.strip()) > 8)

        key_valid = False
        if key_present:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(
                        "https://api.assemblyai.com/v2/transcript?limit=1",
                        headers={"authorization": key.strip()}
                    )
                    key_valid = (resp.status_code == 200)
            except Exception:
                key_valid = False

        self.record(
            "3.1 AssemblyAI: API Key Validity",
            "Valid (HTTP 200)" if key_valid else "Invalid or unreachable",
            "Valid (HTTP 200)",
            key_valid,
            "Verify ASSEMBLYAI_API_KEY in .env"
        )

        model_name = getattr(config, "SPEECH_MODEL_NAME", "")
        self.record(
            "3.2 AssemblyAI: Speech Model",
            model_name,
            "universal-3-5-pro",
            model_name == "universal-3-5-pro",
            "Set SPEECH_MODELS=universal-3-5-pro in .env"
        )

        attempts = getattr(config, "ASSEMBLYAI_POLL_ATTEMPTS", 40)
        interval = getattr(config, "ASSEMBLYAI_POLL_INTERVAL_SEC", 0.5)
        poll_budget = attempts * interval
        self.record(
            "3.3 AssemblyAI: Poll Budget",
            f"{poll_budget:.1f}s ({attempts} x {interval}s)",
            "20.0s (40 x 0.5s)",
            poll_budget == 20.0,
            "Set ASSEMBLYAI_POLL_ATTEMPTS=40 and ASSEMBLYAI_POLL_INTERVAL_SEC=0.5 in .env"
        )

    # -------------------------------------------------------------------------
    # 4. CLASSIFIER
    # -------------------------------------------------------------------------
    def check_classifier(self):
        prompt = BATCH_ANALYTICS_PROMPT

        # 15 topics
        expected_topics = [
            "football", "politics", "music", "movies", "gaming", "tech",
            "food", "travel", "study_work", "health", "cars", "money",
            "personal", "other", "null_topic"
        ]
        missing_topics = [t for t in expected_topics if t not in prompt]
        self.record(
            "4.1 Classifier: 15 Topic Taxonomy",
            f"All 15 present" if not missing_topics else f"Missing: {missing_topics}",
            "All 15 topic values present",
            len(missing_topics) == 0,
            "Restore 15-topic enum to BATCH_ANALYTICS_PROMPT in bot/arbitration/claim_detector.py"
        )

        # ANGER RULE + twin pairs
        has_anger_rule = "ANGER RULE" in prompt and "Twin-pair examples" in prompt
        self.record(
            "4.2 Classifier: ANGER RULE & Twin Pairs",
            "Present" if has_anger_rule else "Missing",
            "Present in BATCH_ANALYTICS_PROMPT",
            has_anger_rule,
            "Restore ANGER RULE and twin-pair examples to BATCH_ANALYTICS_PROMPT"
        )

        # null_topic rules
        has_null_topic = "null_topic rule" in prompt
        self.record(
            "4.3 Classifier: null_topic Rules",
            "Present" if has_null_topic else "Missing",
            "Present in BATCH_ANALYTICS_PROMPT",
            has_null_topic,
            "Restore null_topic rules to BATCH_ANALYTICS_PROMPT"
        )

        # acoustic advisory line
        has_acoustic_advisory = "ACOUSTIC CONTEXT (advisory only)" in prompt and "evidence of arousal" in prompt
        self.record(
            "4.4 Classifier: Acoustic Advisory Line",
            "Present" if has_acoustic_advisory else "Missing",
            "Present in BATCH_ANALYTICS_PROMPT",
            has_acoustic_advisory,
            "Restore acoustic context advisory note to BATCH_ANALYTICS_PROMPT"
        )

    # -------------------------------------------------------------------------
    # 5. REFEREE
    # -------------------------------------------------------------------------
    def check_referee(self):
        # Conflict gates active (incompatible values + public/private + confidence >= 70)
        gates_active = (
            CONFIDENCE_THRESHOLD >= 70 and
            "INCOMPATIBLE, MUTUALLY EXCLUSIVE" in CONFLICT_PROMPT and
            "PRIVATE-ENTITY REFUSAL GATE" in CONFLICT_PROMPT
        )
        self.record(
            "5.1 Referee: Conflict Authenticity Gates",
            f"Active (confidence >= {CONFIDENCE_THRESHOLD}, mutually exclusive, private refusal)" if gates_active else "Incomplete",
            "Active (confidence >= 70, mutually exclusive, private refusal)",
            gates_active,
            "Ensure CONFIDENCE_THRESHOLD >= 70 and conflict prompt rules in conflict_detector.py"
        )

        # Two-stage offer flow wired (offer -> text channel + dashboard)
        from bot.arbitration.engine import ArbitrationEngine
        engine_source = inspect.getsource(ArbitrationEngine)
        offer_wired = (
            "text_channel.send(offer_text)" in engine_source and
            "dispute_check_offered" in engine_source and
            "publisher.publish_sync_task" in engine_source
        )
        self.record(
            "5.2 Referee: Two-Stage Offer Flow Wiring",
            "Wired (Discord chat + Dashboard WebSocket)" if offer_wired else "Missing",
            "Wired (Discord chat + Dashboard WebSocket)",
            offer_wired,
            "Verify publish_dispute_offer in bot/arbitration/engine.py"
        )

        # 30s expiry + 180s cooldown
        cooldown = getattr(config, "DISPUTE_OFFER_COOLDOWN_SEC", 0.0)
        expiry = getattr(config, "DISPUTE_OFFER_EXPIRY_SEC", 0.0)
        times_ok = (cooldown == 180.0 and expiry == 30.0)
        self.record(
            "5.3 Referee: Offer Timing Invariants",
            f"Expiry: {expiry}s, Cooldown: {cooldown}s",
            "Expiry: 30.0s, Cooldown: 180.0s",
            times_ok,
            "Set DISPUTE_OFFER_EXPIRY_SEC=30.0 and DISPUTE_OFFER_COOLDOWN_SEC=180.0 in .env"
        )

        # Private-entity refusal active
        is_priv, reason = is_private_claim("Mostafa", channel_members=["Mostafa"])
        priv_active = (is_priv is True and reason == "voice_channel_member")
        self.record(
            "5.4 Referee: Channel Member Private Entity Refusal",
            f"Active ({reason})" if priv_active else "Inactive",
            "Active (voice_channel_member)",
            priv_active,
            "Verify is_private_claim channel member match in bot/arbitration/verifier.py"
        )

        # Dispute tracker in SHADOW mode
        tracker_shadow = issubclass(DisputeTracker, object) and not hasattr(config, "ENABLE_AUTHORITATIVE_DISPUTE_TRACKER")
        self.record(
            "5.5 Referee: Dispute Tracker Shadow Mode",
            "Shadow Mode (Replay / Telemetry non-authoritative)" if tracker_shadow else "Authoritative",
            "Shadow Mode (Replay / Telemetry non-authoritative)",
            tracker_shadow,
            "Ensure DisputeTracker remains in shadow telemetry mode"
        )

    # -------------------------------------------------------------------------
    # 6. TTS
    # -------------------------------------------------------------------------
    def check_tts(self):
        voice = getattr(config, "TTS_VOICE", "")
        self.record(
            "6.1 TTS: Edge-TTS Voice Model",
            voice,
            "ar-EG-ShakirNeural",
            voice == "ar-EG-ShakirNeural",
            "Set TTS_VOICE=ar-EG-ShakirNeural in .env"
        )

        # Streaming mode active (StreamFFmpegPCMAudio)
        source = create_streaming_source()
        is_streaming = isinstance(source, StreamFFmpegPCMAudio)
        if hasattr(source, "cleanup"):
            source.cleanup()
        self.record(
            "6.2 TTS: Sub-second Streaming Mode",
            "Active (StreamFFmpegPCMAudio pipe:0)" if is_streaming else "File-based save",
            "Active (StreamFFmpegPCMAudio pipe:0)",
            is_streaming,
            "Ensure create_streaming_source returns StreamFFmpegPCMAudio in bot/ai/tts.py"
        )

        # Barge-in detection active (RMS threshold + self-echo filter)
        from bot.audio.receiver import AudioReceiver
        receiver_src = inspect.getsource(AudioReceiver.write)
        barge_in_active = (
            "vc.is_playing() and rms >= config.SILENCE_THRESHOLD_RMS" in receiver_src and
            "speaker.stop(vc" in receiver_src and
            "user_id == vc.user.id" in receiver_src
        )
        self.record(
            "6.3 TTS: Barge-in & Self-Echo Filter",
            "Active (RMS threshold + self-echo guard)" if barge_in_active else "Inactive",
            "Active (RMS threshold + self-echo guard)",
            barge_in_active,
            "Verify barge-in check in bot/audio/receiver.py:write"
        )

        # TTS timeout = 10s (not 2.5s)
        timeout = getattr(config, "TTS_TIMEOUT_SEC", 0.0)
        self.record(
            "6.4 TTS: Synthesis Timeout",
            f"{timeout:.1f}s",
            "10.0s",
            timeout == 10.0,
            "Set TTS_TIMEOUT_SEC=10.0 in .env"
        )

    # -------------------------------------------------------------------------
    # 7. DASHBOARD
    # -------------------------------------------------------------------------
    async def check_dashboard(self):
        # We test backend startup and endpoints on port 8000
        from app.main import app
        import uvicorn

        server_started_by_us = False
        server = None
        server_thread = None

        # Check if port 8000 already running
        already_running = False
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get("http://127.0.0.1:8000/health")
                if r.status_code == 200:
                    already_running = True
        except Exception:
            already_running = False

        if not already_running:
            server_config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="error")
            server = uvicorn.Server(server_config)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()
            server_started_by_us = True
            await asyncio.sleep(1.8)

        backend_online = False
        honest_empty = False
        ws_origin_allowed = False

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r_health = await client.get("http://127.0.0.1:8000/health")
                backend_online = (r_health.status_code == 200)

                r_live = await client.get("http://127.0.0.1:8000/api/live")
                if r_live.status_code == 200:
                    data = r_live.json()
                    honest_empty = (
                        isinstance(data.get("turns"), list) and len(data.get("turns")) == 0 and
                        isinstance(data.get("disputes"), list) and len(data.get("disputes")) == 0 and
                        data.get("active_dispute") is None and
                        data.get("fact_check_mode") == "OFF"
                    )

            # Test WebSocket origin
            try:
                async with websockets.connect(
                    "ws://127.0.0.1:8000/api/ws",
                    origin="http://localhost:3000",
                    open_timeout=3.0
                ) as ws:
                    init_msg = await ws.recv()
                    ws_origin_allowed = bool(init_msg and "initial_state" in init_msg)
            except Exception:
                ws_origin_allowed = False

        finally:
            if server_started_by_us and server:
                server.should_exit = True
                if server_thread:
                    server_thread.join(timeout=3.0)

        self.record(
            "7.1 Dashboard: Backend Startup (Port 8000)",
            "Online (HTTP 200)" if backend_online else "Offline / Port blocked",
            "Online (HTTP 200)",
            backend_online,
            "Start backend via start_backend.bat or check port 8000 availability"
        )

        self.record(
            "7.2 Dashboard: Honest Empty State (/api/live)",
            "Honest empty state (0 turns, 0 disputes)" if honest_empty else "Contains stale/mock data",
            "Honest empty state (0 turns, 0 disputes)",
            honest_empty,
            "Ensure /api/live returns clean initial LIVE_STATE without mock payloads"
        )

        self.record(
            "7.3 Dashboard: WebSocket Origin Check (/api/ws)",
            "Allowed (http://localhost:3000)" if ws_origin_allowed else "Rejected / Disconnected",
            "Allowed (http://localhost:3000)",
            ws_origin_allowed,
            "Add http://localhost:3000 to CORS_ORIGINS in .env"
        )

    # -------------------------------------------------------------------------
    # 8. DISCORD COMMANDS
    # -------------------------------------------------------------------------
    def check_discord_commands(self):
        required_commands = [
            "start", "join", "leave", "check", "arbitrate",
            "recap", "stats", "status", "dashboard", "privacy", "judge-mode",
            "start-capture", "stop-capture", "clear"
        ]
        registered = [c.name for c in bot.commands]
        missing = [cmd for cmd in required_commands if cmd not in registered]

        all_present = (len(missing) == 0)
        self.record(
            "8.1 Discord: Registered Command Inventory",
            f"All {len(required_commands)} present" if all_present else f"Missing: {missing}",
            f"All {len(required_commands)} commands registered",
            all_present,
            f"Register missing commands in bot/main.py: {missing}"
        )

    # -------------------------------------------------------------------------
    # RUNNER & REPORT FORMATTER
    # -------------------------------------------------------------------------
    async def run_all(self):
        print("\n=======================================================")
        print("  CALLWRAPPED — LIVE READINESS VERIFICATION AUDIT")
        print("=======================================================\n")

        self.check_feature_flags()
        await self.check_groq_pool()
        await self.check_assemblyai()
        self.check_classifier()
        self.check_referee()
        self.check_tts()
        await self.check_dashboard()
        self.check_discord_commands()

        # Render Markdown Table
        print("| Check | Current | Expected | PASS/FAIL |")
        print("|---|---|---|---|")
        passed_count = 0
        total_count = len(self.results)

        for r in self.results:
            if r["status"] == "PASS":
                passed_count += 1
            print(f"| {r['check']} | `{r['current']}` | `{r['expected']}` | **{r['status']}** |")

        print("\n" + "=" * 55)
        print(f"LIVE READY: {passed_count}/{total_count} checks passed")
        print("=" * 55)

        if self.failures:
            print("\n[!] EXACT REMEDIATION REQUIRED:")
            for f in self.failures:
                print(f"  * {f}")
            print("\n[!] Update .env or configuration as specified above before starting the live session.")
            return False
        else:
            print("\n[+] ALL LIVE READINESS CHECKS PASSED -- READY FOR LIVE SESSION!")
            return True


async def main():
    auditor = ReadinessAuditor()
    success = await auditor.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
