"""Price sources. Every source returns today's 1-minute bars as a DataFrame with an
IST index and lowercase columns: open, high, low, close, volume."""
from __future__ import annotations

from datetime import timedelta
from typing import Protocol

import pandas as pd

from desk.market.clock import IST, now_ist


class PriceSource(Protocol):
    def intraday(self, symbol: str) -> pd.DataFrame: ...
    def avg_daily_volume(self, symbol: str, days: int) -> float: ...
    def last_price(self, symbol: str) -> float: ...


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    df.index = idx
    return df.sort_index()


class YFinanceSource:
    """Free Yahoo Finance data for NSE (SYMBOL.NS). Delayed and unofficial: paper testing only."""

    def __init__(self):
        import yfinance as yf
        self.yf = yf
        self._adv: dict[tuple[str, str], float] = {}

    def intraday(self, symbol: str) -> pd.DataFrame:
        df = self.yf.Ticker(f"{symbol}.NS").history(period="1d", interval="1m")
        if df.empty:
            raise RuntimeError(f"no intraday data for {symbol}")
        df = normalise(df)
        return df[df.index.date == now_ist().date()]

    def avg_daily_volume(self, symbol: str, days: int) -> float:
        key = (symbol, now_ist().date().isoformat())
        if key not in self._adv:
            df = normalise(self.yf.Ticker(f"{symbol}.NS").history(period=f"{days + 15}d", interval="1d"))
            past = df[df.index.date < now_ist().date()].tail(days)
            self._adv[key] = float(past["volume"].mean()) if len(past) else 0.0
        return self._adv[key]

    def last_price(self, symbol: str) -> float:
        return float(self.intraday(symbol)["close"].iloc[-1])


class KiteSource:
    """Zerodha Kite Connect data. Needs the paid Connect plan (live + historical data)."""

    def __init__(self, kite):
        self.kite = kite
        self._tokens: dict[str, int] | None = None
        self._adv: dict[tuple[str, str], float] = {}

    def _token(self, symbol: str) -> int:
        if self._tokens is None:
            self._tokens = {i["tradingsymbol"]: i["instrument_token"] for i in self.kite.instruments("NSE")}
        return self._tokens[symbol]

    def intraday(self, symbol: str) -> pd.DataFrame:
        now = now_ist()
        start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        rows = self.kite.historical_data(self._token(symbol), start, now, "minute")
        if not rows:
            raise RuntimeError(f"no intraday data for {symbol}")
        return normalise(pd.DataFrame(rows).set_index("date"))

    def avg_daily_volume(self, symbol: str, days: int) -> float:
        key = (symbol, now_ist().date().isoformat())
        if key not in self._adv:
            now = now_ist()
            rows = self.kite.historical_data(self._token(symbol), now - timedelta(days=days * 2), now, "day")
            df = normalise(pd.DataFrame(rows).set_index("date"))
            past = df[df.index.date < now.date()].tail(days)
            self._adv[key] = float(past["volume"].mean()) if len(past) else 0.0
        return self._adv[key]

    def last_price(self, symbol: str) -> float:
        key = f"NSE:{symbol}"
        return float(self.kite.ltp([key])[key]["last_price"])
