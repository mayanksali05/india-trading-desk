"""NEWS (AI): explain why a flagged stock is moving, from NSE corporate announcements.

NSE's announcements endpoint is unofficial: it needs browser-like headers and a cookie from the
home page, and NSE changes it without notice. If fetching fails, NEWS reports no clear reason,
which makes SKEPTIC skip the trade. That is the safe failure."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import requests

from desk.models import Flag, NewsNote
from desk.prompts import NEWS_SYSTEM

log = logging.getLogger("desk")

NSE_HOME = "https://www.nseindia.com"
NSE_ANNOUNCEMENTS = "https://www.nseindia.com/api/corporate-announcements"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


def _parse_when(item: dict) -> datetime | None:
    for key, fmt in (("sort_date", "%Y-%m-%d %H:%M:%S"), ("an_dt", "%d-%b-%Y %H:%M:%S")):
        value = item.get(key)
        if value:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
    return None


class NSEAnnouncements:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._warm = False

    def fetch(self, symbol: str, since: date) -> list[dict]:
        if not self._warm:
            self.session.get(NSE_HOME, timeout=10)
            self._warm = True
        r = self.session.get(NSE_ANNOUNCEMENTS, params={"index": "equities", "symbol": symbol}, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        recent = []
        for item in items:
            when = _parse_when(item)
            if when is None or when.date() >= since:
                recent.append({
                    "when": when.isoformat(sep=" ") if when else "unknown",
                    "subject": item.get("desc", ""),
                    "text": (item.get("attchmntText") or "")[:600],
                    "url": item.get("attchmntFile"),
                })
        return recent[:10]


class News:
    def __init__(self, llm, announcements: NSEAnnouncements | None = None):
        self.llm = llm
        self.announcements = announcements or NSEAnnouncements()

    def explain(self, flag: Flag) -> NewsNote:
        since = flag.at.date() - timedelta(days=1)
        try:
            items = self.announcements.fetch(flag.symbol, since)
        except Exception as e:
            log.warning("NEWS could not fetch announcements for %s: %s", flag.symbol, e)
            items = []
        if not items:
            return NewsNote(flag.symbol, None)

        listing = "\n".join(
            f"[{i}] {it['when']} | {it['subject']} | {it['text']}" for i, it in enumerate(items)
        )
        user = (f"{flag.symbol} is up {flag.move_pct}% at {flag.last_price} on {flag.rel_volume}x normal volume "
                f"({flag.at:%d %b %Y %H:%M} IST).\n\nRecent NSE announcements:\n{listing}")
        data = self.llm.json(NEWS_SYSTEM, user)
        if not data or not data.get("reason"):
            return NewsNote(flag.symbol, None)
        idx = data.get("source_index")
        url = items[idx]["url"] if isinstance(idx, int) and 0 <= idx < len(items) else None
        return NewsNote(flag.symbol, str(data["reason"]).strip(), url)
