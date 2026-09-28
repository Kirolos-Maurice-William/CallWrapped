"""
Unit tests for Dynamic AssemblyAI Keyterm Upstream Biasing (Phase 1).
Verifies:
1. build_keyterms properly prioritizes dynamically discovered session entities.
2. Deduplication, length capping (<=50 chars), and total ceiling (<=100 terms).
3. SessionState entity registry methods (add_discovered_entity, get_active_keyterms, aliases).
4. AssemblyAIClient.transcribe transmits dynamic keyterms in job payload.
"""

import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.ai.assemblyai import build_keyterms, ASSEMBLYAI_KEYTERMS, AssemblyAIClient
from bot.arbitration.engine import SessionState


class TestDynamicKeyterms(unittest.TestCase):

    def test_build_keyterms_none(self):
        """When extra_keyterms is None, returns standard list up to 100 terms."""
        terms = build_keyterms(None)
        self.assertGreaterEqual(len(terms), 50)
        self.assertLessEqual(len(terms), 100)
        self.assertEqual(terms[0], ASSEMBLYAI_KEYTERMS[0])

    def test_build_keyterms_prioritizes_extra(self):
        """Extra keyterms appear at the front of the list."""
        extra = ["Scoutmaster", "League of Legends", "Phasmophobia"]
        terms = build_keyterms(extra)
        
        # Verify first 3 items are the extra terms
        self.assertEqual(terms[0], "Scoutmaster")
        self.assertEqual(terms[1], "League of Legends")
        self.assertEqual(terms[2], "Phasmophobia")
        
        # Verify static terms follow
        self.assertIn("Minecraft", terms)
        self.assertIn("Discord", terms)
        self.assertLessEqual(len(terms), 100)

    def test_build_keyterms_deduplication(self):
        """Deduplicates case-insensitively when extra term matches static term."""
        extra = ["discord", "MINECRAFT", "NewBossEntity"]
        terms = build_keyterms(extra)
        
        # Verify case-insensitive deduplication
        lower_counts = {}
        for t in terms:
            lower_counts[t.lower()] = lower_counts.get(t.lower(), 0) + 1
        for term, count in lower_counts.items():
            self.assertEqual(count, 1, f"Term '{term}' duplicated in keyterms")
            
        self.assertIn("NewBossEntity", terms)

    def test_build_keyterms_bounds_and_filtering(self):
        """Discards empty strings, strings over 50 chars, and caps total at 100."""
        huge_term = "A" * 60
        normal_term = "ValidTerm"
        many_extras = [f"Entity_{i}" for i in range(120)]
        
        terms = build_keyterms([huge_term, "", normal_term] + many_extras)
        self.assertNotIn(huge_term, terms)
        self.assertNotIn("", terms)
        self.assertIn(normal_term, terms)
        self.assertLessEqual(len(terms), 100)

    def test_session_state_entity_registry(self):
        """Tests SessionState add_discovered_entity, get_active_keyterms, and reset."""
        session = SessionState(guild_id=12345)
        
        # 1. Add entities
        session.add_discovered_entity("Scout Master", aliases=["سستيسكات ماستر", "سكوت ماستر"])
        session.add_discovered_entity("League of Legends")
        
        self.assertEqual(session.discovered_entities, ["Scout Master", "League of Legends"])
        self.assertEqual(session.entity_aliases["سستيسكات ماستر"], "Scout Master")
        self.assertEqual(session.entity_aliases["سكوت ماستر"], "Scout Master")
        
        # 2. Get active keyterms (returns most recent first)
        active = session.get_active_keyterms()
        self.assertEqual(active[0], "League of Legends")
        self.assertEqual(active[1], "Scout Master")
        
        # 3. Duplicate addition is idempotent
        session.add_discovered_entity("Scout Master")
        self.assertEqual(len(session.discovered_entities), 2)
        
        # 4. Reset clears registry
        session.reset()
        self.assertEqual(len(session.discovered_entities), 0)
        self.assertEqual(len(session.entity_aliases), 0)

    def test_transcribe_payload_includes_dynamic_keyterms(self):
        """Verifies AssemblyAIClient.transcribe embeds extra_keyterms into job_payload."""
        import asyncio

        async def run():
            client = AssemblyAIClient(api_key="mock_key")
            fake_wav = b"\x00" * 2000

            mock_http_client = AsyncMock()
            upload_resp = MagicMock()
            upload_resp.status_code = 200
            upload_resp.json.return_value = {"upload_url": "https://fake.url/audio.wav"}

            job_resp = MagicMock()
            job_resp.status_code = 200
            job_resp.json.return_value = {"id": "job_999"}

            poll_resp = MagicMock()
            poll_resp.status_code = 200
            poll_resp.json.return_value = {"status": "completed", "text": "test result", "words": []}

            mock_http_client.post.side_effect = [upload_resp, job_resp]
            mock_http_client.get.return_value = poll_resp

            with patch("bot.ai.assemblyai.httpx.AsyncClient") as mock_cls:
                mock_cls.return_value.__aenter__.return_value = mock_http_client
                
                extra = ["CustomGameBoss", "RareItem"]
                text, latency_ms = await client.transcribe(fake_wav, speaker_name="Player1", extra_keyterms=extra)
                
                self.assertEqual(text, "test result")
                
                # Verify job payload had the dynamic keyterms
                job_call_json = mock_http_client.post.call_args_list[1].kwargs.get("json", {})
                keyterms_sent = job_call_json.get("keyterms_prompt", [])
                
                self.assertIn("CustomGameBoss", keyterms_sent)
                self.assertIn("RareItem", keyterms_sent)
                self.assertEqual(keyterms_sent[0], "CustomGameBoss")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
