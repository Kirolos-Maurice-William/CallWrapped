# AUDIT PASS 3/4: Config, Security, Deployment, Repo Hygiene

**Audit Date:** 2026-09-28  
**Scope:** `bot/config.py`, `backend/app/config.py`, `.env.example`, `.env` (structure only), `requirements.txt`, `backend/requirements.txt`, `start_*.bat`, `.gitignore`, `README.md`  
**Secondary Scope:** `backend/app/main.py`, `backend/app/routes.py`, `backend/app/database.py`, `bot/events/publisher.py`, `frontend/package.json`  
**Review Type:** Hostile Code-Level Audit (Read-Only on project code)  
**Status:** COMPLETE — 12 Config, Security & Deployment Findings Identified  

---

## Executive Summary

This audit evaluated CallWrapped from the perspective of an external hackathon judge or developer cloning the repository on a fresh machine. It examined setup reproducibility across Windows and Linux, secrets transit and storage security, CORS configuration, API endpoint protection, dependency licensing, and repository hygiene.

The audit revealed critical deployment blockers and security exposures:
1. **The 404 Dashboard Trap on Fresh Clones ([DEPLOY-01](file:///g:/CallWrapper/README.md#L374-L378)):**  
   [`start_all.bat`](file:///g:/CallWrapper/start_all.bat) directs users to `http://localhost:8000`, relying on FastAPI serving static files from `frontend/out`. However, `frontend/out/` is listed in [`.gitignore`](file:///g:/CallWrapper/.gitignore#L18) and does not exist in a fresh git clone. The [`README.md`](file:///g:/CallWrapper/README.md) Quick Start never instructs the user to run `npm install` and `npm run build` inside `frontend/`, nor does `start_all.bat` launch `start_frontend.bat`. When a judge opens `http://localhost:8000`, FastAPI returns `{"detail":"Not Found"}`.
2. **Unquoted System Dependency: FFmpeg Missing from Documentation ([SETUP-01](file:///g:/CallWrapper/README.md#L350-L365)):**  
   [`bot/ai/tts.py:42`](file:///g:/CallWrapper/bot/ai/tts.py#L42) spawns `ffmpeg` as a subprocess for real-time PCM audio streaming. If FFmpeg is not pre-installed on the host system PATH, the voice bot immediately crashes with `FileNotFoundError` upon speaking any verdict. The [`README.md`](file:///g:/CallWrapper/README.md) contains zero mentions of FFmpeg as a prerequisite.
3. **User PII Leaked to Untracked Shadow Log ([SEC-01](file:///g:/CallWrapper/bot/audio/loudness.py#L427-L431)):**  
   [`bot/audio/loudness.py:427`](file:///g:/CallWrapper/bot/audio/loudness.py#L427) appends `was_loud` records containing actual Discord speaker display names and timestamps to `audit/shadow/loudness_shadow.jsonl`. This path is **not gitignored**. Running `git add .` or `git add audit/` risks publishing private Discord user names into a public GitHub repository.
4. **All Backend Endpoints are Completely Unauthenticated ([SEC-02](file:///g:/CallWrapper/backend/app/routes.py#L400-L509)):**  
   Every FastAPI route (`POST /api/events`, `POST /api/reset`, `POST /api/demo/run`, `GET /api/live`, and `WebSocket /api/ws`) lacks authentication, API key validation, or rate limiting. Any client on the network can inject synthetic transcripts, wipe active session history, or snoop on private voice call transcripts in real time.
5. **Orphaned Duplicate `backend/requirements.txt` with Ghost Dependency ([DEP-01](file:///g:/CallWrapper/backend/requirements.txt#L11)):**  
   [`backend/requirements.txt`](file:///g:/CallWrapper/backend/requirements.txt) is an unsynchronized duplicate of root [`requirements.txt`](file:///g:/CallWrapper/requirements.txt). It includes `google-genai>=0.1.0`, an unused dependency from a legacy prototype that is never imported in the active codebase.

---

## 1. Setup Reproducibility & Fresh Install Simulation

### 1.1 Fresh Windows Simulation (Following README Exactly)

| Step | README Instruction | Windows Behavior | Outcome / Breaking Point |
| :--- | :--- | :--- | :--- |
| **1. Clone** | `git clone https://github.com/Mostafa23/call-agent.git`<br>`cd call-agent` | Clones cleanly. | Success. |
| **2. Virtualenv** | `python -m venv backend/venv`<br>`backend/venv/Scripts/activate` | Creates and activates Python virtual environment. | Success. |
| **3. Dependencies**| `pip install -r requirements.txt` | Installs dependencies. | **Subtle Trap:** Installs Python packages, but does NOT install `ffmpeg.exe`. If the machine lacks FFmpeg, the bot fails on voice playback. |
| **4. Config** | `cp .env.example .env`<br>Populate keys. | Copies template. | Success (assuming user has Discord, AssemblyAI, Groq, Tavily keys). |
| **5. Launch** | `start_all.bat` | Launches `start_backend.bat`, `start_bot.bat`, opens `http://localhost:8000`. | **FATAL FAILURE (DEPLOY-01):** Browser opens `http://localhost:8000` and displays: `{"detail":"Not Found"}`. `frontend/out` does not exist because `npm run build` was never executed! |
| **6. Verification**| `backend/venv/Scripts/python -m unittest discover tests` | Runs 173 tests. | Tests pass, but live dashboard remains inaccessible. |

### 1.2 Fresh Linux VPS Simulation (Ubuntu 24.04 / Debian 12)

| Step | Linux VPS Behavior | Breaking Point / Missing Instructions | Severity |
| :--- | :--- | :--- | :--- |
| **1. Launcher Scripts** | Linux shells cannot execute `.bat` files (`start_all.bat`, `start_backend.bat`, `start_bot.bat`). | **No shell scripts (`.sh`) or `systemd` unit files exist in the repository.** User must manually figure out commands. | **HIGH** |
| **2. Discord Voice C-Libraries** | `discord.py` voice receive on Linux requires `libopus0` and `libffi-dev`. | Without `apt install libopus0 libopus-dev`, `discord.opus.load_opus()` fails, preventing bot from joining voice channels. | **CRITICAL** |
| **3. FFmpeg Package** | `StreamFFmpegPCMAudio` expects `ffmpeg` in system PATH. | Without `apt install ffmpeg`, TTS synthesis raises `FileNotFoundError`. | **CRITICAL** |
| **4. Node.js Build Step** | No Node build instructions provided. | `npm install` and `npm run build` inside `frontend/` must be manually discovered and run. | **HIGH** |

---

## 2. Security & Privacy Audit

### 2.1 User Data & PII Exposure Table

| Data Asset | File System Location | Written By | Data Contained | Gitignored? | Retention / Lifecycle |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Acoustic Shadow Log** | `audit/shadow/loudness_shadow.jsonl` | [`bot/audio/loudness.py:427`](file:///g:/CallWrapper/bot/audio/loudness.py#L427) | Timestamps, **Discord display names** (e.g. "Remi", "2xDanger"), loudness metrics ($z$-peak, sustain ms). | **NO (EXPOSED)** | Persists permanently on disk. Not cleared by `!clear` or `!leave`. |
| **Test Capture Audio** | `recordings/test_session/<date_time>/*.wav` | [`bot/audio/capture.py:139`](file:///g:/CallWrapper/bot/audio/capture.py#L139) | 16kHz mono audio recordings of human speakers. | **YES** (`.gitignore:31`) | Persists in session folder until manually deleted by admin. |
| **Test Capture Logs** | `recordings/test_session/<date_time>/session_log.jsonl` | [`bot/audio/capture.py:155`](file:///g:/CallWrapper/bot/audio/capture.py#L155) | Timestamps, speaker names, verbatim ASR transcripts, audio features. | **YES** (`.gitignore:31`) | Persists in session folder until manually deleted by admin. |
| **Human Annotation CSV** | `recordings/test_session/<date_time>/labels_DRAFT.csv` | [`bot/audio/capture.py:206`](file:///g:/CallWrapper/bot/audio/capture.py#L206) | Transcripts, speaker names, ground-truth labels. | **YES** (`.gitignore:31`) | Persists in session folder. |
| **SQLite Database** | `data/app.db` or `backend/call_intelligence.db` | [`backend/app/database.py:12`](file:///g:/CallWrapper/backend/app/database.py#L12) | SQLAlchemy schema for calls, participants, transcripts. | **YES** (`.gitignore:8-9`) | Cleared if `.db` deleted. |
| **In-Memory Turns** | `LIVE_STATE["turns"]` | [`backend/app/routes.py:382`](file:///g:/CallWrapper/backend/app/routes.py#L382) | Transcripts, timestamps, speaker names. | N/A (RAM) | Cleared on server restart or `POST /api/reset`. |

### 2.2 Gitignore Vulnerability Sweep
Inspection of [`.gitignore`](file:///g:/CallWrapper/.gitignore) and `git status` revealed:
- `audit/shadow/loudness_shadow.jsonl` is **untracked on disk and NOT in `.gitignore`**. It contains actual user display names from real Discord sessions.
- `.venv/` (standard root-level Python virtual environment) is **missing from `.gitignore`** (only `backend/venv/` is ignored at line 7).
- `.qwen/` and `opencode.json` are present in working tree as untracked files without ignore rules.

### 2.3 API Secret Transit Audit

| External API | Client File | Request Mechanism | Secret Location | Transit Security Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **AssemblyAI** | [`bot/ai/assemblyai.py:137`](file:///g:/CallWrapper/bot/ai/assemblyai.py#L137) | `httpx.AsyncClient` | `Authorization: {api_key}` header | **SECURE.** Key never appears in query params or URLs. |
| **Tavily** | [`bot/ai/tavily.py:87`](file:///g:/CallWrapper/bot/ai/tavily.py#L87) | `httpx.AsyncClient` | JSON POST body (`{"api_key": ...}`) | **SECURE.** Key sent over TLS in POST payload. |
| **Groq LPU** | [`bot/ai/groq.py:184`](file:///g:/CallWrapper/bot/ai/groq.py#L184) | `httpx.AsyncClient` | `Authorization: Bearer {key}` header | **SECURE.** Standard Bearer token header over TLS. |
| **Edge-TTS** | [`bot/ai/tts.py:341`](file:///g:/CallWrapper/bot/ai/tts.py#L341) | `edge_tts.Communicate` | WebSocket to Bing Speech | **SECURE.** Uses public Microsoft Edge consumer token. |

### 2.4 Network API Authentication & CORS Audit

#### Endpoint Vulnerability Surface
In [`backend/app/routes.py`](file:///g:/CallWrapper/backend/app/routes.py):
- `POST /api/events` ([line 370](file:///g:/CallWrapper/backend/app/routes.py#L370)): Accepts `VoiceEventPayload`. **No auth token or secret header.** Anyone who can reach port 8000 can inject synthetic transcripts, fabricate claims, or trigger false dispute verdicts.
- `POST /api/reset` ([line 450](file:///g:/CallWrapper/backend/app/routes.py#L450)): Wipes all active turns, disputes, and leaderboard statistics. **No auth.** An attacker can remotely denial-of-service a live demonstration.
- `POST /api/demo/run` ([line 485](file:///g:/CallWrapper/backend/app/routes.py#L485)): Initiates an asynchronous demo replay. **No auth.**
- `WebSocket /api/ws` ([line 360](file:///g:/CallWrapper/backend/app/routes.py#L360)): Unauthenticated streaming socket. Any client can connect and receive verbatim speech transcripts and speaker names in real time.

#### CORS Configuration
In [`backend/app/config.py:45`](file:///g:/CallWrapper/backend/app/config.py#L45):
```python
CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
```
- Configured strictly for localhost port 3000.
- If a judge or developer runs the Next.js dev server on a LAN IP (e.g. `http://192.168.1.50:3000`) or custom port (e.g. 3001), FastAPI's `CORSMiddleware` blocks all API and WebSocket requests.

---

## 3. Dependency & Licensing Audit

### 3.1 Master Dependency Table

| Package | Version Pin | Source File | License | Actually Imported? | Usage in Codebase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fastapi` | `>=0.115.0` | `requirements.txt:1` | BSD-3-Clause | **YES** | [`backend/app/main.py`](file:///g:/CallWrapper/backend/app/main.py) |
| `uvicorn[standard]` | `>=0.30.0` | `requirements.txt:2` | BSD-3-Clause | **YES** | [`start_backend.bat`](file:///g:/CallWrapper/start_backend.bat), [`backend/app/main.py`](file:///g:/CallWrapper/backend/app/main.py) |
| `websockets` | `>=12.0` | `requirements.txt:3` | BSD-3-Clause | **YES** | FastAPI WebSockets, Discord |
| `sqlalchemy` | `>=2.0.30` | `requirements.txt:4` | MIT | **YES** | [`backend/app/database.py`](file:///g:/CallWrapper/backend/app/database.py) |
| `aiosqlite` | `>=0.20.0` | `requirements.txt:5` | MIT | **YES** | Async SQLite driver for SQLAlchemy |
| `pydantic` | `>=2.8.0` | `requirements.txt:6` | MIT | **YES** | [`backend/app/routes.py`](file:///g:/CallWrapper/backend/app/routes.py), schemas |
| `pydantic-settings` | `>=2.4.0` | `requirements.txt:7` | MIT | **YES** | [`backend/app/config.py`](file:///g:/CallWrapper/backend/app/config.py) |
| `python-dotenv` | `>=1.0.1` | `requirements.txt:8` | BSD-3-Clause | **YES** | [`bot/config.py`](file:///g:/CallWrapper/bot/config.py), [`backend/app/config.py`](file:///g:/CallWrapper/backend/app/config.py) |
| `httpx` | `>=0.27.0` | `requirements.txt:9` | BSD-3-Clause | **YES** | [`assemblyai.py`](file:///g:/CallWrapper/bot/ai/assemblyai.py), [`groq.py`](file:///g:/CallWrapper/bot/ai/groq.py), [`tavily.py`](file:///g:/CallWrapper/bot/ai/tavily.py), [`publisher.py`](file:///g:/CallWrapper/bot/events/publisher.py) |
| `edge-tts` | `>=6.1.12` | `requirements.txt:10` | **GPL-3.0** | **YES** | [`bot/ai/tts.py`](file:///g:/CallWrapper/bot/ai/tts.py) |
| `numpy` | `>=1.26.0` | `requirements.txt:11` | BSD-3-Clause | **YES** | [`bot/audio/pcm.py`](file:///g:/CallWrapper/bot/audio/pcm.py), [`bot/audio/receiver.py`](file:///g:/CallWrapper/bot/audio/receiver.py) |
| `discord.py` | `==2.7.1` | `requirements.txt:12` | MIT | **YES** | [`bot/main.py`](file:///g:/CallWrapper/bot/main.py) |
| `discord-ext-voice-recv` | `==0.5.2a179` | `requirements.txt:13` | MIT | **YES** | [`bot/audio/receiver.py`](file:///g:/CallWrapper/bot/audio/receiver.py) |
| `davey` | `==0.1.6` | `requirements.txt:14` | MIT | **YES** | Discord DAVE voice MLS decryption |
| `PyNaCl` | `>=1.5.0` | `requirements.txt:15` | Apache-2.0 | **YES** | Voice packet cryptography |
| `tldextract` | `>=5.1.0` | `requirements.txt:16` | BSD-3-Clause | **YES** | [`bot/arbitration/corroboration.py`](file:///g:/CallWrapper/bot/arbitration/corroboration.py) |
| `Pillow` | `>=10.0.0` | `requirements.txt:17` | HPND | **YES** | [`bot/ui/recap_card_renderer.py`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py) |
| `arabic-reshaper` | `>=3.0.0` | `requirements.txt:18` | MIT | **YES** | [`bot/ui/recap_card_renderer.py`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py) |
| `python-bidi` | `>=0.4.2` | `requirements.txt:19` | **LGPL-3.0** | **YES** | [`bot/ui/recap_card_renderer.py`](file:///g:/CallWrapper/bot/ui/recap_card_renderer.py) |
| `google-genai` | `>=0.1.0` | `backend/requirements.txt:11` | Apache-2.0 | **NO (DEAD)** | **0 imports across codebase** |

### 3.2 Licensing Compatibility Review
- CallWrapped specifies the **MIT License** in [`LICENSE`](file:///g:/CallWrapper/LICENSE).
- `edge-tts` is licensed under **GPLv3**.
  - While running a GPLv3 component in an internal backend service does not trigger source distribution under standard GPL (unlike AGPL), distributing an MIT repository that directly imports and links with a GPLv3 Python library creates a copyleft licensing question if packaged for binary distribution.
- `python-bidi` is licensed under **LGPL-3.0**, which is compatible with MIT applications via dynamic linking.

---

## 4. Deployment Readiness & Environment Variable Reconciliation

### 4.1 Environment Variable Reconciliation

| Environment Variable | In `.env.example`? | In `bot/config.py`? | In `backend/config.py`? | In `.env`? | Status / Discrepancy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DISCORD_BOT_TOKEN` | Yes | Yes (line 20) | Yes (line 48) | Yes | Synchronized. |
| `ASSEMBLYAI_API_KEY` | Yes | Yes (line 24) | Yes (line 22) | Yes | Synchronized. |
| `GROQ_API_KEY` | Yes | Yes (line 34) | Yes (line 28) | Yes | Synchronized. |
| `GROQ_API_KEY_2` to `4`| Yes | Yes (lines 35-37)| Yes (lines 29-31)| Yes | Synchronized. |
| `GROQ_API_KEY_5` to `8`| Yes | Yes (lines 38-41)| **NO (Missing)** | Yes | Backend config only reads up to Key 4; Bot config reads up to Key 8. |
| `TAVILY_API_KEY` | Yes | Yes (line 45) | Yes (line 34) | Yes | Synchronized. |
| `DISPUTE_CONFIRM_SEARCH_TIMEOUT_SEC` | Yes (line 85) | Yes (line 59) | No | **NO** | Missing in live `.env`; falls back to default 8.0. |
| `DISPUTE_OFFER_EXPIRY_SEC` | Yes (line 84) | Yes (line 58) | No | **NO** | Missing in live `.env`; falls back to default 30.0. |
| `DISPUTE_OFFER_COOLDOWN_SEC` | Yes (line 83) | Yes (line 57) | No | **NO** | Missing in live `.env`; falls back to default 180.0. |
| `ACOUSTIC_FUSION_ENABLED` | Yes (line 119) | Yes (line 51) | No | **NO** | Missing in live `.env`; falls back to default 0. |
| `TEST_CAPTURE_MODE` | Yes (line 98) | Yes (line 54) | No | **NO** | Missing in live `.env`; falls back to default 0. |
| `GEMINI_API_KEY` / `_1` to `_3` | No | No | Yes (line 26) | **YES** | Dead environment variables left over from early prototyping. |
| `OPENAI_API_KEY` | No | No | Yes (line 27) | No | Dead config field in `backend/app/config.py`. |

---

## 5. Findings Table

| ID | Severity | File:Line | Summary | Failure Scenario | Evidence Excerpt |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEPLOY-01** | **CRITICAL** | [`README.md:374-378`](file:///g:/CallWrapper/README.md#L374-L378), [`start_all.bat:18`](file:///g:/CallWrapper/start_all.bat#L18) | Fresh clone fails with 404 Not Found at `http://localhost:8000` | Judge follows README Quick Start. `frontend/out` does not exist because Next.js was never built. FastAPI cannot mount static directory; browser displays 404 error. | ```text\nstart "CallWrapped - Backend" cmd /k "%~dp0start_backend.bat"\nstart "CallWrapped - Discord Bot" cmd /k "%~dp0start_bot.bat"\nstart http://localhost:8000\n``` |
| **SETUP-01** | **CRITICAL** | [`README.md:350-365`](file:///g:/CallWrapper/README.md#L350-L365), [`tts.py:42`](file:///g:/CallWrapper/bot/ai/tts.py#L42) | Missing system prerequisite FFmpeg causes runtime voice crash | Host without FFmpeg in PATH crashes on `speak_clauses()` with `FileNotFoundError: [WinError 2]`. FFmpeg is not mentioned anywhere in README prerequisites. | ```python\ncmd = [executable, "-f", "mp3", "-probesize", "32", "-i", "pipe:0", ...]\nself.process = subprocess.Popen(cmd, ...)\n``` |
| **SEC-01** | **HIGH** | [`loudness.py:427-431`](file:///g:/CallWrapper/bot/audio/loudness.py#L427-L431), [`.gitignore`](file:///g:/CallWrapper/.gitignore) | User display names logged to unignored `audit/shadow/loudness_shadow.jsonl` | Real Discord usernames and timestamps logged to shadow file. Staging `audit/` commits user identity data to public git history. | ```python\nrecord = {\n    "timestamp": now,\n    "speaker": speaker,\n    "z_peak": round(features.peak_robust_z, 3),\n}\npath = PROJECT_ROOT / "audit" / "shadow" / "loudness_shadow.jsonl"\n``` |
| **SEC-02** | **HIGH** | [`backend/app/routes.py:370-509`](file:///g:/CallWrapper/backend/app/routes.py#L370-L509) | All backend endpoints are completely unauthenticated | Any network client can post synthetic events, trigger `POST /api/reset` to wipe live session state, or listen to unauthenticated WebSockets. | ```python\n@router.post("/events")\nasync def ingest_voice_event(event: VoiceEventPayload):\n    ...\n@router.post("/reset")\nasync def reset_live_state():\n``` |
| **SETUP-02** | **HIGH** | [`start_all.bat`](file:///g:/CallWrapper/start_all.bat), [`.gitignore`](file:///g:/CallWrapper/.gitignore) | No Linux / macOS launch scripts or system package documentation | Linux VPS deployment fails to run `.bat` scripts and lacks documentation for required `libopus0` and `libffi` packages. | ```bat\nstart "CallWrapped - Backend" cmd /k "%~dp0start_backend.bat"\n``` |
| **DEP-01** | **MEDIUM** | [`backend/requirements.txt:11`](file:///g:/CallWrapper/backend/requirements.txt#L11) | Dead dependency `google-genai` in redundant `backend/requirements.txt` | `backend/requirements.txt` is an outdated duplicate of root `requirements.txt` containing unused `google-genai`. | ```text\nhttpx>=0.27.0\nedge-tts>=6.1.12\ngoogle-genai>=0.1.0\n``` |
| **SEC-03** | **MEDIUM** | [`backend/app/config.py:45`](file:///g:/CallWrapper/backend/app/config.py#L45) | Hardcoded `CORS_ORIGINS` blocks non-localhost frontend access | Developers testing frontend on local network IP (e.g. `192.168.1.X`) or alternative port are blocked by CORS policy. | ```python\nCORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"\n``` |
| **CONFIG-01** | **MEDIUM** | [`backend/app/config.py:28-31`](file:///g:/CallWrapper/backend/app/config.py#L28-L31) | Groq pool keys 5 through 8 missing from backend config | `bot/config.py` supports 8 Groq keys, but `backend/app/config.py` only defines keys up to `GROQ_API_KEY_4`. | ```python\nGROQ_API_KEY: str = ""\nGROQ_API_KEY_2: str = ""\nGROQ_API_KEY_3: str = ""\nGROQ_API_KEY_4: str = ""\n``` |
| **CONFIG-02** | **LOW** | [`backend/app/config.py:26-27`](file:///g:/CallWrapper/backend/app/config.py#L26-L27) | Dead API key definitions (`GEMINI_API_KEY`, `OPENAI_API_KEY`) | Legacy prototype keys clutter configuration class. | ```python\nGEMINI_API_KEY: str = ""\nOPENAI_API_KEY: str = ""\n``` |
| **HYGIENE-01**| **LOW** | [`.gitignore:7`](file:///g:/CallWrapper/.gitignore#L7) | Root `.venv/` missing from `.gitignore` (only `backend/venv/` ignored) | If developer creates virtual environment at repository root (`.venv`), it is not ignored by git. | ```text\n# Python\nbackend/venv/\nbackend/call_intelligence.db\n``` |
| **HYGIENE-02**| **LOW** | [`start_all.bat:15-18`](file:///g:/CallWrapper/start_all.bat#L15-L18) | `start_all.bat` fails to launch `start_frontend.bat` | All-in-one launcher omits frontend dev server script while pointing user to port 8000. | ```bat\nstart "CallWrapped - Backend" cmd /k "%~dp0start_backend.bat"\ntimeout /t 3 /nobreak > nul\nstart "CallWrapped - Discord Bot" cmd /k "%~dp0start_bot.bat"\n``` |
| **LIC-01** | **LOW** | [`requirements.txt:10`](file:///g:/CallWrapper/requirements.txt#L10), [`LICENSE`](file:///g:/CallWrapper/LICENSE) | GPL-3.0 dependency (`edge-tts`) in MIT-licensed repository | Direct import of GPL-3.0 library inside MIT project creates copyleft license boundary consideration. | ```text\nedge-tts>=6.1.12\n``` |

---

## 6. Top 5 Deployment & Security Recommendations

### 1. Resolve the 404 Dashboard Deployment Trap
Update [`README.md`](file:///g:/CallWrapper/README.md) Quick Start to include frontend installation and static export build:
```bash
# Frontend Setup (required to populate frontend/out for port 8000)
cd frontend
npm install
npm run build
cd ..
```
Or include a pre-flight build check in `start_backend.bat` / `start_all.bat`:
```bat
if not exist "frontend\out\index.html" (
    echo [NOTICE] Building frontend static export...
    cd frontend && call npm install && call npm run build && cd ..
)
```

### 2. Add FFmpeg to Prerequisites in README
Explicitly document FFmpeg installation:
- **Windows:** `winget install Gyan.FFmpeg` or `choco install ffmpeg`
- **Linux:** `sudo apt install ffmpeg libopus0 libopus-dev`
- **macOS:** `brew install ffmpeg libopus`

### 3. Gitignore Shadow Logs and User Data Files
Add shadow logs and root virtualenvs to [`.gitignore`](file:///g:/CallWrapper/.gitignore):
```gitignore
# User Data & Shadow Logs
audit/shadow/
*.jsonl
.venv/
.qwen/
opencode.json
```

### 4. Provide Cross-Platform Launch Scripts (`start_all.sh`)
Create bash launcher scripts for Linux/macOS developers and containerized deployments:
```bash
#!/usr/bin/env bash
source backend/venv/bin/activate
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 &
python -m bot.main &
wait
```

### 5. Add Shared Secret Authentication to Internal Event Ingestion
Protect `POST /api/events` and `POST /api/reset` using an internal bearer token shared between bot and backend via `.env` (`INTERNAL_API_SECRET`):
```python
# backend/app/routes.py
from fastapi import Header, HTTPException

@router.post("/events")
async def ingest_voice_event(event: VoiceEventPayload, authorization: Optional[str] = Header(None)):
    expected = getattr(settings, "INTERNAL_API_SECRET", None)
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    ...
```
