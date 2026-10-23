from __future__ import annotations

import re
from typing import Any

from db import add_message, list_files, list_messages, ready_files, touch_conversation
from services import exa_client, gemini_file_search, groq_client, market_data

SMALL_TALK_PATTERN = re.compile(
    r"^(?:hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you|thx|bye|goodbye|what can you do|help)\W*$",
    re.IGNORECASE,
)
FOLLOW_UP_PATTERN = re.compile(r"^(?:tell me more|go deeper|elaborate|why\??|how so\??|expand on that|explain that)\W*$", re.I)
DOCUMENT_ONLY_PATTERN = re.compile(
    r"\b(?:in|from|according to|summari[sz]e|extract from|quote from)\s+(?:the|this|my|uploaded|attached)\s+(?:(?:uploaded|attached)\s+)?(?:document|file|filing|report)\b",
    re.IGNORECASE,
)
LIVE_INFO_PATTERN = re.compile(
    r"\b(latest|current|recent|today|right now|this week|this month|news|market|price|stock|share|company|earnings|filing|risk|valuation|thesis|business)\b",
    re.IGNORECASE,
)
CREATIVE_TASK_PATTERN = re.compile(
    r"^\s*(?:write|draft|rewrite|edit|proofread|translate|compose|brainstorm|make up|tell me a joke|create)\b",
    re.IGNORECASE,
)
COMPANY_RESEARCH_PATTERN = re.compile(r"\b(?:stock|share|listed|company|business|earnings|valuation|risks?|thesis|filing|results|price|market)\b", re.I)


def needs_web_research(question: str, has_files: bool) -> bool:
    text = question.strip()
    if not text or SMALL_TALK_PATTERN.fullmatch(text):
        return False
    if FOLLOW_UP_PATTERN.fullmatch(text):
        return False  # rely on the evidence already in this conversation
    if has_files and DOCUMENT_ONLY_PATTERN.search(text) and not LIVE_INFO_PATTERN.search(text):
        return False
    if CREATIVE_TASK_PATTERN.search(text) and not LIVE_INFO_PATTERN.search(text):
        return False
    # Fresh, specific questions should be sourced. Greetings, drafting and simple follow-ups need no call.
    return len(text.split()) >= 5 or bool(LIVE_INFO_PATTERN.search(text))


def build_research_plan(question: str, has_files: bool) -> dict[str, Any]:
    wants_web = needs_web_research(question, has_files)
    subquestions: list[str] = []
    if wants_web:
        if COMPANY_RESEARCH_PATTERN.search(question):
            if re.search(r"\b(?:price|stock|share|rise|fall|move|underperform|today)\b", question, re.I):
                subquestions = [
                    f"{question.strip()} official company announcement exchange filing and investor relations",
                    f"{question.strip()} independent market news sector benchmark and counter-evidence",
                ]
            elif re.search(r"\b(?:valuation|valued|good business|thesis|worth|buy)\b", question, re.I):
                subquestions = [
                    f"{question.strip()} latest official quarterly results revenue margins cash debt and guidance",
                    f"{question.strip()} valuation multiples peer comparison business risks and counter-evidence",
                ]
            else:
                subquestions = [
                    f"{question.strip()} official company disclosures filings and reported risk factors",
                    f"{question.strip()} independent recent news business risks and counter-evidence",
                ]
        else:
            subquestions = [question.strip()]
    steps = ["Identify the question type and evidence needed"]
    if has_files:
        steps.append("Search this conversation’s uploaded documents")
    if wants_web:
        steps.append("Search public web evidence for the checkable sub-questions")
    else:
        steps.append("Skip web search because this is a follow-up, document-only, creative, or conversational request")
    steps.extend(["Check source quality, dates, and disagreement", "Answer with citations and state evidence limits"])
    return {"steps": steps, "web_queries": subquestions}


def _title_from_question(question: str) -> str:
    cleaned = " ".join(question.split())
    return cleaned[:72] + ("…" if len(cleaned) > 72 else "")


def run_turn(conversation_id: str, question: str) -> dict[str, Any]:
    existing = list_messages(conversation_id)
    if not existing:
        touch_conversation(conversation_id, title=_title_from_question(question))

    user_message = add_message(conversation_id, "user", question)
    attached_files = list_files(conversation_id)
    files = ready_files(conversation_id)
    has_files = bool(attached_files)
    plan = build_research_plan(question, has_files)
    plan_detail = " · ".join(plan["steps"])
    if plan["web_queries"]:
        plan_detail += " · Checks: " + " | ".join(plan["web_queries"])
    trace: list[dict[str, str]] = [{"label": "Research plan", "status": "complete", "detail": plan_detail}]
    tools_used: list[str] = []
    citations: list[dict[str, Any]] = []
    evidence_blocks: list[str] = []

    if attached_files:
        not_ready = [item for item in attached_files if item.get("status") != "ready"]
        if not_ready:
            summary = ", ".join(f"{item['filename']} ({item['status']})" for item in not_ready)
            detail = f"Not searched because indexing is incomplete or unavailable: {summary}."
            trace.append({"label": "Attached file availability", "status": "partial" if files else "skipped", "detail": detail})
            evidence_blocks.append(
                "Some attached files were not available to search: " + summary +
                ". Do not imply these files were checked; tell the user which evidence was unavailable."
            )

    if files:
        if gemini_file_search.available():
            trace.append({"label": "Gemini File Search", "status": "running", "detail": f"Searching {len(files)} indexed document(s) in this conversation."})
            try:
                rag = gemini_file_search.query_store(question, conversation_id)
                if rag.get("text"):
                    evidence_blocks.append("Uploaded document evidence:\n" + rag["text"])
                    citations.extend(rag.get("citations") or [])
                    tools_used.append("gemini_file_search")
                    detail = f"Retrieved document passages; {len(rag.get('citations') or [])} document citation(s)."
                    status = "complete"
                else:
                    detail, status = "No matching passages were returned.", "empty"
            except gemini_file_search.GeminiError as exc:
                detail, status = str(exc), "failed"
                evidence_blocks.append("Document search unavailable; do not imply the uploaded documents were checked.")
            trace[-1].update(status=status, detail=detail)
        else:
            trace.append({"label": "Gemini File Search", "status": "skipped", "detail": "GEMINI_API_KEY is not configured; indexed documents were not searched."})
            evidence_blocks.append(
                "Indexed documents are attached, but Gemini File Search is unavailable. "
                "Do not imply the documents were checked; disclose this limitation."
            )

    if plan["web_queries"]:
        matched_company = market_data.resolve_company(question)
        if matched_company and market_data.quote_requested(question):
            company, symbol = matched_company
            trace.append({"label": "Structured market data", "status": "running", "detail": f"Fetching a recent daily quote for {company} ({symbol})."})
            try:
                quote = market_data.fetch_quote(company, symbol)
                citations.append(quote)
                tools_used.append("market_data")
                trace[-1].update(status="complete", detail="Retrieved a structured quote snapshot; secondary source, may be delayed.")
            except market_data.MarketDataError as exc:
                trace[-1].update(status="failed", detail=str(exc))
        for index, query in enumerate(plan["web_queries"], start=1):
            label = f"Exa web search {index}/{len(plan['web_queries'])}"
            trace.append({"label": label, "status": "running", "detail": query})
            try:
                results = exa_client.search_web(query, num_results=5)
                citations.extend(results)
                if results:
                    tools_used.append("exa")
                    trace[-1].update(status="complete", detail=f"{query} — found {len(results)} usable sources.")
                else:
                    trace[-1].update(status="empty", detail=f"{query} — no usable sources returned.")
            except exa_client.ExaError as exc:
                trace[-1].update(status="failed", detail=f"{query} — {exc}")
        if citations:
            citations = _dedupe_citations(citations)
            evidence_blocks.append("Collected evidence (citation numbers match the source cards):\n" + exa_client.format_evidence(citations))
        else:
            evidence_blocks.append("No usable public web sources were retrieved. Do not state that a web check succeeded.")

    if not plan["web_queries"] and FOLLOW_UP_PATTERN.fullmatch(question):
        prior_sources = next(
            (
                item.get("citations") or []
                for item in reversed(existing)
                if item.get("role") == "assistant" and item.get("citations")
            ),
            [],
        )
        if prior_sources:
            citations = _dedupe_citations(prior_sources)
            evidence_blocks.append(
                "Sources carried forward from the previous research answer; keep citation numbers aligned with these source cards:\n"
                + exa_client.format_evidence(citations)
            )
            trace.append({
                "label": "Prior-turn evidence",
                "status": "complete",
                "detail": f"Carried forward {len(citations)} source card(s) for this follow-up; no new web search was run.",
            })

    history = [
        {"role": item["role"], "content": item["content"]}
        for item in list_messages(conversation_id)
        if item["role"] in {"user", "assistant"}
    ]
    evidence_count = len(citations)
    primary_count = sum(1 for item in citations if item.get("reliability") == "PRIMARY")
    if evidence_count == 0:
        assessment = "LOW — no citations available for this turn"
    elif evidence_count < 3 or primary_count == 0:
        assessment = "LIMITED — sparse evidence or no primary source; qualify conclusions"
    else:
        assessment = "MODERATE — multiple sources collected; verify agreement and dates before concluding"
    trace.append({"label": "Evidence check", "status": "complete", "detail": f"{assessment}. Check whether sources conflict; distinguish sourced facts from interpretation."})
    extra_context = "\n\n".join(evidence_blocks) if evidence_blocks else None
    try:
        answer = groq_client.chat(history, extra_context=extra_context)
        tools_used.append("groq")
        trace.append({"label": "Groq synthesis", "status": "complete", "detail": "Drafted a response using the conversation and collected evidence."})
    except groq_client.GroqError as exc:
        trace.append({"label": "Groq synthesis", "status": "failed", "detail": str(exc)})
        answer = evidence_blocks[0] if evidence_blocks else str(exc)

    assistant = add_message(
        conversation_id,
        "assistant",
        answer,
        tools=list(dict.fromkeys(tools_used)),
        citations=citations,
        trace=trace,
    )
    return {"user": user_message, "assistant": assistant}


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in citations:
        key = (item.get("url") or item.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:8]
