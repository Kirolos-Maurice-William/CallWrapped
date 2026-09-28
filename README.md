<div align="center">

# ⚖️ CallWrapped
### Epistemic Referee & Conversational Intelligence Engine for Voice Calls
**Built for the [AssemblyAI Voice Agent Hackathon](https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon) (September 2026)**  
**Engineered by Team Aang & Bumi (Mostafa Abdallah & Kirolos Maurice William)**

[![AssemblyAI Universal-3.5 Pro](https://img.shields.io/badge/AssemblyAI-Universal--3.5_Pro_Batch_STT-0052FF?style=for-the-badge&logo=assemblyai&logoColor=white)](https://www.assemblyai.com/)
[![Groq LPU Inference](https://img.shields.io/badge/Groq-6--Key_LPU_Rotation_Pool-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![Tavily Search](https://img.shields.io/badge/Tavily-Ground--Truth_Search-4CAF50?style=for-the-badge)](https://tavily.com/)
[![Edge TTS Streaming](https://img.shields.io/badge/Edge--TTS-Two--Clause_Streaming-0078D7?style=for-the-badge&logo=microsoft&logoColor=white)](https://github.com/rany2/edge-tts)
[![Discord.py Voice DAVE](https://img.shields.io/badge/Discord.py-Voice_DAVE_E2EE-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![FastAPI + Next.js](https://img.shields.io/badge/Fullstack-FastAPI_+_Next.js_14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Test Suite](https://img.shields.io/badge/Tests-173%2F173_Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![No Mocks](https://img.shields.io/badge/Acceptance_Tests-Zero_Mocks-orange?style=for-the-badge)](tests/)

---

### 🎙️ [Watch the Demo Video](https://youtu.be/placeholder) | 🌐 [Live Web Dashboard](http://localhost:8000) | 🤖 [Invite Discord Bot](https://discord.com/oauth2/authorize?client_id=1550926707517558864&permissions=36718592&scope=bot%20applications.commands)

> *"Every number in this README is measured, not marketed."*

</div>

---

## 📖 Table of Contents
1. [The Problem: Why Traditional Voice Bots Fail in Group Calls](#-the-problem-why-traditional-voice-bots-fail-in-group-calls)
2. [The Core Innovation: Two-Stage Consent Invariant](#-the-core-innovation-two-stage-consent-invariant)
3. [System Architecture](#-system-architecture)
4. [Key Engineering Components](#-key-engineering-components)
   - [A. Speech Recognition Pipeline (AssemblyAI Universal-3.5 Pro Batch)](#a-speech-recognition-pipeline-assemblyai-universal-35-pro-batch)
   - [B. Split Classification Architecture (Instant vs. Batched)](#b-split-classification-architecture-instant-vs-batched)
   - [C. Pure Python Dispute Tracker FSM (Shadow Mode)](#c-pure-python-dispute-tracker-fsm-shadow-mode)
   - [D. 6-Key Groq LPU Rotation Pool & TPD Pacing](#d-6-key-groq-lpu-rotation-pool--tpd-pacing)
   - [E. Streaming Two-Clause TTS with Pre-Warm Handshake](#e-streaming-two-clause-tts-with-pre-warm-handshake)
   - [F. Scientific Rigor: The Acoustic Fusion Ablation Study](#f-scientific-rigor-the-acoustic-fusion-ablation-study)
5. [Taxonomy v3 (15 Semantic Categories & Conversational Streaks)](#-taxonomy-v3-15-semantic-categories--conversational-streaks)
6. [Empirical Evaluation on Real Sessions (Scorecard Table)](#-empirical-evaluation-on-real-sessions-scorecard-table)
7. [Traditional Prefix Commands](#-traditional-prefix-commands)
8. [Live Judge Dashboard](#-live-judge-dashboard)
9. [Privacy & Epistemic Safety](#-privacy--epistemic-safety)
10. [Known Limitations](#-known-limitations)
11. [Rejected Alternatives (Evidence-Based Engineering)](#-rejected-alternatives-evidence-based-engineering)
12. [Future Roadmap](#-future-roadmap)
13. [Reproducibility & Quick Start](#-reproducibility--quick-start)
14. [Test Suite Verification (173 / 173 Passing)](#-test-suite-verification-173--173-passing)
15. [Audits & Independent Quality Control](#-audits--independent-quality-control)
16. [Team & Contact](#-team--contact)

---

## 💥 The Problem: Why Traditional Voice Bots Fail in Group Calls

In multiplayer gaming calls (Discord lounges, Counter-Strike, Valorant, FIFA), study groups, and podcasts, participants constantly make contradictory factual claims with absolute confidence:
> **Ahmed:** *"يا جدعان كارت الـ RTX 5070 نازل بـ 16 جيجا VRAM رسمي من نفيديا!"*  
> *(Bro, the RTX 5070 is officially launching with 16GB VRAM from Nvidia!)*  
> **Karim:** *"لا يا عم 12 جيجا GDDR7 بس، مفيش 16 جيجا دي خالص."*  
> *(No way man, it's only 12GB GDDR7, there is no 16GB at all!)*

```
Why Standard Voice Bots Fail Here:
❌ Wake-words ("Hey Siri", "OK Google") are never spoken mid-argument.
❌ Bots that barge in uninvited to contradict speakers create socially aggressive disruption and get kicked immediately ("Annoying Bot" syndrome).
❌ Bilingual code-switching (Egyptian Arabic vernacular mixed with English technical specs) breaks standard models.
❌ Verifying private friends' conversations ("محمد قال إنه اشترى عربية") leaks privacy and causes hallucinated searches.
❌ Web search and synthesis delays cause bots to chime in long after the group has changed the subject.
```

**CallWrapped solves this by acting as a respectful, culturally attuned epistemic referee and real-time conversation intelligence engine.**

---

## 🎯 The Core Innovation: Two-Stage Consent Invariant

An AI agent that speaks unsolicited verdicts into a private human conversation violates fundamental social boundaries. CallWrapped strictly enforces the **Two-Stage Consent Invariant**:

```mermaid
stateDiagram-v2
    [*] --> LISTENING
    LISTENING --> OFFERED: Contradiction / Factual Claim Detected
    note right of OFFERED
        Bot posts offer to TEXT CHANNEL & DASHBOARD ONLY:
        "🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟
         قول «شوفها» أو اكتب !check"
        (Edge-TTS TLS pre-warming & Tavily search prefetch start in background)
        BOT REMAINS COMPLETELY SILENT IN VOICE!
    end note
    
    OFFERED --> CONFIRMED: Verbal ("شوفها" / "اتأكد") or Chat (!check)
    OFFERED --> LISTENING: 30s Timeout (Logged as ABSTAIN: offered_not_confirmed)
    
    state CONFIRMED {
        [*] --> DeliverVerdict
        DeliverVerdict --> Clause1_Fact: Streamed via Edge-TTS (Fact + Source)
        Clause1_Fact --> Clause2_Hedge: Background synthesized hedge
    }
    CONFIRMED --> LISTENING: 180s Cooldown per topic
```

1. **Stage 1 (The Polite Offer):** When a factual disagreement or disputed entity is detected, the bot **never speaks into voice uninvited**. Instead, it posts a silent, polite offer to the Discord text channel and live dashboard:  
   *"🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟ قول «شوفها» أو اكتب !check"*  
   In the background, the bot immediately begins pre-fetching search evidence from Tavily and pre-warming a TLS session to Edge-TTS.
2. **Stage 2 (The Human Confirmation):** If and only if a speaker explicitly confirms—either verbally (*"شوفها يا حكم"*, *"اتأكد"*) or via text command (`!check`)—the bot synthesizes and delivers the resolution in voice.
3. **Honest Abstention:** If 30 seconds elapse without confirmation, the offer expires silently (`ABSTAIN: offered_not_confirmed`). If web retrieval returns zero reliable sources, the bot delivers an honest fallback (*"تعذر التحقق من المعلومة من مصادر موثوقة"*) rather than guessing.

---

## 🏗️ System Architecture

```text
                               Discord Voice Channel (Multi-Party Audio)
                                                  │
                                   [Discord DAVE E2EE MLS Decryption]
                                                  │
                                      AudioReceiver (RMS Energy VAD)
                                 (Lock-protected per-speaker 16kHz PCM)
                                                  │
                                                  ▼
                                 AssemblyAI Universal-3.5 Pro Batch
                                   (Chunk Upload & Poll STT Pipeline)
                                                  │
                  ┌───────────────────────────────┴───────────────────────────────┐
                  ▼                                                               ▼
        [Instant Claim Path]                                            [Batched Analytics Path]
       Slim Prompt (<400 tokens)                                          75s Aggregation Window
        Groq LPU (Qwen 3.8-27b)                                           Groq LPU (Qwen 3.8-27b)
                  │                                                               │
                  ▼                                                               ▼
        DisputeTracker Core FSM                                           15-Topic Classifier &
       (SHADOW MODE: Decay/Eviction)                                       Anger Episode Counter
                  │                                                               │
                  ├───────────────────────────────┐                               ▼
                  │ [Contradiction Detected]      │ [Casual Banter]      SessionStatsTracker
                  ▼                               ▼                     (Talk Share / Streaks /
          Two-Stage Referee                 Ignored (Silent)              Arabic Recap Generator)
                  │                                                               │
                  ▼                                                               │
       Stage 1: Text Channel Offer                                                │
      ("أتحقق؟ قول «شوفها» أو !check")                                             │
      (Pre-warm Edge-TTS DNS/TLS +                                                │
      Background Tavily Evidence Search)                                          │
                  │                                                               │
       [Speaker Confirms: "شوفها" / !check]                                       │
                  │                                                               │
                  ▼                                                               │
       Stage 2: Spoken Two-Clause TTS                                             │
       Clause 1: Fact ("المصدر بيقول...")                                         │
       Clause 2: Hedge ("ممكن في سياق فاتني...")                                   │
                  │                                                               │
                  ├───────────────────────────────────────────────────────────────┘
                  ▼
         FastAPI Event Hub (WebSocket: /api/ws)
                  │
                  ▼
     Next.js 14 Live Judge Dashboard
    (Dispute Cards, Latency Ticker,
     Topical Share %, Anger Receipts)
```

---

## 🚀 Key Engineering Components

### A. Speech Recognition Pipeline (AssemblyAI Universal-3.5 Pro Batch)

CallWrapped utilizes **AssemblyAI Universal-3.5 Pro** operating via batch upload and polling:
- **Audio Preprocessing:** 16kHz 16-bit mono linear PCM captured from Discord DAVE E2EE is demuxed per-speaker using thread-safe locks (`threading.Lock`) and trimmed of trailing silence energy (`EXP 1`).
- **Tuned Accuracy:** Evaluated against Egyptian Arabic MGB-3 challenge clips (`audit/exp*.py`):
  - Baseline WER: **30.77%** ($\approx 30.8\%$)
  - Energy-trimmed silence (`EXP 1`): **29.54%** (-1.23% WER improvement, p50 -18ms)
  - 160-item keyterms ablation (`EXP 2`): **28.62%** WER, **90.0%** number accuracy
  - 44 custom spelling mappings (`EXP 3`): **22.15%** Corpus WER, **19.40%** Clean Audio WER, **90.0%** number accuracy
  - Language configuration (`EXP 5`): Fixed `language_code="ar"` matched 22.15% WER with +92ms faster p50.
  - *Data leakage caveat:* Custom spellings were tuned and evaluated on the same 17-clip MGB-3 subset. On spontaneous, multi-party live Discord calls with rapid overlap, micro WER measures **36.9%–44.7%** (see [Empirical Evaluation](#-empirical-evaluation-on-real-sessions-scorecard-table)).
- **STT Processing Latency:** Median processing latency p50 = **3.06s** across production batches.
- **Streaming Exploration:** Streaming STT (WebSocket) was explored and benchmarked (see `assemblyai_capability_report.json`) but deliberately deferred — the batch pipeline is the verified production path. Streaming migration is gated on a side-by-side WER benchmark (see Roadmap).

### B. Split Classification Architecture (Instant vs. Batched)

Running full topic modeling, multi-speaker streak tracking, and claim extraction on every 1.5s utterance would destroy token quotas and introduce severe latency. CallWrapped separates these tasks into two pipelines:
- **Instant Claim Path (`claim_detector.check_claim`):** Uses an ultra-slim prompt ($\le 400$ tokens) on Groq LPU executing in sub-second (measured 276ms-1s depending on load). Only extracts `is_factual_claim`, `claim`, `entity`, and `metric`. Directly feeds conflict detection.
- **Batched Analytics Path (`claim_detector.batch_classify`):** Buffers speech utterances over a 75-second window. Flushes up to 15+ utterances in a single call (measured: 15 lines, 1817ms) using strict JSON schema. Computes 15-category topic distribution, conversational streaks, and anger receipts for `!recap` and the web dashboard.

### C. Pure Python Dispute Tracker FSM (Shadow Mode)

Engineered in [`bot/arbitration/dispute_tracker.py`](file:///g:/CallWrapper/bot/arbitration/dispute_tracker.py) with zero external dependencies:
- **Proposition Families:** Normalizes entities and clusters opposing statements under common slots (e.g. `RTX 5070` with memory values `16GB` vs `12GB`).
- **Thread Lifecycle:** `TRACKING → CONFLICT_DETECTED → OFFERED → RESOLVED / ABSTAINED`.
- **Temporal Decay & Eviction:** Inactive claims decay over 150 seconds. Memory is capped with FIFO eviction (500 items) to prevent unbounded memory growth.
- **Shadow Mode Status:** The dispute tracker FSM currently runs in **shadow mode** (`audit/shadow/`), logging transitions and validating state coherence against real session replays before being granted authoritative gating over live voice.

### D. 6-Key Groq LPU Rotation Pool & TPD Pacing

To prevent service interruption across free-tier limits (TPD / RPM), CallWrapped implements an autonomous multi-key rotation engine (`bot/ai/groq.py`):
- **Dynamic Discovery:** Automatically registers up to 6 keys (`GROQ_API_KEY` through `GROQ_API_KEY_6`).
- **HTTP 429 Cascade:** If a key hits rate limits, the client zeroes remaining tokens and instantly cascades to the next healthy key in the pool.
- **HTTP 401/403 Eviction:** Permanently purges dead or unauthorized keys from the live pool.
- **TPD Pacing Discipline:** Rate-limit sleep is capped at 2.0s max, ensuring free-tier quotas do not freeze the asyncio event loop.

### E. Streaming Two-Clause TTS with Pre-Warm Handshake

When a dispute is confirmed, the bot delivers a two-clause resolution over Microsoft Edge-TTS (`bot/ai/tts.py`):
- **Pre-Warm Handshake:** While Stage 1 is waiting for human confirmation, the bot pre-establishes a live TLS connection to Microsoft Edge-TTS. Reusing this warm connection reduces handshake latency to **0ms**.
- **Clause 1 (The Fact):** Delivers the factual finding and source immediately (unit-measured TTFB: **80ms**; live end-to-end TTFB from Cairo: **~1.0s**):  
  *"تصحيح سريع: المصدر اللي لقيته بيقول كارت RTX 5070 بيجي بـ 12 جيجا بايت VRAM مش 16."*
- **Clause 2 (The Social Hedge):** Synthesizes asynchronously while Clause 1 plays and queues without audible gaps:  
  *"ممكن يكون في سياق فاتني — المصدر ظاهر في الداشبورد."*
- **Live Latency Floor:** Due to batch STT chunking and polling, the measured live $T_{\text{perceived}}$ from Cairo sits between **2.6s and 3.5s**.
- **Barge-in Support:** If a user begins speaking during playback, the audio stream cancels immediately to prevent talking over human participants.

### F. Scientific Rigor: The Acoustic Fusion Ablation Study

Many voice agent architectures add acoustic volume tracking assuming louder speech directly implies anger. We tested this hypothesis rigorously.

We built a complete acoustic loudness pipeline (`SpeakerLoudnessBaseline` tracking log-RMS dB energy and robust MAD $z$-scores with `fuse_anger` late fusion) and evaluated it against **53 real captured clips** across 3 human-labeled dispute sessions (`audit/FINDING_ACOUSTIC_FUSION.md`):

| Evaluation Subset | Text-Only Accuracy | Fused Accuracy | Net Lift | Finding |
|---|---|---|---|---|
| **Full 3-Session Corpus (53 clips)** | **37.7%** (20/53) | **32.1%** (17/53) | **-5.7%** | Net Regression |
| **Shouted / Elevated Subset (37 clips)** | **10.8%** (4/37) | **2.7%** (1/37) | **-8.1%** | Severe Regression |

#### Empirical Root Causes:
1. **Acoustic Magnitude Inversion:** In Egyptian group calls, friendly laughter and playful banter reached extreme relative spikes ($z = 14.98\text{--}24.24$), whereas genuine angry arguments only reached $z = 2.8\text{--}3.5$. Loudness magnitude correlated with excitement, not anger.
2. **Unreachable Mathematical Slope:** For utterances classified as text-neutral ($p_{\text{text}} = 0.0$), the late fusion formula required $z \ge 4.375$ to reach the mild anger threshold ($p_{\text{fused}} \ge 0.45$), making it mathematically impossible to boost natural shouting clips ($z \in [2.8, 3.5]$).
3. **Session-Wide Baseline Absorption:** When a dispute escalated and all participants raised their voices simultaneously, running per-speaker baselines absorbed the volume increase, collapsing relative $z$-scores back to $1.0\text{--}2.2$.

**Production Decision:** In accordance with empirical evidence, acoustic fusion is **disabled by default in production** (`ACOUSTIC_FUSION_ENABLED=0`). All acoustic telemetry is retained in shadow mode (`audit/shadow/loudness_shadow.jsonl`) for dataset collection.

---

## 🏷️ Taxonomy v3 (15 Semantic Categories & Conversational Streaks)

The topic classifier categorizes dialogue into 15 discrete categories (13 semantic topics + `other` + `null_topic`):
```
football | politics | music | movies | gaming | tech | food | travel |
study_work | health | cars | money | personal | other | null_topic
```

### Linguistic & Dialogue Dynamics:
- **Schegloff (1982) Listener Backchannel Rule:** Short acknowledgments (`"تمام"`, `"أيوة"`, `"شايف"`) under 2.0 seconds are classified as `null_topic`. They do not steal the conversational floor or interrupt the active speaker's streak.
- **SwDA Streak Bridging:** If a speaker is talking about a topic (`football`), utters a brief conversational check (`"سامعني؟"` $\rightarrow$ `null_topic`), and continues within 5 seconds, the streak remains bridged and continuous.
- **Topical Talk Share:** `null_topic` utterances are excluded from the denominator of topic percentages, ensuring topic metrics reflect actual topical discourse rather than filler words.

---

## 📊 Empirical Evaluation on Real Sessions (Scorecard Table)

CallWrapped was evaluated on **4 distinct real-world recorded human sessions** totaling 78 clips with human ground-truth labels in `audit/score_results_batch*.md`:

| Metric | Batch 1 (Casual)<br>`2026-09-26_1817` | Batch 2 (Movies)<br>`2026-09-27_1803` | Batch 3 (World Cup)<br>`2026-09-27_1806` | Batch 4 (Real Estate)<br>`2026-09-27_1808` | Benchmark / Target |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Clips Evaluated** | 25 clips | 12 clips | 19 clips | 22 clips | 78 clips total |
| **Micro WER (Corpus)** | **40.10%** | **40.18%** | **44.69%** | **36.92%** | Spontaneous overlap |
| **Clean Audio Micro WER** | **40.10%** | **40.18%** | **44.69%** | **36.92%** | Clean segments |
| **Number Accuracy** | **100.0%** (3/3) | n/a (0 samples) | **100.0%** (3/3) | **85.2%** (23/27) | $\ge 90\%$ target |
| **Topical Accuracy** | **85.7%** (6/7) | **87.5%** (7/8) | **77.8%** (14/18) | **95.2%** (20/21) | $\ge 80\%$ target |
| **Null Detection Accuracy** | **77.8%** (14/18) | **25.0%** (1/4) | **100.0%** (1/1) | **100.0%** (1/1) | $\ge 80\%$ target |
| **Claim Agreement** | **96.0%** (24/25) | **41.7%** (5/12)* | **42.1%** (8/19)* | **59.1%** (13/22)* | $\ge 75\%$ target |
| **Anger Agreement** | **100.0%** (25/25) | **100.0%** (12/12) | **26.3%** (5/19) | **18.2%** (4/22) | Text-only model |
| **False Anger Rate** | **0.0%** (0/25) | **0.0%** (0/12) | **0.0%** (0/4) | **0.0%** (0/4) | $\le 15\%$ target |
| **False Referee Interventions** | **0 false offers** | **0 false offers** | **0 false offers** | **0 false offers** | **0 across all calls** |

*\*Label-Rule Caveat on Claim Agreement:* In Batches 2–4, human annotators labeled all argumentative conversational turns as claims (e.g. debating movie plot points or shouting price guesses). The classifier enforces a strict extraction rule requiring a verifiable entity and numeric/metric slot. Consequently, speculative banter was classified as non-claims, lowering raw agreement but preserving epistemic precision.

> **Shadow-mode dispute tracker:** 3/3 agreement with human judgment on dispute presence across all sessions (live referee: 0 false interventions, honest abstention on unverifiable claims).

### Ground-Truth Resolution Highlights:
- **World Cup Final Dispute (Batch 3):** Two speakers disputed the 2022 World Cup winner (Argentina vs France/Spain/Australia). The bot retrieved official ground truth citing **FIFA.com** and verified Argentina's victory upon confirmation.
- **Agricultural Land Prices (Batch 4):** Speakers argued over price per feddan in rural Egypt. Because agricultural land prices fluctuate wildly and lack authoritative indexed indices, the bot performed an **honest abstention** without hallucinating numbers.
- **Private Entity Refusal:** Disagreements regarding private individuals (*"محمد قال الماتش الساعة 8"*) are automatically refused (`rejection_reason: "private_entity"`). The bot distinguishes private friends from public entities (`محمد` $\ne$ `محمد صلاح`).
- **Hallucinated Findings:** **0** across all sessions.

---

## 🎮 Traditional Prefix Commands

CallWrapped uses standard Discord `!` prefix commands (no slash commands):

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `!join` | None | Connects the bot to your current voice channel. |
| `!start` | None | Posts consent notice + activates Fact Check Mode (offers-only refereeing). |
| `!check` | None | Confirms a pending dispute check offer and triggers spoken two-clause resolution. |
| `!arbitrate` | `<claim>` | Manually triggers an on-demand fact check offer for a specific factual claim. |
| `!recap` | None | Generates session conversational recap (talk-time share, streaks, frustration receipts). |
| `!stats` | None | Displays live session statistics summary in chat. |
| `!status` | None | Reports active session phase, dispute counts, and latency averages. |
| `!dashboard` | None | Displays the URL and connection status for the local Next.js Live Judge Dashboard. |
| `!privacy` | None | Displays the privacy policy, data retention details, and ephemeral memory rules. |
| `!judge-mode` | None | Runs the 7-card adversarial test harness against live APIs to verify arbitration. |
| `!start-capture` | None | Opt-in admin command: initiates recording raw audio clips to timestamped session folder. |
| `!stop-capture` | None | Concludes audio capture and automatically exports `labels_DRAFT.csv` for scoring. |
| `!clear` | None | Resets session memory, dialogue queues, and arbitration history. |
| `!leave` | None | Disconnects the bot from voice and purges all active session context. |

---

## 🖥️ Live Judge Dashboard

Served locally at `http://localhost:8000` via FastAPI backend and Next.js 14 frontend:
- **CORS Access Control:** `CORS_ORIGINS` in `.env` controls dashboard access and defaults to `http://localhost:3000,http://127.0.0.1:3000`.
- **Active Dispute Cards:** Displays real-time side-by-side claims, status badges (`OFFERED`, `CHECKING`, `RESOLVED`, `ABSTAINED`, `REFUSED_PRIVATE`), and direct source links.
- **Live Latency Tickers:** Millisecond-accurate telemetry for STT poll duration, Groq LPU inference, Tavily search retrieval, and Edge-TTS synthesis.
- **Conversational Analytics:** Real-time speaker talk-time distribution bar, Streak Champion indicator, frustration quote receipts, and 15-category topical share.

---

## 🔒 Privacy & Epistemic Safety

1. **Session-Only Ephemeral Memory:** CallWrapped does not store long-term conversational profiles. When `!leave` or `!clear` is invoked, all dialogue memory, speaker stats, and pending claims are completely wiped.
2. **Mandatory Privacy Notice:** Upon connecting to a voice channel with `!start`, the bot posts an explicit transparency notice in the text channel outlining its operating policies.
3. **Private-Entity Refusal:** Verified by `tests/test_phase_b_referee_gates.py` and `test_dispute_cards_api.py`. Statements concerning private non-public individuals are automatically refused to protect user privacy.
4. **Admin-Only Audio Capture:** `TEST_CAPTURE_MODE` is strictly an opt-in developer/administrative tool for generating benchmark datasets. It is disabled by default in production.

---

## ⚠️ Known Limitations

1. **Spontaneous Conversational Overlap WER:** While AssemblyAI Universal-3.5 Pro achieves **22.15%** WER on clean Egyptian Arabic benchmark clips, spontaneous Discord gaming voice chat with frequent interruptions, background game sounds, and overlapping speech yields **36.9%–44.7%** micro WER.
2. **Acoustic Loudness Fusion Disabled:** Volume magnitude alone proved unviable for emotion classification in group calls (causing a **-5.7%** net accuracy degradation). It is disabled in production pending pitch/F0 contour modeling.
3. **Batch STT Latency Floor:** The current production pipeline uploads audio chunks and polls AssemblyAI's batch API. This introduces an inherent **2.6s–3.5s** latency floor from utterance completion to transcript delivery.
4. **Taxonomy Frozen at v3:** The topic classification enum is strictly frozen at 15 categories. Unseen fringe topics fall back to `other`. Open-vocabulary dynamic clustering is not yet deployed.
5. **Frontend Build Prerequisite:** The dashboard requires the frontend to be built before first use. start_all.bat does NOT build the frontend automatically.

---

## 🚫 Rejected Alternatives (Evidence-Based Engineering)

In building CallWrapped, several intuitive design directions were explored, tested, and deliberately rejected based on empirical data:

1. **Immediate Streaming STT Migration:** While WebSocket streaming (`u3-rt-pro`) was explored and benchmarked in `assemblyai_capability_report.json`, migration was parked rather than rushed. Production voice reliability requires an empirical, side-by-side WER evaluation on Egyptian code-switched dialect before replacing the batch upload pipeline.
2. **LLM Post-ASR Error Correction:** Tested in `EXP 4` (`audit/exp4_selective_groq_correction.py`). Feeding raw ASR transcripts to Groq Qwen for spelling correction degraded Corpus WER by **+1.54%** (23.69% vs 22.15%) and added 600ms latency without eliminating number errors. Rejected based on empirical evidence.
3. **LLM Prompt-Based Unit Conversion:** Prompting language models to perform Egyptian currency and land unit conversions (قيراط $\leftrightarrow$ فدان $\leftrightarrow$ جنيه) resulted in arithmetic hallucinations. Unit validation must be performed by deterministic Python validators rather than LLM token guessing.
4. **Server-Wide Audio Muting:** Forcing server-side mute on call participants during arbitration was rejected: Discord API rate limits (`PATCH /guilds/{id}/members/{id}`) trigger 429 lockouts during rapid multi-user toggles, and muting friends mid-game creates unacceptable social friction.

---

## 🗺️ Future Roadmap

- [ ] **Streaming STT Rollout:** Deploy full-duplex WebSocket streaming STT using AssemblyAI Universal-3.5 Pro, gated on maintaining $\le 25\%$ WER on Egyptian dialect audio.
- [ ] **Authoritative Dispute Tracker FSM:** Transition the pure Python Dispute Tracker from shadow mode to the primary arbitration controller following full multi-session replay validation.
- [ ] **Acoustic Fusion v2:** Re-introduce acoustic emotion detection incorporating fundamental frequency ($F_0$) pitch tracking, vocal jitter, and room-relative energy baselines to accurately separate laughter from anger.
- [ ] **Open-Vocabulary Topic Discovery:** Implement unsupervised clustering for conversational topics that fall outside the 15 frozen semantic categories.

---

## ⚡ Reproducibility & Quick Start

### Prerequisites
- **Python:** 3.12+ (tested on Windows 11 & Linux)
- **FFmpeg (REQUIRED for TTS):** `winget install Gyan.FFmpeg` (Windows) / `apt install ffmpeg` (Linux). Without it, the bot crashes on any spoken verdict.
- **Linux System Packages:** `libopus0`, `libopus-dev`, `libffi-dev` (required for Discord voice receive)
- **Node.js:** 18+ for frontend dashboard
- **API Keys Required:**
  - `ASSEMBLYAI_API_KEY`: Speech-to-text processing.
  - `GROQ_API_KEY`: Epistemic reasoning and classification (supports up to 6 keys: `GROQ_API_KEY_2` through `6`).
  - `TAVILY_API_KEY`: Factual web ground-truth retrieval.
  - `DISCORD_BOT_TOKEN`: Discord application bot token with voice and message intents.

### 1. Installation
```bash
git clone https://github.com/Mostafa23/call-agent.git
cd call-agent
python -m venv backend/venv
backend/venv/Scripts/activate     # Windows
# source backend/venv/bin/activate  # Linux
pip install -r requirements.txt
```

### 2. Configuration
```bash
cp .env.example .env
```
Populate your API keys in `.env`. Ensure `ACOUSTIC_FUSION_ENABLED=0` remains set. `CORS_ORIGINS` in `.env` controls dashboard access and defaults to `http://localhost:3000,http://127.0.0.1:3000`.

### 3. Build Frontend Dashboard
```bash
cd frontend && npm install && npm run build && cd ..
```

### 4. Launch Services
Run the all-in-one launcher:
```bash
start_all.bat
```
*(Or launch `start_backend.bat`, `start_bot.bat`, and `start_frontend.bat` in separate terminals).*

### 5. Experience the Golden Demo (Step-by-Step)
1. Join a voice channel in your Discord server and type `!join`.
2. Activate Fact Check Mode by typing `!start`.
3. Open the Live Dashboard at `http://localhost:8000`.
4. Speak the clashing claims in voice (or type `!simulate` to run the multi-party audio pipeline):
   - **Speaker 1:** *"يا جدعان كارت الـ RTX 5070 نازل بـ 16 جيجا VRAM رسمي من نفيديا!"*
   - **Speaker 2:** *"لا يا عم 12 جيجا GDDR7 بس، مفيش 16 جيجا دي خالص."*
5. **Stage 1 (Silent Text Offer):** The bot posts to the text channel and dashboard:  
   *"🤖 شفت اتنين بيقولوا نفس المعلومة بشكل مختلف — أتحقق؟ قول «شوفها» أو اكتب !check"*  
   *(Notice: The bot remains completely silent in voice).*
6. **Stage 2 (Confirmation):** Say *"شوفها يا حكم"* in voice (or type `!check` in chat).
7. **Spoken Resolution:** The pre-warmed TTS stream delivers the factual verdict with official Nvidia citations, while the dashboard highlights the dispute card with Verified/Refuted badges and latency telemetry.

---

## 🧪 Test Suite Verification (173 / 173 Passing)

CallWrapped enforces an unyielding testing discipline: **acceptance tests run against live production APIs with zero mocks.**

To run the complete test suite:
```bash
backend/venv/Scripts/python -m unittest discover tests
```

```text
Ran 173 tests in 125.700s

OK
```

Every commit and bug fix since base commit `701a7c0` is traced with a dedicated acceptance test in [`REGRESSION_LEDGER.md`](file:///g:/CallWrapper/REGRESSION_LEDGER.md).

---

## 🛡️ Audits & Independent Quality Control

The CallWrapped codebase has undergone continuous verification through three comprehensive quality audits:
- **Audit #1 (`audit/PROJECT_AUDIT.md`):** Identified initial event loop bottlenecks, missing dictionary error bounds, and raw latency tracking gaps.
- **Audit #2 (`audit/quality/AUDIT_REPORT_2.md`):** Remediated in commit `2f8ce46` (BOM-safe UTF-8-sig loader, corruption warnings, Groq pool expansion, dead code elimination).
- **Audit #3 (Adversarial Multi-Model Cross-Review):** Evaluated by independent adversarial review models. Resulted in fixes for TTS timeout fallbacks, `FifoSet` capacity capping, atomic CSV writes, thread-safe AudioReceiver locks, and atomic offer confirmations (commits `488f632`, `8f674f3`, `5722d11`, `e2e9bff`).

---

## 👥 Team & Contact

Developed by **Team Aang & Bumi** for the **AssemblyAI Voice Agent Hackathon 2026**:

| Member | Institution | Core Focus | Contact |
| :--- | :--- | :--- | :--- |
| **Mostafa Abdallah** | Faculty of AI, Egyptian Chinese University (ECU) | • Two-stage referee state machine & consent invariant<br>• AssemblyAI batch STT integration & silence trimming<br>• Discord voice DAVE E2EE audio demuxing & VAD | [![GitHub](https://img.shields.io/badge/GitHub-Mostafa23-181717?style=flat&logo=github)](https://github.com/Mostafa23) [![LinkedIn](https://img.shields.io/badge/LinkedIn-Mostafa_Abdallah-0A66C2?style=flat&logo=linkedin)](https://www.linkedin.com/in/mostafa%D9%90abdallah/) |
| **Kirolos Maurice William** | Faculty of AI, Egyptian Chinese University (ECU) | • Groq LPU split classification & 6-key rotation pool<br>• Tavily search verification & private-entity gating<br>• Next.js 14 live judge dashboard & WebSocket hub | [![GitHub](https://img.shields.io/badge/GitHub-Kirolos--Maurice--William-181717?style=flat&logo=github)](https://github.com/Kirolos-Maurice-William) [![LinkedIn](https://img.shields.io/badge/LinkedIn-Kirolos_Maurice-0A66C2?style=flat&logo=linkedin)](https://www.linkedin.com/in/kirolos-maurice-william/) |

---

<div align="center">
<b>CallWrapped — Grounded Truth and Conversational Clarity for Voice Calls.</b>
</div>
