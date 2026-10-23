# Docstox Research Agent: Technical Interview Guide

This guide describes the implementation in this repository as it exists today. It is intended to help explain the system accurately in an interview, including where the design is a prototype and what should be improved before production use.

## 1. Project summary

Docstox is a research chat application for questions about public companies. The user asks a question in a Next.js interface. A FastAPI backend decides whether the turn needs public web research, searches uploaded documents when indexed files are available, optionally retrieves a structured quote for a small allowlist of Indian listings, collects evidence and source metadata, asks a Groq model to synthesize a response, and stores the exchange and its trace in SQLite.

The design goal is evidence-grounded research with inspectable tool activity. It does not expose private chain-of-thought. Instead, it shows an operational trace: the plan, tools attempted, result counts or failures, an evidence-coverage heuristic, and synthesis status.

**One-sentence interview version:** “I built a full-stack research assistant that uses a deterministic planner to decide which evidence tools to call, then grounds an LLM-written answer in retrieved web and document evidence, while persisting citations and an auditable action trace.”

## 2. Challenge fit

The attached challenge asks for an agent that answers a real research question about a listed company using public data, with emphasis on problem decomposition, tool orchestration, reasoning quality, and answer trustworthiness.

| Challenge theme | Implemented approach | Current qualification |
|---|---|---|
| Problem decomposition | `build_research_plan` classifies question patterns and forms at most two query strings. Company risk, price, and valuation patterns get different query templates. | Heuristic rules; no general planner or entity resolution beyond the quote allowlist. |
| Tool orchestration | `run_turn` optionally calls Gemini File Search, the quote adapter, and Exa, then Groq. Trace steps are stored with the assistant message. | Calls are synchronous and sequential; there is no streaming, timeout budget across the entire turn, or retry policy shared by providers. |
| Reasoning quality | The synthesis prompt asks for direct answers, fact/interpretation separation, counter-evidence, uncertainty, and citations. | Quality is not automatically evaluated; the model can still omit or misapply citations. |
| Trustworthiness | Sources have heuristic reliability tiers, dates and excerpts; the backend records a qualitative coverage label; the prompt tells the model to disclose uncertainty. | Coverage is a source-count heuristic, not a calibrated confidence score or proof that claims are supported. |
| Public-data research | Exa search and Yahoo Finance chart endpoint provide public-web evidence and quote snapshots. | Yahoo is secondary and can be delayed. External providers were not live-tested as part of this local audit. |

The accompanying transcript document includes illustrative sourced, missing-evidence, contradictory-evidence, and no-tool follow-up cases. Those examples are fixtures, not live research outputs.

## 3. Architecture and request lifecycle

```text
Browser (Next.js / React)
  ├─ health and conversation APIs
  ├─ chat, history, upload, transcription and speech controls
  └─ renders Markdown, citations and research trace
          │ HTTP / multipart
          ▼
FastAPI
  ├─ chats.py: conversation and message routes
  ├─ files.py: upload validation, local persistence, Gemini indexing
  ├─ voice.py: Groq transcription and speech endpoints
  └─ services/orchestrator.py
       ├─ deterministic question planner
       ├─ Gemini File Search (ready conversation files)
       ├─ Yahoo chart endpoint (supported tickers and quote-like question)
       ├─ Exa (up to two searches)
       ├─ evidence coverage label + citation deduplication
       └─ Groq synthesis
          │
          ├─ SQLite: conversations, messages, files, settings
          ├─ backend/uploads: uploaded file bytes
          └─ external providers: Exa, Gemini, Groq, Yahoo Finance
```

### A normal chat turn

1. `POST /api/conversations/{id}/messages` validates the conversation and message length.
2. `run_turn` saves the user message, loads ready files, and calls `build_research_plan`.
3. For a conversation with ready indexed files, it queries the shared Gemini File Search store with a conversation metadata filter.
4. If the request matches a known NSE company and asks for quote-like data, it fetches a five-day daily chart snapshot from Yahoo Finance.
5. For research questions, it submits up to two Exa queries, deduplicates source URLs and keeps at most eight citations.
6. It creates an evidence-coverage note based on the citation count and count of `PRIMARY` sources.
7. For a recognized short follow-up, it carries forward the previous answer's source cards and excerpts without repeating external search. It sends the saved conversation history and turn evidence to Groq with a system prompt that demands citations for material factual claims and disclosure of uncertainty.
8. It saves the assistant answer with tool names, citations, trace and timestamp. SQLite is the persistence layer for history and uploaded-file metadata.

The trace is an action log, deliberately distinct from chain-of-thought. It makes tool use and failures visible without exposing hidden reasoning.

## 4. Components and responsibilities

### Frontend

- **Next.js 15 / React 19 / TypeScript:** app routes, chat screen, history, API client and UI state.
- **`ChatWorkspace`:** sends turns, loads a conversation, handles file selection, records microphone audio, optionally plays generated speech, and renders the trace and citation cards.
- **`Sidebar`:** recent chats and provider-key presence indicator.
- **`react-markdown` + `remark-gfm`:** renders assistant Markdown and tables. Raw HTML is not enabled by the current configuration.
- **Voice fallback:** if Groq speech generation fails, the browser's speech synthesis API is attempted.

### Backend

- **FastAPI:** HTTP API and CORS middleware.
- **Planner/orchestrator:** controls tool selection, ordering, evidence accumulation, trace creation and answer persistence.
- **Groq client:** chat completions, Whisper transcription and Orpheus speech generation; the chat client tries configured and fallback model names.
- **Exa client:** web retrieval, result normalization and domain-based source tiers.
- **Gemini File Search client:** one persisted store; upload metadata includes a conversation ID; document search uses a metadata filter.
- **Market data adapter:** maps a small set of Indian-company names to Yahoo Finance symbols and returns a dated structured snapshot.
- **SQLite:** conversations, messages, citations/trace JSON, files and Gemini store setting.

### Deployment files

`docker-compose.yml` defines frontend and backend containers with named volumes for database and uploads. The backend Dockerfile builds only the API image. The frontend has its own multi-stage build. Browser API calls use same-origin routes; Next.js rewrites `/api/*` and `/health` to `BACKEND_INTERNAL_URL` on the server, so Compose's internal backend hostname is not exposed to the browser. Compose also waits for backend health before starting the frontend.

## 5. Decisions and trade-offs to discuss

### Deterministic planner instead of an LLM tool caller

**Why:** predictable tool selection, easy-to-review behavior, bounded search volume, fewer prompt-injection opportunities in tool planning, and straightforward unit tests.

**Cost:** regular expressions are brittle. Novel phrasing, multi-company comparisons, ambiguous entities, and domain-specific questions may be classified poorly. The generated queries often repeat the full question with a suffix rather than truly extracting independent sub-questions.

**Next step:** retain deterministic guardrails, but represent a plan as a typed structure (intent, entities, date range, evidence needs, tool budget). Evaluate a constrained model-assisted planner only for ambiguous questions, with schema validation and a deterministic fallback.

### Two web searches maximum

**Why:** limits latency and provider usage, and encourages a focused official-source / independent-source split.

**Cost:** sparse evidence for complex topics; no adaptive search if first results are weak or contradictory.

**Next step:** use a fixed initial budget plus one conditional follow-up when coverage is poor, source dates are stale, or material claims conflict. Enforce a hard overall time and call budget.

### External search plus secondary quote endpoint

**Why:** Exa returns source excerpts and URLs; the quote adapter gives structured figures without asking a language model to invent market values.

**Cost:** external-provider availability, data freshness and licensing/terms dependency. Yahoo Finance is not an exchange-grade or guaranteed real-time source.

**Next step:** add provider contracts, rate limits, freshness validation, explicit market timezone/session semantics and an exchange-authoritative source where licensing permits.

### Gemini File Search rather than a custom vector database

**Why:** managed ingestion and retrieval reduce infrastructure and implementation work for a challenge prototype.

**Cost:** provider coupling, API/model behavior changes, less control over chunking and ranking, and uploaded data is sent to a third party. A single shared store needs strict tenant/conversation isolation.

**Next step:** formalize data retention and deletion, test cross-conversation isolation, and compare managed search with an explicitly controlled ingestion/index pipeline only if product needs justify the operational cost.

### SQLite and synchronous request handling

**Why:** simple local setup, low operational burden and sufficient for a single-user challenge demo.

**Cost:** write contention, limited multi-instance scaling, no asynchronous job lifecycle, and long provider calls occupy request workers.

**Next step:** first add measured latency and concurrency limits. Move to PostgreSQL and a background job queue when multi-user or multi-instance requirements are real.

### Heuristic source tiers and evidence labels

**Why:** visible source context is preferable to opaque model confidence; source type and evidence volume can help a reader inspect the answer.

**Cost:** domain heuristics can misclassify sources; citation count does not measure independence, relevance, recency, or whether a specific answer claim is entailed. “Moderate” must not be interpreted as investment certainty.

**Next step:** calibrate against a reviewed evaluation set, assess claim-to-source support, deduplicate by canonical source identity, score freshness and independence, and keep coverage separate from answer correctness.

## 6. Trustworthiness and security boundaries

### What the implementation does

- Adds title, URL, excerpt, available publication date and a source tier to web citations. Primary classification is restricted to known exchange/regulator host domains; unrecognized issuer investor-relations domains are conservatively classified as `MEDIUM`.
- Labels Yahoo quotes as secondary and potentially delayed.
- Asks the model to use only supplied conversation/evidence, cite numbered sources, report conflicts and state uncertainty.
- Records empty and failed tool calls in the trace.
- Does not treat source excerpts as instructions in the synthesis system prompt.
- Uses parameterized SQL for normal database operations and stores only a reduced file record in API responses (not the local file path).
- Keeps API keys in backend configuration instead of frontend code; `.env` is ignored by git.

### What this does not guarantee

- A source tier is a heuristic, not a fact-check or guarantee of source authority.
- Citation presence does not prove that each claim is entailed by its citation.
- A retrieved excerpt or document may be incomplete, stale, misleading or adversarial.
- The `LOW` / `LIMITED` / `MODERATE` calculation is based on citation count and primary-source count. It is not statistically calibrated.
- The challenge prototype has no user authentication or per-user authorization. Conversation IDs are identifiers, not access control.
- Upload and voice endpoints enforce a 25 MB cap. Upload bytes are written in bounded chunks, but the multipart parser and HTTP server still need infrastructure-level request limits.
- Upload checks extensions, common format signatures and NUL bytes in text-like formats; these checks do not replace parser validation or malware scanning.
- Conversation deletion removes local upload bytes and requests deletion of indexed Gemini documents before deleting database rows. A failed remote deletion keeps the conversation so deletion can be retried.
- No claim should be made that all provider integrations work in a live deployment based on local unit tests alone.

For an interview, frame this as a deliberate prototype boundary: the system demonstrates tool orchestration and inspectable evidence, while production readiness would require access control, resource limits, lifecycle cleanup, evaluation and stronger claim-level validation.

## 7. Known limitations and improvement plan

Priorities below assume the goal is a credible, safe single-user demo first, then a multi-user service. Re-estimate once actual user, latency and deployment requirements are known.

### P0: Remaining demo reliability work

1. **Verify Compose from a host browser.** The proxy and health checks are implemented, but this environment did not have Docker. Build and start from a clean checkout, then verify chat, history, upload and deletion through `http://localhost:3000`.
2. **Set a total request deadline and provider error policy.** Individual provider calls have timeouts, but there is no end-to-end turn deadline, consistent retry budget, or user-safe failure state for every provider exception.
3. **Expand upload validation.** Size is bounded, filenames are unique, MIME is derived from the extension, and common file signatures are checked. Add stronger parser validation, malware scanning and infrastructure-level request limits before public deployment.
4. **Verify real integrations in a controlled environment.** Add a secrets-safe smoke run for Exa, Groq, Gemini upload/query/delete, Yahoo quote, Whisper and TTS. Keep it opt-in, mark expected cost/provider dependency, and never print secrets.

### P1: Improve research quality and answer auditability

1. **Use typed research plans.** Return intent, company identifiers, time scope, specific sub-questions, selected tools, and rationale as validated data. Add explicit behavior for comparisons and questions outside the company-research pattern.
2. **Make searches adaptive.** Inspect result coverage, recency, source diversity and disagreement before deciding whether to issue one follow-up query, within a fixed budget.
3. **Add claim-level citations.** Parse or ask for structured claims with source IDs; verify every factual claim references a valid retrieved source. The answer UI should map citations to the exact evidence card and visibly identify unsupported claims.
4. **Expand source classification carefully.** Add reviewed issuer/regulator host allowlists and preserve the classification rationale. Current strict hostname checks prevent common substring spoofing, but unrecognized issuer pages are conservatively `MEDIUM`.
5. **Model freshness and time correctly.** Distinguish publication time from event time, normalize timezone, and state quote session/as-of details. Mark stale sources and disclose when no current primary filing was found.
6. **Create a contradiction workflow.** Extract numeric claims, units, fiscal periods and definitions; compare sources without averaging incompatible values; state the preferred primary source and unresolved discrepancy.
7. **Build a quality evaluation set.** Curate questions, known answer facts, source targets, expected citations, uncertainty and no-tool cases. Measure factual support, citation precision/recall, freshness, abstention behavior, planner selection, latency and cost. Run regression tests on model/provider changes.

### P2: Production-readiness work if multi-user usage is required

1. Add authentication, ownership checks on every conversation/file route, authorization tests and secrets management.
2. Move persistence to PostgreSQL; add schema migrations, indexes, retention policy and backup/restore verification.
3. Add a job queue for ingestion and long research turns. Return job IDs, expose progress, support cancellation, and persist resumable state.
4. Add streaming answers and trace updates, request IDs, structured logs, metrics for provider latency/error/cost, and privacy-safe tracing.
5. Add rate limits, quotas, upload caps enforced during streaming, file malware scanning, content hashing and retention/deletion controls.
6. Make provider configuration, CORS origins and frontend API base consistent across local, Compose, staging and production environments.
7. Add CI for backend tests, frontend TypeScript/build, linting, dependency/security checks and container build. Pin and regularly update dependencies.

### Suggested implementation sequence

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| 0. Baseline | Record current behavior, supported intents/providers and local setup. | Reproducible setup instructions and a passing isolated unit suite. |
| 1. Demo hardening | Verify Compose API routing; handle file states; make uploads unique, bounded and cleanable; add clear provider failures. | Fresh Compose install works from host browser; upload/ask/delete paths are repeatable; failure traces explain unavailable tools. |
| 2. Research contracts | Typed plans and normalized evidence records with source/date fields. | Planner tests cover greetings, follow-ups, document-only, company risks, price, valuation, comparison, ambiguous and unsupported-company questions. |
| 3. Answer support | Structured claim/citation output and validation; contradiction and freshness checks. | Every material factual claim in evaluation examples has a valid supporting source or is explicitly marked unsupported. |
| 4. Evaluation | Golden research set, regression runner, metrics and provider smoke tests. | Quality report includes evidence coverage, citation quality, freshness, answer correctness, latency and cost. |
| 5. Scale/security | Authentication, authorization, PostgreSQL, background jobs, quotas and observability. | Multi-user isolation, deletion/retention, concurrency and recovery tests pass in staging. |

Avoid implementing all P2 items before validating demand. The best next step for a challenge submission is P0.1 through P0.5 plus the P1 evaluation set; this resolves visible reliability risks and demonstrates disciplined iteration.

## 8. Verification performed for this review

| Check | Result | Scope and limitation |
|---|---|---|
| Backend unit tests | **Pass: 17 tests** using the repository's `.venv312`. | Tests cover planner heuristics, conservative source classification, ticker mapping, SQLite persistence, file-state disclosure, prior-source carry-forward, cleanup/retry behavior and upload validation. Windows temp was redirected into the workspace. |
| Frontend TypeScript | **Pass:** `tsc --noEmit`. | Type checking only; does not prove browser behavior or production compilation. |
| Frontend production build | **Not verified.** | `next build` failed in SWC while canonicalizing the project base path (`Access is denied`, Windows sandbox). This was an environment access error; it is not evidence that the code builds successfully elsewhere. |
| HTTP/API smoke test | **Partially verified.** | Conversation deletion and orchestration paths are tested directly with provider mocks; upload validation is tested at the helper level. A full ASGI/HTTP smoke test remains unverified because Starlette's installed `TestClient` stalled during the first request in this environment. |
| Docker Compose | **Not run.** | Docker is not installed on this machine. Compose health and proxy configuration were reviewed but not executed. |
| Live provider calls | **Not run.** | Unit tests and static inspection do not validate current Groq, Exa, Gemini or Yahoo availability, credentials, quotas or account terms. |

The README verification section now distinguishes local unit/build checks from provider availability. This local review does not independently confirm live provider readiness.

## 9. Interview questions and concise answers

### “Why use tools instead of asking the LLM from memory?”

Company events, filings and market data change. The tool layer fetches public evidence and a structured quote snapshot, then the model writes a readable answer from that evidence. The source cards and trace let the user inspect what was actually retrieved.

### “How do you know the answer is trustworthy?”

I do not treat model confidence as a truth guarantee. I expose source URLs, dates, excerpts and heuristic source types; the prompt asks for claim citations and uncertainty; the trace reports failed or empty tools. The current evidence label is only a coarse coverage heuristic, so the next quality step is claim-level citation validation and an evaluation set.

### “Why is the planner deterministic?”

For a bounded challenge prototype, deterministic rules are predictable, inexpensive and easy to test. The trade-off is limited language coverage. I would evolve it toward a typed plan with a constrained model fallback, validated output and hard tool budgets rather than giving an unconstrained model arbitrary tool access.

### “How do you handle contradictory evidence?”

The prompt directs synthesis to preserve disagreement, distinguish primary from secondary sources and avoid forcing a single explanation. The trace indicates the evidence review step. The current code does not independently detect numeric conflicts, so structured claim extraction and contradiction checks are planned work.

### “How do you avoid unnecessary tools?”

The planner skips web search for greetings, a small set of short follow-ups, creative requests, and document-only prompts when files exist. The benefit is lower latency and cost. The limitation is pattern-based classification, which needs broader intent tests and better handling of unavailable attached files.

### “How are documents isolated?”

Each uploaded document is tagged with the owning conversation ID in Gemini metadata, and each query applies a filter for that ID. This is an important isolation mechanism, but it needs explicit adversarial cross-conversation tests and deletion/retention handling before a multi-user deployment.

### “What would you improve first?”

I would fix the browser-to-backend address in Compose, make upload limits and deletion correct, disclose attached files that were not indexed, and add a repeatable provider smoke test. Then I would build a research evaluation set and enforce claim-level citation support.

### “What is the most important production limitation?”

There is no authentication or ownership authorization, so conversation IDs are not access control. I would not expose this API to multiple users until authentication and per-user authorization are implemented and tested.

## 10. Demo walkthrough

1. Show a listed-company risk question and narrate the two planned evidence checks.
2. Open the research trace and identify which tools succeeded, were empty, or failed.
3. Open citations and distinguish primary disclosures from independent reporting.
4. Ask a quote question for a supported NSE ticker; explain that the Yahoo snapshot is secondary and can be delayed.
5. Upload a document and ask a document-only question; check that the file status is `ready` before treating it as indexed evidence.
6. Demonstrate a greeting or short follow-up and show web search was skipped.
7. State what is heuristic and what remains unknown; do not describe a fixture transcript or mock as live provider evidence.

## 11. Code map

- `backend/services/orchestrator.py` — planner, tool ordering, trace and evidence coverage.
- `backend/services/groq_client.py` — LLM synthesis and voice provider calls.
- `backend/services/exa_client.py` — search normalization and source tiers.
- `backend/services/gemini_file_search.py` — document indexing and retrieval.
- `backend/services/market_data.py` — supported company mapping and quote snapshot.
- `backend/api/chats.py`, `files.py`, `voice.py` — HTTP contracts.
- `backend/db.py` — SQLite schema, persistence and serialization.
- `frontend/components/ChatWorkspace.tsx` — core chat/upload/voice UI and evidence rendering.
- `frontend/lib/api.ts` and `types.ts` — browser API client and data contracts.
- `docs/architecture.md`, `docs/research-methodology.md`, `docs/example-transcripts.md` — supporting project documentation.

