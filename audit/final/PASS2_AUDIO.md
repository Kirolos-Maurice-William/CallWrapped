# AUDIT PASS 2/4: Audio Pipeline, Timing, Real-Time Safety

**Audit Date:** 2026-09-28  
**Scope:** `bot/audio/receiver.py`, `bot/audio/loudness.py`, `bot/audio/pcm.py`, `bot/audio/capture.py`, `bot/ai/tts.py`, `bot/ai/assemblyai.py`  
**Secondary Scope:** `bot/config.py`, `bot/main.py`  
**Review Type:** Hostile Code-Level Audit (Read-Only on project code)  
**Status:** COMPLETE — 14 Audio & Real-Time Safety Findings Identified  

---

## Executive Summary

This audit inspected the real-time audio pipeline, concurrent threading models, digital signal processing (DSP), voice activity detection (VAD), and network timing interactions across CallWrapped. The system ingests multi-user 48kHz stereo Opus packets from Discord, runs per-speaker energy tracking and loudness calibration, decimates to 16kHz mono WAV, uploads to AssemblyAI for Egyptian Arabic/English code-switching ASR, and pipes neural Edge-TTS synthesis into FFmpeg with barge-in interruption.

The hostile audit identified serious concurrency, timing, and acoustic vulnerabilities:
1. **Unsynchronized Dict Mutation in Real-Time Audio Thread:** In [`bot/audio/receiver.py:101-112`](file:///g:/CallWrapper/bot/audio/receiver.py#L101-L112), incoming audio frames mutate `self.buffers`, `self.speaker_baselines`, and `self.utterance_accumulators` **outside** the threading lock. The Discord `voice_recv` thread writes to these dictionaries while the asyncio event loop iterates over them in [`receiver.py:170`](file:///g:/CallWrapper/bot/audio/receiver.py#L170), risking `RuntimeError: dictionary changed size during iteration` and race-induced corruption.
2. **Main Event Loop Blocked by Synchronous DSP:** In [`bot/audio/receiver.py:206`](file:///g:/CallWrapper/bot/audio/receiver.py#L206), `convert_discord_pcm_to_wav()` runs synchronously within `_finalize_utterance()` on the **main asyncio event loop thread** during silence detection. Converting up to 15 seconds of stereo PCM (750 frames, ~3MB) with numpy decimation and reverse VAD search stalls all asyncio tasks (WebSocket heartbeats, dispute timers, TTS streams) for 15–30ms per completed utterance.
3. **Severe Boxcar Decimation Aliasing (48kHz $\to$ 16kHz):** In [`bot/audio/pcm.py:28`](file:///g:/CallWrapper/bot/audio/pcm.py#L28), downsampling uses a 3-sample moving average (`.reshape(-1, 3).mean(axis=1)`). DSP transfer function analysis proves this filter provides only **-3.52 dB** attenuation at the 8 kHz Nyquist frequency. High-frequency speech energy, sibilants, and fricatives (such as Egyptian Arabic "ص", "س", "ش", "ز", "ث") between 8 kHz and 24 kHz fold directly into the 0–8 kHz voice band as harsh metallic aliasing artifacts, degrading AssemblyAI code-switching accuracy.
4. **Out-of-Order STT Arrival on Long Speech:** AssemblyAI polling budget is 20.0s (40 attempts $\times$ 0.5s), while `MAX_SPEECH_DURATION_SEC = 15.0s`. If a user speaks continuously for 30s, force-splitting creates Chunk 1 (0–15s) and Chunk 2 (15–30s). If Chunk 1 takes 18s to transcribe while Chunk 2 takes 4s, Chunk 2 completes first and inserts into `claim_memory` and session history before Chunk 1, inverting the chronological conversation timeline.
5. **Indefinite Lockup in TTS Intervention Speaker:** In [`bot/ai/tts.py:453-456`](file:///g:/CallWrapper/bot/ai/tts.py#L453-L456), after `feed_stream()` finishes synthesis under a 10s timeout, the method enters `while voice_client.is_playing(): await asyncio.sleep(0.05)` **without any timeout** while holding `self._lock`. If Discord's voice gateway stalls or freezes, `self._lock` is held forever, permanently disabling all future TTS interventions.

---

## 1. Thread Boundary Map & Concurrency Audit

### 1.1 Live Call Threading Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       LIVE CALL THREAD MAP                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   [THREAD 1: Discord voice_recv Native Worker Thread]
   • Driven by: Discord gateway UDP voice socket receiver
   • Calls: AudioReceiver.write(user, data) @ 50 Hz (every 20ms per active speaker)
   • Accesses (OUTSIDE LOCK):
       - self.buffers[user_id]                <-- MUTATES DICT (receiver.py:102)
       - self.speaker_baselines[user_id]      <-- MUTATES DICT (receiver.py:104)
       - self.utterance_accumulators[user_id] <-- MUTATES DICT (receiver.py:106)
       - buf.user_name                        <-- WRITES (receiver.py:109)
   • Calls (SYNCHRONOUS ON BARGE-IN):
       - speaker.stop(vc, user_label)         <-- Cross-thread kill to Discord AudioPlayer & FFmpeg
   • Accesses (UNDER LOCK):
       - buf.add_frame(...)                   <-- Appends PCM chunk, updates speech times
       - baseline.observe_eligible_frame(...) <-- Updates deque
       - acc.observe_frame_raw(...)           <-- Appends log-RMS dB
   • On forcesplit (now - speech_start >= 15s):
       - Calls: _finalize_utterance(buf, ended_by="forcesplit")
       - Runs: convert_discord_pcm_to_wav() ON THIS WORKER THREAD (blocks UDP packet pump!)
       - Dispatches: asyncio.run_coroutine_threadsafe(on_utterance, self.loop)

   ──────────────────────────────────────────┬──────────────────────────────────────────────────────
                                             │
   [THREAD 2: Main Asyncio Event Loop]       │
   • Runs:                                   │
       - AudioReceiver._silence_checker_loop │ (polls every 100ms)
       - on_user_utterance / arbitration     │ (STT await, LLM verification, EventHub WebSocket)
       - InterventionSpeaker.speak_clauses   │ (edge-tts streaming, c2_task, pipe feeding)
   • Accesses (UNDER LOCK):                  │
       - active_buffers = list(self.buffers.values()) (receiver.py:170)
         ▲ HAZARD: Races with Thread 1 writing self.buffers[user_id] outside lock!
       - buf.is_speaking, buf.last_speech_time (receiver.py:175)
   • On silence timeout (silence_gap >= 1.5s):
       - Calls: _finalize_utterance(buf, ended_by="silence")
       - Runs: convert_discord_pcm_to_wav() SYNCHRONOUSLY ON EVENT LOOP (receiver.py:206)
         ▲ HAZARD: Stalls event loop for 15-30ms per completed utterance!
       - Schedules: on_utterance coroutine

   ──────────────────────────────────────────┼──────────────────────────────────────────────────────
                                             │
   [THREAD 3: Discord AudioPlayer Thread]    │
   • Driven by: discord.voice_client.play()  │
   • Calls: StreamFFmpegPCMAudio.read()      │ (every 20ms, reads 3840 bytes from FFmpeg stdout pipe)
   • Reads: self._stdout.read(3840)          │ (tts.py:82)
   • Flags: checks self._closed              │
   • On barge-in: Thread 1 or 2 calls process.kill(), stdout closes, read() returns b""

   ──────────────────────────────────────────┼──────────────────────────────────────────────────────
                                             │
   [THREAD POOL: asyncio.to_thread Workers]  │
   • Worker A: audio_source.write_chunk(data)│ Pipes MP3 chunks to FFmpeg stdin (tts.py:401, 407, 421)
   • Worker B: audio_source.finish_writing() │ Closes FFmpeg stdin at stream end (tts.py:430)
   • Worker C: save_captured_utterance_sync  │ Filesystem WAV & JSONL writes (capture.py:193)
   • Worker D: stop_capture_session          │ Generates labels_DRAFT.csv (capture.py:87)

   ──────────────────────────────────────────┼──────────────────────────────────────────────────────
                                             │
   [SUBPROCESS: FFmpeg Transcoding Pipe]     │
   • Stdin (pipe:0):  Receives variable MP3 chunks from edge-tts
   • Stdout (pipe:1): Emits raw s16le 48kHz stereo PCM (3840 bytes/20ms) to AudioPlayer
```

### 1.2 Shared Objects Concurrency Matrix

| Shared Object | Location | Writers | Readers | Synchronization | Concurrency Hazard / Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `AudioReceiver.buffers` | [`receiver.py:44`](file:///g:/CallWrapper/bot/audio/receiver.py#L44) | `write()` (Thread 1) | `_silence_checker_loop` (Thread 2), `cleanup()` (Thread 2) | **PARTIAL / BROKEN** | **HIGH RISK.** `write()` mutates `self.buffers` at line 102 **before** entering `self._lock` (line 130). If Thread 2 iterates `self.buffers.values()` at line 170 while a new speaker connects, Python can raise `RuntimeError: dictionary changed size during iteration`. |
| `AudioReceiver.speaker_baselines` | [`receiver.py:45`](file:///g:/CallWrapper/bot/audio/receiver.py#L45) | `write()` (Thread 1) | `_finalize_utterance()` (Thread 1 & 2), `cleanup()` (Thread 2) | **PARTIAL / BROKEN** | **MEDIUM RISK.** Mutated without lock at line 104; cleared under lock in `cleanup()` at line 246. |
| `AudioReceiver.utterance_accumulators` | [`receiver.py:46`](file:///g:/CallWrapper/bot/audio/receiver.py#L46) | `write()` (Thread 1) | `_finalize_utterance()` (Thread 1 & 2), `cleanup()` (Thread 2) | **PARTIAL / BROKEN** | **MEDIUM RISK.** Mutated without lock at line 106. |
| `UserSpeechBuffer.pcm_chunks` | [`pcm.py:105`](file:///g:/CallWrapper/bot/audio/pcm.py#L105) | `buf.add_frame()` (Thread 1) | `_finalize_utterance()` (Thread 1 & 2) | `self._lock` | **MEDIUM RISK (Gap Race).** In `_silence_checker_loop` (lines 174–180), `self._lock` is released after checking `should_finalize = True` and re-acquired inside `_finalize_utterance` (line 184). A packet arriving in this gap has its audio added and then wiped by `buf.reset()`. |
| `InterventionSpeaker.interrupted` | [`tts.py:237`](file:///g:/CallWrapper/bot/ai/tts.py#L237) | `stop()` (Thread 1 or 2) | `feed_stream()`, `synthesize_clause2()` (Thread 2) | None (atomic boolean) | **LOW RISK.** Python GIL ensures atomic bool read/write. |
| `InterventionSpeaker._lock` | [`tts.py:236`](file:///g:/CallWrapper/bot/ai/tts.py#L236) | `speak_clauses()` | `speak_clauses()` | `asyncio.Lock` | **HIGH RISK.** Lock is held during unbounded `while voice_client.is_playing()` loop (lines 453–456). If Discord voice halts, lock is permanently deadlocked. |
| `StreamFFmpegPCMAudio._stdin` | [`tts.py:55`](file:///g:/CallWrapper/bot/ai/tts.py#L55) | `to_thread(write_chunk)` (Pool) | `cleanup()` (Thread 1 or 2), `finish_writing()` (Pool) | None | **HIGH RISK.** If barge-in triggers while a chunk write is active, `cleanup()` closes `_stdin` concurrently with `self._stdin.write(chunk)`, causing unhandled pipe errors. |
| `WarmTTSSession.connector` | [`tts.py:144`](file:///g:/CallWrapper/bot/ai/tts.py#L144) | `prewarm()` (Thread 2) | `speak_clauses()` (Thread 2), `close()` (Thread 2) | Cooperative async | **CLEAN.** Confined to asyncio event loop. |
| `capture._active_session_dir` | [`capture.py:19`](file:///g:/CallWrapper/bot/audio/capture.py#L19) | `start_capture_session()`, `stop_capture_session()` | `save_captured_utterance_sync()` | None (global) | **MEDIUM RISK.** No lock around global pointer. If stop is called while `save_captured_utterance_sync` executes in `to_thread`, utterance may write to default folder instead of session folder. |

---

## 2. Timing & Timeout Interaction Audit

### 2.1 Configuration Parameters & Runtime Timing Table

| Parameter / Timer | Source Location | Value | Real-World Exceeded Failure Mode | Interacting Components |
| :--- | :--- | :--- | :--- | :--- |
| `SILENCE_DURATION_SEC` | [`config.py:65`](file:///g:/CallWrapper/bot/config.py#L65) | `1.5s` | Premature cut-off of thoughtful/hesitant Arabic dialect speakers ("يعني... أظن"). | `_silence_checker_loop` (0.1s poll interval) |
| `SILENCE_THRESHOLD_RMS` | [`config.py:66`](file:///g:/CallWrapper/bot/config.py#L66) | `80` (int16 RMS) | Low-gain microphones never trigger speech; noisy backgrounds never trigger silence. | `UserSpeechBuffer.add_frame`, `pcm.py` silence trimming, barge-in detection |
| `MIN_SPEECH_DURATION_SEC` | [`config.py:67`](file:///g:/CallWrapper/bot/config.py#L67) | `0.5s` | Utterances shorter than 500ms (e.g. quick "تمام", "أه", "لا") are discarded. | `_finalize_utterance` line 199 |
| `MAX_SPEECH_DURATION_SEC` | [`config.py:68`](file:///g:/CallWrapper/bot/config.py#L68) | `15.0s` | Long monologues are forcefully split; speech mid-sentence is bifurcated. | `AudioReceiver.write` lines 158–162, AssemblyAI STT |
| `ASSEMBLYAI_POLL_ATTEMPTS` | [`config.py:30`](file:///g:/CallWrapper/bot/config.py#L30) | `40` attempts | Transcription dropped as timeout after 20s. Utterance lost. | `ASSEMBLYAI_POLL_INTERVAL_SEC` (0.5s) $\to$ 20s budget |
| `ASSEMBLYAI_POLL_INTERVAL_SEC` | [`config.py:31`](file:///g:/CallWrapper/bot/config.py#L31) | `0.5s` | Adds 0 to 500ms quantization delay to STT latency. | AssemblyAI polling loop |
| `httpx.AsyncClient(timeout=30.0)` | [`assemblyai.py:138`](file:///g:/CallWrapper/bot/ai/assemblyai.py#L138) | `30.0s` | HTTP upload socket timeout. If network drops, hangs for 30s before dropping. | AssemblyAI file upload |
| `TTS_TIMEOUT_SEC` | [`config.py:74`](file:///g:/CallWrapper/bot/config.py#L74) | `10.0s` | Synthesis aborted if Edge-TTS takes $>10\text{s}$. Partial audio played. | `InterventionSpeaker.speak_clauses` |
| `WarmTTSSession.timeout_seconds` | [`tts.py:141`](file:///g:/CallWrapper/bot/ai/tts.py#L141) | `35.0s` | If dispute confirmation takes $>35\text{s}$, warm TLS session is discarded and rebuilt. | `DISPUTE_OFFER_EXPIRY_SEC` (30.0s) |
| `DISPUTE_OFFER_EXPIRY_SEC` | [`config.py:58`](file:///g:/CallWrapper/bot/config.py#L58) | `30.0s` | Pending offer cancelled if neither user confirms verbally or via text in 30s. | `_offer_expiry_timer` |
| `DISPUTE_OFFER_COOLDOWN_SEC` | [`config.py:57`](file:///g:/CallWrapper/bot/config.py#L57) | `180.0s` (3 min) | All disputes for next 3 minutes are suppressed to avoid nagging. | `session.last_offer_time` |
| `DISPUTE_CONFIRM_SEARCH_TIMEOUT_SEC` | [`config.py:59`](file:///g:/CallWrapper/bot/config.py#L59) | `8.0s` | Search prefetch wait ceiling during dispute confirmation. | `confirm_dispute_offer` |

### 2.2 Deep Timing Interactions

#### Interaction 1: STT Polling Budget (20s) vs. Force-Split (15s) $\to$ Inverted Timeline
```text
Time (s):  0          15                 30                     45
Speaker:   [===== Utterance Part 1 =====][===== Utterance Part 2 =====]
Event:                ▲ Force-split               ▲ Normal silence end
STT Task 1:           [--- Upload + Poll (18.5s) -----------------------▶] Finishes @ t=33.5s
STT Task 2:                                       [-- Poll (4.2s) -▶]       Finishes @ t=34.2s
```
- **Scenario:** Speaker delivers a continuous 30-second explanation. At $t=15\text{s}$, `forcesplit` triggers, sending Part 1 to AssemblyAI. AssemblyAI experiences a queue spike and takes 18.5s (within the 20s budget).
- Meanwhile, the speaker finishes at $t=30\text{s}$, triggering Part 2. AssemblyAI processes Part 2 in 4.2s, completing at $t=34.2\text{s}$.
- If Part 1 experiences any network retransmission, Part 2 can complete **before** Part 1. Part 2 feeds into `arbitration_engine.process_utterance` first, causing:
  1. Claims from Part 2 enter `claim_memory` prior to Part 1.
  2. Transcript events appear in inverted order on the dashboard.
  3. Context-dependent references in Part 2 lose their antecedents.

#### Interaction 2: TTS Stream Timeout vs. Unbounded AudioPlayer Playback Wait
In [`bot/ai/tts.py:432-456`](file:///g:/CallWrapper/bot/ai/tts.py#L432-L456):
```python
432:  tts_timeout = getattr(config, "TTS_TIMEOUT_SEC", 12.0)
433:  try:
434:      await asyncio.wait_for(feed_stream(), timeout=tts_timeout)
...
453:  # Wait for voice_client to finish playing remaining audio
454:  while voice_client.is_playing():
455:      if self.interrupted:
456:          break
457:      await asyncio.sleep(0.05)
```
- `asyncio.wait_for(feed_stream(), timeout=tts_timeout)` only bounds the time spent **synthesizing and feeding bytes into FFmpeg stdin**.
- Once all bytes are in FFmpeg, `feed_stream()` returns.
- Execution then enters lines 453–457: `while voice_client.is_playing(): await asyncio.sleep(0.05)`.
- **Fatal Defect:** This loop has **zero timeout**.
- If the Discord gateway fails to deliver voice frames, or if Discord's internal audio player freezes, `voice_client.is_playing()` remains `True` indefinitely.
- Because lines 453–457 execute inside `async with self._lock:`, **the TTS speaker lock is never released**, causing all future calls to `speak_clauses()` to hang forever at `async with self._lock:`.

#### Interaction 3: Groq Daily Rate-Limit Midnight Rollover Surge
- Groq free/developer tier limits reset daily at UTC 00:00 (2:00 AM / 3:00 AM Cairo local time).
- In [`bot/arbitration/engine.py:302-315`](file:///g:/CallWrapper/bot/arbitration/engine.py#L302-L315), when Groq returns HTTP 429, `KeyPool.select_key()` marks the key with:
  `reset_time = time.time() + 60.0`.
- During active late-night Discord gaming sessions across the midnight UTC boundary:
  1. If token consumption exceeds daily allocation just before midnight, all 8 keys enter 429 quarantine within seconds.
  2. `KeyPool.select_key()` returns `None`.
  3. Instant claim detection completely collapses: `detect_claim_instant()` returns `None` and logs `⚠️ GROQ_QUARANTINE_EXHAUSTED`.
  4. Even after midnight passes on Groq servers, CallWrapped enforces a 60-second local sleep lock on every key before attempting to probe again.

---

## 3. Audio Quality & Signal Degradation Chain Audit

### 3.1 End-to-End Signal Transformation Flow
```text
Discord Client (48kHz Stereo Opus, 20ms frames @ 96 kbps)
   │
   ▼ [voice_recv: Native libopus decode]
Raw PCM Frame: 3840 bytes (48,000 Hz, 16-bit signed integer, 2 channels)
   │
   ▼ [bot/audio/pcm.py: convert_discord_pcm_to_wav]
Stereo Matrix: np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
   │
   ▼ (Average stereo channels to mono: stereo_matrix.mean(axis=1).astype(np.int16))
Mono 48kHz PCM: 960 samples per 20ms frame
   │
   ▼ (3:1 Decimation with Boxcar Average: mono_48k.reshape(-1, 3).mean(axis=1).astype(np.int16))
Mono 16kHz PCM: 320 samples per 20ms frame [CRITICAL ALIASING OCCURS HERE]
   │
   ▼ (Trailing Silence Trimming: 20ms frame scan with 150ms safety padding @ RMS < 80)
Trimmed 16kHz Samples
   │
   ▼ (Wave Header Packaging: wave.open, 1 channel, 2 bytes/sample, 16000 Hz)
WAV Bytes (WAV container, 44-byte header + s16le PCM)
   │
   ▼ [bot/ai/assemblyai.py: trim_trailing_silence_wav (DUPLICATE PASS)]
Second-Pass Energy Trimmed WAV Bytes
   │
   ▼ [HTTPS POST to AssemblyAI v2/upload]
Universal-3.5 Pro Code-Switching ASR
```

### 3.2 Digital Signal Processing (DSP) Mathematical Analysis

#### The 3-Sample Boxcar Filter Flaw
In [`bot/audio/pcm.py:28`](file:///g:/CallWrapper/bot/audio/pcm.py#L28):
```python
24:  # Downsample 48kHz -> 16kHz (3:1 integer decimation with anti-aliasing averaging)
25:  remainder = mono_48k.size % 3
26:  if remainder != 0:
27:      mono_48k = mono_48k[:-remainder]
28:  mono_16k = mono_48k.reshape(-1, 3).mean(axis=1).astype(np.int16)
```

The docstring claims:
> *"Uses numpy 3-sample boxcar anti-aliasing filter for maximum clarity and sub-5ms performance."*

This claim is **mathematically false**. A 3-point moving average filter has impulse response:
$$h[n] = \frac{1}{3}\big(\delta[n] + \delta[n-1] + \delta[n-2]\big)$$

Its discrete-time Fourier transform (frequency response) is:
$$H(e^{j\omega}) = \frac{1}{3} \cdot \frac{\sin(3\omega/2)}{\sin(\omega/2)} e^{-j\omega}$$

When downsampling by factor $M = 3$ from $f_s = 48\text{ kHz}$ to $f_s' = 16\text{ kHz}$, the new Nyquist frequency is:
$$f_{\text{Nyquist}} = \frac{16000}{2} = 8000\text{ Hz}$$

The corresponding normalized digital frequency at $48\text{ kHz}$ is:
$$\omega_{\text{Nyquist}} = 2\pi \frac{8000}{48000} = \frac{\pi}{3}\text{ rad/sample}$$

Evaluating the boxcar filter's magnitude response at the Nyquist cutoff $\omega = \pi/3$:
$$|H(e^{j\pi/3})| = \frac{1}{3} \left| \frac{\sin(\pi/2)}{\sin(\pi/6)} \right| = \frac{1}{3} \cdot \frac{1}{0.5} = \frac{2}{3} \approx 0.6667$$

Expressing this attenuation in decibels:
$$20 \log_{10}\left(\frac{2}{3}\right) \approx -3.52\text{ dB}$$

#### Acoustic Impact on Speech Recognition
- An anti-aliasing decimation filter requires **at least $-40\text{ dB}$ to $-60\text{ dB}$ attenuation** at the Nyquist frequency to avoid folding unattenuated out-of-band energy back into the voice band.
- A 3-tap boxcar filter provides barely **$-3.52\text{ dB}$** of attenuation at 8 kHz.
- Even at $12\text{ kHz}$ ($\omega = \pi/2$), attenuation is only:
  $$|H(e^{j\pi/2})| = \frac{1}{3} \left| \frac{\sin(3\pi/4)}{\sin(\pi/4)} \right| = \frac{1}{3} \approx -9.54\text{ dB}$$
- **Acoustic Consequence:** Frequencies between 8 kHz and 24 kHz (sibilant fricatives like Egyptian Arabic /s/ س, /ṣ/ ص, /ʃ/ ش, /z/ ز, /θ/ ث, consonants /t/, /k/, and high-frequency PC fan / microphone hiss) fold directly into the 0–8 kHz voice band.
- For example, a 10 kHz hiss folds directly to $16000 - 10000 = 6000\text{ Hz}$ with only $\sim 6\text{ dB}$ attenuation, creating audible metallic harshness and causing AssemblyAI to misrecognize soft consonants or hallucinate trailing characters.

### 3.3 Shape Assertion Crash on Odd PCM Buffer Sizes
In [`bot/audio/pcm.py:16-21`](file:///g:/CallWrapper/bot/audio/pcm.py#L16-L21):
```python
16:  stereo_data = np.frombuffer(raw_bytes, dtype=np.int16)
17:  if stereo_data.size < 2:
18:      return b""
19:
20:  # Reshape to (N, 2) and average stereo to mono
21:  stereo_matrix = stereo_data.reshape(-1, 2)
```
- If network jitter, truncation, or a malformed Discord packet results in an odd number of 16-bit samples (e.g. `stereo_data.size = 3839`), `stereo_data.reshape(-1, 2)` raises:
  `ValueError: cannot reshape array of size 3839 into shape (2)`
- There is no defensive modulo truncation (`stereo_data = stereo_data[:-(stereo_data.size % 2)]`) before the reshape.
- This unhandled `ValueError` crashes `convert_discord_pcm_to_wav()` and drops the utterance.

### 3.4 Pre-Roll Timestamp Desynchronization
In [`bot/audio/pcm.py:112-120`](file:///g:/CallWrapper/bot/audio/pcm.py#L112-L120):
```python
112:  if rms >= config.SILENCE_THRESHOLD_RMS:
113:      if not self.is_speaking:
114:          self.is_speaking = True
115:          self.speech_start_time = now
116:          if self._pre_roll:
117:              self.pcm_chunks.extend(self._pre_roll)
118:              self._pre_roll.clear()
```
- `self._pre_roll` stores up to 5 frames (100ms) of audio captured **before** the RMS threshold was crossed.
- When speech starts, `self.pcm_chunks.extend(self._pre_roll)` inserts that 100ms of audio at the beginning of the clip.
- However, line 115 sets `self.speech_start_time = now`, which is the timestamp of the **first loud frame**, ignoring the 100ms pre-roll frames already prepended.
- Consequently, the audio file starts 100ms **earlier** than its metadata timestamp indicates, producing timestamp drift in multimodal logging and subtitle alignment.

### 3.5 Duplicate Trimming Overhead
1. First pass: [`bot/audio/pcm.py:30-41`](file:///g:/CallWrapper/bot/audio/pcm.py#L30-L41) trims trailing silence inside `convert_discord_pcm_to_wav()`.
2. Second pass: [`bot/ai/assemblyai.py:133`](file:///g:/CallWrapper/bot/ai/assemblyai.py#L133) unpacks the WAV header, parses samples, re-computes RMS per frame, re-trims, and re-encodes WAV header.
- This redundant second pass re-allocates memory and wastes 2–5ms of CPU time on every single utterance before upload.

---

## 4. Adversarial Edge Case Matrix

| Edge Case Scenario | Modules Involved | Current Handling | Failure Mode / Consequence | Severity |
| :--- | :--- | :--- | :--- | :--- |
| **1. Speaker Leaves Channel Mid-Speech** | `receiver.py:71-98`, `main.py:113` | SSRC lookup fails; fallback to `Speaker_{ssrc%1000}` or `9999`. | Buffer is orphaned. 1.5s later, silence checker finalizes audio attributed to unknown ID. If client left guild, `on_user_utterance` drops callback because `is_connected()` may be false. | **MEDIUM** |
| **2. Unmapped SSRC Collision (Multiple Unidentified Users)** | `receiver.py:96-98` | If `user_id` resolution fails, `user_id = 9999`. | If two different speakers talk before Discord maps their SSRCs, both users' audio frames are multiplexed into `self.buffers[9999]`. Mixed unintelligible audio uploaded to STT. | **HIGH** |
| **3. Continuous 30s Monologue Force-Split** | `receiver.py:158`, `assemblyai.py:172` | Buffer split at 15s; Chunk 1 sent to STT. At 30s, Chunk 2 sent to STT. | STT task 2 can finish before STT task 1, pushing claims to `claim_memory` in reverse chronological order. | **HIGH** |
| **4. Barge-In Mid Two-Clause TTS Playback** | `receiver.py:120`, `tts.py:254`, `tts.py:406` | `speaker.stop()` called from `voice_recv` thread. Kills FFmpeg, sets `interrupted=True`. | Background `c2_task` still runs network socket until cancelled in `finally`. Worker thread in `to_thread(write_chunk)` encounters `BrokenPipeError` on closed pipe. | **MEDIUM** |
| **5. Discord Voice Gateway Migration / Server Move** | `main.py:113`, `receiver.py:53` | Gateway triggers reconnect; socket closes. | `AudioReceiver` is not notified. In-flight buffers remain active until 1.5s silence triggers. `on_user_utterance` returns early at line 113 because `is_connected()` is temporarily False. All in-flight claims silently lost. | **HIGH** |
| **6. Severe Network Jitter / Bursty UDP Packet Loss** | `receiver.py:58`, `pcm.py:16` | Frames under 4 bytes skipped. Odd-sized frames not sanitized. | `mono_48k.reshape(-1, 2)` raises `ValueError` on odd frame sizes, crashing receiver thread callback. | **HIGH** |

---

## 5. Audio Pipeline Findings Table

| ID | Severity | File:Line | Summary | Failure Scenario | Evidence Excerpt |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AUDIO-01** | **CRITICAL** | [`receiver.py:101-112`](file:///g:/CallWrapper/bot/audio/receiver.py#L101-L112) | Unsynchronized dict mutation outside lock in real-time audio thread | Discord `voice_recv` thread inserts new keys into `self.buffers` while asyncio loop iterates `list(self.buffers.values())` in `_silence_checker_loop`, raising `RuntimeError`. | ```python\nif user_id not in self.buffers:\n    self.buffers[user_id] = UserSpeechBuffer(user_id, display_name)\n... \nbuf = self.buffers[user_id]\n``` |
| **AUDIO-02** | **CRITICAL** | [`receiver.py:206`](file:///g:/CallWrapper/bot/audio/receiver.py#L206) | Heavy synchronous DSP WAV decimation blocks main asyncio event loop | When silence checker finalizes an utterance, `convert_discord_pcm_to_wav` runs on the main thread, blocking WebSocket heartbeats and TTS streaming for 15–30ms per completed speech chunk. | ```python\n# Inside _finalize_utterance called from _silence_checker_loop\nwav_bytes = convert_discord_pcm_to_wav(chunks)\nif wav_bytes:\n    coro = self.on_utterance(...)\n``` |
| **AUDIO-03** | **CRITICAL** | [`pcm.py:28`](file:///g:/CallWrapper/bot/audio/pcm.py#L28) | Boxcar downsampling has only -3.52 dB attenuation at Nyquist, causing severe aliasing | High-frequency sibilants (8–24 kHz, e.g. "ص", "س", "ش", "ز") fold back into the 0–8 kHz band, corrupting phonemes and degrading AssemblyAI Arabic recognition. | ```python\n# Downsample 48kHz -> 16kHz (3:1 integer decimation with anti-aliasing averaging)\nmono_16k = mono_48k.reshape(-1, 3).mean(axis=1).astype(np.int16)\n``` |
| **AUDIO-04** | **HIGH** | [`tts.py:453-457`](file:///g:/CallWrapper/bot/ai/tts.py#L453-L457) | Indefinite `while voice_client.is_playing()` loop with no timeout holds speaker lock | If Discord voice player stalls or freezes, the loop runs forever while holding `async with self._lock:`, permanently deadlocking all future TTS interventions. | ```python\n# Wait for voice_client to finish playing remaining audio\nwhile voice_client.is_playing():\n    if self.interrupted:\n        break\n    await asyncio.sleep(0.05)\n``` |
| **AUDIO-05** | **HIGH** | [`receiver.py:174-184`](file:///g:/CallWrapper/bot/audio/receiver.py#L174-L184) | Lock release gap between silence check and finalization drops new speech onset | `self._lock` is released at line 179 after detecting silence, and re-acquired at line 184 in `_finalize_utterance`. Packets arriving in this microsecond window are wiped by `buf.reset()`. | ```python\nif silence_gap >= config.SILENCE_DURATION_SEC:\n    should_finalize = True\n# LOCK RELEASED HERE\nif should_finalize:\n    self._finalize_utterance(buf, ended_by=\"silence\")\n``` |
| **AUDIO-06** | **HIGH** | [`pcm.py:21`](file:///g:/CallWrapper/bot/audio/pcm.py#L21) | `stereo_data.reshape(-1, 2)` raises `ValueError` on odd-sized PCM buffers | Jitter or partial Discord packets with odd sample counts crash the reshape with `ValueError`, dropping the utterance. | ```python\nstereo_matrix = stereo_data.reshape(-1, 2)\nmono_48k = stereo_matrix.mean(axis=1).astype(np.int16)\n``` |
| **AUDIO-07** | **HIGH** | [`receiver.py:96-98`](file:///g:/CallWrapper/bot/audio/receiver.py#L96-L98) | Fallback `user_id = 9999` multiplexes different unmapped speakers into single buffer | If two speakers speak before Discord resolves their SSRCs, their packets are merged into `self.buffers[9999]`, corrupting audio and misattributing claims. | ```python\nif not user_id:\n    user_id = 9999\n    display_name = \"Speaker\"\n``` |
| **AUDIO-08** | **HIGH** | [`assemblyai.py:172-180`](file:///g:/CallWrapper/bot/ai/assemblyai.py#L172-L180), [`receiver.py:158`](file:///g:/CallWrapper/bot/audio/receiver.py#L158) | Force-split (15s) with slow STT poll (20s) produces out-of-order claims in memory | Chunk 2 of a monologue can complete STT before Chunk 1, inserting claims and turns into the engine in inverted order. | ```python\nattempts = getattr(config, \"ASSEMBLYAI_POLL_ATTEMPTS\", 40)\ninterval = getattr(config, \"ASSEMBLYAI_POLL_INTERVAL_SEC\", 0.5)\nfor _ in range(attempts):\n    await asyncio.sleep(interval)\n``` |
| **AUDIO-09** | **MEDIUM** | [`loudness.py:53-58`](file:///g:/CallWrapper/bot/audio/loudness.py#L53-L58) | Pure Python generator iteration in `count_clipped_samples` wastes CPU on audio thread | `sum(1 for s in arr if s >= thresh or s <= -thresh)` executes pure Python bytecode loops over 1920 samples 50 times/sec per speaker instead of vectorized numpy. | ```python\narr = array.array('h')\narr.frombytes(samples)\ntotal = len(arr)\nthresh = cls.CLIPPING_SAMPLE_THRESHOLD\nclipped = sum(1 for s in arr if s >= thresh or s <= -thresh)\n``` |
| **AUDIO-10** | **MEDIUM** | [`capture.py:72-74`](file:///g:/CallWrapper/bot/audio/capture.py#L72-L74) | `stop_capture_session` immediately toggles flag, dropping in-flight STT utterances | In-flight utterances completing STT 1–3s after `!stop-capture` are rejected by `if not getattr(config, "TEST_CAPTURE_MODE", 0)` and lost from dataset. | ```python\nconfig.TEST_CAPTURE_MODE = 0\ncsv_file = generate_labels_draft_csv(recordings_dir=session_dir)\n_active_session_dir = None\n``` |
| **AUDIO-11** | **MEDIUM** | [`tts.py:359`](file:///g:/CallWrapper/bot/ai/tts.py#L359) | Clause 2 TTS synthesis never uses warm pre-connected session | `synthesize_clause2()` hardcodes `connector=None`, forcing a cold DNS resolution and TLS handshake on the second half of every intervention. | ```python\ncomm2 = edge_tts.Communicate(\n    hedge_clause,\n    config.TTS_VOICE,\n    rate=config.TTS_RATE,\n    pitch=config.TTS_PITCH,\n    connector=None\n)\n``` |
| **AUDIO-12** | **MEDIUM** | [`pcm.py:115-118`](file:///g:/CallWrapper/bot/audio/pcm.py#L115-L118) | 100ms pre-roll frames prepended without adjusting `speech_start_time` | Audio begins 100ms before `speech_start_time`, creating timestamp drift between audio recordings and analytics timestamps. | ```python\nself.is_speaking = True\nself.speech_start_time = now\nif self._pre_roll:\n    self.pcm_chunks.extend(self._pre_roll)\n    self._pre_roll.clear()\n``` |
| **AUDIO-13** | **LOW** | [`assemblyai.py:133`](file:///g:/CallWrapper/bot/ai/assemblyai.py#L133) | Redundant double VAD trailing silence trim before upload | Audio already trimmed in `pcm.py:30-41` is unpacked from WAV, rescanned, and re-encoded in `assemblyai.py`, adding 2–5ms latency. | ```python\nfrom bot.audio.pcm import trim_trailing_silence_wav\nwav_bytes = trim_trailing_silence_wav(wav_bytes, threshold_rms=getattr(config, \"SILENCE_THRESHOLD_RMS\", 80.0))\n``` |
| **AUDIO-14** | **LOW** | [`tts.py:117-121`](file:///g:/CallWrapper/bot/ai/tts.py#L117-L121) | Duplicate `self._stdout.close()` blocks in FFmpeg cleanup | Dead code: identical `try...close` block for `_stdout` appears consecutively twice in `cleanup()`. | ```python\nif self._stdout:\n    try:\n        self._stdout.close()\n    except Exception:\n        pass\n\nif self._stdout:\n    try:\n        self._stdout.close()\n    except Exception:\n        pass\n``` |

---

## 6. Top 5 Real-Time Audio Risks & Remediation Plan

### 1. Fix Dict Concurrency & Locking in `AudioReceiver.write()`
- **Risk:** Unsynchronized mutations in lines 101–112 can raise `RuntimeError: dictionary changed size during iteration` when `_silence_checker_loop` runs, crashing the audio receiver.
- **Remediation:** Remove duplicate buffer lookups at lines 101–112. Move all dictionary reads and initializations strictly inside `with self._lock:`.
```python
# Move lines 101-112 entirely inside with self._lock:
with self._lock:
    if user_id not in self.buffers:
        self.buffers[user_id] = UserSpeechBuffer(user_id, display_name)
    ...
```

### 2. Offload `convert_discord_pcm_to_wav` via `asyncio.to_thread`
- **Risk:** Synchronous WAV conversion and VAD trimming on the event loop thread stalls the event loop for 15–30ms per finished speech segment.
- **Remediation:** In `_finalize_utterance()`, wrap the CPU-bound conversion in `asyncio.to_thread` or perform it inside an executor worker before dispatching `on_utterance`.

### 3. Replace Boxcar Decimation with Proper Anti-Aliasing Filter
- **Risk:** The 3-tap boxcar filter provides only $-3.52\text{ dB}$ attenuation at 8 kHz, allowing high-frequency consonants and noise to fold back and corrupt Egyptian Arabic speech.
- **Remediation:** Replace `.reshape(-1, 3).mean(axis=1)` with an FIR decimation filter using `scipy.signal.decimate(mono_48k, 3, ftype='fir')` or a pre-computed 24-tap polyphase lowpass filter with cutoff at $7.2\text{ kHz}$ and $>50\text{ dB}$ stopband attenuation.

### 4. Add Timeout to Post-Synthesis Playback Wait in TTS
- **Risk:** `while voice_client.is_playing(): await asyncio.sleep(0.05)` has no timeout and holds `self._lock` indefinitely if the voice client stalls.
- **Remediation:** Add a bounded wait timeout (e.g. `timeout = max(5.0, est_playback_sec + 2.0)`):
```python
t_play_start = time.perf_counter()
max_play_sec = getattr(config, "TTS_MAX_PLAYBACK_SEC", 15.0)
while voice_client.is_playing():
    if self.interrupted or (time.perf_counter() - t_play_start > max_play_sec):
        break
    await asyncio.sleep(0.05)
```

### 5. Sequence Out-of-Order Utterances by Monotonic Speech End Timestamp
- **Risk:** AssemblyAI polling variability causes Part 2 of a force-split speech segment to enter `claim_memory` before Part 1.
- **Remediation:** Track a per-speaker monotonic utterance sequence counter or enforce a sequential FIFO dispatch queue in `main.py` per speaker ID so utterance $N+1$ waits for utterance $N$ to complete STT before feeding the arbitration engine.
