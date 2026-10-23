# Deployment Guide

## Prerequisites

- Docker & Docker Compose (recommended), OR
- Python 3.11+ and Node 20+ for local deployment

## Option 1: Docker Compose (Recommended)

1. Copy `.env.example` to `.env` and fill in your API keys:
   ```
   GROQ_API_KEY=your_key_here
   EXA_API_KEY=your_key_here
   GEMINI_API_KEY=your_key_here
   ```

2. Build and start:
   ```bash
   docker compose up --build -d
   ```

3. Access:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Health check: http://localhost:8000/health

## Option 2: Local Development

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| GROQ_API_KEY | Yes | Groq API key for LLM chat, STT, TTS |
| EXA_API_KEY | Yes | Exa API key for web search |
| GEMINI_API_KEY | Optional | Enables document upload + File Search |
| GROQ_MODEL | No | Default: openai/gpt-oss-20b |
| CORS_ORIGINS | No | Comma-separated browser origins when calling the backend directly; default: http://localhost:3000 |
| NEXT_PUBLIC_API_BASE | No | Optional direct browser API base. Leave unset to use same-origin Next.js rewrites. |
| BACKEND_INTERNAL_URL | No | Server-side Next.js rewrite target; Compose sets http://backend:8000, local default: http://localhost:8000 |

In Docker Compose, open the frontend at `http://localhost:3000`. The browser calls `/api/*` and `/health` on that same origin; Next.js proxies those requests to the backend using `BACKEND_INTERNAL_URL`. Do not set the browser API base to the Compose-only hostname `backend`.

## API Key Sources

- **Groq**: https://console.groq.com/keys
- **Exa**: https://dashboard.exa.ai/api-keys
- **Gemini**: https://aistudio.google.com/app/apikey

## Production Considerations

- Set `BACKEND_HOST=127.0.0.1` if exposing only through reverse proxy
- Use a reverse proxy (nginx, Caddy) for TLS termination
- Store `.env` securely; never commit it
- The SQLite database at `backend/data/docstox.db` should be backed up
- For multi-user production, consider PostgreSQL instead of SQLite
