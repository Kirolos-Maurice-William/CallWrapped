"""
Unit tests for Step 6: Session Recap Renderer (bot/main.py).
Tests:
1. Empty session returns "No data yet in this call."
2. Scripted session with two speakers, one angry episode, and mixed topics
   renders all four sections:
   - Per-speaker talk minutes + % share bar (▰▱)
   - Longest streak record holder
   - Anger leaderboard (episode count + first anger quote as "receipts")
   - Top-3 topics with %
"""

import sys
import io
import unittest

import tests._setup

from bot.main import render_recap
from bot.arbitration.engine import SessionState


class TestSessionRecapRenderer(unittest.TestCase):

    def test_empty_session_returns_no_data(self):
        empty_session = SessionState(guild_id=111)
        output = render_recap(empty_session)
        self.assertEqual(output, "No speech data recorded in this call yet.")
        print("\n[Test 1: Empty Session]")
        print(f"Output: {output}")

    def test_scripted_utterance_sequence_recap(self):
        """
        Scripted utterance sequence:
        - Two speakers: Alice and Bob
        - Alice: 3 utterances (120s total, streak=45s, 1 angry episode with quote: "زهقت خلاص من السيرفر ده")
        - Bob: 2 utterances (60s total, streak=30s, 0 angry episodes)
        - Mixed topics: gaming (3), football (2), tech (1)
        """
        session = SessionState(guild_id=222)

        # 1. Populate Speaker 1: Alice (120s, 66.7% share)
        session.stats_tracker.record_utterance(
            speaker_id="alice",
            speech_start=0.0,
            speech_end=45.0,
            speaker_name="Alice"
        )
        session.stats_tracker.record_utterance(
            speaker_id="alice",
            speech_start=47.0,
            speech_end=85.0,
            speaker_name="Alice",
            anger="mild",
            anger_quote="زهقت خلاص من السيرفر ده"
        )
        session.stats_tracker.record_utterance(
            speaker_id="alice",
            speech_start=100.0,
            speech_end=137.0,
            speaker_name="Alice"
        )

        # 2. Populate Speaker 2: Bob (60s, 33.3% share)
        session.stats_tracker.record_utterance(
            speaker_id="bob",
            speech_start=140.0,
            speech_end=170.0,
            speaker_name="Bob"
        )
        session.stats_tracker.record_utterance(
            speaker_id="bob",
            speech_start=175.0,
            speech_end=205.0,
            speaker_name="Bob"
        )

        # 3. Populate Mixed Topics: gaming (3), football (2), tech (1)
        session.topic_counts = {
            "gaming": 3,
            "football": 2,
            "tech": 1
        }

        # Render recap
        recap_text = render_recap(session)

        print("\n" + "=" * 60)
        print("=== RENDERED SESSION RECAP ===")
        print("=" * 60)
        print(recap_text)
        print("=" * 60 + "\n")

        # Assertions
        # 1. Header & Talk minutes and % share bar (▰▱)
        self.assertIn("🎙️ **Call Wrapped Summary**", recap_text)
        self.assertIn("🗣️ **Airtime & Participation:**", recap_text)
        self.assertIn("• **Alice**: 2.0m", recap_text)
        self.assertIn("• **Bob**: 1.0m", recap_text)
        self.assertIn("▰", recap_text)
        self.assertIn("▱", recap_text)
        self.assertIn("66.7%", recap_text)
        self.assertIn("33.3%", recap_text)

        # 2. Longest streak record holder formatted as m:ss (83.0s -> "1:23")
        self.assertIn("🔥 **Longest Uninterrupted Streak:**", recap_text)
        self.assertIn("👑 **Alice** (1:23)", recap_text)

        # 3. Anger leaderboard
        self.assertIn("😡 **Anger & Frustration Moments:**", recap_text)
        self.assertIn("• **Alice**: 1 moment | Receipts: \"زهقت خلاص من السيرفر ده\"", recap_text)

        # 4. Top-3 topics with %
        self.assertIn("🏷️ **Top Discussion Topics:**", recap_text)
        self.assertIn("1. **gaming**: 50.0% (3)", recap_text)
        self.assertIn("2. **football**: 33.3% (2)", recap_text)
        self.assertIn("3. **tech**: 16.7% (1)", recap_text)

    def test_zero_angry_episodes_shows_suspicious_message(self):
        """
        Verifies that if zero angry episodes for everyone,
        the anger section is replaced with: '😡 Nobody got angry or frustrated this call... suspicious.'
        """
        session = SessionState(guild_id=333)
        session.stats_tracker.record_utterance("alice", 0.0, 30.0, "Alice")
        session.stats_tracker.record_utterance("bob", 35.0, 60.0, "Bob")
        session.topic_counts = {"gaming": 2}

        recap_text = render_recap(session)
        print("\n" + "=" * 60)
        print("=== ZERO ANGER SESSION RECAP ===")
        print("=" * 60)
        print(recap_text)
        print("=" * 60 + "\n")

        self.assertIn("😡 Nobody got angry or frustrated this call... suspicious. 😂", recap_text)
        self.assertNotIn("Anger & Frustration Moments", recap_text)

    def test_phase2_most_unfiltered_and_diplomat_badges_render_in_recap(self):
        """
        Verifies that Phase 2 badges ('The Most Unfiltered' and 'The Diplomat')
        render correctly in Discord /recap when criteria are met.
        """
        session = SessionState(guild_id=444)
        # Alice: drops 3 vulgarity tokens
        session.stats_tracker.record_utterance(
            "alice", 0.0, 30.0, "Alice",
            text="احا يا عم ده bullshit خالص fuck"
        )
        # Bob: speaks 45s clean with 0 anger and 0 vulgarity
        session.stats_tracker.record_utterance(
            "bob", 30.0, 75.0, "Bob",
            text="يا جماعة نهدى شوية ونتكلم باحترام وهدوء"
        )
        session.topic_counts = {"tech": 2}

        recap_text = render_recap(session)
        print("\n" + "=" * 60)
        print("=== PHASE 2 BADGES SESSION RECAP ===")
        print("=" * 60)
        print(recap_text)
        print("=" * 60 + "\n")

        # Verify The Most Unfiltered badge
        self.assertIn("🌶️ **The Most Unfiltered:** Alice (3 raw tokens)", recap_text)

        # Verify The Diplomat badge
        self.assertIn("🕊️ **The Diplomat (Clean & Civilized):** Bob (45s peaceful)", recap_text)

    def test_render_recap_roast_master_and_friendly_banter(self):
        """Phase 3: Verify The Roast Master badge and friendly banter call vibe."""
        session = SessionState(guild_id=555)
        session.stats_tracker.record_utterance("alice", 0.0, 30.0, "Alice")
        session.stats_tracker.record_utterance("bob", 30.0, 60.0, "Bob")
        session.stats_tracker.record_banter(["alice", "bob"], ["roast1"])
        session.stats_tracker.record_banter(["alice"], ["roast2", "roast3"])
        session.stats_tracker.record_banter(["alice"], ["roast4"])
        session.topic_counts = {"gaming": 2}

        recap_text = render_recap(session)
        print("\n" + "=" * 60)
        print("=== PHASE 3 ROAST MASTER RECAP ===")
        print("=" * 60)
        print(recap_text)
        print("=" * 60 + "\n")

        self.assertIn("🎭 **The Roast Master:** Alice (3 friendly banter turns)", recap_text)
        self.assertIn("playful vibe (4 roasts, 0 anger) 😂", recap_text)


if __name__ == "__main__":
    unittest.main()


