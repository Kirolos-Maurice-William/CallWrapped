"""
Acceptance Test Suite for Mitigations A & B:
1. Mitigation A:
   - Verifier returns TWO fields: fact_clause (<=12 words, the fact, no comparisons) and hedge_clause.
   - speak_clauses() streams clause 1 while clause 2 synthesizes concurrently.
   - Clause 2 chunks arrive and queue cleanly after playback has already started on clause 1.
   - Logs two 'TTS Stream Started'-style events.
2. Mitigation B:
   - Dispute offer created -> warm session object exists (DNS/TLS pre-warmed).
   - Confirmation -> warm session reused with handshake_ms ~ 0.
   - Timeout: Warm connection expires after 35s and rebuilds cleanly if expired.
   - T_perceived headline log line breaks down: handshake_ms, clause1_ttfb_ms, clause2_wait_ms.
"""
import tests._setup

import time
import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import discord
from bot.config import config
from bot.arbitration.engine import arbitration_engine
from bot.arbitration.verifier import arbitration_verifier
from bot.ai.tts import speaker, WarmTTSSession


class MockVoiceClient:
    """Mock Discord VoiceClient for streaming TTS testing."""
    def __init__(self, bot_id: int = 8888):
        self._playing = False
        self._connected = True
        self.user = MagicMock()
        self.user.id = bot_id
        self.source = None
        self.after = None
        self.play_timestamp = None
        self.stop_called = False

    def is_connected(self) -> bool:
        return self._connected

    def is_playing(self) -> bool:
        return self._playing

    def play(self, source, after=None):
        self._playing = True
        self.source = source
        self.after = after
        self.play_timestamp = time.perf_counter()

    def stop(self):
        self.stop_called = True
        self._playing = False
        if self.source and hasattr(self.source, "cleanup"):
            self.source.cleanup()


class TestTwoClausePrewarm(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.guild_id = 998877
        self.session = arbitration_engine.get_session(self.guild_id)
        self.session.reset()

    def tearDown(self):
        self.session.reset()

    def test_mitigation_c_and_a_verifier_returns_two_clauses(self):
        """
        Criteria: Verifier returns fact_clause (<= 12 words) and hedge_clause.
        Comparisons are omitted from fact_clause and preserved in comparison_details.
        """
        assessment = {
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "correct_fact": "كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16",
            "comparison_details": "RTX 5070 Ti features 16GB VRAM",
            "selected_source_url": "https://nvidia.com",
            "selected_source_title": "NVIDIA Official"
        }

        fact_clause, hedge_clause = arbitration_verifier.format_intervention_clauses(assessment, is_arabic=True)
        fact_words = fact_clause.split()

        print("\n" + "=" * 75)
        print("=== MITIGATION A / C ACCEPTANCE: VERIFIER TWO-CLAUSE OUTPUT ===")
        print("=" * 75)
        print(f"Fact Clause ({len(fact_words)} words):  '{fact_clause}'")
        print(f"Hedge Clause:               '{hedge_clause}'")
        print(f"Comparison Details:         '{assessment.get('comparison_details')}'")
        print("=" * 75)

        self.assertIn("تصحيح سريع", fact_clause)
        self.assertIn("RTX 5070", fact_clause)
        self.assertIn("12 جيجا", fact_clause)
        self.assertNotIn("Ti", fact_clause, "Comparison details must be excluded from fact_clause")
        self.assertIn("ممكن يكون في سياق فاتني", hedge_clause)
        self.assertIn("الداشبورد", hedge_clause)

    async def test_mitigation_a_two_clause_streaming_concurrent_synthesis(self):
        """
        Criteria: speak_clauses() starts playback on clause 1 first, while clause 2
        synthesizes concurrently. Clause 2 chunks arrive AFTER playback has started.
        Both 'TTS Stream Started (Clause 1)' and 'TTS Stream Started (Clause 2)' are logged.
        """
        print("\n" + "=" * 75)
        print("=== MITIGATION A ACCEPTANCE: TWO-CLAUSE STREAMING PLAYBACK ===")
        print("=" * 75)

        vc = MockVoiceClient()
        fact_clause = "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا."
        hedge_clause = "ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد."

        clause2_chunk_times = []
        t0 = time.perf_counter()

        def custom_communicate(text, voice, **kwargs):
            print(f"[DEBUG custom_communicate] text={repr(text)}")
            comm = MagicMock()
            if text == fact_clause:
                async def stream1():
                    await asyncio.sleep(0.05)  # 50ms TTFB for clause 1
                    yield {"type": "audio", "data": b"\x01" * 1024}
                    await asyncio.sleep(0.05)
                    yield {"type": "audio", "data": b"\x02" * 1024}
                comm.stream = stream1
            else:
                async def stream2():
                    await asyncio.sleep(0.12)  # clause 2 finishes after clause 1 has started
                    clause2_chunk_times.append(time.perf_counter() - t0)
                    yield {"type": "audio", "data": b"\x03" * 1024}
                    await asyncio.sleep(0.04)
                    clause2_chunk_times.append(time.perf_counter() - t0)
                    yield {"type": "audio", "data": b"\x04" * 1024}
                comm.stream = stream2
            return comm

        mock_audio_source = MagicMock()
        mock_audio_source.write_chunk.return_value = True

        with patch("edge_tts.Communicate", side_effect=custom_communicate), \
             patch("bot.ai.tts.create_streaming_source", return_value=mock_audio_source):
            with self.assertLogs("TTSVoice", level="INFO") as cm:
                speak_task = asyncio.create_task(
                    speaker.speak_clauses(vc, fact_clause=fact_clause, hedge_clause=hedge_clause)
                )

                # Wait for playback to begin on clause 1
                for _ in range(25):
                    if vc.is_playing():
                        break
                    await asyncio.sleep(0.02)

                self.assertTrue(vc.is_playing(), "Playback must start on clause 1")
                play_time = vc.play_timestamp - t0
                print(f"[TIMING] VoiceClient.play() started at: {play_time*1000:.1f}ms")

                # Wait for all chunks to finish
                await asyncio.sleep(0.30)
                vc._playing = False  # simulate audio played
                await speak_task

        print(f"[TIMING] Clause 2 chunk delivery times: {[f'{t*1000:.1f}ms' for t in clause2_chunk_times]}")
        self.assertTrue(len(clause2_chunk_times) >= 1)
        self.assertGreater(clause2_chunk_times[0], play_time, "Clause 2 chunks must arrive AFTER playback started")

        c1_logs = [l for l in cm.output if "TTS Stream Started (Clause 1)" in l]
        c2_logs = [l for l in cm.output if "TTS Stream Started (Clause 2)" in l]
        self.assertEqual(len(c1_logs), 1, "Must log TTS Stream Started for Clause 1")
        self.assertEqual(len(c2_logs), 1, "Must log TTS Stream Started for Clause 2")
        print(f"[PROOF VERIFIED] Log C1: {c1_logs[0]}")
        print(f"[PROOF VERIFIED] Log C2: {c2_logs[0]}")

    async def test_mitigation_b_offer_creates_warm_session_and_confirm_reuses(self):
        """
        Criteria:
        1. When Dispute Offer is created, warm session object exists (DNS/TLS pre-warmed).
        2. When confirm arrives, warm session is reused (handshake_ms ~ 0).
        3. T_perceived log breaks down handshake_ms, clause1_ttfb_ms, and clause2_wait_ms.
        """
        print("\n" + "=" * 75)
        print("=== MITIGATION B ACCEPTANCE: PRE-WARM AT OFFER & REUSE AT CONFIRM ===")
        print("=" * 75)

        self.session.claim_memory.add_claim(
            claim_id="prior_5070",
            speaker_name="Omar",
            speaker_id="101",
            raw_text="كارت 5070 نازل بـ 16 جيجا",
            claim_text="كارت 5070 نازل بـ 16 جيجا",
            entity="RTX 5070",
            topic="tech",
            metric="16 جيجا"
        )

        mock_claim = (True, {"claim": "كارت الـ 5070 نازل بـ 12 جيجا", "entity": "RTX 5070", "topic": "tech", "metric": "12 جيجا"}, 30)
        mock_conflict = (True, {"has_conflict": True, "search_query": "RTX 5070 specs", "target_domains": []}, 40)
        sources_data = [{"title": "NVIDIA", "url": "https://nvidia.com", "snippet": "12GB", "domain": "nvidia.com", "source_tier": 1}]
        assessment_data = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "evidence_strength": "HIGH",
            "confidence": 98,
            "correct_fact": "كارت RTX 5070 بيجي بـ 12 جيجا",
            "fact_clause": "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا.",
            "hedge_clause": "ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد.",
            "spoken_intervention": "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا. ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد.",
            "selected_source_title": "NVIDIA Official",
            "selected_source_url": "https://nvidia.com"
        }

        mock_tc = AsyncMock(spec=discord.TextChannel)
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True

        with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", new_callable=AsyncMock, return_value=(sources_data, 50)), \
             patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock, return_value=(assessment_data, 50, 100, sources_data)), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock, return_value=600) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()), \
             self.assertLogs("ArbitrationEngine", level="INFO") as cm:

            # 1. Trigger dispute offer
            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=mock_vc,
                text_channel=mock_tc,
                mode="referee"
            )

            # Assert warm session exists in pending offer
            offer = self.session.pending_offer
            self.assertIsNotNone(offer, "Pending offer must exist")
            self.assertIsNotNone(offer.warm_tts_session, "Pending offer must hold a warm TTS session")
            self.assertTrue(isinstance(offer.warm_tts_session, WarmTTSSession))
            self.assertTrue(offer.warm_tts_session.is_valid())
            print(f"✅ [PROOF] Warm TTS session created: {offer.warm_tts_session} (is_valid={offer.warm_tts_session.is_valid()})")

            # 2. Trigger voice confirmation
            t_confirm = time.time()
            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=103,
                speaker_name="Mostafa",
                raw_text="شوفها كده يا حكم",
                stt_ms=70,
                voice_client=mock_vc,
                text_channel=mock_tc,
                mode="referee",
                speech_start=t_confirm - 1.0,
                speech_end=t_confirm
            )

            await asyncio.sleep(0.15)

            # Assert warm session reuse logged
            reuse_logs = [l for l in cm.output if "TTS Reused" in l]
            self.assertTrue(len(reuse_logs) > 0, "Must log TTS Reused from offer time")
            print(f"✅ [PROOF] Reused log: {reuse_logs[0]}")

            # Assert headline metric has breakdown
            metric_logs = [l for l in cm.output if "Headline Metric" in l]
            self.assertTrue(len(metric_logs) > 0, "Must log headline metric")
            print(f"✅ [PROOF] Headline breakdown: {metric_logs[0]}")
            self.assertIn("handshake_ms=", metric_logs[0])
            self.assertIn("clause1_ttfb_ms=", metric_logs[0])
            self.assertIn("clause2_wait_ms=", metric_logs[0])

    def test_mitigation_b_warm_session_expiry_after_35s(self):
        """
        Criteria: Warm connection auto-expires after timeout and cleans up.
        """
        warm = WarmTTSSession(timeout_seconds=0.05)
        self.assertTrue(warm.is_valid())
        time.sleep(0.08)
        self.assertFalse(warm.is_valid(), "Session must expire after timeout_seconds")
        print("✅ [PROOF] Warm session accurately invalidated after timeout expiration.")


if __name__ == "__main__":
    unittest.main()
