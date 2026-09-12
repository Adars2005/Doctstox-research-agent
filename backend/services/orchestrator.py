from __future__ import annotations

import re
from typing import Any

from db import add_message, list_messages, ready_files, touch_conversation
from services import exa_client, gemini_file_search, groq_client

RESEARCH_PATTERNS = (
    r"\bwhy did\b",
    r"\bstock\b",
    r"\bshare price\b",
    r"\bfell\b",
    r"\bfall\b",
    r"\brose\b",
    r"\brise\b",
    r"\bunderperform",
    r"\bearnings\b",
    r"\bcatalyst\b",
    r"\bnifty\b",
    r"\bfilings?\b",
    r"\bannouncement\b",
    r"\brisks?\b",
    r"\bvaluation\b",
    r"\bgood business\b",
    r"\bcompare\b",
    r"\btoday\b",
    r"\bnews\b",
)


def needs_web_research(question: str, has_files: bool) -> bool:
    text = question.lower()
    if any(re.search(pattern, text) for pattern in RESEARCH_PATTERNS):
        return True
    if has_files:
        return False
    return bool(re.search(r"\b(latest|current|recent|market|company)\b", text))


def _title_from_question(question: str) -> str:
    cleaned = " ".join(question.split())
    return cleaned[:72] + ("…" if len(cleaned) > 72 else "")


def run_turn(conversation_id: str, question: str) -> dict[str, Any]:
    existing = list_messages(conversation_id)
    if not existing:
        touch_conversation(conversation_id, title=_title_from_question(question))

    user_message = add_message(conversation_id, "user", question)
    files = ready_files(conversation_id)
    has_files = bool(files)

    tools_used: list[str] = []
    citations: list[dict[str, Any]] = []
    evidence_blocks: list[str] = []

    if has_files and gemini_file_search.available():
        try:
            rag = gemini_file_search.query_store(question, conversation_id)
            if rag.get("text"):
                evidence_blocks.append("Uploaded document evidence:\n" + rag["text"])
                citations.extend(rag.get("citations") or [])
                tools_used.append("gemini_file_search")
        except gemini_file_search.GeminiError as exc:
            evidence_blocks.append(f"Document search unavailable: {exc}")

    if needs_web_research(question, has_files):
        try:
            results = exa_client.search_web(question)
            if results:
                evidence_blocks.append(
                    "Web research from Exa:\n" + exa_client.format_evidence(results)
                )
                citations.extend(results)
                tools_used.append("exa")
            else:
                evidence_blocks.append("Exa returned no usable web results.")
                tools_used.append("exa")
        except exa_client.ExaError as exc:
            evidence_blocks.append(f"Web research unavailable: {exc}")

    history = [
        {"role": item["role"], "content": item["content"]}
        for item in list_messages(conversation_id)
        if item["role"] in {"user", "assistant"}
    ]

    extra_context = "\n\n".join(evidence_blocks) if evidence_blocks else None
    if not extra_context and has_files and not gemini_file_search.available():
        extra_context = (
            "The user uploaded files, but GEMINI_API_KEY is missing so File Search "
            "RAG could not run. Answer from conversation only and say document "
            "indexing is unavailable."
        )

    try:
        answer = groq_client.chat(history, extra_context=extra_context)
        tools_used.append("groq")
    except groq_client.GroqError as exc:
        if tools_used and "gemini_file_search" in tools_used and evidence_blocks:
            answer = evidence_blocks[0]
            tools_used.append("gemini_fallback")
        else:
            answer = str(exc)

    assistant = add_message(
        conversation_id,
        "assistant",
        answer,
        tools=tools_used,
        citations=_dedupe_citations(citations),
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
