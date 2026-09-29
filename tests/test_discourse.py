"""
Tests for Conversational Pragmatics & Multi-Turn Discourse Trajectory Engine.
Validates:
1. User Scenario: "fuck you ali" -> "fuck you too" -> "how are you" (friendly banter, 0 anger).
2. Egyptian Vernacular Banter: "يابن الكلب" -> "يا عم انت حمار" -> "هههه ضحكتني تعال نلعب" (friendly banter).
3. Unilateral Hostile Attack: Aggressor insults -> Victim defends -> Aggressor persists (hostile escalation).
4. Single-Speaker Monologue Rant (3 consecutive hostile turns -> rant confirmed).
5. Self-Contained In-Line Banter (Laughter/greeting in same utterance).
6. Prosodic Baseline Reset (Acoustic energy drops to baseline).
7. End-of-Session Flush.
"""

import unittest
from bot.arbitration.discourse import DiscourseTracker, DiscourseResolution


class TestDiscourseTrajectory(unittest.TestCase):

    def setUp(self):
        self.tracker = DiscourseTracker(session_id="test_session")

    def test_user_scenario_fuck_you_rebound_greeting(self):
        """
        Exact user scenario:
        Ali: 'fuck you ali' (loud, peak_z=3.1)
        Omar: 'fuck you too' (loud, peak_z=3.0)
        Ali: 'how are you you slave' (greeting 'how are you', calm)
        Outcome: Friendly banter! Zero anger episodes!
        """
        # Turn 1: Ali shouts insult
        res1 = self.tracker.observe_turn(
            speaker_id="ali",
            speaker_name="Ali",
            text="fuck you ali",
            timestamp=100.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.1},
            raw_anger="mild",
            anger_evidence="fuck you ali"
        )
        # Should NOT commit anger immediately on Turn 1!
        self.assertEqual(len(res1), 0)
        self.assertEqual(len(self.tracker.pending_candidates), 1)

        # Turn 2: Omar replies with matching energy and insult (symmetrical entrainment)
        res2 = self.tracker.observe_turn(
            speaker_id="omar",
            speaker_name="Omar",
            text="fuck you too",
            timestamp=102.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.0},
            raw_anger="mild",
            anger_evidence="fuck you too"
        )
        self.assertEqual(len(res2), 0)
        # Symmetrical response detected for Ali's candidate
        self.assertTrue(self.tracker.pending_candidates[0].has_symmetrical_response)
        self.assertEqual(self.tracker.pending_candidates[0].responding_speaker_name, "Omar")

        # Turn 3: Ali greets Omar ('how are you you slave') -> Lexical rebound!
        res3 = self.tracker.observe_turn(
            speaker_id="ali",
            speaker_name="Ali",
            text="how are you you slave",
            timestamp=104.5,
            audio_features={"was_loud": False, "peak_robust_z": 1.1},
            raw_anger="none"
        )
        # Symmetrical banter is resolved with lexical rebound for both participants!
        self.assertEqual(len(res3), 2)
        names = {r.speaker_name for r in res3}
        self.assertEqual(names, {"Ali", "Omar"})
        for banter in res3:
            self.assertEqual(banter.resolution_type, "friendly_banter")
            self.assertIn("symmetrical_banter_with_rebound", banter.trajectory_context)
        self.assertEqual(self.tracker.resolved_banter_count, 2)
        self.assertEqual(self.tracker.resolved_escalation_count, 0)

    def test_egyptian_banter_and_laughter_rebound(self):
        """
        Egyptian gaming banter:
        Ziad: 'يابن الكلب' (loud)
        Mostafa: 'يا عم انت حمار' (loud)
        Ziad: 'هههه ضحكتني تعال نلعب كول أوف ديوتي' (laughter + game transition)
        Outcome: Friendly banter!
        """
        # Turn 1: Ziad drops Egyptian profanity
        self.tracker.observe_turn(
            speaker_id="ziad",
            speaker_name="Ziad",
            text="يابن الكلب",
            timestamp=200.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.8},
            raw_anger="mild",
            anger_evidence="يابن الكلب"
        )

        # Turn 2: Mostafa responds reciprocally
        self.tracker.observe_turn(
            speaker_id="mostafa",
            speaker_name="Mostafa",
            text="يا عم انت حمار",
            timestamp=202.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.7},
            raw_anger="mild",
            anger_evidence="يا عم انت حمار"
        )

        # Turn 3: Ziad laughs and suggests playing
        res = self.tracker.observe_turn(
            speaker_id="ziad",
            speaker_name="Ziad",
            text="هههه ضحكتني تعال نلعب كول أوف ديوتي",
            timestamp=204.0,
            audio_features={"was_loud": False, "peak_robust_z": 1.4},
            raw_anger="none"
        )

        self.assertEqual(len(res), 2)
        names = {r.speaker_name for r in res}
        self.assertEqual(names, {"Ziad", "Mostafa"})
        for banter in res:
            self.assertEqual(banter.resolution_type, "friendly_banter")
        self.assertEqual(self.tracker.resolved_banter_count, 2)

    def test_unilateral_hostile_escalation(self):
        """
        Unilateral aggression & hostile escalation:
        Karim: 'أنت غبي وبتبوظ السيرفر' (loud, raw_anger=mild)
        Tamer: 'مالك يا عم براحة في ايه' (defense/hurt cue)
        Karim: 'بقولك اخرس خالص يا فاشل ومقرف' (persistent hostile attack)
        Outcome: Hostile escalation confirmed!
        """
        # Turn 1: Karim attacks
        self.tracker.observe_turn(
            speaker_id="karim",
            speaker_name="Karim",
            text="أنت غبي وبتبوظ السيرفر",
            timestamp=300.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.2},
            raw_anger="mild",
            anger_evidence="أنت غبي وبتبوظ السيرفر"
        )

        # Turn 2: Tamer defends / asks him to chill
        self.tracker.observe_turn(
            speaker_id="tamer",
            speaker_name="Tamer",
            text="مالك يا عم براحة في ايه",
            timestamp=302.5,
            audio_features={"was_loud": False, "peak_robust_z": 1.2},
            raw_anger="none"
        )

        # Turn 3: Karim attacks again with persistent contempt
        res = self.tracker.observe_turn(
            speaker_id="karim",
            speaker_name="Karim",
            text="بقولك اخرس خالص يا فاشل ومقرف",
            timestamp=305.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.5},
            raw_anger="high",
            anger_evidence="بقولك اخرس خالص يا فاشل ومقرف"
        )

        # Karim's turn 1 candidate escalates and is resolved as hostile_escalation!
        escalation_events = [r for r in res if r.resolution_type == "hostile_escalation"]
        self.assertGreaterEqual(len(escalation_events), 1)
        esc = escalation_events[0]
        self.assertEqual(esc.speaker_name, "Karim")
        self.assertIn("hostile_escalation", esc.trajectory_context)
        self.assertEqual(self.tracker.resolved_escalation_count, 1)

    def test_single_speaker_sustained_monologue_rant(self):
        """
        User observation:
        'if i repeat bad words and bad way of talking for more than 5 sentences
        so that means i might be angry it is all depends on context'
        Outcome: Sustained monologue rant detected!
        """
        # Turn 1:
        self.tracker.observe_turn(
            speaker_id="ahmed",
            speaker_name="Ahmed",
            text="زهقت خلاص من اللعبة دي",
            timestamp=400.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.5},
            raw_anger="mild",
            anger_evidence="زهقت خلاص من اللعبة دي"
        )
        # Turn 2:
        self.tracker.observe_turn(
            speaker_id="ahmed",
            speaker_name="Ahmed",
            text="كل ماتش نفس القرف ده ومش طايق حد",
            timestamp=405.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.6},
            raw_anger="mild",
            anger_evidence="مش طايق حد"
        )
        # Turn 3:
        res = self.tracker.observe_turn(
            speaker_id="ahmed",
            speaker_name="Ahmed",
            text="سيرفر زبالة والرانك بيعصب أوي خلاص كفاية",
            timestamp=410.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.9},
            raw_anger="high",
            anger_evidence="سيرفر زبالة والرانك بيعصب أوي"
        )

        escalations = [r for r in res if r.resolution_type == "hostile_escalation"]
        self.assertGreaterEqual(len(escalations), 1)
        rant = escalations[0]
        self.assertEqual(rant.speaker_name, "Ahmed")
        self.assertIn("sustained_monologue_rant", rant.trajectory_context)

    def test_self_contained_banter_with_inline_laughter(self):
        """
        Utterance containing both teasing/vulgarity and inline laughter:
        'يا عم انت حمار هههه ضحكتني'
        Outcome: Immediately resolved as friendly banter!
        """
        res = self.tracker.observe_turn(
            speaker_id="bob",
            speaker_name="Bob",
            text="يا عم انت حمار هههه ضحكتني",
            timestamp=500.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.5},
            raw_anger="none"
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].resolution_type, "friendly_banter")
        self.assertEqual(res[0].speaker_name, "Bob")
        self.assertIn("self_contained_banter", res[0].trajectory_context)

    def test_prosodic_baseline_reset(self):
        """
        Mutual banter followed by acoustic baseline reset (drop back to normal voice).
        Outcome: Friendly banter!
        """
        self.tracker.observe_turn(
            speaker_id="alice",
            speaker_name="Alice",
            text="fuck off",
            timestamp=600.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.9},
            raw_anger="mild"
        )
        self.tracker.observe_turn(
            speaker_id="bob",
            speaker_name="Bob",
            text="fuck you too",
            timestamp=601.5,
            audio_features={"was_loud": True, "peak_robust_z": 2.8},
            raw_anger="mild"
        )
        res = self.tracker.observe_turn(
            speaker_id="alice",
            speaker_name="Alice",
            text="okay let's look at the leaderboard",
            timestamp=603.5,
            audio_features={"was_loud": False, "peak_robust_z": 1.0},
            raw_anger="none"
        )
        self.assertEqual(len(res), 2)
        names = {r.speaker_name for r in res}
        self.assertEqual(names, {"Alice", "Bob"})
        for banter in res:
            self.assertEqual(banter.resolution_type, "friendly_banter")
        self.assertEqual(self.tracker.resolved_banter_count, 2)

    def test_flush_pending_at_session_end(self):
        """
        Session ends with an unresolved reciprocal exchange -> flushes as friendly banter.
        """
        self.tracker.observe_turn(
            speaker_id="alice",
            speaker_name="Alice",
            text="احا يا عم",
            timestamp=700.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.6},
            raw_anger="mild"
        )
        self.tracker.observe_turn(
            speaker_id="bob",
            speaker_name="Bob",
            text="احا انت يا باشا",
            timestamp=702.0,
            audio_features={"was_loud": True, "peak_robust_z": 2.5},
            raw_anger="mild"
        )
        flushed = self.tracker.flush_pending()
        self.assertEqual(len(flushed), 2)
        self.assertEqual(flushed[0].resolution_type, "friendly_banter")
        self.assertEqual(flushed[1].resolution_type, "friendly_banter")
        self.assertEqual(len(self.tracker.pending_candidates), 0)

    def test_flush_pending_hostile_escalation_with_defense(self):
        """
        Session disconnects right after an aggressive insult + victim defense:
        Aggressor attacks ('أنت غبي وبتبوظ السيرفر') -> Victim defends ('مالك يا عم براحة') -> Call ends.
        Must resolve as hostile_escalation, NOT suppressed!
        """
        self.tracker.observe_turn(
            speaker_id="aggressor",
            speaker_name="Aggressor",
            text="أنت غبي وبتبوظ السيرفر",
            timestamp=800.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.1},
            raw_anger="mild",
            anger_evidence="أنت غبي وبتبوظ السيرفر"
        )
        self.tracker.observe_turn(
            speaker_id="victim",
            speaker_name="Victim",
            text="مالك يا عم براحة",
            timestamp=802.0,
            audio_features={"was_loud": False, "peak_robust_z": 1.2},
            raw_anger="none"
        )
        flushed = self.tracker.flush_pending()
        self.assertEqual(len(flushed), 1)
        self.assertEqual(flushed[0].resolution_type, "hostile_escalation")
        self.assertEqual(flushed[0].speaker_name, "Aggressor")
        self.assertEqual(flushed[0].partner_name, "Victim")
        self.assertEqual(self.tracker.resolved_escalation_count, 1)

    def test_flush_pending_hostile_hangup(self):
        """
        Aggressor screams severe hostile friction token and immediately disconnects:
        'مش طايقكم وغوروا في داهية' (raw_anger=high) -> Call disconnects.
        Must resolve as hostile_escalation!
        """
        self.tracker.observe_turn(
            speaker_id="quitter",
            speaker_name="Quitter",
            text="مش طايقكم وغوروا في داهية",
            timestamp=850.0,
            audio_features={"was_loud": True, "peak_robust_z": 3.5},
            raw_anger="high",
            anger_evidence="مش طايقكم وغوروا في داهية"
        )
        flushed = self.tracker.flush_pending()
        self.assertEqual(len(flushed), 1)
        self.assertEqual(flushed[0].resolution_type, "hostile_escalation")
        self.assertEqual(flushed[0].speaker_name, "Quitter")
        self.assertEqual(self.tracker.resolved_escalation_count, 1)

    def test_flush_pending_isolated_shout_suppressed(self):
        """
        Speaker utters an isolated teasing/profane word with 0 anger and 0 victim defense:
        'يا حمار' (calm, raw_anger=none) -> Call ends.
        Must resolve as isolated_shout (suppressed from anger episodes).
        """
        self.tracker.observe_turn(
            speaker_id="joker",
            speaker_name="Joker",
            text="يا حمار",
            timestamp=900.0,
            audio_features={"was_loud": False, "peak_robust_z": 1.0},
            raw_anger="none"
        )
        flushed = self.tracker.flush_pending()
        self.assertEqual(len(flushed), 1)
        self.assertEqual(flushed[0].resolution_type, "isolated_shout")
        self.assertEqual(self.tracker.resolved_escalation_count, 0)
        self.assertEqual(self.tracker.resolved_banter_count, 0)

    def test_end_to_end_user_scenario_through_arbitration_engine(self):
        """
        End-to-End User Scenario via ArbitrationEngine:
        Turn 1: Ali: 'fuck you ali' (loud, peak_z=3.1)
        Turn 2: Omar: 'fuck you too' (loud, peak_z=3.0)
        Turn 3: Ali: 'how are you you slave' (greeting rebound)
        Turn 4: Ali: 'let's play a game you noob' (second banter turn)

        Verifies:
        1. Both Ali and Omar have 0 angry episodes (false anger suppressed!).
        2. Ali has 2 banter turns, Omar has 1 banter turn.
        3. The Roast Master is crowned to Ali (2 > 1).
        4. Rendered session recap reflects friendly banter vibe and crowns The Roast Master!
        """
        from bot.arbitration.engine import arbitration_engine
        from bot.main import render_recap

        session = arbitration_engine.get_session(123456789)
        session.reset()

        session._stats_tracker.record_utterance("101", 100.0, 130.0, "Ali")
        session._stats_tracker.record_utterance("102", 135.0, 160.0, "Omar")

        buffer_items = [
            {
                "timestamp": 100.0,
                "speaker_id": "ali",
                "speaker_name": "Ali",
                "user_id": 101,
                "text": "fuck you ali",
                "talk_delta_seconds": 2.0,
                "streak_seconds": 2.0,
                "correlation_id": "c1",
                "audio_features": {"was_loud": True, "peak_robust_z": 3.1}
            },
            {
                "timestamp": 102.0,
                "speaker_id": "omar",
                "speaker_name": "Omar",
                "user_id": 102,
                "text": "fuck you too",
                "talk_delta_seconds": 2.0,
                "streak_seconds": 2.0,
                "correlation_id": "c2",
                "audio_features": {"was_loud": True, "peak_robust_z": 3.0}
            },
            {
                "timestamp": 104.5,
                "speaker_id": "ali",
                "speaker_name": "Ali",
                "user_id": 101,
                "text": "how are you you slave",
                "talk_delta_seconds": 2.5,
                "streak_seconds": 4.5,
                "correlation_id": "c3",
                "audio_features": {"was_loud": False, "peak_robust_z": 1.1}
            },
            {
                "timestamp": 107.0,
                "speaker_id": "ali",
                "speaker_name": "Ali",
                "user_id": 101,
                "text": "let's play lol you noob",
                "talk_delta_seconds": 2.0,
                "streak_seconds": 6.5,
                "correlation_id": "c4",
                "audio_features": {"was_loud": False, "peak_robust_z": 1.2}
            }
        ]

        batch_results = [
            {"line_number": 1, "topic": "gaming", "anger": "mild", "anger_evidence": "fuck you ali"},
            {"line_number": 2, "topic": "gaming", "anger": "mild", "anger_evidence": "fuck you too"},
            {"line_number": 3, "topic": "gaming", "anger": "none", "anger_evidence": None},
            {"line_number": 4, "topic": "gaming", "anger": "none", "anger_evidence": None},
        ]

        arbitration_engine._apply_batch_results(
            session=session,
            guild_id=123456789,
            buffer_to_process=buffer_items,
            results=batch_results,
            tokens={},
            reason="test_user_scenario"
        )

        ali_stats = session._stats_tracker.get_speaker("101")
        omar_stats = session._stats_tracker.get_speaker("102")

        self.assertIsNotNone(ali_stats)
        self.assertIsNotNone(omar_stats)

        # 1. Zero anger episodes
        self.assertEqual(ali_stats.angry_episodes, 0, "Ali must have 0 anger episodes due to banter de-escalation")
        self.assertEqual(omar_stats.angry_episodes, 0, "Omar must have 0 anger episodes due to banter de-escalation")

        # 2. Banter counts
        self.assertEqual(ali_stats.banter_count, 2, "Ali should have 2 banter turns (mutual rebound + in-line teasing)")
        self.assertEqual(omar_stats.banter_count, 1, "Omar should have 1 banter turn (mutual rebound)")

        # 3. Roast Master Award
        roast_master = session._stats_tracker.get_roast_master()
        self.assertIsNotNone(roast_master)
        self.assertEqual(roast_master[0], "101")
        self.assertEqual(roast_master[1], 2)

        # 4. Session Recap text
        recap_text = render_recap(session)
        self.assertIn("ملك الضحك والمناوشات", recap_text)
        self.assertIn("Ali", recap_text)
        self.assertIn("أجواء ضحك ومناوشات", recap_text)
        self.assertNotIn("نوبات إحباط", recap_text)


if __name__ == "__main__":
    unittest.main()
