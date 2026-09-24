import tests._setup

import time
import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import discord
from discord.ext import commands
from bot.config import config
from bot.arbitration.engine import arbitration_engine, is_confirmation_utterance, PendingOffer
from bot.arbitration.claim_memory import StoredClaim
from bot.events.models import VoiceEvent
from bot.main import bot, start_session, check_dispute, build_fact_check_mode_embed


class TestTwoStageReferee(unittest.IsolatedAsyncioTestCase):
    """
    Acceptance test suite for Two-Stage Referee:
    1. Flow change: When gates pass -> offer text posted, VoiceEvent(dispute_check_offered) published,
       Tavily search prefetch started in background, pending offer with 30s expiry, ZERO unsolicited TTS.
    2. Confirmation paths:
       - Voice: Utterance matching keywords ('شوفها', 'شوف', 'اكد', 'اتأكد', 'تحقق', 'check it', 'check')
         via local keyword matching (0 LLMs) confirms verification and processes normally.
       - Text: !check command confirms offer.
    3. On confirmation:
       - Awaits prefetched search (capped at 5s)
       - Groq synthesis + template
       - TTS speaks hedged verdict (ONLY path that speaks)
       - Logs headline metric: T_perceived = t_first_audio - t_confirm_end
       - Publishes dispute_check_completed VoiceEvent
    4. On expiry:
       - 30s without confirmation -> cancels prefetch, logs 'ABSTAIN: offered_not_confirmed',
         publishes dispute_check_expired, zero speech.
    5. Cooldown: Max 1 offer per 3 min (180s) -> second dispute within 180s drops with log.
    6. Replaces older pending offer with warning if unconfirmed.
    7. !start command sets Fact Check Mode ON and publishes fact_check_mode_update event.
    """

    def setUp(self):
        self.guild_id = 900777
        self.session = arbitration_engine.get_session(self.guild_id)
        self.session.reset()

    def tearDown(self):
        self.session.reset()

    def test_confirmation_keywords_local_matching(self):
        """Proves local keyword matching works for all required keywords without LLM calls."""
        valid_phrases = [
            "شوفها",
            "طب شوف",
            "اكد",
            "اتأكد من المعلومة يا حكم",
            "تحقق لو سمحت",
            "check it please",
            "check",
            "شوفها، كارت الـ RTX 5070 نازل بـ 12 جيجا"
        ]
        for phrase in valid_phrases:
            self.assertTrue(is_confirmation_utterance(phrase), f"Failed to match valid confirmation: '{phrase}'")

        invalid_phrases = [
            "ماتش امبارح كان وحش",
            "أنا بقول 16 جيجا",
            "لا مش كده خالص",
            "checkout this website",
            "سلام عليكم"
        ]
        for phrase in invalid_phrases:
            self.assertFalse(is_confirmation_utterance(phrase), f"Incorrectly matched invalid phrase: '{phrase}'")

    async def test_a_gate_pass_offers_and_prefetches_with_zero_tts(self):
        """
        Test a: Gate pass -> offer event published + pre-fetch started, ZERO TTS.
        Assert pre-fetch is running before any confirmation.
        """
        self.session.claim_memory.add_claim(
            claim_id="prior_claim_1",
            speaker_name="Omar",
            speaker_id="101",
            raw_text="كارت 5070 نازل بـ 16 جيجا",
            claim_text="كارت 5070 نازل بـ 16 جيجا",
            entity="RTX 5070",
            topic="tech",
            metric="16 جيجا"
        )

        mock_claim = (True, {"claim": "كارت الـ 5070 نازل بـ 12 جيجا", "entity": "RTX 5070", "topic": "tech", "metric": "12 جيجا"}, 30)
        mock_conflict = (True, {"has_conflict": True, "search_query": "RTX 5070 VRAM specs", "target_domains": []}, 40)

        published_events = []
        def mock_publish(evt):
            published_events.append(evt)

        search_started_event = asyncio.Event()
        search_finish_event = asyncio.Event()

        async def mock_search(query, target_domains=None):
            search_started_event.set()
            await search_finish_event.wait()
            return [{"title": "NVIDIA Specs", "url": "https://nvidia.com", "domain": "nvidia.com", "snippet": "12GB GDDR7"}], 50

        mock_text_channel = AsyncMock(spec=discord.TextChannel)

        with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", side_effect=mock_search), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=mock_publish):

            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=None,
                text_channel=mock_text_channel,
                mode="referee"
            )

            # 1. Assert prefetch search has started in background
            await asyncio.wait_for(search_started_event.wait(), timeout=1.0)
            self.assertTrue(search_started_event.is_set(), "Search pre-fetch must have started immediately in background")

            # 2. Assert offer message sent to text channel (call 1 is transcript mirror, call 2 is offer)
            self.assertEqual(mock_text_channel.send.call_count, 2)
            offer_msg = mock_text_channel.send.call_args_list[1][0][0]
            self.assertIn("🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟ قول «شوفها» أو اكتب !check", offer_msg)

            # 3. Assert VoiceEvent(dispute_check_offered) was published
            offer_events = [e for e in published_events if e.type == "dispute_check_offered"]
            self.assertEqual(len(offer_events), 1, "Must publish exactly 1 dispute_check_offered event")
            self.assertEqual(offer_events[0].payload["entity"], "RTX 5070")

            # 4. Assert pending offer registered with 30s expiry
            self.assertIsNotNone(self.session.pending_offer)
            self.assertFalse(self.session.pending_offer.is_resolved)
            self.assertFalse(self.session.pending_offer.prefetch_task.done(), "Prefetch should be running concurrently")

            # 5. Assert ZERO TTS speech occurred
            mock_speak.assert_not_called()

            # Clean up background search task
            search_finish_event.set()
            await asyncio.sleep(0.05)

    async def test_b_voice_confirmation_triggers_verification_and_logs_t_perceived(self):
        """
        Test b: Voice confirmation utterance ('شوفها') -> verifier runs -> TTS called,
        T_perceived logged with real number, dispute_check_completed published.
        """
        self.session.claim_memory.add_claim(
            claim_id="prior_claim_2",
            speaker_name="Omar",
            speaker_id="101",
            raw_text="كارت 5070 نازل بـ 16 جيجا",
            claim_text="كارت 5070 نازل بـ 16 جيجا",
            entity="RTX 5070",
            topic="tech",
            metric="16 جيجا"
        )

        mock_claim = (True, {"claim": "كارت الـ 5070 نازل بـ 12 جيجا", "entity": "RTX 5070", "topic": "tech", "metric": "12 جيجا"}, 30)
        mock_conflict = (True, {"has_conflict": True, "search_query": "RTX 5070 VRAM specs", "target_domains": []}, 40)
        sources_data = [{"title": "NVIDIA Official", "url": "https://nvidia.com", "domain": "nvidia.com", "snippet": "12GB GDDR7"}]

        assessment_data = {
            "status": "CONTRADICTED",
            "speaker_a_status": "CONTRADICTED",
            "speaker_b_status": "SUPPORTED",
            "evidence_strength": "HIGH",
            "confidence": 98,
            "correct_fact": "كارت RTX 5070 يأتي بذاكرة 12 جيجابايت وليس 16",
            "spoken_intervention": "تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 يأتي بذاكرة 12 جيجابايت. ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد.",
            "selected_source_title": "NVIDIA Official",
            "selected_source_url": "https://nvidia.com"
        }

        published_events = []
        def mock_publish(evt):
            published_events.append(evt)

        mock_text_channel = AsyncMock(spec=discord.TextChannel)
        mock_voice_client = MagicMock(spec=discord.VoiceClient)
        mock_voice_client.is_connected.return_value = True

        with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", new_callable=AsyncMock, return_value=(sources_data, 60)), \
             patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock, return_value=(assessment_data, 60, 150, sources_data)), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock, return_value=850) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=mock_publish), \
             self.assertLogs("ArbitrationEngine", level="INFO") as cm:

            # 1. Trigger dispute offer
            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=mock_voice_client,
                text_channel=mock_text_channel,
                mode="referee"
            )

            self.assertIsNotNone(self.session.pending_offer)
            offer_id = self.session.pending_offer.offer_id

            # 2. Participant says 'شوفها'
            t_confirm = time.time()
            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=103,
                speaker_name="Mostafa",
                raw_text="شوفها كده يا حكم",
                stt_ms=80,
                voice_client=mock_voice_client,
                text_channel=mock_text_channel,
                mode="referee",
                speech_start=t_confirm - 1.2,
                speech_end=t_confirm
            )

            # Yield to let confirmation task execute
            await asyncio.sleep(0.15)

            # 3. Assert TTS was called with hedged verdict
            mock_speak.assert_called_once_with(mock_voice_client, assessment_data["spoken_intervention"])

            # 4. Assert headline metric T_perceived was logged
            headline_logs = [line for line in cm.output if "T_perceived" in line]
            self.assertTrue(len(headline_logs) > 0, "Must log T_perceived headline metric")
            print(f"\n[ACCEPTANCE PROOF] Log line: {headline_logs[0]}")

            # 5. Assert VoiceEvent(dispute_check_completed) published
            completed_events = [e for e in published_events if e.type == "dispute_check_completed"]
            self.assertEqual(len(completed_events), 1)
            self.assertEqual(completed_events[0].payload["offer_id"], offer_id)
            self.assertEqual(completed_events[0].payload["confirmed_by"], "Mostafa")
            self.assertEqual(completed_events[0].payload["status"], "CONTRADICTED")

            # 6. Assert pending offer cleared
            self.assertIsNone(self.session.pending_offer)

    async def test_c_offer_expires_after_30s_without_confirmation(self):
        """
        Test c: 30s expiry -> 'ABSTAIN: offered_not_confirmed' logged, no TTS,
        dispute_check_expired published.
        """
        self.session.claim_memory.add_claim(
            claim_id="prior_claim_3",
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

        published_events = []
        def mock_publish(evt):
            published_events.append(evt)

        # Set expiry timeout to 0.05s for rapid unit test
        with patch.object(config, "DISPUTE_OFFER_EXPIRY_SEC", 0.05), \
             patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", new_callable=AsyncMock, return_value=([], 10)), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=mock_publish), \
             self.assertLogs("ArbitrationEngine", level="INFO") as cm:

            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=None,
                text_channel=None,
                mode="referee"
            )

            self.assertIsNotNone(self.session.pending_offer)
            offer_id = self.session.pending_offer.offer_id

            # Wait for 0.05s timer to expire
            await asyncio.sleep(0.1)

            # Assert ABSTAIN log line was logged
            abstain_logs = [line for line in cm.output if "ABSTAIN: offered_not_confirmed" in line]
            self.assertTrue(len(abstain_logs) > 0, "Must log ABSTAIN: offered_not_confirmed on expiry")
            print(f"\n[ACCEPTANCE PROOF] Log line: {abstain_logs[0]}")

            # Assert dispute_check_expired published
            expired_events = [e for e in published_events if e.type == "dispute_check_expired"]
            self.assertEqual(len(expired_events), 1)
            self.assertEqual(expired_events[0].payload["offer_id"], offer_id)

            # Assert ZERO speech occurred
            mock_speak.assert_not_called()
            self.assertIsNone(self.session.pending_offer)

    async def test_d_cooldown_suppresses_second_dispute_within_180s(self):
        """
        Test d: 3-min cooldown -> second dispute within 180s suppresses second offer
        with log 'DISPUTE_SUPPRESSED: cooldown active (remaining: Xs)'.
        """
        self.session.claim_memory.add_claim(
            claim_id="prior_claim_4",
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

        with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", new_callable=AsyncMock, return_value=([], 10)), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock), \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()), \
             self.assertLogs("ArbitrationEngine", level="INFO") as cm:

            # First dispute passes gates -> creates Offer 1
            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=None,
                text_channel=None,
                mode="referee"
            )

            self.assertIsNotNone(self.session.pending_offer)
            first_offer_id = self.session.pending_offer.offer_id

            # Add another conflicting claim in memory for a second dispute
            self.session.claim_memory.add_claim(
                claim_id="prior_claim_5",
                speaker_name="Omar",
                speaker_id="101",
                raw_text="ماتش الأهلي الساعة 9",
                claim_text="ماتش الأهلي الساعة 9",
                entity="الأهلي",
                topic="sports",
                metric="الساعة 9"
            )

            mock_claim_2 = (True, {"claim": "ماتش الأهلي الساعة 8", "entity": "الأهلي", "topic": "sports", "metric": "الساعة 8"}, 30)
            mock_conflict_2 = (True, {"has_conflict": True, "search_query": "Al Ahly match time", "target_domains": []}, 40)

            with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim_2), \
                 patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict_2):

                # Second dispute passes gates only 5 seconds later
                await arbitration_engine.process_utterance(
                    guild_id=self.guild_id,
                    user_id=104,
                    speaker_name="Tamer",
                    raw_text="ماتش الأهلي الساعة 8",
                    stt_ms=90,
                    voice_client=None,
                    text_channel=None,
                    mode="referee"
                )

            # Assert cooldown suppression log appeared
            suppressed_logs = [line for line in cm.output if "DISPUTE_SUPPRESSED: cooldown active" in line]
            self.assertTrue(len(suppressed_logs) > 0, "Second dispute within 180s must be suppressed with cooldown log")
            print(f"\n[ACCEPTANCE PROOF] Cooldown Log: {suppressed_logs[0]}")

            # Original offer remains intact and was not overwritten
            self.assertEqual(self.session.pending_offer.offer_id, first_offer_id)

    async def test_e_start_command_announces_fact_check_mode_and_publishes_event(self):
        """
        Test e: !start command sets Fact Check Mode ON and publishes fact_check_mode_update event.
        """
        mock_ctx = AsyncMock(spec=commands.Context)
        mock_ctx.guild.id = self.guild_id
        mock_ctx.author.display_name = "Judge_Omar"

        published_events = []
        def mock_publish(evt):
            published_events.append(evt)

        with patch("bot.main.publisher.publish_sync_task", side_effect=mock_publish):
            await start_session(mock_ctx)

            # 1. Assert session state updated
            self.assertTrue(self.session.fact_check_mode, "Session fact_check_mode must be True")

            # 2. Assert Discord message sent with announcement
            mock_ctx.send.assert_called_once()
            sent_embed = mock_ctx.send.call_args[1].get("embed") or mock_ctx.send.call_args[0][0]
            self.assertIn("Fact Check Mode: ON", sent_embed.title)
            self.assertIn("offers only — bot never speaks uninvited", sent_embed.description)

            # 3. Assert VoiceEvent published
            mode_events = [e for e in published_events if e.type == "fact_check_mode_update"]
            self.assertEqual(len(mode_events), 1)
            self.assertEqual(mode_events[0].payload["mode"], "ON")
            self.assertEqual(mode_events[0].payload["badge"], "Fact Check Mode: ON")
            print(f"\n[ACCEPTANCE PROOF] !start mode event: {mode_events[0].payload}")

    async def test_f_check_command_confirms_pending_offer(self):
        """
        Test f: !check command confirms pending offer via text channel.
        """
        # Register a pending offer manually
        search_task = asyncio.create_task(asyncio.sleep(0.01))
        offer = PendingOffer(
            offer_id="off_test_text",
            guild_id=self.guild_id,
            speaker_a="Omar",
            claim_a="16GB",
            speaker_b="Ziad",
            claim_b="12GB",
            entity="RTX 5070",
            search_query="RTX 5070 specs",
            target_domains=[],
            prefetch_task=search_task,
            created_at=time.time(),
            expires_at=time.time() + 30.0
        )
        self.session.pending_offer = offer

        mock_ctx = AsyncMock(spec=commands.Context)
        mock_ctx.guild.id = self.guild_id
        mock_ctx.author.display_name = "TextUser"
        mock_ctx.channel = AsyncMock(spec=discord.TextChannel)

        with patch("bot.arbitration.engine.arbitration_engine.confirm_dispute_offer", new_callable=AsyncMock) as mock_confirm:
            await check_dispute(mock_ctx)

            mock_ctx.send.assert_called_once()
            mock_confirm.assert_called_once()
            print(f"\n[ACCEPTANCE PROOF] !check confirmed offer with args: {mock_confirm.call_args}")

    async def test_g_confirming_utterance_with_claim_confirms_and_processes_normally(self):
        """
        Test g: If the confirmation utterance ALSO contains a claim, it confirms the check AND processes normally.
        Verifies talk time stats recorded, analytics buffered, and claim added to ClaimMemory.
        """
        search_task = asyncio.create_task(asyncio.sleep(0.01))
        offer = PendingOffer(
            offer_id="off_dual",
            guild_id=self.guild_id,
            speaker_a="Omar",
            claim_a="16GB",
            speaker_b="Ziad",
            claim_b="12GB",
            entity="RTX 5070",
            search_query="RTX 5070 specs",
            target_domains=[],
            prefetch_task=search_task,
            created_at=time.time(),
            expires_at=time.time() + 30.0
        )
        self.session.pending_offer = offer

        raw_text = "شوفها، كارت الـ RTX 5070 نازل بـ 12 جيجا بايت بس"
        mock_claim = (True, {"claim": "كارت الـ RTX 5070 نازل بـ 12 جيجا بايت بس", "entity": "RTX 5070", "topic": "tech", "metric": "12 جيجا"}, 30)

        with patch("bot.arbitration.engine.arbitration_engine.confirm_dispute_offer", new_callable=AsyncMock) as mock_confirm, \
             patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):

            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=105,
                speaker_name="Ziad",
                raw_text=raw_text,
                stt_ms=90,
                voice_client=None,
                text_channel=None,
                mode="referee",
                speech_start=0.0,
                speech_end=2.5
            )

            # 1. Assert confirmation was dispatched
            mock_confirm.assert_called_once()
            self.assertEqual(mock_confirm.call_args[1]["confirmed_by"], "Ziad")

            # 2. Assert talk time recorded
            stats = self.session.stats_tracker.get_speaker("105")
            self.assertIsNotNone(stats)
            self.assertEqual(stats.total_speak_seconds, 2.5)

            # 3. Assert claim was processed and saved in ClaimMemory
            stored_claims = self.session.claim_memory.claims
            self.assertTrue(any(c.entity == "RTX 5070" for c in stored_claims), "Claim must be stored in ClaimMemory")
            print(f"\n[ACCEPTANCE PROOF] Dual confirmation & claim successfully verified: {stats.total_speak_seconds}s recorded, claim stored.")

    async def test_h_replaces_older_pending_offer_with_warning(self):
        """
        Test h: If a new offer triggers while an older one is pending (unconfirmed), replace the older one and log a warning.
        """
        self.session.claim_memory.add_claim(
            claim_id="prior_claim_h",
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

        # Existing unconfirmed pending offer
        old_search_task = asyncio.create_task(asyncio.sleep(10.0))
        old_offer = PendingOffer(
            offer_id="off_older_unconfirmed",
            guild_id=self.guild_id,
            speaker_a="Omar",
            claim_a="Old Claim",
            speaker_b="Ziad",
            claim_b="Old Claim",
            entity="OldEntity",
            search_query="old query",
            target_domains=[],
            prefetch_task=old_search_task,
            created_at=time.time() - 200,  # outside cooldown
            expires_at=time.time() + 10.0
        )
        self.session.pending_offer = old_offer
        self.session.last_offer_time = time.time() - 200  # cooldown expired

        with patch("bot.arbitration.engine.claim_detector.check_claim", new_callable=AsyncMock, return_value=mock_claim), \
             patch("bot.arbitration.engine.conflict_detector.detect_conflict", new_callable=AsyncMock, return_value=mock_conflict), \
             patch("bot.arbitration.engine.arbitration_verifier.search_evidence", new_callable=AsyncMock, return_value=([], 10)), \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock), \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()), \
             self.assertLogs("ArbitrationEngine", level="WARNING") as cm:

            await arbitration_engine.process_utterance(
                guild_id=self.guild_id,
                user_id=102,
                speaker_name="Ziad",
                raw_text="كارت الـ 5070 نازل بـ 12 جيجا",
                stt_ms=100,
                voice_client=None,
                text_channel=None,
                mode="referee"
            )

            # Assert warning was logged
            replace_warnings = [line for line in cm.output if "Replacing older unconfirmed pending offer" in line]
            self.assertTrue(len(replace_warnings) > 0, "Must log warning when replacing older unconfirmed offer")
            print(f"\n[ACCEPTANCE PROOF] Offer Replacement Warning: {replace_warnings[0]}")

            # Assert old offer cancelled and new offer active
            self.assertTrue(old_offer.is_resolved)
            self.assertNotEqual(self.session.pending_offer.offer_id, "off_older_unconfirmed")


if __name__ == "__main__":
    unittest.main()
