"""
BUG 4 Acceptance Test:
Verifies that SilenceRTCPFilter suppresses 'Received unexpected rtcp packet' log spam
while allowing all normal operational log messages through.
"""
import tests._setup
import logging
import unittest
from bot.main import SilenceRTCPFilter


class TestSilenceRTCPFilter(unittest.TestCase):

    def test_rtcp_filter_drops_spam_and_keeps_normal(self):
        rtcp_filter = SilenceRTCPFilter()

        # 1. Test unexpected RTCP packet record
        spam_record = logging.LogRecord(
            name="discord.ext.voice_recv.reader",
            level=logging.WARNING,
            pathname=__file__,
            lineno=20,
            msg="Received unexpected rtcp packet of type %d (expected %d)",
            args=(200, 201),
            exc_info=None
        )

        # 2. Test normal voice record
        normal_record = logging.LogRecord(
            name="discord.ext.voice_recv.reader",
            level=logging.INFO,
            pathname=__file__,
            lineno=30,
            msg="Voice packet received successfully for user %s",
            args=("Ahmed",),
            exc_info=None
        )

        should_log_spam = rtcp_filter.filter(spam_record)
        should_log_normal = rtcp_filter.filter(normal_record)

        print("\n" + "=" * 65)
        print("=== BUG 4 ACCEPTANCE: RTCP SPAM FILTER TEST ===")
        print("=" * 65)
        print(f"Spam Record:   '{spam_record.getMessage()}'")
        print(f"Filter Result: Passed={should_log_spam} (Expected: False - Suppressed)")
        print(f"Normal Record: '{normal_record.getMessage()}'")
        print(f"Filter Result: Passed={should_log_normal} (Expected: True - Allowed)")
        print("=" * 65 + "\n")

        self.assertFalse(should_log_spam, "Spammy RTCP packet log MUST be dropped by filter")
        self.assertTrue(should_log_normal, "Normal log records MUST pass through filter")
        print("[VERIFIED] RTCP log spam silenced successfully.\n")


if __name__ == "__main__":
    unittest.main()
