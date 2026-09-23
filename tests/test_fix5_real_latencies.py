import tests._setup

import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.main import manual_arbitrate, simulate_demo
from bot.events.models import VoiceEvent


class TestFix5RealLatencies(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test for Fix 5:
    - Tests !arbitrate and !simulate send real measured latencies (not hardcoded stt=10, search=540, tts=175).
    - Tests dynamic speaker winner/loser resolution.
    - Pastes VoiceEvent payload.
    """

    async def test_manual_arbitrate_measured_latencies(self):
        # Mock Context
        ctx = AsyncMock()
        ctx.guild.id = 111222
        ctx.author.display_name = "Tamer"
        ctx.send = AsyncMock()
        mock_msg = AsyncMock()
        ctx.send.return_value = mock_msg

        # Mock verify_dispute returning measured latencies
        measured_search_ms = 312
        measured_synth_ms = 189
        mock_verdict = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "NVIDIA RTX 5070 has 12GB VRAM",
            "selected_source_url": "https://nvidia.com/specs",
            "selected_source_title": "NVIDIA Specifications",
            "confidence": 98,
            "spoken_intervention": "Correction: RTX 5070 features 12GB VRAM."
        }

        captured_events = []
        def capture_publish(event: VoiceEvent):
            if event.type == "intervention":
                captured_events.append(event)

        with patch("bot.main.arbitration_verifier.verify_dispute", new_callable=AsyncMock) as mock_verify, \
             patch("bot.main.publisher.publish_sync_task", side_effect=capture_publish):

            mock_verify.return_value = (mock_verdict, measured_search_ms, measured_synth_ms, [])

            await manual_arbitrate(ctx, query="RTX 5070 has 16GB")

            self.assertEqual(len(captured_events), 1)
            event = captured_events[0]

            # Latency Breakdown assertions: NO hardcoded stt=10, search=540
            self.assertEqual(event.latency.stt_ms, 0, "STT must be 0ms for text chat command")
            self.assertEqual(event.latency.search_ms, measured_search_ms)
            self.assertEqual(event.latency.llm_ms, measured_synth_ms)
            self.assertEqual(event.latency.tts_ms, 0, "TTS must be 0ms when voice not connected")

            # Dynamic speaker resolution assertions
            self.assertEqual(event.payload["loser"], "Tamer", "Speaker A (Tamer) must be loser for CONTRADICTED")
            self.assertEqual(event.payload["winner"], "Fact Checker", "Speaker B must be winner for SUPPORTED")
            self.assertEqual(event.payload["status"], "contradicted")

            print("\n" + "=" * 60)
            print("=== FIX 5 ACCEPTANCE: !arbitrate VoiceEvent Payload ===")
            print("=" * 60)
            print(json.dumps({
                "type": event.type,
                "speaker_name": event.speaker_name,
                "latency": {
                    "stt_ms": event.latency.stt_ms,
                    "llm_ms": event.latency.llm_ms,
                    "search_ms": event.latency.search_ms,
                    "tts_ms": event.latency.tts_ms
                },
                "payload": event.payload
            }, indent=2, ensure_ascii=False))

    async def test_simulate_demo_measured_latencies(self):
        ctx = AsyncMock()
        ctx.guild.id = 111333
        ctx.send = AsyncMock()

        measured_search_ms = 410
        measured_synth_ms = 220
        mock_verdict = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "NVIDIA GeForce RTX 5070 features 12GB GDDR7 VRAM.",
            "selected_source_url": "https://nvidia.com/specs",
            "selected_source_title": "Official Specs",
            "confidence": 99,
            "spoken_intervention": "Correction: RTX 5070 features 12GB GDDR7 memory."
        }

        captured_events = []
        def capture_publish(event: VoiceEvent):
            if event.type == "intervention":
                captured_events.append(event)

        with patch("bot.main.arbitration_verifier.verify_dispute", new_callable=AsyncMock) as mock_verify, \
             patch("bot.main.publisher.publish_sync_task", side_effect=capture_publish):

            mock_verify.return_value = (mock_verdict, measured_search_ms, measured_synth_ms, [])

            await simulate_demo(ctx)

            self.assertEqual(len(captured_events), 1)
            event = captured_events[0]

            # Latency Breakdown assertions: NO hardcoded stt=260, search=540, tts=175
            self.assertEqual(event.latency.stt_ms, 0, "STT must be 0ms for simulated text")
            self.assertEqual(event.latency.search_ms, measured_search_ms)
            self.assertEqual(event.latency.llm_ms, measured_synth_ms)
            self.assertEqual(event.latency.tts_ms, 0, "TTS must be 0ms when voice not connected")

            # Dynamic speaker resolution assertions
            self.assertEqual(event.payload["loser"], "Ahmed")
            self.assertEqual(event.payload["winner"], "Omar")

            print("\n" + "=" * 60)
            print("=== FIX 5 ACCEPTANCE: !simulate VoiceEvent Payload ===")
            print("=" * 60)
            print(json.dumps({
                "type": event.type,
                "speaker_name": event.speaker_name,
                "latency": {
                    "stt_ms": event.latency.stt_ms,
                    "llm_ms": event.latency.llm_ms,
                    "search_ms": event.latency.search_ms,
                    "tts_ms": event.latency.tts_ms
                },
                "payload": event.payload
            }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
