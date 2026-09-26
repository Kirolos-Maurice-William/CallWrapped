# Self-Supervision Traceback #4: Taxonomy v2 & Batch 1 Scoring Audit

**Audit Date:** 2026-09-26  
**Review Type:** Hostile Traceback of Session Claims (`4dafda2` -> `4b1d243`)  
**Scope:** Commits `b946f65`, `d821245`, `6dbbfbb`, `4b1d243`  
**Review Mode:** Read-Only on project code; report to `audit/selfcheck/TRACEBACK_4.md` only.

---

## 1. Commit and Diff Summary

```
git diff 4dafda2..4b1d243 --stat
 REGRESSION_LEDGER.md                     |   3 +
 audit/score_results_batch1.md            |  66 +++++------
 audit/score_test_session.py              |  99 +++++++++++++++--
 bot/arbitration/claim_detector.py        |  35 +++++-
 bot/arbitration/stats.py                 | 185 +++++++++++++++++++++++++++----
 bot/main.py                              |  23 ++--
 frontend/components/AnalyticsWidgets.tsx |  26 +++--
 tests/test_stats.py                      | 126 +++++++++++++++++++++
 8 files changed, 479 insertions(+), 84 deletions(-)
```

---

## 2. Claim-by-Claim Verification

### Claim 1 — Phase 1: Classifier Taxonomy Update (`b946f65`)
- **Claim:** Updated `BATCH_ANALYTICS_PROMPT` and `BATCH_ANALYTICS_SCHEMA` in `bot/arbitration/claim_detector.py` to include `personal` and `null_topic`. Added Egyptian dialectal examples for backchannels, greetings, call logistics, and reactions. Kept prompt token budget $\le 450$ tokens. Live verified 17-sentence battery on real Groq API.
- **Code Trace:**
  - `bot/arbitration/claim_detector.py:51`: Enum updated to `football|politics|music|movies|gaming|tech|personal|other|null_topic`.
  - `bot/arbitration/claim_detector.py:57-76`: Added Egyptian topic examples and null_topic rules/examples (`ازيك يا مصطفى عامل ايه`, `تمام سامعك كويس`, `بتسجل صوتنا استنى دقيقة`).
  - `bot/arbitration/claim_detector.py:106`: JSON schema enum updated with `personal` and `null_topic`.
  - Token count verified at ~448 tokens (within $\le 450$ token target).
  - Transcript step records confirm live 17-sentence battery on Groq key#4 returned 100% agreement.
- **Verdict:** **VERIFIED**.

### Claim 2 — Phase 2: Scorer & Stats Semantics Update (`d821245`)
- **Claim:**
  1. `bot/arbitration/stats.py` excludes `null_topic` from topic share denominator: $\text{topic share} = \frac{\text{topical time in class } k}{\text{total topical time}}$. Returns `{}` if total topical time is 0.
  2. Added Topical Coverage metric: $\frac{\text{topical time}}{\text{total talk time}}$.
  3. `audit/score_test_session.py` splits topic agreement into Topical Accuracy, Null Detection Accuracy, and Topical Coverage.
  4. `bot/main.py` recap Section D and `frontend/components/AnalyticsWidgets.tsx` exclude `null_topic` from ranking and show coverage disclosure.
- **Code Trace:**
  - `bot/arbitration/stats.py:251-267`: `get_topic_share()` filters out `null_topic`, `null`, `none`, `بدون موضوع`, `""`, and divides by `total_topical_time`.
  - `bot/arbitration/stats.py:269-284`: `get_topical_coverage()` divides `topical_time` by `total_talk_time`.
  - `audit/score_test_session.py:289-307`: Aggregates `topical_accuracy_pct`, `null_accuracy_pct`, and `human_topical_coverage_pct` vs `model_topical_coverage_pct`.
  - `audit/score_test_session.py:377-457`: Summary table formats separate rows for Topical Accuracy, Null Detection Accuracy, and Topical Coverage.
  - `bot/main.py:415-427`: Filters `null_topic` and adds `ℹ️ نسبة التغطية الموضوعية: ...`.
  - `frontend/components/AnalyticsWidgets.tsx:59-70, 132-136`: Excludes `null_topic` from pie chart and adds `Topical Coverage: X% | Excl. Y null` footer.
  - Frontend verified compiling via `npm run build` (exit code 0).
- **Verdict:** **VERIFIED**.

### Claim 3 — Phase 3: Dialogue-Act Streak Bridging (`d821245`)
- **Claim:**
  1. A speaker's `null_topic` utterance (< 5s gap) does not break their topic streak; null duration is excluded from topic streak seconds, acting as an unbroken bridge.
  2. Schegloff (1982) listener backchannel rule: A listener's `null_topic` utterance (< 2.0s duration) is an acknowledgment, not floor-taking, and does not break the primary speaker's active monologue or topic streak.
  3. Substantive listener speech or topic switches end the streak normally.
- **Code Trace:**
  - `bot/arbitration/stats.py:192-203`: Identifies `is_listener_backchannel` when `spk_key != self.primary_speaker_id and is_null and duration < 2.0`. Primary speaker's streaks are not reset.
  - `bot/arbitration/stats.py:228-235`: If `is_null`, active speaker's topic streak is not broken if gap < 5.0s and no floor change; `current_topic_streak` does not add null duration.
  - `bot/arbitration/stats.py:236-250`: When topical speech resumes, `stats.current_topic_streak += duration` and `topic_streak_count` does not increment.
  - `tests/test_stats.py:234-355`: 5 dedicated unit tests assert topic share calculations, null topic bridging, listener backchannels, substantive speech floor breaks, and topic switching.
  - `tests.test_stats` ran 10 tests in 0.001s: OK.
- **Verdict:** **VERIFIED**.

### Claim 4 — Phase 4: Batch 1 Relabeling & Re-Score (`6dbbfbb`)
- **Claim:** Relabeled `recordings/test_session/2026-09-26_1817/labels_DRAFT.csv` topic column without touching `correct_text` or `asr_text`. Re-ran scorer to `audit/score_results_batch1.md`.
- **Numbers Verification:**
  - Scored count: **25** (recomputed: 25 non-empty rows) -> VERIFIED.
  - Skipped count: **0** -> VERIFIED.
  - Topical Accuracy: **85.7%** (6/7 matches: tech 4/4, football 2/3) -> VERIFIED ($6/7 = 85.71\%$).
  - Null Detection Accuracy: **77.8%** (14/18 matches) -> VERIFIED ($14/18 = 77.77\%$).
  - Topical Coverage: **Model: 62.6% / Human: 45.2%** -> VERIFIED.
    - Recomputed from raw WAV files: total audio duration = 76.51s.
    - Human topical duration = 34.57s ($34.57 / 76.51 = 45.18\% \rightarrow 45.2\%$).
    - Model topical duration = 47.89s ($47.89 / 76.51 = 62.59\% \rightarrow 62.6\%$).
  - Micro WER: **40.10%** -> VERIFIED from AssemblyAI raw outputs. (Report did not blindly copy the 4.75% hypothesis from the user prompt).
  - Number Accuracy: **100.0%** (3/3) -> VERIFIED.
  - Claim Agreement: **96.0%** (24/25) -> VERIFIED.
  - Anger Agreement: **100.0%** (25/25) -> VERIFIED.
  - False-Anger Rate: **0.0%** (0/25) -> VERIFIED.
  - Contradiction Pairs Evaluated: **0**; Referee Triggers: **0** (no false positive interventions on natural speech) -> VERIFIED.
- **Verdict:** **VERIFIED**.

### Claim 5 — Full Test Suite Green (`4b1d243`)
- **Claim:** Full test suite verified with zero regressions across 115 unit & integration tests.
- **Evidence Trace:**
  - `task-4190.log`: `Ran 115 tests in 114.028s. OK (skipped=2)`.
  - 2 skipped tests were standard Groq TPD daily headroom skips in `test_fanout_analytics.py`.
- **Verdict:** **VERIFIED**.

---

## 3. Findings Registry (Severity-Tagged)

### [TRACE4-01] SEV-2 (Medium) — Heuristic Precedence Inversion in `infer_topic()` Fallback
- **Location:** [`bot/arbitration/claim_detector.py:148-149`](file:///g:/CallWrapper/bot/arbitration/claim_detector.py#L148-L149)
- **Description:** In the local keyword-heuristic fallback `infer_topic()`, `null_topic` keywords (`"تمام"`, `"أيوة"`, `"شايف"`, `"جامد"`, `"ماشي"`) are checked before topical domain keywords (`"tech"`, `"football"`, `"gaming"`).
- **Impact:**
  1. Any composite sentence beginning with a backchannel before stating a technical fact (e.g. `"تمام، كارت الـ RTX 5070 نازل بـ 12 جيجا"`) returns `"null_topic"`, hiding the topical domain.
  2. The slang word `"جامد"` matches as a bare substring anywhere in the utterance (e.g. `"الأهلي فريق جامد"` or `"كارت جامد أوي"`), forcing `"null_topic"` even though the prompt definition explicitly specifies `'جامد' as bare reaction`.
- **Mitigation:** In production, the batched Groq LLM classifier handles topic classification with full sentence context. However, if Groq fails and the engine falls back to `infer_topic()`, this heuristic ordering causes misclassifications.

### [TRACE4-02] SEV-3 (Low) — Dead Code: Unreferenced Module-Level Helpers in `stats.py`
- **Location:** [`bot/arbitration/stats.py:102-123`](file:///g:/CallWrapper/bot/arbitration/stats.py#L102-L123)
- **Description:** Functions `compute_topic_percentages(topic_durations: Dict[str, float])` and `compute_topical_coverage(topical_time: float, total_talk_time: float)` were added as standalone functions in `stats.py`.
- **Impact:** `SessionStatsTracker` defines its own member methods (`get_topic_share()` and `get_topical_coverage()`) and does not call these standalone functions. A repository-wide `git grep` confirms 0 references outside their own definitions. They represent 22 lines of unused scaffolding code.

### [TRACE4-03] SEV-3 (Low) — Loop-Internal Module Import in `score_test_session.py`
- **Location:** [`audit/score_test_session.py:93`](file:///g:/CallWrapper/audit/score_test_session.py#L93)
- **Description:** `import wave` is executed inside the clip scoring loop (`for row in rows:` line 93) on every utterance rather than at the top of the file alongside `jiwer`, `csv`, and `argparse`.
- **Impact:** Minor code smell / PEP 8 violation. Python caches the module in `sys.modules`, so runtime overhead is negligible, but it is inconsistent with top-level import patterns.

### [TRACE4-04] SEV-3 (Low) — Blank String Conflation with `null_topic` in Scorer
- **Location:** [`audit/score_test_session.py:141, 201`](file:///g:/CallWrapper/audit/score_test_session.py#L141)
- **Description:** In `score_test_session.py`, `human_is_null` is computed as:
  `human_is_null = human_topic in ("null_topic", "null", "none", "بدون موضوع", "")`
- **Impact:** If a human annotator leaves the `topic` column completely blank (`""`) while providing `correct_text`, the scorer does not flag it as "unannotated topic" or skip topic scoring for that row; instead, it silently treats the blank cell as an intentional human label of `null_topic`. If the model also predicts `null_topic`, it records a false match.

---

## 4. Dead Code Sweep

| File | Lines | Symbol | Status |
|---|---|---|---|
| `bot/arbitration/stats.py` | 102-116 | `def compute_topic_percentages` | Dead addition (0 calls repo-wide) |
| `bot/arbitration/stats.py` | 118-123 | `def compute_topical_coverage` | Dead addition (0 calls repo-wide) |

---

## 5. Confidence Statement

| Area | Status | Verification Basis |
|---|---|---|
| Phase 1: Classifier Prompt & Schema | **VERIFIED** | Live 17-sentence battery, schema inspection, token budget |
| Phase 2: Topical-only Share & Scorer Split | **VERIFIED** | Unit tests in `test_stats.py`, Next.js build clean, scorer math recomputed |
| Phase 3: Dialogue-Act Streak Bridging | **VERIFIED** | 5 dedicated unit tests in `test_stats.py`, all passed |
| Phase 4: Batch 1 Re-Score & Report | **VERIFIED** | Live AssemblyAI + Groq scoring, exact recomputation of all cited percentages |
| Regression Ledger Synchronization | **VERIFIED** | Clean git status, commits match ledger entries exactly |

---

## Closing Sentence
**What would break if this diff shipped as-is?**

Nothing would break in production or tests (all 115 tests pass, Next.js compiles cleanly, and the Discord bot runs as intended); however, if Groq API goes down and the bot falls back to `infer_topic()`, any topical claim containing common acknowledgment words like `"تمام"` or the adjective `"جامد"` (e.g. `"الأهلي فريق جامد"`) would be misclassified as non-topical `null_topic`. Additionally, 22 lines of dead helper functions in `bot/arbitration/stats.py` will persist in the codebase.
