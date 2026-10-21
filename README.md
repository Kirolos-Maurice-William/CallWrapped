# CallWrapped

Discord voice referee and post-call conversational intelligence.

CallWrapped listens to multi-party Discord voice calls, detects conflicting factual claims between participants in real time, and resolves them on demand. The bot operates on a strict consent model: it never interrupts a call uninvited. When a factual disagreement occurs, it offers to verify the claim and only delivers a spoken resolution after explicit verbal confirmation.

---

## Core Mechanics

### Two-Stage Verification Protocol

1. **Passive Transcription**: Audio packets are decrypted using Discord DAVE E2EE and transcribed per speaker using AssemblyAI Universal-3.5 Pro with bilingual code-switching support (English and Arabic).
2. **Dispute Detection & Speculative Pre-fetch**: When two speakers make conflicting claims, Groq LPU extracts the disputed entities and numerical values. In parallel, Tavily queries authoritative web sources and Edge-TTS pre-warms the audio connection.
3. **Consensual Voice Offer**: The bot asks a short verbal question in the channel:
   - Arabic: «أشوفها؟»
   - English: "Do I check?"
4. **Verbal Confirmation**: A participant confirms verbally:
   - Arabic: «شوفها» / «تأكد»
   - English: "check it" / "verify"
   - Text command: `!check`
5. **Instant Spoken Resolution**: Because search results and TTS were pre-fetched in step 2, the verified answer with citations is spoken in under 1.5 seconds. If no one confirms within 30 seconds, the offer quietly expires.
6. **Barge-in Protection**: If a participant speaks while the referee is talking, playback cuts off immediately.

---

## Architecture

- **Audio Ingestion**: Discord DAVE MLS end-to-end encryption adapter (`bot/audio/dave_adapter.py`) with per-speaker 16kHz PCM ring buffers and Voice Activity Detection.
- **Speech-to-Text**: AssemblyAI Universal-3.5 Pro with dynamic keyterm injection and colloquial normalization.
- **Reasoning**: Groq LPU with multi-key rotation and token-budget balancing for claim extraction and topic categorization.
- **Verification**: Tavily Search targeting official documentation, authoritative domains, and manufacturer specifications.
- **Voice Output**: Microsoft Edge Neural TTS (Arabic: `ar-EG-Shakir`, English: `en-US-Christopher`).
- **Dashboard**: FastAPI WebSocket hub paired with a Next.js 14 frontend running on port 8000.

---

## Discord Commands

| Command | Description |
| :--- | :--- |
| `!join` | Connects the bot to your current voice channel. |
| `!start` | Enables fact-checking mode and posts session transparency notice. |
| `!check` | Confirms a pending dispute offer and speaks the verdict. |
| `!arbitrate <claim>` | Manually requests verification for a specific claim. |
| `!recap` | Displays the session talk-time breakdown and badges. |
| `!stats` | Displays participant speech metrics. |
| `!status` | Shows connection state, dispute count, and latency metrics. |
| `!dashboard` | Prints the link to the local web dashboard. |
| `!privacy` | Displays data retention and ephemeral memory policies. |
| `!clear` | Resets session memory and claim history. |
| `!leave` | Disconnects from voice and purges all session state. |

---

## Privacy Policy

- **In-Memory Only**: Audio and transcripts are processed in volatile memory. Disconnecting the bot (`!leave`) or clearing the session (`!clear`) immediately purges all conversation context.
- **Private Entity Veto**: Claims regarding private individuals (such as personal salaries, personal belongings, or private rumors) are rejected by the classifier and never searched on the web.

---

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- FFmpeg installed and available on PATH

### 1. Installation

```bash
git clone https://github.com/Kirolos-Maurice-William/CallWrapped.git
cd CallWrapped

# Python dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend build
cd frontend
npm install
npm run build
cd ..
```

### 2. Configuration

Create a `.env` file in the root directory:

```env
DISCORD_BOT_TOKEN=your_discord_token
ASSEMBLYAI_API_KEY=your_assemblyai_key
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
```

### 3. Running

```bash
# Windows
start_all.bat

# Or run services individually:
# Terminal 1: python -m backend.app.main
# Terminal 2: python -m bot.main
```

The web dashboard is served at `http://localhost:8000`.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
