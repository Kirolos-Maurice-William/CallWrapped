# Adversarial Codebase Quality Audit #3 (Pre-Submission Final Audit)

**Date:** September 27, 2026  
**Auditor:** Adversarial QA & System Reliability Engine  
**Scope:** Full repository (`bot/`, `backend/`, `frontend/`, `tests/`, `audit/`)  
**Mode:** READ-ONLY on project code, evidence-only, zero speculation  

---

## 1. Executive Summary: Top 5 Demo & Production Risks

Ranked strictly by live demo failure probability and severity:

1. **Ghosting Referee upon Human Confirmation (`bot/arbitration/engine.py:856-859, 873-875`) [HIGH]**  
   When a user confirms a dispute check offer via voice («شوفها») or text (`!check`), if Tavily search returns 0 sources or Groq evaluates the dispute as `UNVERIFIABLE`, `confirm_dispute_offer` executes a bare `return`. It neither speaks the fallback hedge clause nor posts an explanation embed to Discord. To the user and judge, the bot prompts for permission, hears the confirmation, and then falls completely mute.

2. **Unsynchronized Cross-Thread Concurrency in Audio Receiver (`bot/audio/receiver.py:98-142`) [HIGH]**  
   The `discord.ext.voice_recv` background reader thread calls `AudioReceiver.write()` concurrently while the main `asyncio` event loop runs `_silence_checker_loop()`. Shared objects (`UserSpeechBuffer`, `self.buffers`, `UtteranceLoudnessAccumulator`) lack thread synchronization locks. A 15-second force-split and a silence timeout occurring near-simultaneously triggers concurrent `_finalize_utterance()` calls, causing corrupted audio accumulator state and duplicate AssemblyAI STT dispatches.

3. **Silent Exception Swallow in Audio Worker Coroutine Dispatcher (`bot/audio/receiver.py:184-187`) [HIGH]**  
   `asyncio.run_coroutine_threadsafe(coro, self.loop)` launches utterance processing from the worker thread. The returned `concurrent.futures.Future` is discarded without storing, awaiting, or attaching a done callback. Any unhandled exception during speech transcription or arbitration is silently swallowed by the Python runtime, causing the bot to appear deaf with zero error logs.

4. **FSM State Demotion and Premature Eviction of Offered Disputes (`bot/arbitration/dispute_tracker.py:266, 326`) [HIGH]**  
   When a dispute reaches the offer threshold (`ThreadState.OFFERED`), any subsequent claim on the same proposition family unconditionally overwrites `thread.state = ThreadState.TRACKING`. When `tick()` sweeps, the thread is demoted to `ThreadState.DECAY` and becomes eligible for capacity eviction under Rule 1, directly violating the core invariant *"Rule 4: Never evict OFFERED"*.

5. **$O(N \log N)$ Per-Frame Sorting & Allocations in Real-Time Audio Callback (`bot/audio/loudness.py:141-146, 201-207`) [HIGH]**  
   `SpeakerLoudnessBaseline.observe_eligible_frame()` marks the baseline dirty on every frame, causing `score()` to call `_recompute_stats_if_dirty()` on the next frame. Every 20ms audio frame converts a 1200-element deque to a list and sorts it twice to calculate median and MAD. For 4 active speakers, this executes 400 float sorts per second inside the time-critical audio receiver callback.

---

## 2. Prioritized Findings Table

| ID | Severity | Category | File:Line | Finding Summary | Failure Scenario | Suggested Fix Direction |
|:---|:---|:---|:---|:---|:---|:---|
| **F3-01** | `HIGH` | Correctness / Demo | [`bot/arbitration/engine.py:856-859, 873-875`](file:///g:/CallWrapper/bot/arbitration/engine.py#L856-L859) | Bare `return` on unverifiable dispute ghosts user after confirmation | Bot offers check; user confirms with «شوفها»; search finds 0 sources or status is UNVERIFIABLE; bot exits without speaking or sending any message | Speak or post fallback clause: `"تعذر التحقق من المعلومة من مصادر موثوقة"` |
| **F3-02** | `HIGH` | Concurrency | [`bot/audio/receiver.py:98-109, 140-142, 148-153`](file:///g:/CallWrapper/bot/audio/receiver.py#L98-L109) | Cross-thread race between audio worker and asyncio event loop | Audio thread forcesplit and asyncio silence checker concurrently call `_finalize_utterance()`, corrupting accumulators and sending duplicate STT requests | Add `threading.Lock` across `write()` buffer updates and `_finalize_utterance()` |
| **F3-03** | `HIGH` | Error Handling | [`bot/audio/receiver.py:184-187`](file:///g:/CallWrapper/bot/audio/receiver.py#L184-L187) | Discarded `Future` from `run_coroutine_threadsafe` swallows pipeline exceptions | Unhandled exception in `on_utterance` (STT error, key error) is swallowed by Python future; bot goes deaf silently | Attach `.add_done_callback()` logging unhandled future exceptions |
| **F3-04** | `HIGH` | Correctness / FSM | [`bot/arbitration/dispute_tracker.py:266, 326`](file:///g:/CallWrapper/bot/arbitration/dispute_tracker.py#L266) | Offered dispute thread demoted to `TRACKING` and evicted on decay | Subsequent claims on an OFFERED thread overwrite state to `TRACKING`; `tick()` marks it `DECAY` and evicts it under capacity pressure | Preserve `OFFERED` state: `if not thread.offered: thread.state = TRACKING` |
| **F3-05** | `HIGH` | Concurrency | [`bot/main.py:672-678`](file:///g:/CallWrapper/bot/main.py#L672-L678) | Check-then-act gap in `!check` text command | `await ctx.send()` yields event loop before `offer.is_resolved = True` is set; voice confirmation or double `!check` creates duplicate message and phantom rejected check | Mark `session.pending_offer.is_resolved = True` before `await ctx.send()` |
| **F3-06** | `HIGH` | Performance | [`bot/audio/loudness.py:141-146, 201-207`](file:///g:/CallWrapper/bot/audio/loudness.py#L141-L146) | 1200-element deque sorted twice per frame in real-time audio callback | Baseline marked dirty on every frame; `score()` sorts 1200 floats twice 50 times/sec per speaker, creating heavy CPU/GIL contention | Recompute median/MAD lazily (e.g. every 50 frames / 1s) instead of per-frame |
| **F3-07** | `MEDIUM` | Architecture | [`bot/arbitration/engine.py:681-740`](file:///g:/CallWrapper/bot/arbitration/engine.py#L681-L740) | `DisputeTracker` core is never invoked in live runtime | Live arbitration pipeline uses legacy `ClaimMemory` and pairwise `ConflictDetector`; multi-speaker FSM and confidence formulas remain offline replay-only | Wire `DisputeTracker.ingest()` into `ArbitrationEngine.process_utterance()` |
| **F3-08** | `MEDIUM` | Data Integrity | [`bot/audio/capture.py:274-278`](file:///g:/CallWrapper/bot/audio/capture.py#L274-L278) | Non-atomic write of `labels_DRAFT.csv` truncates existing human annotations on crash | `open(csv_file, "w")` truncates before writing; process kill mid-write leaves 0-byte file, permanently destroying preserved human annotations | Write to temporary file (`.tmp`) and atomically replace with `os.replace` |
| **F3-09** | `MEDIUM` | Error Handling | [`bot/ai/groq.py:406-411`](file:///g:/CallWrapper/bot/ai/groq.py#L406-L411) | Silent swallow of JSON decode errors in Groq client | Malformed JSON or fenced markdown from Groq is swallowed silently without logging; caller receives `None` with no diagnostic visibility | Log warning with error and first 100 characters of raw LLM content |
| **F3-10** | `LOW` | Dead Code | [`bot/arbitration/claim_detector.py:320-383`](file:///g:/CallWrapper/bot/arbitration/claim_detector.py#L320-L383) | `batch_classify_sync` has zero callers across repository | 64 lines of synchronous Groq batch classification logic unused by both bot and test suite | Remove or deprecate unused synchronous method |
| **F3-11** | `LOW` | Configuration | [`backend/app/config.py:18, 42`](file:///g:/CallWrapper/backend/app/config.py#L18), [`.env.example:85`](file:///g:/CallWrapper/.env.example#L85) | Stale branding `"AI Third Participant"` and DB default mismatch | Backend defaults to `./call_intelligence.db` while `.env.example` specifies `./data/app.db`; legacy project title displayed in OpenAPI docs | Update `PROJECT_NAME = "CallWrapped"` and align DB default path |
| **F3-12** | `LOW` | Test Honesty | [`tests/test_classifier.py:57-60`](file:///g:/CallWrapper/tests/test_classifier.py#L57-L60) | Unit test silently skips all assertions when Groq returns None/429 | `test_twelve_transcripts_real_groq_api` executes `continue` on missing data; entire test passes with 0 assertions if API is down | Assert at least one transcript was classified: `self.assertGreater(count, 0)` |

---

## 3. Deep Evidence & Code Excerpts

### F3-01: Bare `return` on Unverifiable Dispute Ghosts User
- **File:** `bot/arbitration/engine.py:856-859, 873-875`
```python
856:             if not sources:
857:                 logger.warning(f"⚠️ [DisputeConfirm] No search sources found for query: '{offer.search_query}'")
858:                 session.unverifiable_count += 1
859:                 return
...
873:             if not assessment or assessment.get("status") == "UNVERIFIABLE":
874:                 session.unverifiable_count += 1
875:                 return
```
**Failure Scenario:** A dispute offer is triggered in voice ("🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟"). User says "شوفها". If Tavily search finds 0 sources (e.g. niche local claim or search timeout), or Groq verdict is `UNVERIFIABLE`, the code executes `return`. The bot produces zero speech and zero chat message. The user and judges see a bot that asked for confirmation and then fell completely silent.

### F3-02: Cross-Thread Concurrency Race in Audio Receiver
- **File:** `bot/audio/receiver.py:140-142, 150-153, 162-166`
```python
140:         if buf.is_speaking and (now - buf.speech_start_time >= config.MAX_SPEECH_DURATION_SEC):
141:             self._finalize_utterance(buf, ended_by="forcesplit")
...
150:                 if buf.is_speaking and buf.pcm_chunks:
151:                     silence_gap = now - buf.last_speech_time
152:                     if silence_gap >= config.SILENCE_DURATION_SEC:
153:                         self._finalize_utterance(buf, ended_by="silence")
...
162:         buf.reset()
163: 
164:         baseline = self.speaker_baselines.get(user_id)
165:         acc = self.utterance_accumulators.get(user_id)
166:         audio_features: Optional[UtteranceAudioFeatures] = acc.finalize(baseline) if acc else None
```
**Failure Scenario:** `write()` is invoked by `voice-recv`'s internal audio reader thread. `_silence_checker_loop()` is an asyncio task on the main event loop. Neither `buf` nor `acc` are thread-safe. When a 15-second speech duration expires at the same time a speaker pauses, both threads invoke `_finalize_utterance(buf)`. One thread calls `acc.finalize()` which resets `self.frames_log_rms_db.clear()`; the second thread attempts to finalize an empty accumulator, corrupting baseline statistics and dispatching two simultaneous `on_utterance` tasks for the same speech segment.

### F3-03: Discarded Future in Audio Dispatcher
- **File:** `bot/audio/receiver.py:184-187`
```python
184:                 asyncio.run_coroutine_threadsafe(
185:                     coro,
186:                     self.loop
187:                 )
```
**Failure Scenario:** `run_coroutine_threadsafe` returns a `concurrent.futures.Future`. The future is ignored. If `self.on_utterance` encounters an unhandled exception (network drop during AssemblyAI transcription upload, unhandled exception in claim detection), Python's `concurrent.futures` captures the exception in the future object. Because nothing ever reads `future.result()`, the exception is swallowed silently, causing the utterance to vanish without any error log or trace.

### F3-04: FSM State Demotion and Eviction of Offered Dispute
- **File:** `bot/arbitration/dispute_tracker.py:266-288, 326`
```python
266:             thread.state = ThreadState.TRACKING
267:             c_score = self.compute_confidence(thread, event)
268:             thread.peak_score = max(thread.peak_score, c_score)
269: 
270:             if not thread.offered and c_score >= self.offer_threshold:
271:                 thread.state = ThreadState.OFFERED
272:                 thread.offered = True
...
283:             else:
284:                 return TrackerDecision(
285:                     action="tracking",
286:                     thread_id=thread.thread_id,
287:                     state=thread.state,
288:                     confidence=c_score,
289:                     reason="tracking_below_threshold" if not thread.offered else "already_offered",
290:                     thread=thread,
291:                 )
```
**Failure Scenario:** A thread reaches offer threshold at Event A (`thread.offered = True`, `thread.state = OFFERED`). When Event B arrives for the same thread, line 266 unconditionally executes `thread.state = ThreadState.TRACKING`. Because `thread.offered` is True, line 270 is skipped, leaving `thread.state == TRACKING`. In `tick()`, line 326 marks the thread `DECAY`. When capacity reaches 8 threads, `_evict_if_needed()` priority 1 evicts `DECAY` threads, purging an active offered dispute.

### F3-05: Check-Then-Act Race in `!check` Command
- **File:** `bot/main.py:672-678`
```python
672:     if not session.pending_offer or session.pending_offer.is_resolved:
673:         await ctx.send("ℹ️ لا يوجد طلب تحقق معلق حالياً.")
674:         return
675: 
676:     await ctx.send("🔍 جاري التحقق من المعلومة عبر المصادر الموثوقة...")
677:     await arbitration_engine.confirm_dispute_offer(
678:         guild_id=ctx.guild.id,
```
**Failure Scenario:** At line 672, `session.pending_offer.is_resolved` is False. Line 676 awaits Discord API HTTP request (`ctx.send`), yielding the event loop for 150–300ms. A second user types `!check` or a voice user says "شوفها". Line 672 still evaluates to False for the second caller. Two calls to `confirm_dispute_offer` are launched. The second call is rejected inside `confirm_dispute_offer:832`, but only after having already sent a duplicate "🔍 جاري التحقق" to the chat channel.

### F3-06: $O(N \log N)$ Sorting in Real-Time Frame Callback
- **File:** `bot/audio/loudness.py:141-146, 201-207`
```python
141:                 hist_list = list(self.history)
142:                 med = float(statistics.median(hist_list))
143:                 self._cached_median = med
144:                 mad = float(statistics.median([abs(x - med) for x in hist_list]))
145:                 self._cached_mad = mad
...
201:         if self.baseline_ready:
202:             z = self.score(log_rms_db)
...
206:         self.history.append(float(log_rms_db))
207:         self._dirty = True
```
**Failure Scenario:** Every frame observed appends to history and sets `self._dirty = True`. On the subsequent frame, `score()` invokes `_recompute_stats_if_dirty()`. `statistics.median` sorts the 1200-element list, computes deviations, and sorts them again. In a voice call with 4 active speakers, the audio worker thread runs 400 array allocations and sorts every second, causing CPU starvation and potential audio buffer underruns.

---

## 4. Regression Verification of Prior Audits

| Prior Finding | Origin | Claimed Fix | Verification in Current Code | Status |
|:---|:---|:---|:---|:---|
| **F2-01 (BOM in replay CSV)** | Audit #2 | `encoding="utf-8-sig"` in `dispute_replay.py:141` | Checked `bot/arbitration/dispute_replay.py:141`: uses `utf-8-sig`. Verified headers clean without `\ufeff`. | **CLEAN ✅** |
| **F2-02 (Silent JSONL except)** | Audit #2 | `logger.warning` on malformed line in `dispute_replay.py:134` | Checked `bot/arbitration/dispute_replay.py:134`: logs warning with exception message. | **CLEAN ✅** |
| **F2-03 (Silent PCM except)** | Audit #2 | `logger.warning` in `loudness.py:76` | Checked `bot/audio/loudness.py:76`: logs warning with input type and exception. | **CLEAN ✅** |
| **F2-04 (Dead import dispute_models)** | Audit #2 | Remove `canonicalize_entity` in `dispute_models.py` | Checked `bot/arbitration/dispute_models.py:5`: only `_STRIP_PREFIXES_AR` imported. Vulture 0 hits. | **CLEAN ✅** |
| **F2-05 (Dead imports loudness)** | Audit #2 | Remove `asdict`, `Sequence` in `loudness.py` | Checked `bot/audio/loudness.py:3, 11`: unused imports removed. Vulture 0 hits. | **CLEAN ✅** |
| **F2-06 (Missing env vars)** | Audit #2 | Sync `.env.example` with config defaults | Checked `.env.example`: all 5 variables present with defaults. | **CLEAN ✅** |
| **A1-01 (CORS Wildcard)** | Audit #1 | Use `settings.CORS_ORIGINS` in `backend/app/main.py:48` | Checked `backend/app/main.py:49`: `allow_origins=cors_origins` parsed from settings. | **CLEAN ✅** |
| **A1-02 (!arbitrate speaks uninvited)** | Audit #1 | Gate `!arbitrate` through two-stage offer flow | Checked `bot/main.py:733-835`: creates `PendingOffer`, posts offer text, zero unsolicited speech. | **CLEAN ✅** |
| **A1-03 (Groq sync retry sleep)** | Audit #1 | Cap sleep at 2.0s or skip in `bot/ai/groq.py:368` | Checked `bot/ai/groq.py:368`: skips if `sleep_wait > 2.0s`. | **CLEAN ✅** |

---

## 5. Category-by-Category Audit Results

### 1. Concurrency
- `LIVE_STATE` in `backend/app/routes.py`: Single-process async endpoints on uvicorn event loop. `broadcast_event()` creates a defensive snapshot `list(active_connections)`. Safe.
- `AudioReceiver`: **FINDING F3-02**. Cross-thread race between audio reader thread and asyncio event loop on buffer reset and accumulator finalization.
- `PendingOffer`: **FINDING F3-05**. Check-then-act gap between `!check` validation and setting `is_resolved = True`.

### 2. Resource Lifecycle
- **FFmpeg Subprocesses (`bot/ai/tts.py`):** Verified clean. `StreamFFmpegPCMAudio.cleanup()` executes `process.kill()` followed by `process.wait(timeout=0.2)` to reap child processes. Tested in `test_barge_in.py` with zero zombie processes.
- **Warm TTS Sessions (`WarmTTSSession`):** Background prewarm tasks are tracked and cancelled on `close()` or `close_sync()`. `TCPConnector` is closed with `abort_ssl=True`.
- **WebSockets Pool (`backend/app/routes.py`):** Disconnects caught via `WebSocketDisconnect` and removed from `active_connections`.

### 3. Error Handling
- Total `except` blocks in `bot/`: 49.
- Logged/Handled: 44.
- Silent/Bare Swallows:
  - **FINDING F3-03:** Discarded `Future` from `run_coroutine_threadsafe` in `bot/audio/receiver.py:184`.
  - **FINDING F3-09:** Silent `json.loads` exception swallow in `bot/ai/groq.py:410`.
  - Harmless/Defensive: `pcm.py:92` (falls back to untrimmed audio), `tts.py:74-120` (pipe close during process teardown).

### 4. Config Truth
- Every `os.getenv` in `bot/config.py` matches an entry in `.env.example`.
- Mismatches identified:
  - **FINDING F3-11:** `backend/app/config.py:18, 42` has default `DATABASE_URL = "sqlite+aiosqlite:///./call_intelligence.db"` whereas `.env.example` specifies `"sqlite+aiosqlite:///./data/app.db"`. Legacy `PROJECT_NAME = "AI Third Participant"`.

### 5. Data Integrity
- All text/JSON files use explicit UTF-8 encodings.
- All CSV reads and writes use `utf-8-sig` (BOM-safe).
- **FINDING F3-08:** `capture.py:274` truncates `labels_DRAFT.csv` on open rather than writing to a temporary file and atomically renaming.

### 6. Dead Weight
- **FINDING F3-10:** `batch_classify_sync` (lines 320–383 in `bot/arbitration/claim_detector.py`) has 0 callers across the repository.
- Unused local variables: `t_claim_start` and `t_conflict_start` in `bot/arbitration/engine.py:573, 633`.

### 7. Test Honesty
- Total unit/integration tests: 157 passing.
- **FINDING F3-12:** `tests/test_classifier.py:57-60` contains `if data is None ... continue`, allowing the test to pass with 0 assertions if the Groq API rate limits or errors.
- **Coverage Gap (F3-04):** No unit test in `test_dispute_tracker.py` ever ingests an event into a thread after `ThreadState.OFFERED` has been reached, which concealed the state demotion bug.

---

## 6. Closing Statement

> **"If a judge used this bot live for 30 minutes, the most likely visible failure would be:**
>
> **The bot triggers a legitimate dispute verification offer in Discord («🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟»), a speaker enthusiastically confirms by saying «شوفها» (or typing `!check`), and the bot falls completely silent—never speaking a verdict, never posting a fallback embed, and leaving the participants wondering if the bot crashed.**
>
> *(Root cause: `bot/arbitration/engine.py:856-859, 873-875` executes a bare `return` on unverifiable or zero-source search results without speaking the fallback hedge clause or posting to the text channel).*
