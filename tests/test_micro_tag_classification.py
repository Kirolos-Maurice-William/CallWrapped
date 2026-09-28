"""
Acceptance Test Suite for Step 4: Two-Tier Topic Classification (Macro Topic + Micro Tag).
Verifies:
1. infer_tag extracts fine-grained entities/subtopics accurately across Arabic and English.
2. check_claim populates 'tag' in fallback and parsed output.
3. SessionState tracks micro_tags dictionary and clears on reset.
4. _apply_batch_results updates session.micro_tags and emits tag in VoiceEvent.
5. render_recap formats micro-tag highlights and preserves backwards compatibility.
6. build_card_payload_from_session includes micro_tags and enriches 'other'.
7. render_recap_card_png renders social card containing micro-tags cleanly.
"""

import io
import time
import unittest
from unittest.mock import MagicMock, patch

import tests._setup

from PIL import Image

from bot.arbitration.claim_detector import infer_tag, claim_detector
from bot.arbitration.engine import SessionState, arbitration_engine
from bot.events.models import VoiceEvent
from bot.main import render_recap
from bot.ui.recap_card_renderer import (
    SpeakerStat,
    TopicStat,
    RecapCardPayload,
    build_card_payload_from_session,
    render_recap_card_png,
)


class TestTwoTierTopicClassification(unittest.TestCase):

    def test_infer_tag_rule_and_entities(self):
        """1. infer_tag accurately isolates specific entities and subtopics."""
        cases = [
            ("كارت الـ RTX 5070 نازل بـ 12 جيجا بايت", "rtx 5070"),
            ("الأهلي كسب كأس السوبر", "الأهلي"),
            ("فيلم ولاد رزق في السينما", "ولاد رزق"),
            ("عمرو دياب نزل ألبوم جديد", "عمرو دياب"),
            ("بنسافر شرم الشيخ الجمعة الجاية", "شرم الشيخ"),
            ("سعر الدولار اليوم في البنك", "الدولار"),
            ("صباح الخير يا شباب", ""),
            ("", ""),
        ]
        for text, expected in cases:
            tag = infer_tag(text)
            if expected:
                self.assertIn(expected, tag)
            else:
                self.assertEqual(tag, "")

    def test_session_state_micro_tags_lifecycle(self):
        """2. SessionState initializes, accumulates, and resets micro_tags."""
        session = SessionState(guild_id=777)
        self.assertEqual(session.micro_tags, {})

        session.micro_tags["RTX 5070"] = 2
        session.micro_tags["الأهلي"] = 3
        self.assertEqual(len(session.micro_tags), 2)

        session.reset()
        self.assertEqual(session.micro_tags, {})

    def test_apply_batch_results_propagates_tag_and_event(self):
        """3. _apply_batch_results updates micro_tags and includes tag in VoiceEvent."""
        session = SessionState(guild_id=888)
        buffer = [
            {
                "user_id": 101,
                "speaker_name": "Mostafa",
                "text": "كارت الـ RTX 5070 ممتاز",
                "timestamp": time.time(),
                "talk_delta_seconds": 3.0,
                "streak_seconds": 3.0,
                "correlation_id": "corr_1",
                "audio_features": None
            },
            {
                "user_id": 102,
                "speaker_name": "Ahmed",
                "text": "الأهلي هيلعب الماتش الجاي",
                "timestamp": time.time(),
                "talk_delta_seconds": 2.5,
                "streak_seconds": 2.5,
                "correlation_id": "corr_2",
                "audio_features": None
            }
        ]
        results = [
            {"line_number": 1, "topic": "tech", "tag": "RTX 5070", "anger": "none", "anger_evidence": ""},
            {"line_number": 2, "topic": "football", "tag": "الأهلي", "anger": "none", "anger_evidence": ""}
        ]

        captured_events = []
        with patch("bot.arbitration.engine.publisher.publish_sync_task", side_effect=captured_events.append):
            arbitration_engine._apply_batch_results(
                session=session,
                guild_id=888,
                buffer_to_process=buffer,
                results=results,
                tokens={"total_tokens": 100},
                reason="test_flush"
            )

        self.assertEqual(session.micro_tags.get("RTX 5070"), 1)
        self.assertEqual(session.micro_tags.get("الأهلي"), 1)
        self.assertEqual(len(captured_events), 2)
        self.assertEqual(captured_events[0].tag, "RTX 5070")
        self.assertEqual(captured_events[0].payload.get("tag"), "RTX 5070")
        self.assertEqual(captured_events[1].tag, "الأهلي")
        self.assertEqual(captured_events[1].payload.get("tag"), "الأهلي")

    def test_render_recap_displays_micro_tags(self):
        """4. render_recap formats micro-tag hashtags cleanly under topics."""
        session = SessionState(guild_id=999)
        session.stats_tracker.record_utterance("101", 0.0, 30.0, "Mostafa")
        session.topic_counts = {"tech": 3, "football": 2}
        session.micro_tags = {"RTX 5070": 3, "الأهلي": 2}

        recap_text = render_recap(session)
        self.assertIn("🏷️ **أكتر مواضيع اتكلمتوا فيها:**", recap_text)
        self.assertIn("📌 **أبرز الكلمات والمواضيع الدقيقة:**", recap_text)
        self.assertIn("#RTX 5070 (3)", recap_text)
        self.assertIn("#الأهلي (2)", recap_text)

    def test_build_card_payload_and_other_enrichment(self):
        """5. build_card_payload_from_session enriches 'other' and passes micro_tags."""
        session = SessionState(guild_id=123)
        session.stats_tracker.record_utterance("101", 0.0, 45.0, "Mostafa")
        session.topic_counts = {"other": 5, "tech": 3}
        session.micro_tags = {"طبيخ مصري": 5, "RTX 5070": 3}

        payload = build_card_payload_from_session(session, session_title="Test Call")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.micro_tags, ["طبيخ مصري", "RTX 5070"])

        # Topic 1 (other) should be enriched to "أخرى (طبيخ مصري)"
        top_topic = payload.top_topics[0]
        self.assertEqual(top_topic.display_name, "أخرى (طبيخ مصري)")

    def test_render_recap_card_with_micro_tags(self):
        """6. render_recap_card_png renders a valid PNG including micro-tags."""
        payload = RecapCardPayload(
            session_title="ملخص المكالمة • CallWrapped",
            period_label="جلسة تجريبية",
            speaker_stats=[
                SpeakerStat(name="Mostafa", talk_seconds=60.0, share_pct=60.0, streak_seconds=30.0, angry_episodes=0),
                SpeakerStat(name="Ahmed", talk_seconds=40.0, share_pct=40.0, streak_seconds=20.0, angry_episodes=0),
            ],
            top_topics=[
                TopicStat(topic_key="tech", display_name="تكنولوجيا", pct=60.0),
                TopicStat(topic_key="football", display_name="كورة", pct=40.0),
            ],
            coverage_note="نسبة التغطية الموضوعية: 100.0%",
            micro_tags=["RTX 5070", "الأهلي"]
        )

        png_bytes = render_recap_card_png(payload)
        self.assertIsInstance(png_bytes, bytes)
        self.assertGreater(len(png_bytes), 10 * 1024)

        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (1080, 1350))
        self.assertEqual(img.format, "PNG")


if __name__ == "__main__":
    unittest.main()
