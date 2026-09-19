# AI Third Participant for Voice Calls

An intelligent AI co-participant that joins private two-person voice conversations (mixing **Egyptian Arabic and English** code-switching), understands who is speaking, calculates exact speaking time and topics, detects factual claims and disagreements, verifies facts against authoritative web sources, intervenes politely with voice when high-confidence disputes occur, and generates an interactive post-call **Conversation Intelligence Report**.

---

## Key Features

1. **AssemblyAI Universal-3.5 Pro Realtime STT**:
   - Handles the live speech recognition with native Arabic/English code-switching, low latency (~285ms median time-to-final), contextual prompting, and keyterms.
2. **Dual-Stream Speaker Attribution**:
   - Speaker A (You) and Speaker B (Friend) are identified deterministically by their respective audio streams.
3. **Async Conversation Intelligence**:
   - Off-the-live-path analysis of topics (movies, football, music, tech, politics, etc.), speech intent, and rolling conversation heat scores (0.0 to 1.0).
4. **Grounded Fact Checking**:
   - Objective search queries retrieve evidence from Wikipedia, Britannica, IMDB, etc. (via Tavily or DuckDuckGo). The system never relies on raw LLM hallucinations.
5. **Polite Voice Interruption**:
   - When confidence is high on a factual dispute, the AI generates a brief voice note (≤ 15 words) and yields immediately.
6. **Post-Call Insights Dashboard**:
   - Interactive report with mathematically exact speaking time percentages (`sum(end - start)`), topic duration bars, heated moments timeline, fact-checked claims ledger, and synchronized full transcript.

---

## Quick Start Guide

### 1. Environment Configuration
Copy the example environment file in `backend`:
```bash
cp backend/.env.example backend/.env
```
Fill in your API keys in `backend/.env`:
- `ASSEMBLYAI_API_KEY`: Your AssemblyAI key (Universal-3.5 Pro Realtime enabled).
- `GEMINI_API_KEY` or `OPENAI_API_KEY`: For asynchronous conversation enrichment.
- `TAVILY_API_KEY`: (Optional) For search retrieval. If left blank, DuckDuckGo search is used automatically.
- `TTS_PROVIDER`: `edge-tts` (free, high-quality neural voice, zero API key required) or `openai`.

### 2. Start the Backend
Double-click `run_backend.bat` or run:
```bash
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be live at: `http://localhost:8000/docs`

### 3. Start the Frontend
Double-click `run_frontend.bat` or run:
```bash
cd frontend
npm run dev
```
Open your browser at: `http://localhost:3000`

### 4. Running the Automated Simulation
You can test the entire pipeline (Egyptian code-switching, fact-checking, AI voice interruption, and post-call metrics) with the included automated simulation:
```bash
cd backend
.\venv\Scripts\python.exe test_simulation.py
```
