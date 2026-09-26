# SELF-SUPERVISION TRACEBACK REPORT
**Date:** 2026-09-26  
**Auditor Mode:** Hostile Adversarial Reviewer  
**Scope:** Verification of Post-Audit Cleanup Claims (Phases 0–5, Claims 1–8) & Repository-Wide Invariants  
**Target Commit:** `e6609fc` (`docs: update REGRESSION_LEDGER.md with Phase 5`)

---

## EXECUTIVE SUMMARY & HOSTILE VERDICT

The previous cleanup session claimed a comprehensive remediation of dead code, strict CORS locking, uncompromised referee invariants, bounded rate-limit sleep times, complete rebranding to CallWrapped, clean dependencies, updated privacy notices, and a clean working tree with 96/96 passing tests.

**Hostile Judge Verdict:**
> **"The codebase passed 96 unit/integration tests and achieved significant dead code removal, but the cleanup's security and branding claims are incomplete: WebSockets remain completely unauthenticated and bypass CORS origin checks, manual arbitration commands bypass the 180s cooldown invariant, seven user-facing scripts/docs still display legacy 'Voice Arbitrator' branding, and the working tree was left with 12 untracked audit artifacts."**

| Claim / Area | Claimed State | Actual Ground Truth | Status |
| :--- | :--- | :--- | :--- |
| **Claim 1: CORS Lockdown** | `allow_origins=["*"]` replaced with `settings.CORS_ORIGINS` | HTTP endpoints guarded; WebSocket `/api/ws` accepts connections unconditionally with **zero** origin validation. | **PARTIAL / FINDING** |
| **Claim 2: Referee Invariant** | `speaker.speak` eradicated, `!arbitrate` creates pending offer | `speaker.speak` 0 calls; but `!arbitrate` completely bypasses the 180s cooldown throttle. | **PARTIAL / FINDING** |
| **Claim 3: Sync Sleep Bounded** | Sync sleeps capped at 2.0s maximum | Sync & async sleep sites in `bot/ai/groq.py` abort immediately if wait exceeds 2.0s. | **VERIFIED** |
| **Claim 4: Branding Sweep** | "Voice Arbitrator" & "universal-3.6" removed | Eradicated from `bot/`, `backend/`, and `frontend/`, but 19 legacy references remain in launchers, README, and `.env.example`. | **PARTIAL / FINDING** |
| **Claim 5: Dead Code Removal** | Stale functions, dead yields, dead imports removed | `flush_analytics_sync`, `record_classification`, `if False: yield {}`, `import inspect` fully removed. | **VERIFIED** |
| **Claim 6: Dead Dependencies** | `assemblyai`, `openai`, `duckduckgo` eradicated | 0 external imports across all `.py` files; `requirements.txt` files clean. | **VERIFIED** |
| **Claim 7: Privacy Disclosure** | In-memory processing & opt-in capture accurately reflected | Text & embeds dynamically disclose in-memory processing unless `!start-capture` is enabled. | **VERIFIED** |
| **Claim 8: Suite & Working Tree** | 96/96 green, working tree clean | 96/96 tests pass in 95.3s, but working tree is **dirty** (`audit/quality/` untracked). | **PARTIAL / FINDING** |

---

## DETAILED TRACEBACK AUDIT PER CLAIM

### Claim 1 — CORS Lockdown (`backend/app/main.py`, `backend/app/config.py`, `backend/app/routes.py`)
- **Claimed:** Wildcard `*` removed and replaced with validated `settings.CORS_ORIGINS`.
- **Verification Evidence:**
  1. [`backend/app/config.py:41-66`](file:///g:/CallWrapper/backend/app/config.py#L41-L66):
     ```python
     @field_validator("CORS_ORIGINS", mode="before")
     @classmethod
     def parse_cors_origins(cls, v: Any) -> list[str]:
         if isinstance(v, str):
             return [origin.strip() for origin in v.split(",") if origin.strip()]
         ...
     ```
     Whitespace stripping and empty token elimination function correctly.
  2. [`backend/app/main.py:48`](file:///g:/CallWrapper/backend/app/main.py#L48):
     ```python
     app.add_middleware(
         CORSMiddleware,
         allow_origins=settings.CORS_ORIGINS,
         allow_credentials=True,
         allow_methods=["*"],
         allow_headers=["*"],
     )
     ```
     Wildcard string is removed. Real runtime check:
     - Request from `http://localhost:3000` $\to$ `access-control-allow-origin: http://localhost:3000`
     - Request from `http://evil.com` $\to$ No CORS headers returned.
- **CRITICAL ADVERSARIAL FINDING (HIGH SEVERITY):**
  - Location: [`backend/app/routes.py:145-156`](file:///g:/CallWrapper/backend/app/routes.py#L145-L156)
  - Detail: The live WebSocket endpoint unconditionally accepts connections without origin checking:
    ```python
    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        _active_websockets.add(websocket)
        ...
    ```
  - Exploit / Risk: Starlette's `CORSMiddleware` applies **only** to HTTP requests. WebSockets bypass `CORSMiddleware` entirely. Any malicious site opened in a user's browser (e.g., `http://evil-tracker.com`) can initiate `new WebSocket("ws://localhost:8000/api/ws")` and receive the entire stream of real-time call telemetry, speaker transcriptions, and dispute notifications without restriction.
- **Verdict:** **PARTIAL / FINDING**

---

### Claim 2 — Referee Invariant: Zero Uninvited Audio & Manual Commands (`bot/main.py`)
- **Claimed:** `speaker.speak` completely eradicated; `!arbitrate` and `!simulate` only create pending offers awaiting user confirmation; stale fields (`correct_fact`, `spoken_intervention`) removed.
- **Verification Evidence:**
  1. Search for `speaker.speak` in `bot/main.py` yields **0 hits**.
  2. Search for `correct_fact` and `spoken_intervention` in `bot/main.py` yields **0 hits**.
  3. [`bot/main.py:726-795`](file:///g:/CallWrapper/bot/main.py#L726-L795): `manual_arbitrate` properly registers a `PendingOffer` with a 30-second cancellation timer via `_offer_expiry_timer`, broadcasting `dispute_check_offered` and posting the interactive Arabic offer in text chat.
- **CRITICAL ADVERSARIAL FINDING (MEDIUM SEVERITY):**
  - Location: [`bot/main.py:707-724`](file:///g:/CallWrapper/bot/main.py#L707-L724)
  - Detail: In `bot/arbitration/engine.py:652`, the referee invariant enforces a 180-second throttle:
    ```python
    if session.last_offer_time > 0 and (now - session.last_offer_time) < self.cooldown_sec:
        return None
    ```
    However, [`bot/main.py:707-724`](file:///g:/CallWrapper/bot/main.py#L707-L724) implements `manual_arbitrate` as follows:
    ```python
    async def manual_arbitrate(ctx: commands.Context, claim: str) -> None:
        ...
        session = arbitration_engine.get_session(guild_id)
        # BUG: It checks if pending_offer exists, but does NOT check cooldown!
        if session.pending_offer is not None and not session.pending_offer.is_expired():
            await ctx.send("... عرض سابق قيد الانتظار ...")
            return
        session.last_offer_time = now  # sets cooldown, but never checked before entry!
    ```
  - Exploit / Risk: A Discord user can spam `!arbitrate <claim>` immediately whenever an offer is rejected, expired, or cancelled, completely bypassing the 180-second cooldown invariant intended to protect the voice channel from spam.
- **Verdict:** **PARTIAL / FINDING**

---

### Claim 3 — Bounded Synchronous Sleep in Rate-Limiter (`bot/ai/groq.py`)
- **Claimed:** Synchronous fallback sleep sites capped at $\le 2.0\text{s}$, immediately bailing out if `wait_sec > 2.0`.
- **Verification Evidence:**
  1. Lines 337–344:
     ```python
     if sleep_wait > 2.0:
         logger.warning("Rate-limit wait exceeds 2.0s limit (sync) ... bailing out")
         return None, {}, latency_ms
     time.sleep(sleep_wait)
     ```
  2. Lines 350–357:
     ```python
     if wait_sec > 2.0:
         logger.warning("Rate-limit retry exceeds 2.0s limit (sync) ... bailing out")
         return None, {}, latency_ms
     time.sleep(wait_sec)
     ```
  3. Async sleep paths at lines 194 and 213 similarly abort at $> 2.0\text{s}$.
- **Verdict:** **VERIFIED**

---

### Claim 4 — Rebranding Sweep: "Voice Arbitrator" & "universal-3.6"
- **Claimed:** "Voice Arbitrator" and stale model string `"universal-3.6"` purged from codebase.
- **Verification Evidence:**
  - `bot/`, `backend/`, and `frontend/` are clean of `"voice arbitrator"`.
  - Stale model `"universal-3.6"` is purged from code files (the only 3.6 strings remaining in `frontend/app/page.tsx` are SVG `viewBox` coordinates).
- **CRITICAL ADVERSARIAL FINDING (MEDIUM SEVERITY):**
  - Legacy branding was **not** removed from launcher batch files, root scripts, documentation, and demo fixtures:
    1. [`README.md:3, 7, 28, 90, 201`](file:///g:/CallWrapper/README.md) (5 occurrences: title `# Voice Arbitrator`, repo URLs, etc.)
    2. [`start_all.bat:3, 6, 12, 15`](file:///g:/CallWrapper/start_all.bat) (4 occurrences: `Voice Arbitrator — All Services Launcher`, console titles)
    3. [`start_backend.bat:3, 6`](file:///g:/CallWrapper/start_backend.bat) (2 occurrences)
    4. [`start_frontend.bat:3, 6`](file:///g:/CallWrapper/start_frontend.bat) (2 occurrences)
    5. [`run_cloud.py:15, 35, 36`](file:///g:/CallWrapper/run_cloud.py) (3 occurrences: `Voice Arbitrator - Production Run Script`)
    6. [`.env.example:2`](file:///g:/CallWrapper/.env.example#L2) (1 occurrence: `# Voice Arbitrator - Environment Variables Template`)
    7. [`demo/sessions/rtx5070_dispute.json:4, 77`](file:///g:/CallWrapper/demo/sessions/rtx5070_dispute.json) (2 occurrences)
    8. Stale model string in [`.env.example:21-23`](file:///g:/CallWrapper/.env.example#L21-L23): still specifies `universal-3-6-pro`.
- **Verdict:** **PARTIAL / FINDING**

---

### Claim 5 — Dead Code & Dead Paths Elimination
- **Claimed:** `flush_analytics_sync`, `record_classification`, `if False: yield {}`, and unused `inspect` import eradicated with zero orphaned callers.
- **Verification Evidence:**
  1. Grep for `flush_analytics_sync` across repo: **0 hits**.
  2. Grep for `record_classification` across repo: **0 hits**.
  3. Grep for `if False: yield` across repo: **0 hits**.
  4. Grep for `import inspect` in `bot/tts/` across repo: **0 hits**.
  5. Vulture AST dead code analysis (`--min-confidence 80`) across `bot/` and `backend/app/`:
     - Returned only 1 finding: `bot/main.py:592: unused variable 'is_on'`.
     - No dangling references or dead imports.
- **Verdict:** **VERIFIED**

---

### Claim 6 — Dead Dependencies Removal
- **Claimed:** `assemblyai`, `openai`, and `duckduckgo` eradicated from dependencies and code.
- **Verification Evidence:**
  1. Grep for `import assemblyai` in `.py` files: **0 hits** (only internal `from bot.ai.assemblyai import ...` exists).
  2. Grep for `import openai` in `.py` files: **0 hits**.
  3. Grep for `duckduckgo` in `.py` files: **0 hits**.
  4. Inspected `requirements.txt` and `backend/requirements.txt`: zero occurrences of dead libraries.
- **Verdict:** **VERIFIED**

---

### Claim 7 — Privacy Disclosure Accuracy
- **Claimed:** Privacy notices updated to reflect memory-only processing by default and opt-in capture.
- **Verification Evidence:**
  1. [`bot/main.py:169-215`](file:///g:/CallWrapper/bot/main.py#L169-L215) (`build_privacy_notice_text` and `build_privacy_embed`):
     - Explicitly declares: *"Processing is strictly in-memory; no audio is written to disk unless an authorized administrator explicitly enables capture mode (`!start-capture`) for dataset collection."*
  2. Grep for misleading legacy strings (`"never recorded"`, `"no audio is recorded"`) in `bot/`: **0 hits**.
- **Verdict:** **VERIFIED**

---

### Claim 8 — Test Suite & Working Tree Cleanliness
- **Claimed:** 96/96 tests green, working tree clean.
- **Verification Evidence:**
  1. Full test discovery suite run:
     ```
     Ran 96 tests in 95.259s
     OK
     ```
     All 96 unit and integration tests passed.
- **ADVERSARIAL FINDING (LOW SEVERITY):**
  - Git status reports working tree is **NOT clean**:
    ```
    Untracked files:
      audit/quality/
    ```
    12 audit files generated during the Phase 0 audit remain uncommitted in the repo.
- **Verdict:** **PARTIAL / FINDING**

---

## ADDITIONAL ADVERSARIAL SWEEPS

### Sweep A — Configuration Inconsistencies (`.env.example` vs Reality)
A line-by-line audit between `.env.example` and codebase `os.getenv()` calls revealed significant drift:
1. **Dead variables still documented in `.env.example`:**
   - `PRIMARY_STT_PROVIDER` (Code uses AssemblyAI exclusively)
   - `TTS_PROVIDER` (Code uses Edge-TTS exclusively)
   - `TTS_VOICE_EN` (Code exclusively speaks Egyptian Arabic via ShakirNeural)
   - `HOST` and `PORT` (Read nowhere in `bot/` or `backend/config.py`)
   - `EMBED_COLOR_DISPUTE`, `EMBED_COLOR_ECHO` (Read nowhere)
2. **Active variables missing from `.env.example`:**
   - `DISPUTE_OFFER_COOLDOWN_SEC` (Read in `bot/arbitration/engine.py:27`)
   - `DISPUTE_OFFER_EXPIRY_SEC` (Read in `bot/arbitration/engine.py:28`)
   - `TEST_CAPTURE_MODE` (Read in `bot/main.py:61`)
   - `DISCORD_CLIENT_ID` (Read in `bot/main.py:465`)
   - `DISCORD_INVITE_PERMISSIONS` (Read in `bot/main.py:466`)
   - `TTS_TIMEOUT_SEC` (Read in `bot/tts/edge_tts_client.py:23`)

### Sweep B — Command Documentation Gap (`!help` Command)
In [`bot/main.py:436-475`](file:///g:/CallWrapper/bot/main.py#L436-L475), the `!help` embed fails to list 5 active bot commands:
- `!start` (Joins user's current voice channel)
- `!check` / `!verify` / `شوفها` (Triggers arbitration check for a pending dispute offer)
- `!judge-mode` (Toggles real-time refereeing)
- `!start-capture` (Begins debug audio capture)
- `!stop-capture` (Stops debug audio capture)

### Sweep C — Frontend / Backend Contract Discrepancy
[`backend/app/routes.py:38-39`](file:///g:/CallWrapper/backend/app/routes.py#L38-L39) broadcasts `fact_check_mode` and `fact_check_mode_badge` in `LIVE_STATE`. However, [`frontend/app/page.tsx`](file:///g:/CallWrapper/frontend/app/page.tsx) does not bind or display this state anywhere in the dashboard UI.

---

## RISK MATRIX & RECOMMENDATIONS

| Finding ID | Severity | Area | Recommended Remediation |
| :--- | :--- | :--- | :--- |
| **SEC-01** | **HIGH** | `backend/app/routes.py:145` | Add WebSocket origin header validation in `websocket_endpoint` matching `settings.CORS_ORIGINS`. |
| **INV-01** | **MEDIUM** | `bot/main.py:707` | Enforce `session.last_offer_time` cooldown check inside `manual_arbitrate`. |
| **BRD-01** | **MEDIUM** | Launcher batch files, README, `.env.example` | Global string replace `Voice Arbitrator` $\to$ `CallWrapped` and update stale model strings. |
| **CFG-01** | **LOW** | `.env.example` | Remove 7 dead keys; document 6 active environment variables. |
| **DOC-01** | **LOW** | `bot/main.py:436` | Add missing commands (`!start`, `!check`, `!judge-mode`, `!start-capture`, `!stop-capture`) to `!help`. |
| **GIT-01** | **LOW** | Working tree | Commit or add `audit/quality/` to `.gitignore`. |
