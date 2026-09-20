import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.config import config
from bot.ai.assemblyai import AssemblyAIClient


class TestAssemblyAIPollBudget(unittest.TestCase):
    def test_config_budget_defaults(self):
        """Verify budget values exist in bot.config with correct defaults."""
        self.assertEqual(config.ASSEMBLYAI_POLL_ATTEMPTS, 40)
        self.assertEqual(config.ASSEMBLYAI_POLL_INTERVAL_SEC, 0.5)

    def test_stt_timeout_warning_logged_with_speaker_name(self):
        """Verify that when polling budget is exceeded, a WARNING with speaker name and 'STT timeout, utterance dropped' is logged."""
        import asyncio

        async def run_test():
            client = AssemblyAIClient(api_key="test_key")
            fake_wav = b"\x00" * 2000

            # Mock httpx.AsyncClient
            mock_http_client = AsyncMock()
            
            # 1. Upload response
            upload_resp = MagicMock()
            upload_resp.status_code = 200
            upload_resp.json.return_value = {"upload_url": "https://fake.url/audio.wav"}
            
            # 2. Job submit response
            job_resp = MagicMock()
            job_resp.status_code = 200
            job_resp.json.return_value = {"id": "job_12345"}

            # 3. Poll response: always "processing" (never completed)
            poll_resp = MagicMock()
            poll_resp.status_code = 200
            poll_resp.json.return_value = {"status": "processing"}

            mock_http_client.post.side_effect = [upload_resp, job_resp]
            mock_http_client.get.return_value = poll_resp

            # Use 2 attempts and 0.001 interval for instant test
            with patch("bot.config.config.ASSEMBLYAI_POLL_ATTEMPTS", 2), \
                 patch("bot.config.config.ASSEMBLYAI_POLL_INTERVAL_SEC", 0.001), \
                 patch("bot.ai.assemblyai.httpx.AsyncClient") as mock_async_client_cls, \
                 patch("bot.ai.assemblyai.logger.warning") as mock_warn:

                mock_async_client_cls.return_value.__aenter__.return_value = mock_http_client

                text, latency_ms = await client.transcribe(fake_wav, speaker_name="Ziad")

                self.assertIsNone(text)
                self.assertGreaterEqual(latency_ms, 0)

                # Verify warning was logged with speaker name and message
                mock_warn.assert_called()
                warn_calls = [c[0][0] for c in mock_warn.call_args_list]
                timeout_warning = next((msg for msg in warn_calls if "STT timeout, utterance dropped" in msg), None)
                self.assertIsNotNone(timeout_warning, f"Expected warning not found in {warn_calls}")
                self.assertIn("Ziad", timeout_warning)
                print(f"[TEST PASSED] Logged Warning: {timeout_warning}")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
