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
)


class ExaError(RuntimeError):
    pass


def classify_source(url: str, source_name: str | None = None) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or not host:
        return "LOW"
    if any(host == domain or host.endswith(f".{domain}") for domain in PRIMARY_HINTS):
        return "PRIMARY"
    if any(host == domain or host.endswith(f".{domain}") for domain in HIGH_DOMAINS):
        return "HIGH"
    if host.endswith(".gov") or host.endswith(".gov.in"):
        return "PRIMARY"
    if any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("medium.com", "substack.com", "reddit.com", "twitter.com", "x.com")
    ):
        return "LOW"
    return "MEDIUM"


def search_web(query: str, num_results: int = 8) -> list[dict]:
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
                    "text": {"maxCharacters": 1800},
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
                "excerpt": excerpt[:1200],
                "reliability": classify_source(url, title),
                "why": "Independent web evidence from Exa search.",
            }
        )
    return results


def format_evidence(results: list[dict], start_index: int = 0) -> str:
    if not results:
        return ""
    lines = []
    for index, item in enumerate(results, start=start_index + 1):
        published = item.get("published_date") or "date not provided"
        lines.append(
            f"[{index}] [{item['reliability']}] {item['title']} | "
            f"{item['source_name']} | Published: {published}\n"
            f"URL: {item['url']}\nExcerpt: {item['excerpt']}"
        )
    return "\n\n".join(lines)
