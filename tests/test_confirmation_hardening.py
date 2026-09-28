"""
Unit tests for confirmation hardening:
- FIX 2 (DATA-03): Concurrent confirm_dispute_offer calls on same offer -> exactly ONE TTS invocation, second returns 'already confirmed'
- FIX 3 (DATA-04): Speaker attribution -> completed event has speaker_b's name AND admin as confirmed_by
- FIX 7 (DATA-05 + DATA-08): Completed event published BEFORE speak() returns; task reference held in publisher._background_tasks (no GC)
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from bot.arbitration.engine import arbitration_engine, PendingOffer
from bot.events.publisher import publisher
from bot.events.models import VoiceEvent


class TestConfirmationHardening(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.guild_id = 999333
        self.session = arbitration_engine.get_session(self.guild_id)
        self.session.pending_utterances.clear()
        self.session.is_arbitrating = False

    async def test_double_confirmation_race_invokes_tts_once(self):
        """
        ACCEPTANCE (FIX 2 / DATA-03):
        Two concurrent confirm_dispute_offer calls on the same offer:
        -> exactly ONE TTS invocation
        -> second call returns 'already confirmed'
        """
        async def mock_search_coro():
            return [{"title": "Python Wiki", "url": "https://wiki.python.org", "domain": "python.org", "snippet": "1991"}], 50
        search_task = asyncio.create_task(mock_search_coro())
        offer = PendingOffer(
            offer_id="off_race_test",
            guild_id=self.guild_id,
            speaker_a="Alice",
            claim_a="Python was released in 1991",
            speaker_b="Bob",
            claim_b="Python was released in 2000",
            entity="Python",
            search_query="Python release year",
            target_domains=[],
            prefetch_task=search_task,
            created_at=time.time(),
            expires_at=time.time() + 30.0
        )
        self.session.pending_offer = offer

        mock_assessment = {
            "status": "CONTRADICTED",
            "correct_fact": "Python was released in 1991.",
            "spoken_intervention": "Python was released in 1991 by Guido van Rossum.",
            "confidence": 95,
            "evidence_strength": "STRONG"
        }
        mock_sources = [{"title": "Python Wiki", "url": "https://wiki.python.org", "domain": "python.org", "snippet": "1991"}]

        with patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock) as mock_synth, \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", MagicMock()):

            mock_synth.return_value = (mock_assessment, 50, 100, mock_sources)
            mock_speak.return_value = 500

            # Run two concurrent confirm_dispute_offer calls on the same offer
            res1, res2 = await asyncio.gather(
                arbitration_engine.confirm_dispute_offer(
                    guild_id=self.guild_id,
                    confirmation_end_time=time.time(),
                    confirmed_by="Admin1",
                    target_offer=offer
                ),
                arbitration_engine.confirm_dispute_offer(
                    guild_id=self.guild_id,
                    confirmation_end_time=time.time(),
                    confirmed_by="Admin2",
                    target_offer=offer
                )
            )

            # Exactly one invocation of speak()
            self.assertEqual(mock_speak.call_count, 1)

            # One returns None (success), the other returns "already confirmed"
            results = [res1, res2]
            self.assertIn("already confirmed", results)
            print(f"[Race Test Output] Concurrent calls returned: res1={res1}, res2={res2} (TTS call count: {mock_speak.call_count})")

    async def test_speaker_attribution_and_confirmer_separation(self):
        """
        ACCEPTANCE (FIX 3 / DATA-04):
        Speaker B's claim confirmed by Admin ->
        completed event has speaker_b's name AND admin as confirmed_by.
        """
        async def mock_search_coro():
            return [{"title": "GPU Specs", "url": "https://specs.com", "domain": "specs.com", "snippet": "12GB"}], 50
        search_task = asyncio.create_task(mock_search_coro())
        offer = PendingOffer(
            offer_id="off_attrib_test",
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
            expires_at=time.time() + 30.0,
            user_id=102
        )
        self.session.pending_offer = offer

        mock_assessment = {
            "status": "CONTRADICTED",
            "correct_fact": "RTX 5070 has 12GB.",
            "spoken_intervention": "Verified: RTX 5070 has 12GB.",
            "confidence": 90,
            "evidence_strength": "STRONG"
        }
        mock_sources = [{"title": "GPU Specs", "url": "https://specs.com", "domain": "specs.com", "snippet": "12GB"}]
        published_events = []

        with patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock) as mock_synth, \
             patch("bot.arbitration.engine.speaker.speak", new_callable=AsyncMock) as mock_speak, \
             patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=published_events.append):

            mock_synth.return_value = (mock_assessment, 40, 80, mock_sources)
            mock_speak.return_value = 400

            await arbitration_engine.confirm_dispute_offer(
                guild_id=self.guild_id,
                confirmation_end_time=time.time(),
                confirmed_by="AdminUser",
                target_offer=offer
            )

            completed = [e for e in published_events if e.type == "dispute_check_completed"]
            self.assertEqual(len(completed), 1)
            evt = completed[0]

            # Verifications: speaker_name is Ziad (Speaker B), confirmed_by is AdminUser
            self.assertEqual(evt.speaker_name, "Ziad")
            self.assertEqual(evt.confirmed_by, "AdminUser")
            self.assertEqual(evt.payload["confirmed_by"], "AdminUser")
            self.assertEqual(evt.payload["speaker_b"], "Ziad")
            print(f"[Attribution Test Output] evt.speaker_name='{evt.speaker_name}', evt.confirmed_by='{evt.confirmed_by}'")

    async def test_publish_before_speak_and_gc_safe_task_set(self):
        """
        ACCEPTANCE (FIX 7 / DATA-05 + DATA-08):
        - completed event is published BEFORE speak() returns.
        - task reference is held in publisher._background_tasks (no GC).
        """
        async def mock_search_coro():
            return [{"title": "T", "url": "U", "domain": "D", "snippet": "S"}], 50
        search_task = asyncio.create_task(mock_search_coro())
        offer = PendingOffer(
            offer_id="off_publish_order",
            guild_id=self.guild_id,
            speaker_a="A",
            claim_a="claim A",
            speaker_b="B",
            claim_b="claim B",
            entity="entity",
            search_query="query",
            target_domains=[],
            prefetch_task=search_task,
            created_at=time.time(),
            expires_at=time.time() + 30.0
        )
        self.session.pending_offer = offer

        mock_assessment = {
            "status": "CONTRADICTED",
            "correct_fact": "Fact",
            "spoken_intervention": "Intervention",
            "confidence": 90,
            "evidence_strength": "STRONG"
        }
        published_events = []
        event_published_before_speak = False

        async def slow_speak(vc, text):
            nonlocal event_published_before_speak
            # When speak() is called, completed event must ALREADY be published
            if any(e.type == "dispute_check_completed" for e in published_events):
                event_published_before_speak = True
            await asyncio.sleep(0.05)
            return 300

        with patch("bot.arbitration.engine.arbitration_verifier.synthesize_verdict", new_callable=AsyncMock) as mock_synth, \
             patch("bot.arbitration.engine.speaker.speak", side_effect=slow_speak), \
             patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=published_events.append):

            mock_synth.return_value = (mock_assessment, 30, 60, [{"title": "T", "url": "U", "domain": "D", "snippet": "S"}])

            await arbitration_engine.confirm_dispute_offer(
                guild_id=self.guild_id,
                confirmation_end_time=time.time(),
                confirmed_by="Verifier",
                target_offer=offer
            )

            self.assertTrue(event_published_before_speak, "Completed event must be published BEFORE speak() returns")
            print("[Publish Order Output] Confirmed: dispute_check_completed published BEFORE speak() execution")

        # Test DATA-08: publisher._background_tasks holds task reference while running
        dummy_event = VoiceEvent(
            type="transcript",
            speaker_name="Tester",
            text="Testing GC task reference"
        )
        finish_publish = asyncio.Event()
        async def slow_publish(evt):
            await finish_publish.wait()

        with patch.object(publisher, "publish", side_effect=slow_publish):
            publisher.publish_sync_task(dummy_event)
            # Assert task reference is in publisher._background_tasks set
            self.assertEqual(len(publisher._background_tasks), 1)
            task_ref = list(publisher._background_tasks)[0]
            self.assertFalse(task_ref.done())

            # Release publish
            finish_publish.set()
            await asyncio.sleep(0.01)

            # Assert task is removed from set on completion
            self.assertEqual(len(publisher._background_tasks), 0)
            print("[Task Reference Output] Task successfully held in publisher._background_tasks during execution, discarded upon completion")


if __name__ == "__main__":
    unittest.main()
