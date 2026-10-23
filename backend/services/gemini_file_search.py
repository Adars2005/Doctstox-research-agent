from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote as quote_path

import httpx

from config import GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL, GEMINI_MODEL
from db import get_setting, set_setting

STORE_SETTING = "gemini_file_search_store"


class GeminiError(RuntimeError):
    pass


def available() -> bool:
    return bool(GEMINI_API_KEY)


def _client():
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not configured.")
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=12000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _wait_for_operation(client: Any, operation: Any, timeout_seconds: int = 90) -> Any:
    started = time.time()
    current = operation
    while not getattr(current, "done", False):
        if time.time() - started > timeout_seconds:
            raise GeminiError("File indexing timed out. Try again in a moment.")
        time.sleep(3)
        current = client.operations.get(current)
    error = getattr(current, "error", None)
    if error:
        raise GeminiError(str(error))
    return current


def get_or_create_store() -> str:
    existing = get_setting(STORE_SETTING)
    if existing:
        return existing

    client = _client()
    store = client.file_search_stores.create(
        config={
            "display_name": "docstox-research-store",
            "embedding_model": GEMINI_EMBEDDING_MODEL,
        }
    )
    name = getattr(store, "name", None)
    if not name:
        raise GeminiError("Gemini did not return a File Search store name.")
    set_setting(STORE_SETTING, name)
    return name


def upload_and_index(
    file_path: str,
    display_name: str,
    conversation_id: str,
) -> str:
    client = _client()
    store_name = get_or_create_store()
    operation = client.file_search_stores.upload_to_file_search_store(
        file=file_path,
        file_search_store_name=store_name,
        config={
            "display_name": display_name,
            "custom_metadata": [
                {"key": "conversation_id", "string_value": conversation_id},
                {"key": "filename", "string_value": display_name},
            ],
        },
    )
    finished = _wait_for_operation(client, operation)
    response = getattr(finished, "response", None) or finished
    document_name = (
        getattr(response, "name", None)
        or getattr(getattr(response, "document", None), "name", None)
    )
    if not document_name or "/documents/" not in str(document_name):
        raise GeminiError("Gemini indexed the file but did not return its document resource name.")
    return str(document_name)


def delete_document(document_name: str) -> None:
    """Delete one indexed document and its chunks from the shared File Search store."""
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is required to delete this indexed document.")
    if not document_name.startswith("fileSearchStores/") or "/documents/" not in document_name:
        raise GeminiError("The stored Gemini document name is invalid; it was not deleted.")
    try:
        response = httpx.delete(
            f"https://generativelanguage.googleapis.com/v1beta/{quote_path(document_name, safe='/')}",
            params={"force": "true"},
            headers={"x-goog-api-key": GEMINI_API_KEY},
            timeout=20.0,
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GeminiError("Gemini could not delete an indexed document.") from exc


def query_store(question: str, conversation_id: str) -> dict[str, Any]:
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not configured.")

    store_name = get_setting(STORE_SETTING)
    if not store_name:
        raise GeminiError("No File Search store is available yet.")

    try:
        return _query_via_sdk(question, store_name, conversation_id)
    except Exception:
        return _query_via_rest(question, store_name, conversation_id)


def _query_via_sdk(question: str, store_name: str, conversation_id: str) -> dict[str, Any]:
    client = _client()
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=question,
        tools=[
            {
                "type": "file_search",
                "file_search_store_names": [store_name],
                "metadata_filter": f'conversation_id="{conversation_id}"',
            }
        ],
    )
    return _parse_interaction(interaction)


def _query_via_rest(question: str, store_name: str, conversation_id: str) -> dict[str, Any]:
    models = list(dict.fromkeys((GEMINI_MODEL, "gemini-3.8-flash")))
    last_error = "Gemini File Search failed."
    for model in models:
        response = None
        for attempt in range(2):
            try:
                response = httpx.post(
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                    json={"model": model, "input": question, "tools": [{
                        "type": "file_search", "file_search_store_names": [store_name],
                        "metadata_filter": f'conversation_id="{conversation_id}"',
                    }]},
                    timeout=12.0,
                )
            except httpx.TimeoutException as exc:
                last_error = "Gemini File Search timed out."
                if attempt == 1:
                    continue
            if response is not None and (response.is_success or response.status_code not in (429, 500, 502, 503, 504)):
                break
            if response is not None:
                last_error = response.text[:300]
            if attempt == 0:
                time.sleep(1.5)
        if response is None:
            continue
        if response.is_success:
            return _parse_interaction(response.json())
        last_error = response.text[:300]
    raise GeminiError(last_error)


def _parse_interaction(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {
            "steps": getattr(payload, "steps", []),
            "output_text": getattr(payload, "output_text", None),
        }

    texts: list[str] = []
    citations: list[dict[str, Any]] = []
    for step in data.get("steps") or []:
        if isinstance(step, dict):
            step_type = step.get("type")
            content_blocks = step.get("content") or []
        else:
            step_type = getattr(step, "type", None)
            content_blocks = getattr(step, "content", []) or []
        if step_type != "model_output":
            continue
        for block in content_blocks:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
                for annotation in block.get("annotations") or []:
                    citation = _annotation_to_citation(annotation)
                    if citation:
                        citations.append(citation)
            else:
                if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                    texts.append(block.text)
                for annotation in getattr(block, "annotations", None) or []:
                    citation = _annotation_to_citation(annotation)
                    if citation:
                        citations.append(citation)

    text = "\n".join(texts).strip() or (data.get("output_text") or "").strip()
    return {"text": text, "citations": citations}


def _annotation_to_citation(annotation: Any) -> dict[str, Any] | None:
    if isinstance(annotation, dict):
        if annotation.get("type") not in (None, "file_citation"):
            if annotation.get("file_name") is None:
                return None
        file_name = annotation.get("file_name") or "Uploaded file"
        page = annotation.get("page_number")
        source = annotation.get("source") or file_name
    else:
        if getattr(annotation, "type", "file_citation") not in (None, "file_citation"):
            return None
        file_name = getattr(annotation, "file_name", None) or "Uploaded file"
        page = getattr(annotation, "page_number", None)
        source = getattr(annotation, "source", None) or file_name
    why = f"Cited from uploaded document{f', page {page}' if page else ''}."
    return {
        "title": file_name,
        "url": source if str(source).startswith("http") else "",
        "source_name": file_name,
        "published_date": None,
        "reliability": "PRIMARY",
        "why": why,
        "excerpt": "",
    }


def index_path_exists(path: str) -> bool:
    return Path(path).exists()
