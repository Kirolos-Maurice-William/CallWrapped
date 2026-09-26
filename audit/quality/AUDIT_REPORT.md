# CallWrapped Code Quality & Architecture Audit Report

**Audit Date:** September 25, 2026  
**Repository:** `CallWrapper`  
**Git HEAD:** `dd42bfe`  
**Audit Scope:** Read-Only Full Codebase Analysis (`bot/`, `backend/`, `frontend/components`, `frontend/app`, `tests/`)  
**Output Target:** `audit/quality/AUDIT_REPORT.md`  

---

## 1. Executive Summary

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Total Lines of Code (LOC)** | **14,148 LOC** across 79 source files | `bot/`: 5,556 LOC (25 files) \| `backend/`: 945 LOC (7 files) \| `frontend/`: 1,476 LOC (5 files) \| `tests/`: 6,171 LOC (42 files) |
| **Active Test Suite** | **95 tests passing (100% OK)** | Execution time: **98.13s** (0 failures, 0 errors, 0 skipped, 0 xfail) |
| **Test Assertion Count** | **556 assertions** | 0 vacuous assertions (`assert True` / trivial mock identity) |
| **Git Activity (since `701a7c0`)** | **58 commits** | Bot: 26 commits, Backend: 14 commits, Tests: 12 commits, Root/Audit: 6 commits |
| **Cleanliness Score** | **70 / 100** | See detailed rubric breakdown below |

### Top 5 Codebase Risks
1. **Critical Security / CORS Wildcard:** [`backend/app/main.py:48`](file:///g:/CallWrapper/backend/app/main.py#L48) hardcodes `allow_origins=["*"]`, completely ignoring the `.env` `CORS_ORIGINS` setting (`http://localhost:3000`) and exposing live call telemetry, transcript streaming, and reset endpoints to any web origin.
2. **Event Loop Freeze Risk (Synchronous Sleep):** [`bot/ai/groq.py:337, 344`](file:///g:/CallWrapper/bot/ai/groq.py#L337-L344) calls blocking `time.sleep(sleep_wait)` and `time.sleep(wait_sec)` in `complete_chat_sync()`. If triggered during rate-limiting, this blocks the execution thread for up to 60 seconds, freezing Discord gateway heartbeats and voice streams.
3. **Two-Stage Referee Invariant Violation (Auto-Speak Remnants):** [`bot/main.py:766`](file:///g:/CallWrapper/bot/main.py#L766) (`!arbitrate`) and [`bot/main.py:863`](file:///g:/CallWrapper/bot/main.py#L863) (`!simulate`) call `speaker.speak()` uninvited and consume deprecated `correct_fact` schema fields, violating the fundamental project policy that the bot *"never speaks uninvited (offers only)"*.
4. **Test Suite Flakiness via Live API Dependency:** Tests (`test_classifier.py`, `test_groq_rotation.py`, `test_phase_b_referee_gates.py`, `test_judge_mode.py`) make direct HTTP calls to real Groq LPU, Tavily, and AssemblyAI endpoints. Live token quotas (6,000 TPM) hit 429 rate-limits during test execution, causing 60-second backoffs and potential build timeouts.
5. **Branding Inconsistency & Deprecated Schemas:** 49 occurrences of "Voice Arbitrator" remain across production embeds, loggers, backend service names, and Next.js UI titles after the rebranding to "CallWrapped", alongside dead `correct_fact` references in `bot/main.py:722` and `backend/app/routes.py:221`.

---

## 2. Prioritized Findings Table

| # | Severity | Category | File:Line | Finding | Evidence | Suggested Fix |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `MUST-FIX-BEFORE-SUBMISSION` | Security | [`backend/app/main.py:48`](file:///g:/CallWrapper/backend/app/main.py#L48) | CORS middleware hardcoded to `*`, ignoring `.env` `CORS_ORIGINS` | `allow_origins=["*"]` hardcoded while `settings.CORS_ORIGINS` is configured | Set `allow_origins=settings.CORS_ORIGINS` in `CORSMiddleware` |
| **2** | `MUST-FIX-BEFORE-SUBMISSION` | Correctness | [`bot/main.py:766, 863`](file:///g:/CallWrapper/bot/main.py#L766) | `!arbitrate` and `!simulate` bypass two-stage referee gate and speak uninvited | Direct calls to `speaker.speak(voice_client, spoken_text)` without dispute offer/confirm | Route `!arbitrate` through standard `dispute_check_offered` flow or gate with confirmation |
| **3** | `MUST-FIX-BEFORE-SUBMISSION` | Correctness | [`bot/ai/groq.py:337, 344`](file:///g:/CallWrapper/bot/ai/groq.py#L337-L344) | Blocking `time.sleep` in Groq sync client rate-limit retry | `time.sleep(sleep_wait)` and `time.sleep(wait_sec)` on 429 response | Cap wait time or raise exception instead of blocking synchronous thread |
| **4** | `MUST-FIX-BEFORE-SUBMISSION` | Dead Code | [`bot/main.py:722, 837`](file:///g:/CallWrapper/bot/main.py#L722) | Stale verifier fields `correct_fact` and `spoken_intervention` used in fallback | `correct_fact = verdict.get("correct_fact", query)` instead of `fact_clause` | Update call sites to consume `fact_clause` and `hedge_clause` |
| **5** | `SHOULD-FIX` | Test Isolation | [`tests/test_classifier.py:55`](file:///g:/CallWrapper/tests/test_classifier.py#L55) | Tests hit live third-party Groq API without mock fallback | Live POST requests to `https://api.groq.com/openai/v1/chat/completions` during pytest/unittest | Use `unittest.mock` or recorded VCR cassettes for unit test execution |
| **6** | `SHOULD-FIX` | Dead Dependencies | [`backend/requirements.txt:1-5`](file:///g:/CallWrapper/backend/requirements.txt#L1-L5) | Unused packages declared in `requirements.txt` | `assemblyai`, `openai`, `duckduckgo-search` have 0 imports in codebase | Remove unused dependencies from `requirements.txt` |
| **7** | `SHOULD-FIX` | Architecture | [`bot/arbitration/engine.py:1-1058`](file:///g:/CallWrapper/bot/arbitration/engine.py#L1-L1058) | Monolithic `engine.py` violates Single Responsibility Principle | 1,057 lines managing session state, VAD queues, TTS playback, analytics, and embeds | Decompose into `SessionManager`, `ArbitrationCoordinator`, and `PlaybackDispatcher` |
| **8** | `SHOULD-FIX` | Configuration | [`.env:1-38`](file:///g:/CallWrapper/.env#L1-L38) | 11 configuration keys defined in `.env` are never read by application code | `PRIMARY_STT_PROVIDER`, `GEMINI_API_KEY`, `TTS_PROVIDER`, `TTS_VOICE_EN`, etc. | Prune `.env` and `.env.example` of orphaned keys |
| **9** | `SHOULD-FIX` | Branding | [`bot/main.py:66`](file:///g:/CallWrapper/bot/main.py#L66), [`frontend/app/page.tsx:80`](file:///g:/CallWrapper/frontend/app/page.tsx#L80) | 49 lingering instances of legacy "Voice Arbitrator" branding | `logger = logging.getLogger("VoiceArbitratorBot")`, `export default function VoiceArbitratorDashboard()` | Standardize branding across embeds, titles, and loggers to "CallWrapped" |
| **10** | `SHOULD-FIX` | Correctness | [`bot/ai/tavily.py:142`](file:///g:/CallWrapper/bot/ai/tavily.py#L142), [`bot/ai/tts.py:176`](file:///g:/CallWrapper/bot/ai/tts.py#L176) | 28 bare/silent exception swallows across critical modules | `except Exception: pass` drops network exceptions silently | Log errors at `logger.warning` with error details |
| **11** | `COSMETIC` | Dead Code | [`bot/ai/tts.py:8`](file:///g:/CallWrapper/bot/ai/tts.py#L8), [`bot/ai/tts.py:335`](file:///g:/CallWrapper/bot/ai/tts.py#L335) | Unused import `inspect` and dead condition `if False:` in TTS generator | Vulture 100% confidence: `if False: yield {}` | Remove unused import and simplify empty generator to `return iter([])` |
| **12** | `COSMETIC` | Code Hygiene | [`bot/main.py:977-984`](file:///g:/CallWrapper/bot/main.py#L977-L984) | 20 raw `print()` statements in production code | `print(f" Voice Arbitrator Bot is ONLINE!")` in `on_ready` | Replace `print()` with structured `logger.info()` |
| **13** | `COSMETIC` | Hardcoded Values | [`backend/app/config.py:46-47`](file:///g:/CallWrapper/backend/app/config.py#L46-L47) | Hardcoded Discord Client ID and Permission bits in backend config | `DISCORD_CLIENT_ID = "1550926707517558864"`, `DISCORD_INVITE_PERMISSIONS = "36718592"` | Ensure `.env.example` documents these fallback defaults |
| **14** | `COSMETIC` | UI Hardcoded Model | [`frontend/app/page.tsx:120`](file:///g:/CallWrapper/frontend/app/page.tsx#L120) | Hardcoded fallback model string in frontend dashboard | `if (!modelId) return "Universal-3.6 Pro";` | Dynamically display model ID reported from backend `/api/live` |
| **15** | `IGNORE` | Dead Code | [`backend/app/schemas.py:46-149`](file:///g:/CallWrapper/backend/app/schemas.py#L46-L149) | Vulture reports unused attributes on Pydantic models | Attributes like `heat_score`, `is_disagreement`, `duration_ms` flagged | False positive: Pydantic model fields are serialized via FastAPI |

---

## 3. Section-by-Section Breakdown

### Phase 0 — Inventory & File Tree Analysis
- **Total Codebase:** 14,148 LOC across 79 tracked files.
- **Distribution:**
  - `bot/`: 25 files, 5,556 LOC
  - `backend/`: 7 files, 945 LOC
  - `frontend/components + app`: 5 files, 1,476 LOC
  - `tests/`: 42 files, 6,171 LOC
- **Top 5 Largest Files:**
  1. [`bot/arbitration/engine.py`](file:///g:/CallWrapper/bot/arbitration/engine.py) (1,057 lines) — Monolithic orchestrator.
  2. [`bot/main.py`](file:///g:/CallWrapper/bot/main.py) (995 lines) — Discord commands, event routing, demo simulation.
  3. [`frontend/app/page.tsx`](file:///g:/CallWrapper/frontend/app/page.tsx) (892 lines) — Real-time analytics and dispute dashboard.
  4. [`tests/test_two_stage_referee.py`](file:///g:/CallWrapper/tests/test_two_stage_referee.py) (577 lines) — End-to-end referee integration tests.
  5. [`bot/ai/tts.py`](file:///g:/CallWrapper/bot/ai/tts.py) (519 lines) — Streaming TTS, pre-warm handshake, FFmpeg process manager.
- **Git Activity:** 58 commits since baseline `701a7c0`. High commit velocity in arbitration engine, two-clause TTS delivery, and STT dialect experiments.

---

### Phase 1 — Dead Code & Stale References

#### a) Config Truth Check
Comparison of `.env` definitions against codebase references:
- **11 Unused Keys in `.env`:**
  - `BOT_OWNER_IDS`: Defined in `.env`, never read anywhere in `bot/` or `backend/`.
  - `CORS_ORIGINS`: Loaded in `backend/app/config.py`, but ignored by `backend/app/main.py` which hardcodes `["*"]`.
  - `EMBED_COLOR_DISPUTE`, `EMBED_COLOR_ECHO`: Configured in `bot/config.py`, never applied to any embed.
  - `GEMINI_API_KEY`: Defined in `.env`, zero active Gemini clients exist (system standardized on Groq LPU).
  - `HOST`, `PORT`: Defined in `.env`, `backend/app/config.py` defaults to `0.0.0.0` / `8000`.
  - `PRIMARY_STT_PROVIDER`: Hardcoded to AssemblyAI REST client in `bot/ai/assemblyai.py`.
  - `TTS_PROVIDER`: Hardcoded to `edge-tts` in `bot/ai/tts.py`.
  - `TTS_VOICE_AR`: Hardcoded to `ar-EG-SalmaNeural` in `bot/ai/tts.py`.
  - `TTS_VOICE_EN`: Hardcoded in `bot/ai/tts.py`.
- **Reverse Check (Keys referenced in code but missing from `.env`):**
  - `DISCORD_CLIENT_ID` (defaults to hardcoded ID `"1550926707517558864"` in `backend/app/config.py:46`).
  - `DISCORD_INVITE_PERMISSIONS` (defaults to `"36718592"` in `backend/app/config.py:47`).
  - `DISPUTE_OFFER_COOLDOWN_SEC` (read in `bot/config.py:39`, missing from `.env`).
  - `DISPUTE_OFFER_EXPIRY_SEC` (read in `bot/config.py:40`, missing from `.env`).
  - `SPEECH_MODEL_NAME` (read in `bot/config.py:29`, missing from `.env`).
  - `TEST_CAPTURE_MODE` (read in `bot/config.py:53`, missing from `.env`).

#### b) Two-Stage Refactor Remnants & Legacy Paths
- [`bot/main.py:722, 723`](file:///g:/CallWrapper/bot/main.py#L722-L723):
  ```python
  correct_fact = verdict.get("correct_fact", query)
  spoken_text = verdict.get("spoken_intervention", correct_fact)
  ```
  The `manual_arbitrate` and `simulate_demo` routines extract legacy single-stage keys (`correct_fact`, `spoken_intervention`) rather than modern two-stage streaming keys (`fact_clause`, `hedge_clause`).
- [`bot/arbitration/engine.py:879`](file:///g:/CallWrapper/bot/arbitration/engine.py#L879):
  ```python
  correct_fact = assessment.get("correct_fact", "")
  ```
  `correct_fact` is extracted from the verifier payload but never referenced again; line 903 correctly uses `fact_clause = assessment.get("fact_clause") or spoken_text`.

#### c) Vulture AST Dead Code Scan
Running Vulture with `--min-confidence 80`:
- [`bot/ai/tts.py:8`](file:///g:/CallWrapper/bot/ai/tts.py#L8): `unused import 'inspect' (90% confidence)`
- [`bot/ai/tts.py:335`](file:///g:/CallWrapper/bot/ai/tts.py#L335): `unsatisfiable 'if' condition (100% confidence)`:
  ```python
  async def _empty():
      if False:
          yield {}
  return _empty()
  ```
- [`bot/main.py:587`](file:///g:/CallWrapper/bot/main.py#L587): `unused variable 'is_on' (100% confidence)` in `build_fact_check_mode_embed(is_on: bool = True)`.
- [`bot/arbitration/engine.py:283`](file:///g:/CallWrapper/bot/arbitration/engine.py#L283): `unused method 'flush_analytics_sync' (60% confidence)` — Dead synchronous buffer flushing path.
- [`bot/arbitration/stats.py:189`](file:///g:/CallWrapper/bot/arbitration/stats.py#L189): `unused method 'record_classification' (60% confidence)` — Defective dead wrapper passing a dictionary to a string parameter.

#### d) Dead Dependencies
Scanning `backend/requirements.txt`:
- `assemblyai`: 0 imports across the codebase (`bot/ai/assemblyai.py` directly executes async HTTP requests with `httpx`).
- `openai`: 0 imports across the codebase (Gemini and OpenAI SDKs are absent; Groq uses direct HTTP client).
- `duckduckgo-search`: 0 imports across the codebase (Tavily REST API is the sole search provider).

#### e) Scratch Files & Leftovers
- `run_cloud.py`: Scratch script in repo root from early development.
- `tests/smoke_real_voice.py`, `tests/verify_apis.py`: Standalone CLI testing scripts living inside `tests/` without `test_` prefix (not discovered by unittest).
- `audit/`: Contains 22 scratch benchmark scripts, JSON events, and CSV ablation logs from past experiments.

---

### Phase 2 — Ghost Strings & Consistency

#### a) Model Name Grep
- Hardcoded fallback in frontend: [`frontend/app/page.tsx:120`](file:///g:/CallWrapper/frontend/app/page.tsx#L120):
  ```typescript
  if (!modelId) return "Universal-3.6 Pro";
  ```
- Dead Gemini config: [`backend/app/config.py:26`](file:///g:/CallWrapper/backend/app/config.py#L26):
  ```python
  GEMINI_API_KEY: str = ""
  ```
- All backend and bot Groq LLM calls correctly read configured model parameters (`config.LLM_MODEL`, `config.GROQ_BATCH_MODEL`, `llama-3.3-70b-versatile`).

#### b) Branding Sweep ("Voice Arbitrator" vs "CallWrapped")
49 lingering references to the legacy project name "Voice Arbitrator" were identified:
- [`bot/main.py:66`](file:///g:/CallWrapper/bot/main.py#L66): `logger = logging.getLogger("VoiceArbitratorBot")`
- [`bot/__init__.py:2`](file:///g:/CallWrapper/bot/__init__.py#L2): `AI Third Participant - Discord Voice Arbitrator`
- [`backend/app/main.py:23`](file:///g:/CallWrapper/backend/app/main.py#L23): `logger = logging.getLogger("voice_arbitrator")`
- [`backend/app/main.py:36`](file:///g:/CallWrapper/backend/app/main.py#L36): `title="Voice Arbitrator API"`
- [`backend/app/main.py:58`](file:///g:/CallWrapper/backend/app/main.py#L58): `"service": "Voice Arbitrator"`
- [`backend/app/routes.py:17, 29`](file:///g:/CallWrapper/backend/app/routes.py#L17): `# Live Analytics State for Voice Arbitrator`
- [`frontend/app/page.tsx:80`](file:///g:/CallWrapper/frontend/app/page.tsx#L80): `export default function VoiceArbitratorDashboard()`
- [`frontend/app/page.tsx:412`](file:///g:/CallWrapper/frontend/app/page.tsx#L412): Header text: `VOICE ARBITRATOR`
- [`frontend/app/page.tsx:439`](file:///g:/CallWrapper/frontend/app/page.tsx#L439): Button title: `title="Invite Voice Arbitrator Bot to your Discord Server"`
- Embed footers in [`bot/main.py:412, 479, 759`](file:///g:/CallWrapper/bot/main.py#L412): `embed.set_footer(text="AssemblyAI Hackathon • Real-Time Voice Arbitrator")`

#### c) TODO / FIXME / HACK Sweep
- 0 instances of `TODO`, `FIXME`, `XXX`, or `HACK` in active production code files.

#### d) Debug Prints
20 raw `print()` statements exist in production code rather than structured logging:
- [`bot/main.py:977-984`](file:///g:/CallWrapper/bot/main.py#L977-L984): 8 raw `print()` statements in `on_ready` logging bot startup banners.
- [`bot/arbitration/judge_mode.py:318-351`](file:///g:/CallWrapper/bot/arbitration/judge_mode.py#L318-L351): 12 raw `print()` statements in the Judge Mode CLI harness.

#### e) Hardcoded Values & Magic Numbers
- [`backend/app/config.py:46`](file:///g:/CallWrapper/backend/app/config.py#L46):
  ```python
  DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "1550926707517558864")
  ```
- [`backend/app/config.py:47`](file:///g:/CallWrapper/backend/app/config.py#L47):
  ```python
  DISCORD_INVITE_PERMISSIONS: str = os.getenv("DISCORD_INVITE_PERMISSIONS", "36718592")
  ```

---

### Phase 3 — Correctness Patterns

#### a) Async Hygiene & Blocking Calls
- **Blocking `time.sleep` in Async Execution Context:**
  [`bot/ai/groq.py:337, 344`](file:///g:/CallWrapper/bot/ai/groq.py#L337-L344) in `complete_chat_sync()`:
  ```python
  time.sleep(sleep_wait)
  ...
  time.sleep(wait_sec)
  ```
  While labeled sync, this function is reachable from event-loop threads during buffer flushes. Line 344 has no maximum sleep bound, risking prolonged blocking.
- **`async def` Without `await`:**
  - [`bot/main.py:975`](file:///g:/CallWrapper/bot/main.py#L975): `async def on_ready` has no `await`.
  - [`backend/app/main.py:55`](file:///g:/CallWrapper/backend/app/main.py#L55): `async def health_check` has no `await`.
  - [`backend/app/routes.py:426, 432`](file:///g:/CallWrapper/backend/app/routes.py#L426): `async def get_live_state` and `async def get_analytics` perform sync dictionary lookups without `await`.

#### b) Network Call Timeout Audit
- `bot/ai/groq.py`: Both `complete_chat` and `complete_chat_sync` use explicit `timeout=15.0` on `httpx.AsyncClient` / `httpx.Client`.
- `bot/ai/tavily.py`: Line 51 uses explicit `timeout=10.0` on `httpx.AsyncClient`.
- `bot/ai/assemblyai.py`: Line 32 uses explicit `timeout=10.0` on `httpx.AsyncClient`.
- `bot/events/publisher.py`: Line 19 uses explicit `timeout=5.0` on `httpx.AsyncClient`.
- **Verdict:** All external HTTP call sites have explicit timeouts.

#### c) Silent Exception Handling
28 exception blocks silently discard errors or downgrade them to `debug`:
- [`bot/ai/tavily.py:142`](file:///g:/CallWrapper/bot/ai/tavily.py#L142): `except Exception: pass` silently suppresses Tavily search failures.
- [`bot/ai/tts.py:176, 181, 210, 225`](file:///g:/CallWrapper/bot/ai/tts.py#L176): Multiple `except Exception: pass` blocks in TTS cleanup and stream reading routines.
- [`bot/arbitration/engine.py:427, 734, 963`](file:///g:/CallWrapper/bot/arbitration/engine.py#L427): Discard Discord send message errors as `logger.debug`. If a text channel is deleted or lacks permissions, the failure is hidden from operations.

#### d) Shared Mutable State & Race Conditions
- [`bot/arbitration/engine.py:785`](file:///g:/CallWrapper/bot/arbitration/engine.py#L785):
  `session.pending_offer` is an in-memory dictionary mutated across multiple async tasks without an `asyncio.Lock()`. An incoming voice confirmation task and an offer expiration task can read and mutate `session.pending_offer` concurrently.
- [`backend/app/routes.py:18`](file:///g:/CallWrapper/backend/app/routes.py#L18):
  `LIVE_STATE` is a global in-memory dictionary modified across multiple FastAPI async route handlers without lock synchronization.

#### e) Resource Leaks & Cleanup
- [`bot/ai/tts.py:43`](file:///g:/CallWrapper/bot/ai/tts.py#L43):
  `self.process = subprocess.Popen(...)` starts FFmpeg. While `cleanup()` calls `self.process.kill()`, `__del__` does not guarantee process termination if an exception interrupts initialization.
- **Unclosed Sockets during Test Suite:**
  Test execution outputs `ResourceWarning: unclosed transport <asyncio._SSLProtocolTransport object>` and `ResourceWarning: unclosed transport <_ProactorSocketTransport>`, confirming unclosed `httpx` / `aiohttp` sessions in tests.

---

### Phase 4 — Structure & Readability

#### a) Module Responsibilities & Cohesion
- **`bot/arbitration/engine.py` (1,057 LOC) — Overloaded Responsibility:**
  `ArbitrationEngine` acts as an anti-pattern "God Object". It handles:
  1. Per-guild session state management (`SessionState`).
  2. Utterance queue draining and sequential gating (`is_arbitrating`).
  3. Fanout of batched analytics to Groq and tracking speaker statistics.
  4. Real-time dispute offer registration, timeout tracking, and voice confirmation matching.
  5. TTS playback invocation, two-clause synthesis timing, and barge-in listener coordination.
  6. Discord text embed construction and formatting.
  *Recommendation:* Split into `SessionManager`, `ArbitrationReferee`, and `VoiceSpeakerManager`.

#### b) Import Health
- **Circular Imports:** None detected.
- **Wildcard Imports (`from x import *`):** 0 instances. Clean, explicit imports used across all modules.

#### c) Duplicate Logic
- **Confirmation Keyword List:**
  The list of dispute confirmation triggers (`"شوفها"`, `"check"`, `"وريني"`, `"اتأكد"`, `"شوف"`, `"احكم"`) is duplicated in [`bot/arbitration/engine.py:688`](file:///g:/CallWrapper/bot/arbitration/engine.py#L688), [`bot/main.py:640`](file:///g:/CallWrapper/bot/main.py#L640), and [`bot/arbitration/judge_mode.py:150`](file:///g:/CallWrapper/bot/arbitration/judge_mode.py#L150). It should be defined once in `bot/config.py`.

---

### Phase 5 — Test Health

#### a) Test Assertions Honesty
- **Total Assertions:** 556 across 39 test files.
- **Vacuous Assertions:** **0**. Zero occurrences of `assert True`, `assertEqual(True, True)`, or asserting non-nullity on mocks. Assertions verify concrete state values, schema structures, latency numbers, and event payloads.

#### b) Test Duration Profile (Slowest Tests)
The full test suite executes in **98.13s**. The top 5 slowest tests are:
1. `TestJudgeMode.test_judge_mode_harness_all_cards` — **5.04s** (Executes full 7-card referee pipeline with live LLM calls).
2. `EventPublisher.publish` — **4.88s** (Live HTTP event publisher draining).
3. `TestPhaseBRefereeGates.test_all_six_referee_cases` — **4.12s** (Executes 6 live LLM referee gatekeeper evaluations).
4. `TestEveryUtteranceClassifier.test_twelve_transcripts_real_groq_api` — **2.12s** (12 sequential live Groq API completions).
5. `TestGroqRotation.test_six_rapid_real_classification_calls` — **1.73s** (Rapid live Groq calls testing key rotation).

#### c) Skipped & Xfail Tests
- **0 skipped tests, 0 xfailed tests.** All 95 tests actively execute and pass.

#### d) Test Isolation Issues
- **Live External Network Dependencies:** Multiple test suites (`test_classifier.py`, `test_groq_rotation.py`, `test_judge_mode.py`, `test_phase_b_referee_gates.py`) make unmocked HTTP requests to `api.groq.com`, `api.tavily.com`, and `api.assemblyai.com`. During execution, Groq rate-limit headers triggered:
  ```
  WARNING:GroqClient:⚠️ [GroqClient] Both keys hit 429. Waiting 2.00s reset...
  ```
- **Real Disk Artifact Generation:** [`tests/test_capture_mode.py`](file:///g:/CallWrapper/tests/test_capture_mode.py) writes real CSV files to `recordings/test_session/labels_DRAFT.csv` on the host filesystem without using a `pytest` `tmp_path` fixture.

---

### Phase 6 — Security & Privacy

#### a) Secret Leaks in Logs
- Inspection of log statements across `bot/` and `backend/` confirmed that API keys, Bearer tokens, and auth secrets are not logged in plain text.
- Token keys are masked (e.g. `logger.info(f"⚡ [GroqClient] {k['id']} completed...")` where `k['id']` is `"key#1"` or `"key#2"`).

#### b) Hardcoded Tokens & Credentials
- No hardcoded Discord bot tokens or API keys were detected in git-tracked code files. All API secrets are retrieved via `os.getenv()`.

#### c) CORS Middleware Exposure
- [`backend/app/main.py:44`](file:///g:/CallWrapper/backend/app/main.py#L44) configures:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
  This overrides the secure origin whitelist (`http://localhost:3000,http://127.0.0.1:3000`) defined in `.env` and `settings.CORS_ORIGINS`.

#### d) Audio Privacy & Ephemeral Data Handling
- In standard referee mode, raw audio PCM bytes received from Discord voice are processed in memory and immediately discarded.
- In test capture mode (`!start-capture`), audio files are saved to `recordings/<session>/`.
- **Privacy Notice Discrepancy:** The `!privacy` command embed ([`bot/main.py:590`](file:///g:/CallWrapper/bot/main.py#L590)) states *"No audio is ever recorded or saved to disk"*, which contradicts the existence of the `!start-capture` command. The privacy text should clarify: *"Audio is processed strictly in-memory unless server administrators explicitly activate benchmark capture mode."*

---

## 4. Cleanliness Score & Rubric Breakdown

```
Overall Cleanliness Score: 70 / 100
```

| Rubric Category | Max Points | Awarded | Deductions & Justification |
| :--- | :---: | :---: | :--- |
| **1. Configuration & Environment** | 15 | **8** | **-3 pts:** 11 unused `.env` variables.<br>**-2 pts:** CORS `allow_origins=["*"]` overrides `.env`.<br>**-1 pt:** Discrepancy between `.env` sync `sqlite:///` and `config.py` async `sqlite+aiosqlite:///`.<br>**-1 pt:** Missing reverse-check keys in `.env.example`. |
| **2. Dead Code & Architecture** | 20 | **12** | **-3 pts:** Monolithic `engine.py` (1,057 LOC) violates SRP.<br>**-2 pts:** 3 dead dependencies in `requirements.txt` (`assemblyai`, `openai`, `duckduckgo-search`).<br>**-2 pts:** Vulture dead code hits (`flush_analytics_sync`, `record_classification`, `if False:`).<br>**-1 pt:** 49 stale "Voice Arbitrator" branding occurrences. |
| **3. Correctness, Async & Concurrency** | 25 | **18** | **-2 pts:** Blocking `time.sleep` in `bot/ai/groq.py:337, 344`.<br>**-2 pts:** 28 silent exception blocks (`except Exception: pass`).<br>**-1 pt:** `async def` without `await` in `main.py:975` and `routes.py:426`.<br>**-1 pt:** Unsynchronized mutable state (`session.pending_offer`, `LIVE_STATE`).<br>**-1 pt:** Unclosed transport resource warnings. |
| **4. Test Health & Coverage Honesty** | 20 | **17** | **+0 pts:** 95/95 passing tests, 556 real assertions, 0 vacuous asserts.<br>**-2 pts:** Tests hit live cloud APIs, causing 429 rate limit delays.<br>**-1 pt:** Tests write directly to disk (`recordings/test_session/labels_DRAFT.csv`). |
| **5. Security, Privacy & Compliance** | 20 | **15** | **-3 pts:** Wildcard `allow_origins=["*"]` on live dashboard endpoints.<br>**-1 pt:** Hardcoded Discord Client ID and Permission integers.<br>**-1 pt:** Contradiction between `!privacy` policy text and `!start-capture` disk recording. |
| **TOTAL** | **100** | **70** | **Grade: C+ (Functional, solid core logic, needs architectural cleanup)** |

---

## 5. Module-by-Module Responsibility Summary

| Module | LOC | Primary Responsibility | Architectural Assessment |
| :--- | :---: | :--- | :--- |
| [`bot/main.py`](file:///g:/CallWrapper/bot/main.py) | 995 | Discord bot lifecycle, CLI command dispatching (`!mode`, `!check`, `!stats`, `!recap`), event listeners (`on_ready`, `on_voice_state_update`). | **Overloaded:** Contains demo simulation routines, manual arbitration logic, and raw `print()` statements that should be split into service modules. |
| [`bot/config.py`](file:///g:/CallWrapper/bot/config.py) | 120 | Environment configuration loading and application-wide constants. | **Needs Pruning:** Contains stale STT/TTS constants that are no longer used by active providers. |
| [`bot/ai/assemblyai.py`](file:///g:/CallWrapper/bot/ai/assemblyai.py) | 158 | Direct REST client for AssemblyAI speech-to-text with keyterm prompting and trailing silence trim. | **Clean:** Lightweight, focused HTTP client. Correctly avoids unnecessary SDK overhead. |
| [`bot/ai/groq.py`](file:///g:/CallWrapper/bot/ai/groq.py) | 400 | Multi-key Groq LPU client with automatic key rotation, rate-limit header parsing, and backoff. | **Needs Attention:** Contains blocking `time.sleep` in `complete_chat_sync()`. |
| [`bot/ai/tavily.py`](file:///g:/CallWrapper/bot/ai/tavily.py) | 149 | Web search evidence retriever for factual claim verification. | **Good:** Solid prompt and search ranking, but swallows exceptions silently on line 142. |
| [`bot/ai/tts.py`](file:///g:/CallWrapper/bot/ai/tts.py) | 520 | Two-clause streaming TTS voice generator with DNS/TLS pre-warming and barge-in interruption. | **Complex:** High performance with sub-200ms TTFB, but contains Vulture-flagged dead dummy generator (`if False: yield {}`). |
| [`bot/arbitration/engine.py`](file:///g:/CallWrapper/bot/arbitration/engine.py) | 1,057 | Orchestrator for session state, claim gating, batched analytics, dispute verification, and voice playback. | **Critical Refactor Candidate:** Monolithic God object violating SRP. Merits division into smaller subcomponents. |
| [`bot/arbitration/claim_detector.py`](file:///g:/CallWrapper/bot/arbitration/claim_detector.py) | 313 | Two-tier claim gate: instant regex/heuristic claim extraction and batched analytics classification. | **Clean & Fast:** Highly effective separation of instant reflex gating vs batched analytics. |
| [`bot/arbitration/conflict_detector.py`](file:///g:/CallWrapper/bot/arbitration/conflict_detector.py) | 260 | Public dispute referee: determines if two assertions form a public disagreement and filters private claims. | **Clean:** Solid epistemic prompt engineering and topic whitelisting. |
| [`bot/arbitration/verifier.py`](file:///g:/CallWrapper/bot/arbitration/verifier.py) | 222 | Synthesizes search evidence into structured two-clause spoken verdicts (`fact_clause` + `hedge_clause`). | **Clean:** Robust Arabic hedging templates and citation extraction. |
| [`bot/arbitration/stats.py`](file:///g:/CallWrapper/bot/arbitration/stats.py) | 208 | Participant analytics tracking (speak time, longest streak, topic breakdown, anger episodes). | **Good:** Contains one dead method (`record_classification`). |
| [`bot/arbitration/judge_mode.py`](file:///g:/CallWrapper/bot/arbitration/judge_mode.py) | 360 | 7-card adversarial test harness validating referee gates without live audio. | **High Value:** Excellent testing utility, but uses raw `print()` statements. |
| [`bot/audio/receiver.py`](file:///g:/CallWrapper/bot/audio/receiver.py) | 185 | Discord Opus voice packet receiver, PCM buffer, energy-based VAD segmentation, and speech chunk emitter. | **Clean:** Low-latency VAD chunking and clean audio dispatching. |
| [`bot/events/publisher.py`](file:///g:/CallWrapper/bot/events/publisher.py) | 48 | Asynchronous HTTP telemetry event publisher transmitting live events to backend. | **Clean & Non-blocking:** Dispatches background tasks cleanly. |
| [`backend/app/main.py`](file:///g:/CallWrapper/backend/app/main.py) | 65 | FastAPI server entry point, CORS middleware, and WebSocket broadcast manager. | **Security Risk:** Hardcodes `allow_origins=["*"]`. |
| [`backend/app/routes.py`](file:///g:/CallWrapper/backend/app/routes.py) | 455 | REST API and WebSocket controllers managing live session state, events, and database queries. | **Good:** Comprehensive state machine, though relies on un-locked global `LIVE_STATE`. |
| [`frontend/app/page.tsx`](file:///g:/CallWrapper/frontend/app/page.tsx) | 892 | Next.js 14 real-time call dashboard displaying speaking streaks, topics, anger receipts, and dispute cards. | **Functional:** Rich UI, but contains hardcoded fallback model strings and legacy branding. |
