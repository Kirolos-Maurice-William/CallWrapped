"""
Unit tests for Phase 4: Spotify Wrapped Importance Scoring & Recap Integration.
Verifies that:
1. compute_topic_importance ranks multi-party discussions higher than solo monologues of equal duration.
2. render_recap displays continuous interval durations (e.g. '18s', '2.5m') when available.
3. build_card_payload_from_session generates correct percentages and topic order from continuous intervals.
"""

import sys
import unittest
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.arbitration.engine import SessionState, TopicInterval
from bot.arbitration.stats import compute_topic_importance
from bot.main import render_recap
from bot.ui.recap_card_renderer import build_card_payload_from_session


class TestTopicImportanceRecap(unittest.TestCase):

    def test_multi_party_debate_prioritized_over_solo_monologue(self):
        """
        Scenario:
        Topic A ('gaming'): 300 seconds, 4 distinct speakers, 20 turns.
        Topic B ('tech'): 300 seconds, 1 single speaker (solo monologue), 5 turns.
        Even though both lasted 300s (50% duration each), gaming should rank #1
        due to multi-speaker participation and discourse density.
        """
        itv_gaming = TopicInterval(
            macro_topic="gaming",
            canonical_tag="League of Legends",
            start_time=0.0,
            last_activity_time=300.0
        )
        itv_gaming.participating_speakers = {"Alice", "Bob", "Charlie", "David"}
        itv_gaming.turn_count = 20

        itv_tech = TopicInterval(
            macro_topic="tech",
            canonical_tag="RTX 5070",
            start_time=310.0,
            last_activity_time=610.0
        )
        itv_tech.participating_speakers = {"Alice"}
        itv_tech.turn_count = 5

        ranked = compute_topic_importance(
            topic_durations={"gaming": 300.0, "tech": 300.0},
            topic_counts={"gaming": 20, "tech": 5},
            intervals=[itv_gaming, itv_tech],
            total_speakers=4
        )

        self.assertEqual(len(ranked), 2)
        top_1_topic, top_1_score, top_1_pct = ranked[0]
        top_2_topic, top_2_score, top_2_pct = ranked[1]

        self.assertEqual(top_1_topic, "gaming")
        self.assertEqual(top_2_topic, "tech")
        self.assertGreater(top_1_score, top_2_score)
        self.assertEqual(top_1_pct, 50.0)
        self.assertEqual(top_2_pct, 50.0)

    def test_render_recap_with_continuous_durations(self):
        """Verifies that render_recap formats continuous duration strings (e.g. 18s, 2.5m)."""
        session = SessionState(guild_id=777)
        session.stats_tracker.record_utterance("alice", 0.0, 60.0, "Alice")
        session.stats_tracker.record_utterance("bob", 60.0, 120.0, "Bob")

        # Record continuous intervals
        session.record_topic_turn("gaming", "League of Legends", "Alice", 10.0, 8.0)
        session.record_topic_turn("gaming", "League of Legends", "Bob", 19.0, 9.0)  # total 18.0s
        session.record_topic_turn("tech", "RTX 5070", "Alice", 35.0, 150.0)  # 150s = 2.5m

        recap_text = render_recap(session)

        self.assertIn("🏷️ **أكتر مواضيع اتكلمتوا فيها:**", recap_text)
        # Tech: 150s = 2.5m
        self.assertIn("2.5m", recap_text)
        # Gaming: 18s
        self.assertIn("18s", recap_text)

    def test_build_card_payload_with_continuous_durations(self):
        """Verifies that recap card payload properly computes topic pct from continuous intervals."""
        session = SessionState(guild_id=888)
        session.stats_tracker.record_utterance("alice", 0.0, 100.0, "Alice")
        session.stats_tracker.record_utterance("bob", 105.0, 205.0, "Bob")

        # 300s Gaming, 100s Tech -> Gaming = 75.0%, Tech = 25.0%
        session.record_topic_turn("gaming", "GTA", "Alice", 0.0, 300.0)
        session.record_topic_turn("tech", "Docker", "Bob", 305.0, 100.0)

        payload = build_card_payload_from_session(session, session_title="Card Test")
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload.top_topics), 2)

        gaming_stat = payload.top_topics[0]
        tech_stat = payload.top_topics[1]

        self.assertEqual(gaming_stat.topic_key, "gaming")
        self.assertAlmostEqual(gaming_stat.pct, 75.0, places=1)
        self.assertEqual(tech_stat.topic_key, "tech")
        self.assertAlmostEqual(tech_stat.pct, 25.0, places=1)


if __name__ == "__main__":
    unittest.main()
