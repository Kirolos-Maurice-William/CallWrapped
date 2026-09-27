import json
import unittest
from typing import Optional

from bot.arbitration.dispute_models import (
    ThreadState,
    PropositionFamily,
    ClaimEvent,
    DisputeThread,
    TrackerDecision,
)
from bot.arbitration.dispute_tracker import DisputeTracker, FEATURE_WEIGHTS


class FakeClock:
    """Settable, injectable in-memory clock for deterministic unit testing."""

    def __init__(self, start_time: float = 1000.0):
        self._time = float(start_time)

    def __call__(self) -> float:
        return self._time

    def set(self, t: float) -> None:
        self._time = float(t)

    def advance(self, seconds: float) -> None:
        self._time += float(seconds)


class TestDisputeTracker(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(1000.0)
        self.tracker = DisputeTracker(
            clock=self.clock,
            decay_seconds=150.0,
            max_threads=8,
            offer_threshold=0.72,
        )

    def test_proposition_family_key_normalizes_and_excludes_disputed_value(self):
        family1 = PropositionFamily(
            entity="كارت الـ RTX 5070",
            dimension="VRAM",
            temporal_anchor=None,
            value_type="categorical",
        )
        family2 = PropositionFamily(
            entity="RTX 5070",
            dimension="vram",
            temporal_anchor="",
            value_type="categorical",
        )
        self.assertEqual(family1.proposition_key(), "rtx 5070|vram||categorical")
        self.assertEqual(family1.proposition_key(), family2.proposition_key())
        # The disputed values ("12gb" vs "16gb") are absent from the key
        self.assertNotIn("12", family1.proposition_key())
        self.assertNotIn("16", family1.proposition_key())

    def test_first_incompatible_pair_watching_created(self):
        prop_key = "rtx 5070|vram||categorical"
        e1 = ClaimEvent(
            event_id="e1",
            timestamp=self.clock(),
            speaker_id="speaker_a",
            proposition_key=prop_key,
            value_key="12gb",
            confidence=0.9,
            text="كارت الـ 5070 نازل بـ 12 جيجا",
        )
        d1 = self.tracker.ingest(e1)
        self.assertEqual(d1.action, "watching")
        self.assertEqual(d1.state, ThreadState.WATCHING)

        # Incompatible claim from speaker_b
        self.clock.advance(2.0)
        e2 = ClaimEvent(
            event_id="e2",
            timestamp=self.clock(),
            speaker_id="speaker_b",
            proposition_key=prop_key,
            value_key="16gb",
            confidence=0.88,
            text="لا الـ 5070 هينزل بـ 16 جيجا",
        )
        d2 = self.tracker.ingest(e2)

        # First incompatible pair -> WATCHING created and sides recorded
        self.assertEqual(d2.action, "watching")
        self.assertEqual(d2.state, ThreadState.WATCHING)

        thread = self.tracker.get_thread(prop_key)
        self.assertIsNotNone(thread)
        self.assertEqual(thread.state, ThreadState.WATCHING)
        self.assertTrue(thread.is_conflict)
        self.assertEqual(set(thread.sides.keys()), {"12gb", "16gb"})
        self.assertEqual(thread.sides["12gb"], {"speaker_a"})
        self.assertEqual(thread.sides["16gb"], {"speaker_b"})
        self.assertFalse(thread.offered)

    def test_repeat_of_same_pair_tracking_confidence_computed(self):
        prop_key = "rtx 5070|vram||categorical"
        # 1. Speaker A says 12gb
        self.tracker.ingest(
            ClaimEvent("e1", self.clock(), "speaker_a", prop_key, "12gb", 0.9, "12 جيجا")
        )
        # 2. Speaker B says 16gb (first incompatible pair)
        self.clock.advance(2.0)
        self.tracker.ingest(
            ClaimEvent("e2", self.clock(), "speaker_b", prop_key, "16gb", 0.9, "16 جيجا")
        )

        # 3. Speaker A repeats 12gb -> repeat of same pair!
        self.clock.advance(3.0)
        e3 = ClaimEvent("e3", self.clock(), "speaker_a", prop_key, "12gb", 0.95, "بقولك 12 جيجا أكيد")
        d3 = self.tracker.ingest(e3)

        thread = self.tracker.get_thread(prop_key)
        self.assertIsNotNone(thread)
        # State transitioned to TRACKING (or OFFERED if high score)
        self.assertIn(thread.state, (ThreadState.TRACKING, ThreadState.OFFERED))
        # Confidence was computed
        self.assertIsNotNone(d3.confidence)
        self.assertGreater(d3.confidence, 0.0)
        self.assertGreater(thread.peak_score, 0.0)

    def test_multi_speakers_per_side_eligible_at_threshold(self):
        prop_key = "world_cup|winner|2022|categorical"
        # Side 1: Argentina (Ahmed, Mostafa)
        # Side 2: France (Karim, Tamer)
        self.tracker.ingest(
            ClaimEvent("e1", self.clock(), "Ahmed", prop_key, "argentina", 0.95, "الأرجنتين كسبت كأس العالم")
        )
        self.clock.advance(1.0)
        self.tracker.ingest(
            ClaimEvent("e2", self.clock(), "Karim", prop_key, "france", 0.90, "فرنسا اللي كسبت")
        )
        self.clock.advance(1.0)
        d3 = self.tracker.ingest(
            ClaimEvent("e3", self.clock(), "Mostafa", prop_key, "argentina", 0.95, "ميسي والأرجنتين كسبوا")
        )
        # At event 3: France side still only has 1 speaker, so multi-speaker threshold not reached yet
        self.assertEqual(d3.action, "tracking")
        self.assertFalse(self.tracker.get_thread(prop_key).offered)

        self.clock.advance(1.0)
        d4 = self.tracker.ingest(
            ClaimEvent("e4", self.clock(), "Tamer", prop_key, "france", 0.92, "مبابي جاب هاتريك وفرنسا كسبت")
        )

        thread = self.tracker.get_thread(prop_key)
        self.assertIsNotNone(thread)
        # >= 2 distinct speakers per side:
        self.assertGreaterEqual(len(thread.sides["argentina"]), 2)
        self.assertGreaterEqual(len(thread.sides["france"]), 2)

        # Must reach offer threshold C >= 0.72 -> PEAK -> request_offer (OFFERED)
        self.assertGreaterEqual(d4.confidence, 0.72)
        self.assertEqual(d4.action, "request_offer")
        self.assertEqual(d4.state, ThreadState.OFFERED)
        self.assertTrue(thread.offered)
        self.assertEqual(thread.state, ThreadState.OFFERED)

    def test_single_speaker_repeating_alone_capped_lower(self):
        prop_key = "monologue|fact||categorical"
        # One speaker talking alone making competing claims or reiterating
        self.tracker.ingest(
            ClaimEvent("e1", self.clock(), "Solo", prop_key, "opt_a", 0.9, "الخيار أ")
        )
        self.clock.advance(1.0)
        self.tracker.ingest(
            ClaimEvent("e2", self.clock(), "Solo", prop_key, "opt_b", 0.9, "الخيار ب")
        )
        self.clock.advance(1.0)
        self.tracker.ingest(
            ClaimEvent("e3", self.clock(), "Solo", prop_key, "opt_a", 0.9, "الخيار أ تاني")
        )
        self.clock.advance(1.0)
        d4 = self.tracker.ingest(
            ClaimEvent("e4", self.clock(), "Solo", prop_key, "opt_a", 0.9, "الخيار أ تالت")
        )

        thread = self.tracker.get_thread(prop_key)
        self.assertIsNotNone(thread)
        # Single speaker alone does NOT satisfy multi-speaker criterion:
        self.assertEqual(len(thread.distinct_speakers), 1)
        # Confidence is capped lower (< 0.72 threshold)
        self.assertLess(d4.confidence, 0.72)
        self.assertNotEqual(d4.action, "request_offer")
        self.assertFalse(thread.offered)
        self.assertEqual(thread.state, ThreadState.TRACKING)

    def test_agreement_same_side_no_conflict_thread(self):
        prop_key = "rtx 5070|vram||categorical"
        # Both say 16 جيجا
        e1 = ClaimEvent("e1", self.clock(), "speaker_1", prop_key, "16 جيجا", 0.95, "الـ 5070 بيجي بـ 16 جيجا")
        d1 = self.tracker.ingest(e1)
        self.assertEqual(d1.action, "watching")

        self.clock.advance(1.0)
        e2 = ClaimEvent("e2", self.clock(), "speaker_2", prop_key, "16 جيجا", 0.95, "أيوة فعلاً بـ 16 جيجا")
        d2 = self.tracker.ingest(e2)

        # Same side agreement -> action "none", no conflict
        self.assertEqual(d2.action, "none")
        thread = self.tracker.get_thread(prop_key)
        self.assertIsNotNone(thread)
        self.assertFalse(thread.is_conflict)
        self.assertFalse(self.tracker.has_conflict(prop_key))
        self.assertEqual(len(self.tracker.get_conflict_threads()), 0)
        self.assertEqual(len(thread.sides), 1)
        self.assertEqual(thread.sides["16 جيجا"], {"speaker_1", "speaker_2"})

    def test_decay_advance_past_150s_tick_expired(self):
        prop_key = "decay_test|topic||categorical"
        self.tracker.ingest(
            ClaimEvent("e1", self.clock(), "A", prop_key, "v1", 0.9, "claim 1")
        )
        self.clock.advance(2.0)
        self.tracker.ingest(
            ClaimEvent("e2", self.clock(), "B", prop_key, "v2", 0.9, "claim 2")
        )

        thread = self.tracker.get_thread(prop_key)
        self.assertEqual(thread.state, ThreadState.WATCHING)

        # Advance past decay_seconds (150s)
        self.clock.advance(155.0)
        decisions = self.tracker.tick()

        # Thread must be marked EXPIRED
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action, "expired")
        self.assertEqual(decisions[0].thread_id, thread.thread_id)
        self.assertEqual(thread.state, ThreadState.EXPIRED)

    def test_revival_new_event_before_decay_stays_alive(self):
        prop_key = "revival_test|topic||categorical"
        self.tracker.ingest(
            ClaimEvent("e1", self.clock(), "A", prop_key, "v1", 0.9, "claim 1")
        )

        # Advance 100s (> 150*0.6 = 90s, enters DECAY state on tick)
        self.clock.advance(100.0)
        decay_decisions = self.tracker.tick()
        self.assertEqual(len(decay_decisions), 1)
        self.assertEqual(decay_decisions[0].action, "decay")
        thread = self.tracker.get_thread(prop_key)
        self.assertEqual(thread.state, ThreadState.DECAY)

        # Relevant event arrives at 100s elapsed (< 150s decay_seconds) -> revives!
        e2 = ClaimEvent("e2", self.clock(), "B", prop_key, "v2", 0.9, "claim 2")
        d2 = self.tracker.ingest(e2)

        self.assertNotEqual(thread.state, ThreadState.EXPIRED)
        self.assertEqual(thread.last_activity, self.clock())
        self.assertEqual(d2.state, ThreadState.WATCHING)

        # Advance another 100s from last activity: still alive, not expired
        self.clock.advance(100.0)
        tick_decisions = self.tracker.tick()
        # May be in decay, but strictly NOT EXPIRED
        self.assertNotEqual(thread.state, ThreadState.EXPIRED)
        self.assertTrue(all(d.action != "expired" for d in tick_decisions))

    def test_max_threads_eviction_order(self):
        # Create 8 threads
        for i in range(8):
            pk = f"prop_{i}|dim||categorical"
            self.tracker.ingest(
                ClaimEvent(f"ev_{i}", self.clock(), f"spk_{i}", pk, f"val_{i}", 0.8, f"text_{i}")
            )
            self.clock.advance(1.0)

        self.assertEqual(len(self.tracker.threads), 8)

        # Thread 0: set to EXPIRED
        self.tracker.threads["prop_0|dim||categorical"].state = ThreadState.EXPIRED
        self.tracker.threads["prop_0|dim||categorical"].last_activity = 100.0

        # Thread 1: set to DECAY
        self.tracker.threads["prop_1|dim||categorical"].state = ThreadState.DECAY
        self.tracker.threads["prop_1|dim||categorical"].last_activity = 200.0

        # Thread 2: set to OFFERED (must NEVER be evicted)
        self.tracker.threads["prop_2|dim||categorical"].state = ThreadState.OFFERED
        self.tracker.threads["prop_2|dim||categorical"].offered = True
        self.tracker.threads["prop_2|dim||categorical"].peak_score = 0.9

        # Thread 3: WATCHING with lowest score 0.05
        self.tracker.threads["prop_3|dim||categorical"].peak_score = 0.05

        # Threads 4-7: WATCHING with higher scores
        self.tracker.threads["prop_4|dim||categorical"].peak_score = 0.40
        self.tracker.threads["prop_5|dim||categorical"].peak_score = 0.50
        self.tracker.threads["prop_6|dim||categorical"].peak_score = 0.60
        self.tracker.threads["prop_7|dim||categorical"].peak_score = 0.70

        # 1. Add 9th thread -> oldest EXPIRED (prop_0) evicted first
        self.tracker.ingest(
            ClaimEvent("e_new1", self.clock(), "spk_x", "prop_new1|dim||categorical", "v", 0.9, "t")
        )
        self.tracker.threads["prop_new1|dim||categorical"].peak_score = 0.80
        self.assertNotIn("prop_0|dim||categorical", self.tracker.threads)
        self.assertIn("prop_new1|dim||categorical", self.tracker.threads)
        self.assertEqual(len(self.tracker.threads), 8)

        # 2. Add 10th thread -> DECAY (prop_1) evicted next
        self.tracker.ingest(
            ClaimEvent("e_new2", self.clock(), "spk_x", "prop_new2|dim||categorical", "v", 0.9, "t")
        )
        self.tracker.threads["prop_new2|dim||categorical"].peak_score = 0.80
        self.assertNotIn("prop_1|dim||categorical", self.tracker.threads)
        self.assertIn("prop_new2|dim||categorical", self.tracker.threads)

        # 3. Add 11th thread -> lowest-score WATCHING (prop_3, score 0.05) evicted
        self.tracker.ingest(
            ClaimEvent("e_new3", self.clock(), "spk_x", "prop_new3|dim||categorical", "v", 0.9, "t")
        )
        self.assertNotIn("prop_3|dim||categorical", self.tracker.threads)
        self.assertIn("prop_new3|dim||categorical", self.tracker.threads)

        # 4. Verify OFFERED thread was NEVER evicted
        self.assertIn("prop_2|dim||categorical", self.tracker.threads)
        self.assertTrue(self.tracker.threads["prop_2|dim||categorical"].offered)

    def test_snapshot_restore_round_trip_preserves_state(self):
        # Create two rich threads
        pk1 = "phone|battery||categorical"
        self.tracker.ingest(ClaimEvent("e1", self.clock(), "UserA", pk1, "5000mah", 0.9, "5000 mAh"))
        self.clock.advance(2.0)
        self.tracker.ingest(ClaimEvent("e2", self.clock(), "UserB", pk1, "4500mah", 0.9, "4500 mAh"))

        pk2 = "cpu|cores||categorical"
        self.tracker.ingest(ClaimEvent("e3", self.clock(), "UserC", pk2, "8cores", 0.85, "8 cores"))

        snapshot = self.tracker.snapshot()
        # Verify plain dict and JSON serializable
        json_data = json.dumps(snapshot)
        deserialized = json.loads(json_data)

        # Restore into clean tracker
        new_clock = FakeClock(self.clock())
        restored = DisputeTracker(clock=new_clock)
        restored.restore(deserialized)

        self.assertEqual(len(restored.threads), len(self.tracker.threads))
        t1 = restored.get_thread(pk1)
        orig_t1 = self.tracker.get_thread(pk1)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.thread_id, orig_t1.thread_id)
        self.assertEqual(t1.state, orig_t1.state)
        self.assertEqual(t1.sides, orig_t1.sides)
        self.assertEqual(len(t1.events), len(orig_t1.events))
        self.assertEqual(t1.events[0].text, orig_t1.events[0].text)
        self.assertEqual(t1.created_at, orig_t1.created_at)
        self.assertEqual(t1.last_activity, orig_t1.last_activity)

    def test_confidence_with_missing_features_uses_normalized_denominator(self):
        prop_key = "test|metric||categorical"
        thread = DisputeThread(
            thread_id="th_test",
            proposition_key=prop_key,
            state=ThreadState.TRACKING,
            sides={"v1": {"spk1"}, "v2": {"spk2"}},
        )

        # Features with only repetition (0.32) and checkability (0.15) present
        # Missing: speaker_diversity (0.25), stability (0.18), escalation (0.10)
        custom_feats = {
            "repetition": 0.80,
            "checkability": 0.90,
            "speaker_diversity": None,
            "stability": None,
            "escalation": None,
        }
        score = self.tracker.compute_confidence(thread, custom_features=custom_feats)

        expected_numerator = (0.32 * 0.80) + (0.15 * 0.90)  # 0.256 + 0.135 = 0.391
        expected_denominator = 0.32 + 0.15                  # 0.47
        expected_normalized_score = expected_numerator / expected_denominator  # ~0.83191489

        self.assertAlmostEqual(score, expected_normalized_score, places=5)
        # Must NOT equal the zeroed denominator version (0.391 / 1.0 = 0.391)
        self.assertNotAlmostEqual(score, expected_numerator, places=2)

        # Also verify hyphenated alias 'speaker-diversity'
        alias_feats = {
            "repetition": 1.0,
            "speaker-diversity": 1.0,
        }
        alias_score = self.tracker.compute_confidence(thread, custom_features=alias_feats)
        # Denominator: 0.32 + 0.25 = 0.57. Numerator: 0.32 + 0.25 = 0.57. Result = 1.0
        self.assertAlmostEqual(alias_score, 1.0, places=5)

    def test_f3_04_offered_state_not_demoted_and_not_evicted_on_decay(self):
        """
        F3-04: When a thread reaches OFFERED state, subsequent claims on the same thread
        must NOT demote thread.state to TRACKING or WATCHING.
        When tick() sweeps, the offered thread must remain OFFERED and never enter DECAY,
        preserving the Rule 4 invariant: 'Never evict OFFERED'.
        """
        prop_key = "rtx_vram|gpu||categorical"
        # Side A: Omar, Side B: Ziad, Side A: Mostafa, Side B: Tamer (2 vs 2 multi-speaker dispute)
        self.tracker.ingest(ClaimEvent("e1", self.clock(), "Omar", prop_key, "16GB", 0.95, "كارت 16 جيجا"))
        self.clock.advance(1.0)
        self.tracker.ingest(ClaimEvent("e2", self.clock(), "Ziad", prop_key, "12GB", 0.95, "لا هو 12 بس"))
        self.clock.advance(1.0)
        self.tracker.ingest(ClaimEvent("e3", self.clock(), "Mostafa", prop_key, "16GB", 0.95, "أنا متأكد 16"))
        self.clock.advance(1.0)
        d4 = self.tracker.ingest(ClaimEvent("e4", self.clock(), "Tamer", prop_key, "12GB", 0.95, "لا 12 جيجا بايت"))

        thread = self.tracker.get_thread(prop_key)
        self.assertTrue(thread.offered, "Thread should be marked offered")
        self.assertEqual(thread.state, ThreadState.OFFERED, "Thread state should be OFFERED")
        self.assertEqual(d4.action, "request_offer")

        # Subsequent claim on the SAME proposition after OFFERED
        self.clock.advance(2.0)
        d5 = self.tracker.ingest(ClaimEvent("e5", self.clock(), "Kareem", prop_key, "12GB", 0.95, "أنا مع تامر 12"))
        self.assertEqual(d5.state, ThreadState.OFFERED, "Subsequent claim must NOT demote state to TRACKING")
        self.assertEqual(thread.state, ThreadState.OFFERED, "Thread state must remain OFFERED")

        # Advance past 60% decay window (> 90s)
        self.clock.advance(100.0)
        decisions = self.tracker.tick()
        # Verify tick() did NOT demote to DECAY
        decay_for_thread = [d for d in decisions if d.thread_id == thread.thread_id and d.action == "decay"]
        self.assertEqual(len(decay_for_thread), 0, "OFFERED thread must never enter DECAY on tick()")
        self.assertEqual(thread.state, ThreadState.OFFERED, "Thread state must remain OFFERED after tick()")


if __name__ == "__main__":
    unittest.main()
