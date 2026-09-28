import time
import unittest
from unittest.mock import AsyncMock, patch

from bot.arbitration.engine import arbitration_engine, normalize_topic_key
from bot.arbitration.fast_gate import fast_gate
from bot.config import config


class TestGranularCooldownAndCasualGate(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild_id = 998811
        self.session = arbitration_engine.get_session(self.guild_id)
        self.session.reset()

    def tearDown(self):
        self.session.reset()

    def test_casual_arabic_disputes_pass_fast_gate(self):
        """Verifies colloquial Egyptian Arabic disputes pass FastGate into arbitration."""
        casual_disputes = [
            "الفدان بخمسين الف",
            "لا خمسة الاف بس",
            "لا خمسة بس",
            "الفيلم نازل يوم الخميس",
            "لا الجمعة يابني",
            "كارت الـ 4060 نازل بـ 12 جيجا",
            "مش تمانية؟",
            "الماتش الساعة تسعة",
            "لا تمانية ونص",
            "صلاح جاب 25 جون مش عشرين"
        ]
        for utterance in casual_disputes:
            is_cand, reason = fast_gate.is_candidate(utterance)
            self.assertTrue(
                is_cand,
                f"Expected casual dispute '{utterance}' to pass fast_gate, got False ({reason})"
            )

    def test_chit_chat_and_banter_rejected_by_fast_gate(self):
        """Verifies banter and chit-chat are rejected by FastGate (0% false positives)."""
        controls = [
            "تمام يا صاحبي ماشي",
            "هههههههههه جامد اوي",
            "ايوة بالظبط كلامك مظبوط",
            "الوو الصوت واضح يا شباب؟",
            "صباح الفل يا رجالة",
            "يا عم تمام ههههه"
        ]
        for utterance in controls:
            is_cand, reason = fast_gate.is_candidate(utterance)
            self.assertFalse(
                is_cand,
                f"Expected chit-chat '{utterance}' to be rejected, got True ({reason})"
            )

    def test_granular_topic_cooldown_isolation(self):
        """
        Verifies per-topic TTLCache isolation:
        - T=0: Offer Topic A (allowed)
        - T=5: Repeat Topic A (blocked by global backstop)
        - T=35: Offer distinct Topic B (allowed, >30s global backstop satisfied)
        - T=40: Repeat Topic A (blocked by topic TTL, <180s)
        - T=70: Offer distinct Topic C (allowed)
        - T=200: Repeat Topic A (allowed, 180s TTL expired)
        """
        topic_a = normalize_topic_key("Al Ahly", "football")
        topic_b = normalize_topic_key("RTX 5070", "hardware")
        topic_c = normalize_topic_key("Oppenheimer", "movies")

        t0 = 1000.0

        # T=0: Offer Topic A
        is_cool, _, _ = self.session.is_in_cooldown(topic_a, now=t0)
        self.assertFalse(is_cool)
        self.session.record_offer(topic_a, now=t0)

        # T=5: Repeat Topic A (blocked by global backstop)
        is_cool, rem, reason = self.session.is_in_cooldown(topic_a, now=t0 + 5.0)
        self.assertTrue(is_cool)
        self.assertEqual(reason, "global_backstop")

        # T=35: Distinct Topic B (allowed, >30s backstop)
        is_cool, _, _ = self.session.is_in_cooldown(topic_b, now=t0 + 35.0)
        self.assertFalse(is_cool)
        self.session.record_offer(topic_b, now=t0 + 35.0)

        # T=66: Repeat Topic A (global backstop passed: 66 - 35 = 31s > 30s; blocked by per-topic cache: 180 - 66 = 114s remaining)
        is_cool, rem, reason = self.session.is_in_cooldown(topic_a, now=t0 + 66.0)
        self.assertTrue(is_cool)
        self.assertTrue(reason.startswith("topic:"))
        self.assertGreater(rem, 100)

        # T=70: Distinct Topic C (allowed: 70 - 35 = 35s > 30s)
        is_cool, _, _ = self.session.is_in_cooldown(topic_c, now=t0 + 70.0)
        self.assertFalse(is_cool)
        self.session.record_offer(topic_c, now=t0 + 70.0)

        # T=200: Repeat Topic A (allowed, >180s passed since T=0)
        is_cool, _, _ = self.session.is_in_cooldown(topic_a, now=t0 + 200.0)
        self.assertFalse(is_cool)


if __name__ == "__main__":
    unittest.main()
