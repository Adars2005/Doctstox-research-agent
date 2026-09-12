# Docstox-research agent

Evidence-driven AI equity research agent. It answers real questions about publicly listed companies by combining structured market data with unstructured web research.

**Current status:** ChatGPT-style research chat is live. Groq handles conversation and voice. Exa handles web research. Gemini File Search indexes uploaded documents for RAG.

## Problem

Equity questions such as "Why did this stock move today?" cannot be answered from a single search result or a chatbot summary. A useful answer needs:

- verified price, volume, and benchmark context
- company announcements and filings
- independent news
- source reliability
- contradiction handling
- an explicit statement when evidence is insufficient

## Solution

The agent will decompose a question, build a research plan, call tools only when needed, collect evidence, validate it, detect contradictions, decide when to stop, then produce a sourced conclusion with confidence.

User-facing interface is a simple ChatGPT-style research chat named **Docstox-research agent**. The UI does not use Tailwind CSS.

## Architecture

```text
USER QUESTION
     |
     v
Question Planner
     |
     v
Research Plan
     |
     v
Agent Orchestrator
   /     |      \
  v      v       v
Market  Exa   Company
Data   Search  Data
   \     |      /
    v    v     v
Evidence Store
     |
     v
Evidence Judge
  /          \
stop        search again
  \          /
   v        v
Final Synthesizer
     |
     v
ANSWER + SOURCES + CONFIDENCE
```

## Tool orchestration

- **Groq** — chat, speech-to-text, and spoken replies
- **Exa** — primary web research layer for company and market questions
- **Gemini File Search** — RAG over uploaded filings and documents; used when files are attached, not as the default web search

The orchestrator calls Exa for research questions. If the user uploaded documents, Gemini File Search retrieves evidence from those files first.

## Exa

Exa is the primary unstructured research/search tool. All Exa calls happen server-side using `EXA_API_KEY` in `backend/services/exa_client.py`.

## Trustworthiness

Later phases will implement:

- source hierarchy (primary, high, medium, low)
- evidence and claim models
- contradiction detection
- qualitative confidence (HIGH / MEDIUM / LOW)
- missing-data behavior
- a maximum of 5 research iterations

## Example transcripts

Placeholder. Demo transcripts for successful investigation, missing evidence, and contradictory data will be added in Phase 12.

## Tradeoffs

Deliberately not built in Phase 1:

- research loop
- Exa / OpenAI / yfinance integrations
- streaming tool trace
- demo scenarios
- tests

The frontend is a simple chat-style page rather than a dense research terminal. That keeps the first demo readable; the workspace panels can be added later without turning the product into a generic chatbot.

## Future work

- more financial data providers
- richer valuation models
- portfolio-level research
- historical event analysis
- analyst consensus
- automated report generation

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: [http://localhost:3000](http://localhost:3000)

Copy `.env.example` to `.env` and set:

- `GROQ_API_KEY` for chat and voice
- `EXA_API_KEY` for web research
- `GEMINI_API_KEY` for document upload / File Search RAG

Never commit `.env`. Keys stay on the server.
