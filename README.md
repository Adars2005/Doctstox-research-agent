# Docstox Research Agent

Evidence-driven AI research chat for public companies. ChatGPT-style interface with Groq synthesis, Exa web research, Gemini File Search over uploaded documents, and structured quote snapshots for Indian listings.

## Features

- **ChatGPT-style UI** — Markdown rendering, clean typography, smooth animations, responsive design
- **Web search** — Exa-powered real-time web research with source reliability tiers
- **Document upload** — Gemini File Search indexes PDFs, docs, and spreadsheets per conversation
- **Structured quotes** — Yahoo Finance data for major NSE tickers (TCS, Reliance, Infosys, HDFC Bank, ICICI Bank, Wipro, Bharti Airtel)
- **Research trace** — Visible tool orchestration: plan → tools → evidence → synthesis
- **Citations** — Clickable source cards with reliability ratings (PRIMARY / HIGH / MEDIUM / LOW)
- **Voice support** — Speech-to-text (Whisper) and text-to-speech (Orpheus) with browser fallback
- **Conversation history** — SQLite persistence with full message, citation, and trace history

## Challenge Requirements

| Requirement | Status |
|---|---|
| Problem decomposition | Implemented with deterministic intent patterns and up to two research query templates; complex phrasing remains a limitation. |
| Tool orchestration | Implemented with persisted per-message plan, tool outcomes, evidence check and synthesis trace. |
| Reasoning quality | Evidence-grounded synthesis prompt; trace exposes actions and concise rationale without hidden chain-of-thought. Claim-level support validation is not implemented. |
| Answer trustworthiness | Citations, source tiers, dates, uncertainty instructions and a qualitative evidence-coverage label. Tiers and coverage are heuristics, not correctness guarantees. |
| Missing and contradictory evidence | Illustrative transcripts in `docs/example-transcripts.md`; live contradiction detection remains a quality improvement. |
| Unnecessary tool calls | Rule-based skips for greetings, short follow-ups, document-only and creative requests. |

## Architecture

```
Question → deterministic planner → Gemini File Search (when indexed files are ready)
                                ↘ structured quote snapshot (supported NSE tickers)
                                ↘ Exa web search (one or two targeted searches)
Evidence and tool outcomes → Groq synthesis → answer + citations + persisted trace
```

- **Backend**: FastAPI + SQLite (Python 3.11+)
- **Frontend**: Next.js 15 + React 19 + TypeScript
- **LLM**: Groq (`openai/gpt-oss-20b`)
- **Web search**: Exa API
- **Document AI**: Gemini File Search
- **TTS/STT**: Groq (Orpheus + Whisper)

## API Keys

| Provider | Environment Variable | Required | Get Key |
|---|---|---|---|
| Groq | `GROQ_API_KEY` | Yes | https://console.groq.com/keys |
| Exa | `EXA_API_KEY` | Yes | https://dashboard.exa.ai/api-keys |
| Gemini | `GEMINI_API_KEY` | Optional | https://aistudio.google.com/app/apikey |

Set API keys in `.env` using `.env.example` as a template. Never commit `.env`.

## Quick Start (Docker)

```bash
# 1. Configure API keys
copy .env.example .env
# Edit .env with your keys

# 2. Build and run
docker compose up --build -d

# 3. Open
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/health
```

## Quick Start (Local)

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```powershell
cd frontend
npm install
npm run dev
```

The app runs at http://localhost:3000 and the backend health route is http://localhost:8000/health.

## Verification

### Local checks
```powershell
cd backend
python -m unittest discover -s tests -v
cd ..\frontend
npm run build
```

The commands above check the backend unit suite and frontend production build. They do not verify external provider credentials or current provider availability. Run the app and exercise Groq, Exa, Gemini, Yahoo Finance, transcription, and speech separately when those integrations are configured. In Docker Compose, the browser calls same-origin API paths and Next.js proxies them to the backend service.

See [docs/interview-guide.md](docs/interview-guide.md) for a requirement-by-requirement review, architecture walkthrough, design trade-offs, verification record, and prioritized implementation plan.

### End-to-end test
```powershell
cd backend
python -c "import httpx; r=httpx.post('http://localhost:8000/api/conversations', json={'title':'Test'}); print(r.json())"
```

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app + health endpoint
│   ├── config.py            # Env loading + provider status
│   ├── db.py                # SQLite persistence
│   ├── api/
│   │   ├── chats.py         # Conversation + message routes
│   │   ├── files.py         # File upload + Gemini indexing
│   │   └── voice.py         # STT + TTS routes
│   ├── services/
│   │   ├── orchestrator.py   # Planner + tool orchestration
│   │   ├── groq_client.py   # LLM chat, STT, TTS
│   │   ├── exa_client.py    # Web search + source classification
│   │   ├── gemini_file_search.py  # Document upload + RAG
│   │   └── market_data.py   # Yahoo Finance quote adapter
│   └── tests/
│       └── test_research_agent.py  # Unit tests
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main chat page
│   │   ├── layout.tsx       # Root layout
│   │   ├── globals.css      # ChatGPT-style design system
│   │   ├── history/page.tsx # Chat history
│   │   └── c/[id]/page.tsx  # Individual conversation
│   ├── components/
│   │   ├── ChatWorkspace.tsx # Main chat UI with markdown
│   │   └── Sidebar.tsx      # Navigation sidebar
│   └── lib/
│       ├── api.ts           # API client
│       └── types.ts         # TypeScript types
├── docs/
│   ├── architecture.md
│   ├── research-methodology.md
│   ├── example-transcripts.md
│   └── interview-guide.md  # Technical walkthrough, trade-offs, verification and improvement plan
├── Dockerfile               # Backend Docker build
├── frontend/Dockerfile      # Frontend Docker build
├── docker-compose.yml       # Multi-service orchestration
├── DEPLOYMENT.md            # Full deployment guide
└── .env.example             # Environment template
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Docker, reverse proxy, and production guidance.

## Limitations

- Quotes are from Yahoo Finance's public endpoint — secondary, may be delayed
- Source tiers (PRIMARY/HIGH/MEDIUM/LOW) are heuristics, not accuracy guarantees
- At most 2 Exa web searches per turn to limit latency
- SQLite is suitable for single-server deployment; use PostgreSQL for multi-user production
- Groq TTS (Orpheus) requires account terms acceptance; browser fallback included
