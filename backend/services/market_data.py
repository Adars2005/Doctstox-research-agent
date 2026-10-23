"""Small structured quote adapter using Yahoo Finance's public chart endpoint.

Quotes are treated as secondary, potentially delayed evidence and never as an
exchange-grade execution price. News, filings, and company disclosures still
come from Exa and remain necessary to explain a move.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import quote

import httpx

COMPANY_SYMBOLS = {
    "tcs": ("TCS", "TCS.NS"),
    "tata consultancy services": ("TCS", "TCS.NS"),
    "reliance": ("Reliance Industries", "RELIANCE.NS"),
    "reliance industries": ("Reliance Industries", "RELIANCE.NS"),
    "infosys": ("Infosys", "INFY.NS"),
    "hdfc bank": ("HDFC Bank", "HDFCBANK.NS"),
    "icici bank": ("ICICI Bank", "ICICIBANK.NS"),
    "wipro": ("Wipro", "WIPRO.NS"),
    "bharti airtel": ("Bharti Airtel", "BHARTIARTL.NS"),
}


class MarketDataError(RuntimeError):
    pass


def quote_requested(question: str) -> bool:
    return bool(re.search(r"\b(?:stock|share|price|market|underperform|rise|fall|move|trading|volume|quote)\b", question, re.I))


def resolve_company(question: str) -> tuple[str, str] | None:
    text = question.casefold()
    matches = [(len(name), value) for name, value in COMPANY_SYMBOLS.items() if name in text]
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def fetch_quote(company: str, symbol: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
    try:
        response = httpx.get(
            url,
            params={"range": "5d", "interval": "1d", "events": "history"},
            headers={"User-Agent": "Mozilla/5.0 DocstoxResearch/1.0"},
            timeout=12.0,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        meta = result["meta"]
        quote_data = result["indicators"]["quote"][0]
        closes = [value for value in quote_data.get("close", []) if value is not None]
        volumes = [value for value in quote_data.get("volume", []) if value is not None]
        if not closes:
            raise MarketDataError("No recent quote returned.")
        current = float(meta.get("regularMarketPrice", closes[-1]))
        previous = float(meta.get("chartPreviousClose", meta.get("previousClose", closes[-2] if len(closes) > 1 else current)))
        change = ((current - previous) / previous * 100) if previous else 0.0
        timestamp = int(meta.get("regularMarketTime") or result.get("timestamp", [0])[-1])
        as_of = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else "not provided"
        currency = meta.get("currency", "currency not provided")
        excerpt = (
            f"{company} ({symbol}) quote snapshot: {current:.2f} {currency}; "
            f"previous close {previous:.2f} {currency}; change {change:+.2f}%; "
            f"latest reported daily volume {int(volumes[-1]) if volumes else 'not provided'}; "
            f"provider timestamp {as_of}. Quote is secondary and may be delayed."
        )
        return {
            "title": f"{company} structured market quote ({symbol})",
            "url": f"https://finance.yahoo.com/quote/{quote(symbol)}/",
            "published_date": as_of,
            "source_name": "Yahoo Finance quote data",
            "excerpt": excerpt,
            "reliability": "MEDIUM",
            "why": "Structured market snapshot; secondary source and may be delayed.",
        }
    except MarketDataError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise MarketDataError("Structured market quote is unavailable.") from exc
