"""NSE session times in IST."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def _t(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def load_holidays(path: Path) -> set[date]:
    if not path.exists():
        return set()
    days = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            days.add(date.fromisoformat(line))
    return days


class MarketClock:
    def __init__(self, cfg, holidays: set[date] | None = None):
        self.open = _t(cfg.open)
        self.close = _t(cfg.close)
        self.scan_start = _t(cfg.scan_start)
        self.cutoff = _t(cfg.no_new_trades_after)
        self.square_off = _t(cfg.square_off_at)
        self.holidays = holidays or set()

    def _now(self, now: datetime | None) -> datetime:
        return (now or now_ist()).astimezone(IST)

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def is_open(self, now: datetime | None = None) -> bool:
        now = self._now(now)
        return self.is_trading_day(now.date()) and self.open <= now.time() < self.close

    def can_scan(self, now: datetime | None = None) -> bool:
        now = self._now(now)
        return self.is_open(now) and self.scan_start <= now.time() < self.cutoff

    def must_square_off(self, now: datetime | None = None) -> bool:
        now = self._now(now)
        return self.is_open(now) and now.time() >= self.square_off

    def session_fraction(self, now: datetime | None = None) -> float:
        """Share of the trading session that has elapsed, in (0, 1]."""
        now = self._now(now)
        start = datetime.combine(now.date(), self.open, IST)
        end = datetime.combine(now.date(), self.close, IST)
        frac = (now - start) / (end - start)
        return min(max(frac, 1e-6), 1.0)
