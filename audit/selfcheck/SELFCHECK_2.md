# Self-Supervision Traceback #2: Test-Capture Correctness Audit

**Audit Date:** 2026-09-26  
**Auditor Mode:** Hostile Independent Self-Reviewer (Read-Only on Project Code)  
**Target Scope:** Activation Truth, Session Isolation, Migration, Docs Synchronization  

---

## Executive Summary

This traceback independently audited the test-capture correctness pass implemented across commits `dac9b02`, `ca7fa7e`, and `2b5df7f`. Every claim made in the previous report was re-derived from raw repository evidence and executed under adversarial conditions.

### High-Level Verdict:
- **Activation Truth & Privacy Invariant:** **VERIFIED**. Capture was never silently ON by default; `TEST_CAPTURE_MODE` has defaulted to `0` since inception. The in-memory privacy claim is 100% true.
- **Session Isolation:** **VERIFIED**. Two consecutive sessions produce distinct timestamped folders with zero cross-session leakage, zero parent-level file appends, and clean isolation.
- **Migration & Human Label Preservation:** **VERIFIED**. Pre-existing human annotations survive untouched; non-audio files are never deleted.
- **Ledger Invariant:** **VIOLATION (REG-01)**. `REGRESSION_LEDGER.md` is missing Phase 1 commit `dac9b02` and contains an outdated commit hash for Phase 3 due to an edit conflict in the previous session.
- **Lifecycle Integration:** **FINDING (CAP-02)**. `!leave` disconnects voice and resets arbitration, but does not finalize active capture sessions.
- **Evaluation Tooling:** **FINDING (SCR-01)**. `audit/` scripts are hardcoded to MGB-3 and cannot directly evaluate `labels_DRAFT.csv` without an adapter.

---

## Claim-by-Claim Verification

### CLAIM 1 — "Activation truth answered honestly"
- **Verdict:** **VERIFIED**
- **Evidence:**
  - `git grep -inE "TEST_CAPTURE|CAPTURE|start.capture" -- "bot/*.py" "backend/*.py"` confirms the activation mechanism is controlled exclusively by:
    1. Environment variable `TEST_CAPTURE_MODE` in `bot/config.py:45` (`int(os.getenv("TEST_CAPTURE_MODE", "0"))`).
    2. Dynamic Discord admin command `!start-capture` (`bot/main.py:674`), invoking `start_capture_session()` (`bot/audio/capture.py:47`).
  - Trace end-to-end: In `bot/main.py:121`, utterance saving is strictly guarded by `if getattr(config, "TEST_CAPTURE_MODE", 0):`. When `0` (the default), the branch is entirely bypassed.
  - **Privacy Check:** Commit history (`git log -p -S "TEST_CAPTURE_MODE" bot/config.py`) reveals that commit `6e11630` introduced `TEST_CAPTURE_MODE` with default `"0"`. It was **never** silently ON by default in any release. The `!privacy` text disclosure asserting that voice is processed strictly in-memory unless capture is explicitly toggled by admins is **100% TRUE**.

### CLAIM 2 — "Session isolation works, two sessions never stack"
- **Verdict:** **VERIFIED**
- **Evidence:**
  - Reproduced the exact unit scenario in an isolated test harness:
    ```python
    s_a = start_capture_session(base_dir=temp_dir)
    save_captured_utterance_sync(speaker_name='SpeakerA1', ...)
    save_captured_utterance_sync(speaker_name='SpeakerA2', ...)
    stop_capture_session(recordings_dir=s_a)

    s_b = start_capture_session(base_dir=temp_dir)
    save_captured_utterance_sync(speaker_name='SpeakerB1', ...)
    stop_capture_session(recordings_dir=s_b)
    ```
  - Result:
    - Root directory files: `[]` (zero loose files).
    - Session A folder: `2026-09-26_1517/` -> 2 WAVs, `session_log.jsonl` (2 lines), `labels_DRAFT.csv` (2 rows).
    - Session B folder: `2026-09-26_1517_1/` -> 1 WAV, `session_log.jsonl` (1 line), `labels_DRAFT.csv` (1 row).
    - `grep -n "open(" bot/audio/capture.py` proves `session_log.jsonl` and `labels_DRAFT.csv` are opened exclusively against `target_dir` (the session folder). Zero appends to parent-level root paths.
    - Session A's `labels_DRAFT.csv` was verified after Session B completed: it remained strictly 2 rows, completely uncorrupted.

### CLAIM 3 — "Migration split the old stacked files correctly"
- **Verdict:** **VERIFIED**
- **Evidence:**
  - Unit test `tests/test_migrate_recordings.py` proves:
    1. Loose WAV files separated by >10-minute gap split into distinct session folders.
    2. Existing human annotations in root `labels_DRAFT.csv` (`correct_text`, `topic`, `is_claim`, `anger`, `loud`) survive byte-identical into the migrated session's CSV.
    3. Unattributed files (`unattributed_notes.txt`) remain untouched in root (`DELETE NOTHING` rule).
  - Inspection of `recordings/` on disk:
    - `recordings/test_session/`: Contained 0 loose WAVs and 0 logs prior to migration. Only an empty `labels_DRAFT.csv` (created during unit testing) was present.
    - `recordings/2026-09-22/`: Contains 28 historic `.json`/`.txt` files from commit `28db81a`, 0 WAVs.
    - Migration executed against `recordings/test_session/` safely returned `status: no_stacked_clips`, preserving the existing draft file without deletion or distortion.

### CLAIM 4 — "Docs & privacy synced"
- **Verdict:** **VERIFIED**
- **Evidence:**
  - Rendered `!privacy` command text was verified via `tests/test_p1_privacy.py` (3/3 passed). Text explicitly states in-memory processing by default, admin-only capture toggle, and isolated session storage (`recordings/test_session/<timestamp>/`).
  - `.env.example` bidirectional reconciliation:
    - Total keys in `.env.example`: 34.
    - Keys in `.env.example` not found in code: **0**.
    - Keys in code but missing from `.env.example`: 12 (7 internal constants/FastAPI metadata like `PROJECT_NAME`, `ROOT_ENV`, `VERSION`, `EMBED_COLOR_DISPUTE`, `EMBED_COLOR_ECHO`; 5 legacy pre-refactor fallback keys `GEMINI_API_KEY`, `OPENAI_API_KEY`, `PRIMARY_STT_PROVIDER`, `TTS_PROVIDER`, `TTS_VOICE_EN`).
  - `!help` text in `bot/main.py:474-476` accurately documents:
    - `!start-capture`: Enables test-mode audio capture into a new isolated folder `recordings/test_session/<YYYY-MM-DD_HHMM>/`.
    - `!stop-capture`: Stops capture, finalizes session, and generates `labels_DRAFT.csv` in the session folder.

### CLAIM 5 — "Non-blocking capture preserved"
- **Verdict:** **VERIFIED**
- **Evidence:**
  - `git diff 2bf3fb8 -- tests/test_barge_in.py` produces 0 diff (unmodified).
  - `tests/test_barge_in.py` passes 4/4 tests in 0.088s (sub-100ms TTFB, immediate barge-in truncation, clean FFmpeg kill).
  - Trace of disk I/O in `bot/audio/capture.py:146-171`: `save_captured_utterance_async` delegates all filesystem writes to a worker thread pool via `await asyncio.to_thread(save_captured_utterance_sync, ...)`.
  - In `bot/main.py:690`: `stop_capture_session` is also wrapped in `await asyncio.to_thread(stop_capture_session)`.
  - The Discord bot event loop and voice receiving threads are never blocked by disk I/O.

### CLAIM 6 — "Suite green, ledger updated, tree clean"
- **Verdict:** **VIOLATION (REG-01)**
- **Evidence:**
  - Full test suite: 104/104 tests pass in 97.780s (`backend\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`).
  - Working tree: `git status` reports clean working tree.
  - **Ledger Inconsistency (REG-01):**
    - Git log history:
      - `dac9b02`: `feat(audio): implement session-isolated capture with per-session folders (Phase 1)`
      - `ca7fa7e`: `feat(audio): add recordings migration utility with label preservation (Phase 2)`
      - `2b5df7f`: `docs: sync .env.example and !help with session-isolated capture (Phase 3)`
    - However, `REGRESSION_LEDGER.md` lines 56-58 read:
      ```markdown
      | 2026-09-26 | `44f5d52` | Complete repo-wide branding sweep to CallWrapped and synchronize `.env.example` with active configuration (Phase 3 / BRD-01 + CFG-01) | `git grep -in "voice arbitrator"` -> 0 hits, full suite 100/100 OK |
      | 2026-09-26 | `ca7fa7e` | Safe recordings migration clustering stacked clips by >10-minute gap, preserving human labels (Phase 2) | `tests/test_migrate_recordings.py`, full suite 104/104 OK |
      | 2026-09-26 | `f8a5cdc` | Document TEST_CAPTURE_MODE in .env.example, update !help with per-session folders, verify !privacy (Phase 3) | `tests/test_p1_privacy.py`, full suite 104/104 OK |
      ```
    - **Deficiencies:**
      1. Commit `dac9b02` (Phase 1) is completely missing from the ledger table.
      2. Previous session commit `2bf3fb8` was overwritten.
      3. Commit hash `f8a5cdc` was amended to `2b5df7f`, but the ledger retains the dead hash `f8a5cdc`.

---

## Adversarial Sweeps (A–F)

| Sweep | Target Area | Status | Finding / Analysis |
|---|---|---|---|
| **A** | Filename Collision | **CLEAN** | `capture.py:118-122` executes a collision loop: if `wav_path.exists()`, it increments `counter` and formats `{int(ts)}_{speaker}_{counter}.wav`. Tested with two clips sharing the identical timestamp `1700000000.0` and speaker: both clips were saved distinctly (`1700000000_Ahmed.wav` and `1700000000_Ahmed_1.wav`) with intact byte payloads. |
| **B** | Force-Split Handling | **CLEAN** | `receiver.py:113` checks `now - buf.speech_start_time >= config.MAX_SPEECH_DURATION_SEC` (15.0s) and invokes `self._finalize_utterance(buf, ended_by="forcesplit")`. The utterance is converted to WAV, transcribed, and routed to `save_captured_utterance_async`, yielding a complete WAV, valid JSONL entry, and row in `labels_DRAFT.csv`. |
| **C** | `ended_by` Field Recording | **CLEAN** | The `ended_by` tag is passed from `receiver.py:142` to `main.py:129` to `capture.py:134`. Verified that `session_log.jsonl` correctly records `"ended_by": "silence"` and `"ended_by": "forcesplit"`. |
| **D** | Empty Session (`!stop-capture` with 0 clips) | **CLEAN** | Executed `stop_capture_session()` on an empty session folder: produces a valid `labels_DRAFT.csv` with standard header and 0 data rows. No crashes, no unhandled exceptions. |
| **E** | Unicode / Arabic Integrity | **CLEAN** | Tested Arabic speaker name `مصطفى_عبدالله` and transcript `الأهلي كسب 2-0 في نهائي أفريقيا`. Files are written with `utf-8` (JSONL) and `utf-8-sig` (CSV with UTF-8 BOM). Verified that Microsoft Excel on Windows reads the CSV without mojibake, and JSON parsing retains raw Arabic text byte-identical. *(Note: Windows console printing requires UTF-8 wrapper in standalone scripts)*. |
| **F** | Disk Full / Permission Degradation | **FINDING (CAP-01)** | `save_captured_utterance_sync` (`capture.py:111-140`) does not wrap `target_dir.mkdir()` or `open()` in a `try...except OSError` block. If disk is full or read-only, the fire-and-forget task in `main.py:123` raises an unhandled asyncio task exception rather than an intentional warning log (`logger.error(...)`). Main bot operation does not crash, but error reporting is unhandled. |

---

## Severity-Tagged Findings List

### [MEDIUM] CAP-02: `!leave` Does Not Finalize Active Capture Sessions
- **File:** [`bot/main.py:976-990`](file:///G:/CallWrapper/bot/main.py#L976-L990)
- **Description:** When an administrator runs `!leave`, the bot disconnects from voice and resets arbitration state (`session.reset()`). However, if capture mode was activated via `!start-capture`, `stop_capture_session()` is not invoked.
- **Consequence:** `_active_session_dir` remains set in memory and `config.TEST_CAPTURE_MODE` remains `1`. If the bot joins another voice channel without `!start-capture`, subsequent audio continues writing into the previous session folder. Additionally, `labels_DRAFT.csv` is not generated until someone explicitly types `!stop-capture`.
- **Recommendation:** In `leave_channel()`, check `if config.TEST_CAPTURE_MODE:` and invoke `await asyncio.to_thread(stop_capture_session)`.

### [MEDIUM] SCR-01: No Scoring Pipeline for `labels_DRAFT.csv`
- **File:** [`audit/run_hearing_test.py:25`](file:///G:/CallWrapper/audit/run_hearing_test.py#L25), [`audit/check_numbers.py:44`](file:///G:/CallWrapper/audit/check_numbers.py#L44)
- **Description:** Existing evaluation scripts in `audit/` are hardcoded to the MGB-3 dataset schema (`audit/mgb3_clips/labels.csv`: columns `id`, `genre`, `duration_s`, `transcript`).
- **Consequence:** When the owner annotates `recordings/test_session/<session>/labels_DRAFT.csv` (columns `clip_id`, `wav_filename`, `speaker`, `asr_text`, `correct_text`, `topic`, `is_claim`, `anger`, `loud`), there is no existing audit script capable of scoring WER or claim accuracy against these labeled sessions without manual file restructuring.
- **Recommendation:** Create `audit/score_test_session.py` accepting `--session-dir` to score labeled draft CSVs.

### [LOW] REG-01: `REGRESSION_LEDGER.md` Synchronization Desync
- **File:** [`REGRESSION_LEDGER.md:56-58`](file:///G:/CallWrapper/REGRESSION_LEDGER.md#L56-L58)
- **Description:** During commit amendments in the last session, commit `dac9b02` (Phase 1) was overwritten, commit `2bf3fb8` was lost, and dead hash `f8a5cdc` was recorded instead of `2b5df7f`.
- **Recommendation:** Restore rows for `2bf3fb8` and `dac9b02`, and update Phase 3 hash to `2b5df7f`.

### [LOW] CAP-01: Uncaught `OSError` in Capture Save Routine
- **File:** [`bot/audio/capture.py:111-140`](file:///G:/CallWrapper/bot/audio/capture.py#L111-L140)
- **Description:** File writes lack explicit `try...except OSError` handling, resulting in asyncio unhandled task warnings under disk-full or permission-denied conditions.

---

## Final Honest Verdict: "If the owner labels these folders and we score them, what will go wrong?"

1. **Annotation Safety:** **Nothing will be lost.** The files generated in `recordings/test_session/<YYYY-MM-DD_HHMM>/` (`labels_DRAFT.csv`, `session_log.jsonl`, and WAVs) are byte-safe, UTF-8-BOM encoded for Excel, and isolated per session. Re-running `!stop-capture` preserves human annotations (`correct_text`, `topic`, `is_claim`, `anger`, `loud`).
2. **Session Ending Risk:** If the owner ends a call using `!leave` and forgets to type `!stop-capture`, the CSV is not generated until `!stop-capture` is executed, and subsequent calls could leak into the same folder until bot restart.
3. **Scoring Barrier:** The owner cannot simply run `python audit/run_hearing_test.py` to evaluate their annotations, because `run_hearing_test.py` expects the MGB-3 dataset structure (`audit/mgb3_clips/labels.csv`), not `labels_DRAFT.csv`. A dedicated scoring adapter is needed to calculate WER and metrics from labeled test-session folders.
