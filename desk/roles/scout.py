"""SCOUT (plain code): flag watchlist stocks that jump or trade unusual volume. Never judges the move."""
from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from desk.models import Flag

log = logging.getLogger("desk")


def evaluate(symbol: str, bars: pd.DataFrame, avg_daily_volume: float, session_fraction: float, cfg) -> Flag | None:
    """Return a Flag if the stock is up >= move_pct over the window, or volume is >= volume_multiple
    times normal for this point in the session while the price is up. Long-only desk, so falls are ignored."""
    if len(bars) < 2:
        return None
    last = float(bars["close"].iloc[-1])
    window_start = bars.index[-1] - timedelta(minutes=cfg.move_window_minutes)
    earlier = bars[bars.index <= window_start]
    ref = float(earlier["close"].iloc[-1]) if len(earlier) else float(bars["open"].iloc[0])
    move_pct = (last / ref - 1) * 100

    expected_volume = avg_daily_volume * session_fraction
    rel_volume = float(bars["volume"].sum()) / expected_volume if expected_volume > 0 else 0.0

    if move_pct >= cfg.move_pct or (rel_volume >= cfg.volume_multiple and move_pct > 0):
        return Flag(symbol, round(last, 2), round(move_pct, 2), round(rel_volume, 2), bars.index[-1].to_pydatetime())
    return None


class Scout:
    def __init__(self, cfg, source, clock, db):
        self.cfg, self.source, self.clock, self.db = cfg, source, clock, db

    def scan(self, watchlist: list[str]) -> list[Flag]:
        remaining = self.cfg.max_flags_per_day - self.db.flag_count()
        if remaining <= 0:
            return []
        already = self.db.flags_today()
        fraction = self.clock.session_fraction()
        found: list[Flag] = []
        for symbol in watchlist:
            if symbol in already:
                continue
            try:
                bars = self.source.intraday(symbol)
                adv = self.source.avg_daily_volume(symbol, self.cfg.volume_lookback_days)
            except Exception as e:
                log.warning("SCOUT could not read %s: %s", symbol, e)
                continue
            flag = evaluate(symbol, bars, adv, fraction, self.cfg)
            if flag:
                found.append(flag)

        found.sort(key=lambda f: f.move_pct, reverse=True)
        found = found[:remaining]
        for f in found:
            self.db.record_flag(f)
            self.db.post("SCOUT", f"FLAG: +{f.move_pct}% in the window, {f.rel_volume}x normal volume, at {f.last_price}",
                         f.symbol)
        return found
