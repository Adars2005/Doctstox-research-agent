# Architecture

Docstox is a FastAPI service with a Next.js chat UI. A user message is saved in SQLite, planned, sent to relevant evidence tools, synthesized through Groq, and saved with citations and a visible action trace.

```text
Question → deterministic planner → Gemini File Search (when files exist)
                               ↘ structured quote snapshot (supported Indian tickers)
                               ↘ Exa web search (one or two targeted searches)
Evidence and tool outcomes → Groq synthesis → answer + citations + persisted trace
```

## Components

- `backend/services/orchestrator.py` decides whether a tool is needed and forms checkable sub-questions. Greetings, creative writing, document-only prompts, and short follow-ups do not trigger web search. Short follow-ups carry forward the prior answer's sources. Attached files that are not indexed are disclosed in the trace and answer context.
- `backend/services/market_data.py` fetches recent daily quote, previous close, percent change, volume, and timestamp for a small curated set of NSE listings. Yahoo Finance is a secondary quote source; values may be delayed and must not be treated as execution prices.
- `backend/services/exa_client.py` retrieves web evidence and assigns a transparent source tier. Tier labels are heuristics, not a guarantee of accuracy.
- `backend/services/gemini_file_search.py` indexes uploads in a File Search store with conversation metadata and queries only that conversation's ready documents. Conversation deletion removes indexed documents and local uploads before deleting the database rows.
- `backend/services/groq_client.py` produces the user-facing answer, applies citations to factual claims, and surfaces uncertainty. Tool traces show actions and outcomes; they do not expose private chain-of-thought.
- `backend/db.py` stores messages, citations, tool names, and trace steps. Existing databases migrate the nullable `trace` column on startup.

## Health and provider requirements

`GET /health` checks that the backend process is running and reports which API keys are configured. It is not an upstream availability check. Actual upstream readiness is validated by live chat, Exa, File Search, transcription, and speech calls. Groq may require account terms acceptance for the Orpheus TTS model; the chat UI falls back to browser speech synthesis when server-side speech is unavailable.

The browser uses same-origin `/api/*` and `/health` paths. Next.js proxies those paths to `BACKEND_INTERNAL_URL`, which is `http://backend:8000` in Compose and defaults to `http://localhost:8000` for local development. This keeps Docker service DNS on the server side.

Set `GROQ_API_KEY` and `EXA_API_KEY` for web research. `GEMINI_API_KEY` enables uploads and document retrieval. Keys are read only by the backend and must not be committed.
