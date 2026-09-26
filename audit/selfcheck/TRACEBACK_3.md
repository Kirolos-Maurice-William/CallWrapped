# Self-Supervision Traceback #3: Capture Finalization & Step 9 Scorer Review

**Audit Date:** 2026-09-26  
**Review Type:** Hostile Traceback of Session Claims (`2b5df7f` -> `2999aca`)  
**Scope:** Commits `3416d10`, `f0b16cc`, `2fa65f1`, `2999aca`  
**Review Mode:** Read-Only on project code; report to `audit/selfcheck/TRACEBACK_3.md` only.

---

## 1. Commit and Diff Summary

```
git diff 2b5df7f..2999aca --stat
 REGRESSION_LEDGER.md             |  14 +-
 audit/score_results.md           |  37 +++++
 audit/score_test_session.py      | 347 +++++++++++++++++++++++++++++++++++++++
 audit/selfcheck/SELFCHECK_2.md   | 153 +++++++++++++++++
 bot/audio/__init__.py            |   6 +
 bot/audio/capture.py             | 100 +++++++----
 bot/main.py                      |  21 ++-
 tests/test_capture_mode.py       | 101 +++++++++++-
 tests/test_score_test_session.py | 159 ++++++++++++++++++
 9 files changed, 900 insertions(+), 38 deletions(-)
```

---

## 2. Claim-by-Claim Verification

### Claim 1 — CAP-02: Active Capture Finalization on `!leave` & `!clear`
- **Claim:** Active capture sessions auto-finalize on `!leave` and `!clear`, write `labels_DRAFT.csv`, clear session folder, reset `TEST_CAPTURE_MODE=0`, and report the CSV path to Discord.
- **Code Trace:**
  - `bot/audio/capture.py:79-81`: `is_capture_active()` checks `bool(getattr(config, "TEST_CAPTURE_MODE", 0) or _active_session_dir is not None)`.
  - `bot/audio/capture.py:97-101`: `finalize_capture_if_active_async()` delegates to `asyncio.to_thread(stop_capture_session)`.
  - `bot/main.py:974-981`: `clear_session` awaits `finalize_capture_if_active_async()` and appends `capture_msg` with CSV path.
  - `bot/main.py:990-1004`: `leave_channel` awaits `finalize_capture_if_active_async()` and appends `capture_msg` with CSV path.
  - `tests/test_capture_mode.py:325-373`: `test_e_leave_finalizes_active_capture_session` asserts CSV existence, reset flag, released directory, and Discord message contents.
- **Verdict:** **VERIFIED**. Implementation matches claims exactly.

### Claim 2 — CAP-01: Graceful OSError Handling in Capture Save
- **Claim:** File operations in `save_captured_utterance_sync` are wrapped in `try...except OSError as e`, logging error at ERROR level, preventing audio thread crashes, and returning `capture_status="capture_failed"`.
- **Code Trace:**
  - `bot/audio/capture.py:137-183`: Encloses folder creation, audio file write, and JSONL append inside `try...except OSError as e`.
  - On exception: logs `logger.error(f"❌ [Capture Failed] Filesystem error saving utterance to {target_dir}: {e}")` and returns dict with `wav_filename=None`, `capture_status="capture_failed"`, and `error=str(e)`.
  - `tests/test_capture_mode.py:375-424`: `test_f_save_captured_utterance_oserror_graceful_degradation` simulates an invalid nested path under a regular file (`NotADirectoryError`), capturing the error log and validating return structure.
- **Verdict:** **VERIFIED**. Degrades gracefully without uncaught task exceptions.

### Claim 3 — REG-01: Regression Ledger Desync Resolution
- **Claim:** All commit entries since `7edf883` restored and synchronized with git log.
- **Code Trace:**
  - `REGRESSION_LEDGER.md:54-63` lists commits `7edf883`, `6d0d025`, `6b93ac1`, `2bf3fb8`, `dac9b02`, `ca7fa7e`, `2b5df7f`, `3416d10`, `f0b16cc`, `2fa65f1`, and `2999aca`.
  - `git log -n 5 --oneline` matches ledger entries exactly.
- **Verdict:** **VERIFIED**.

### Claim 4 — SCR-01: Step 9 Scorer Tool & Refusal Rule
- **Claim:** `audit/score_test_session.py` reads session CSVs, runs real AssemblyAI transcription, computes WER, number accuracy, claim/anger classification via `ClaimDetector`, contradiction pairs via `ConflictDetector`, and skips empty `correct_text` rows.
- **Code Trace:**
  - `audit/score_test_session.py:72-80`: Refusal gate skips any row with empty `correct_text`, populating `skipped_records`.
  - `audit/score_test_session.py:94-110`: Transcribes via `assemblyai_client.transcribe` with `pace_delay_sec` and computes WER via `jiwer.wer(ref_clean, hyp_clean)`.
  - `audit/score_test_session.py:112-120`: Number matching extracts tokens via `get_numbers`.
  - `audit/score_test_session.py:122-176`: Classifies claim, topic, and anger via `claim_detector.check_claim`.
  - `audit/score_test_session.py:186-206`: Evaluates contradiction pairs via `conflict_detector.detect_conflict`.
- **Verdict:** **VERIFIED (Functionality)** / **DEFECT DETECTED (Test Isolation)**. The tool works, but the unit test has a severe side-effect (see Finding TRACE-01).

### Claim 5 — Phase 4: Real Rehearsal & `score_results.md`
- **Claim:** Rehearsal run against `recordings/test_session/2026-09-26_smoke_rehearsal` produced `audit/score_results.md` with Overall WER 8.91%, Clean WER 8.91%, 3 scored clips, 1 skipped clip.
- **Evidence Trace:**
  - Step 2965 created the smoke session with 4 clips.
  - Step 2967 (`task-2968`) executed `audit.score_test_session` and successfully generated the 8.91% WER report.
  - **HOWEVER:** In git commit `2999aca` (and currently on disk), `audit/score_results.md` contains `Session Folder: test_score_session_vz224c0e` with **16.72% WER** — NOT the 8.91% rehearsal!
  - **Root Cause:** In the subsequent full test suite run (`task-2992`), `tests/test_score_test_session.py` ran at 15:50:19 and executed line 149: `DEFAULT_RESULTS_FILE.write_text(md_text, encoding="utf-8")`. This unconditionally clobbered `audit/score_results.md` with the unit test's synthetic data immediately prior to committing!
- **Verdict:** **PARTIAL / MISMATCH**. The rehearsal ran, but the committed repository artifact was clobbered by the test suite.

### Claim 6 — Full Suite Green (65s Discipline)
- **Claim:** Full test suite ran with 107 tests green in 102.015s, 1 skipped.
- **Evidence Trace:**
  - `task-2992.log` confirms: `Ran 107 tests in 102.015s. OK (skipped=1)`.
- **Verdict:** **VERIFIED**.

---

## 3. Findings Registry (Severity-Tagged)

### [TRACE-01] SEV-1 (High) — Unit Test Pollution: `test_score_test_session.py` Clobbers Tracked Project File
- **Location:** [`tests/test_score_test_session.py:149`](file:///G:/CallWrapper/tests/test_score_test_session.py#L149)
- **Description:** Line 149 contains `DEFAULT_RESULTS_FILE.write_text(md_text, encoding="utf-8")`, where `DEFAULT_RESULTS_FILE = PROJECT_ROOT / "audit" / "score_results.md"`.
- **Impact:** Every single run of `unittest discover` or `test_score_test_session.py` overwrites the persistent project report with temporary synthetic test runner data. This violates unit test isolation (tests must only write within `tempfile` sandboxes).
- **Evidence:** Commit `2999aca` committed `Session Folder: test_score_session_vz224c0e` (WER 16.72%) instead of the rehearsal session (`2026-09-26_smoke_rehearsal`, WER 8.91%).

### [TRACE-02] SEV-2 (Medium) — Top-Level Executing Code in `check_numbers.py` Pollutes STDOUT and Crashes If CWD != Repo Root
- **Location:** [`audit/check_numbers.py:44-50`](file:///G:/CallWrapper/audit/check_numbers.py#L44-L50)
- **Description:** `audit/check_numbers.py` has no `if __name__ == '__main__':` guard. At module load time, lines 44-50 execute:
  ```python
  with open('audit/mgb3_clips/labels.csv', 'r', encoding='utf-8') as f:
      reader = csv.DictReader(f)
      for r in reader:
          nums = get_numbers(r['reference_cleaned'])
          if nums:
              print(f"{r['id']} ({r['genre']}): {nums}")
  ```
- **Impact:**
  1. Whenever `from audit.check_numbers import get_numbers` is called by `score_test_session.py`, 5 print lines pollute STDOUT.
  2. If Python is executed from any working directory other than repository root (e.g., from `backend/` or in subfolder testing), `open('audit/mgb3_clips/labels.csv')` raises `FileNotFoundError: [Errno 2] No such file or directory: 'audit/mgb3_clips/labels.csv'` and prevents module import entirely.
- **Evidence:** Confirmed via CLI: `python -c "import os; os.chdir('backend'); from audit.score_test_session import score_session"` crashes with `FileNotFoundError`.

### [TRACE-03] SEV-3 (Low) — Metric Methodology Nuance: Macro-Average WER vs. Corpus Micro-Average WER
- **Location:** [`audit/score_test_session.py:210`](file:///G:/CallWrapper/audit/score_test_session.py#L210)
- **Description:** `score_test_session.py` computes `avg_wer = (sum(r["wer"] for r in scored_records) / n_scored)` (macro-average of per-clip WERs), whereas `audit/run_hearing_test.py:219` computes `overall_wer = jiwer.wer(all_refs, all_hyps)` (standard micro-average corpus WER: total word errors / total reference words).
- **Impact:** Macro-average gives equal weight to short (e.g. 2-word) and long (50-word) utterances. A single substitution in a 2-word utterance adds 50% to the macro-average. While per-clip WER is appropriate for tabular breakdown, the headline "Overall WER" differs in methodology from standard ASR benchmarking without notation in the report.

### [TRACE-04] SEV-3 (Low) — Unused Imports Left Behind in New Modules
- **Location:**
  - [`audit/score_test_session.py:1,4,10`](file:///G:/CallWrapper/audit/score_test_session.py#L1-L10): `import os`, `import json`, and `Tuple` from `typing` are unused.
  - [`tests/test_score_test_session.py:2,4`](file:///G:/CallWrapper/tests/test_score_test_session.py#L2-L4): `import os` and `import json` are unused.
  - [`bot/audio/capture.py:84`](file:///G:/CallWrapper/bot/audio/capture.py#L84): `finalize_capture_if_active()` (sync variant) is defined and exported in `bot/audio/__init__.py`, but never called in production code (production callers use `finalize_capture_if_active_async()`).

### [TRACE-05] SEV-4 (Info) — Commit Scope Leak in Phase 1
- **Location:** Commit [`3416d10`](file:///G:/CallWrapper/audit/selfcheck/SELFCHECK_2.md)
- **Description:** Commit `3416d10` titled `"feat(audio): auto-finalize active capture on !leave and !clear (Phase 1 / CAP-02)"` also staged and committed `audit/selfcheck/SELFCHECK_2.md` (153 lines), which was left untracked from the preceding traceback session.

---

## 4. Dead Code & Scaffolding Roster

| File | Line(s) | Symbol / Statement | Status |
|---|---|---|---|
| `audit/score_test_session.py` | 1 | `import os` | Unused import |
| `audit/score_test_session.py` | 4 | `import json` | Unused import |
| `audit/score_test_session.py` | 10 | `Tuple` (from `typing`) | Unused import |
| `tests/test_score_test_session.py` | 2 | `import os` | Unused import |
| `tests/test_score_test_session.py` | 4 | `import json` | Unused import |
| `bot/audio/capture.py` | 84-94 | `def finalize_capture_if_active()` | Unreferenced helper in production code (sync wrapper) |

---

## 5. Confidence Statement

| Major Change Area | Confidence | Notes / Prerequisites |
|---|---|---|
| **Phase 1: CAP-02 (`!leave` / `!clear`)** | **VERIFIED** | Code paths verified, unit test passes cleanly, Discord messaging verified. |
| **Phase 2: CAP-01 (OSError degradation)** | **VERIFIED** | File I/O wrapped in `try/except OSError`, unit test proves failure capture and pipeline survival. |
| **Phase 2: REG-01 (Ledger sync)** | **VERIFIED** | Exact hash alignment verified against `git log`. |
| **Phase 3: SCR-01 (Scorer Tool)** | **PARTIAL** | Core engine functional, but blocked by TRACE-01 (test overwrites tracked file) and TRACE-02 (CWD import failure). |
| **Phase 4: Step 9 Rehearsal Output** | **PARTIAL** | Command executed and generated reported metrics, but committed artifact in repo was clobbered by TRACE-01. |

---

## Closing Summary

What would break if this diff shipped as-is?

Running tests in CI or local development will perpetually clobber `audit/score_results.md` with synthetic test data, importing `audit.score_test_session` from any non-root directory will crash immediately with `FileNotFoundError`, and the committed Step 9 scoring artifact does not reflect the rehearsal data claimed in the report.
