from __future__ import annotations

from urllib.parse import urlparse

import httpx

from config import EXA_API_KEY

HIGH_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "economictimes.indiatimes.com",
    "moneycontrol.com",
    "livemint.com",
    "business-standard.com",
    "thehindu.com",
}

PRIMARY_HINTS = (
    "nseindia.com",
    "bseindia.com",
    "sec.gov",
    "sebi.gov.in",
    "investor.",
    "ir.",
)


class ExaError(RuntimeError):
    pass


def classify_source(url: str, source_name: str | None = None) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    blob = f"{host} {source_name or ''}".lower()
    if any(hint in blob for hint in PRIMARY_HINTS):
        return "PRIMARY"
    if any(host.endswith(domain) or domain in host for domain in HIGH_DOMAINS):
        return "HIGH"
    if host.endswith(".gov") or host.endswith(".gov.in"):
        return "PRIMARY"
    if any(token in blob for token in ("blog", "medium.com", "substack", "reddit", "twitter", "x.com")):
        return "LOW"
    return "MEDIUM"


def search_web(query: str, num_results: int = 6) -> list[dict]:
    if not EXA_API_KEY:
        raise ExaError("EXA_API_KEY is not configured.")

    try:
        response = httpx.post(
            "https://api.exa.ai/search",
            headers={
                "Authorization": f"Bearer {EXA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "type": "auto",
                "numResults": num_results,
                "contents": {
                    "highlights": True,
                    "text": {"maxCharacters": 1200},
                },
            },
            timeout=45.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExaError(f"Exa search failed: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise ExaError("Exa is unavailable right now.") from exc

    seen: set[str] = set()
    results: list[dict] = []
    for item in response.json().get("results", []):
        url = (item.get("url") or "").strip()
        if not url:
            continue
        canonical = url.split("?")[0].rstrip("/").lower()
        if canonical in seen:
            continue
        seen.add(canonical)
        highlights = item.get("highlights") or []
        excerpt = " ".join(highlights) if highlights else (item.get("text") or "")
        if not excerpt:
            continue
        title = item.get("title") or url
        results.append(
            {
                "title": title,
                "url": url,
                "published_date": item.get("publishedDate"),
                "source_name": urlparse(url).netloc.removeprefix("www."),
                "excerpt": excerpt[:800],
                "reliability": classify_source(url, title),
                "why": "Independent web evidence from Exa search.",
            }
        )
    return results


def format_evidence(results: list[dict]) -> str:
    if not results:
        return ""
    lines = []
    for index, item in enumerate(results, start=1):
        lines.append(
            f"{index}. [{item['reliability']}] {item['title']} ({item['url']})\n{item['excerpt']}"
        )
    return "\n\n".join(lines)
