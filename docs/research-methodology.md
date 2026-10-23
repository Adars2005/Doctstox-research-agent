# Research methodology

## Planning and tool judgment

The planner classifies the user's request before it calls providers. It avoids web calls for greetings, creative writing, short conversational follow-ups, and questions explicitly limited to an uploaded document. A current or substantive factual question is split into at most two public-web searches: one focused on official disclosures/filings and one on independent coverage or counter-evidence. A small supported set of Indian listed companies also gets a structured daily quote when the question asks about price or market movement. Uploaded files are searched only in their owning conversation.

The plan shown in the chat lists the evidence steps and sub-questions. The persisted trace reports which tools ran, how many results were returned, and whether a call failed or returned no evidence. A recognized short follow-up carries forward the prior answer's source cards and evidence excerpts without repeating web search. The trace is an action log, not hidden chain-of-thought.

## Evidence and trustworthiness

- Every web source includes a title, URL, excerpt, publication date when available, and a heuristic tier (`PRIMARY`, `HIGH`, `MEDIUM`, `LOW`). `PRIMARY` is conservative and currently recognizes exchange/regulator domains; unrecognized issuer investor-relations domains remain `MEDIUM`. Tier labels describe source type and do not certify truth.
- The quote adapter provides structured price/previous-close/change/volume/timestamp data for a maintained list of NSE tickers. Yahoo Finance is secondary and may be delayed. Missing quote data is not filled from model memory.
- The answer should cite material factual claims with source markers, separate observations from interpretation, check dates and conflicts, and explain when evidence is missing or indirect.
- Internal evidence check is qualitative: no citations is low coverage; fewer than three sources or no primary source is limited; multiple sources including a primary source is moderate coverage. This does not prove agreement, correctness, or investment quality. The synthesis prompt asks the model to inspect for disagreement, but the application does not independently validate claim support.
- If providers fail or return no usable sources, the trace records that result and the answer must say what could not be checked. The system does not present a failed search as a successful review.
- Attachments that are not ready are named in the trace and evidence context; the answer is instructed not to imply that those files were searched.

## Stopping policy

The agent currently makes at most two targeted Exa calls per turn, then synthesizes. This limits latency and provider use. For consequential conclusions, users should inspect the linked primary sources and consult current exchange filings; the agent does not provide personalized investment advice.
