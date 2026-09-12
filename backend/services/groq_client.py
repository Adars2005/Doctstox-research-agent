from __future__ import annotations

from typing import Any

import httpx

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_STT_MODEL,
    GROQ_TTS_MODEL,
    GROQ_TTS_VOICE,
)

GROQ_BASE = "https://api.groq.com/openai/v1"

SYSTEM_PROMPT = """You are Docstox-research agent, an evidence-driven equity research assistant.

Rules:
- Use only the provided conversation, document evidence, and web evidence.
- Do not invent financial figures, catalysts, or sources.
- Do not treat coincidence as causality. Prefer "strongest supported explanation", "likely contributor", or "insufficient evidence".
- If evidence is missing, say so clearly.
- Keep answers concise and structured.
- Never expose hidden chain-of-thought. Share only findings, evidence, and confidence as HIGH, MEDIUM, or LOW.
"""


class GroqError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY is not configured.")
    return {"Authorization": f"Bearer {GROQ_API_KEY}"}


def chat(
    messages: list[dict[str, str]],
    extra_context: str | None = None,
) -> str:
    payload_messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if extra_context:
        payload_messages.append(
            {
                "role": "system",
                "content": "Evidence collected for this turn:\n" + extra_context,
            }
        )
    payload_messages.extend(messages)

    last_error = "Groq chat failed."
    for model in (GROQ_MODEL, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        try:
            response = httpx.post(
                f"{GROQ_BASE}/chat/completions",
                headers={**_headers(), "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": payload_messages,
                    "temperature": 0.2,
                },
                timeout=60.0,
            )
            if response.is_success:
                data: dict[str, Any] = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content:
                    return content.strip()
                last_error = "Groq returned an empty reply."
                continue
            last_error = response.text[:400]
        except httpx.HTTPError as exc:
            last_error = "Groq is unavailable right now."
            if model == "llama-3.1-8b-instant":
                raise GroqError(last_error) from exc
    raise GroqError(f"Groq chat failed: {last_error}")


def transcribe_audio(filename: str, content: bytes, content_type: str | None) -> str:
    try:
        response = httpx.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers=_headers(),
            files={"file": (filename, content, content_type or "application/octet-stream")},
            data={"model": GROQ_STT_MODEL},
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GroqError(f"Transcription failed: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise GroqError("Groq speech-to-text is unavailable.") from exc

    text = response.json().get("text", "").strip()
    if not text:
        raise GroqError("No speech was recognized.")
    return text


def speak(text: str) -> bytes:
    clipped = text.strip()[:1200]
    if not clipped:
        raise GroqError("Nothing to speak.")
    try:
        response = httpx.post(
            f"{GROQ_BASE}/audio/speech",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "model": GROQ_TTS_MODEL,
                "voice": GROQ_TTS_VOICE,
                "input": clipped,
                "response_format": "wav",
            },
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GroqError(f"Speech synthesis failed: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise GroqError("Groq text-to-speech is unavailable.") from exc
    return response.content
