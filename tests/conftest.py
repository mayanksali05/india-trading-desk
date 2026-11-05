import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desk.config import load_settings  # noqa: E402
from desk.market.clock import IST, now_ist  # noqa: E402


@pytest.fixture
def settings():
    return load_settings()


def make_bars(start_price: float, end_price: float, minutes: int = 90, volume: int = 10_000,
              dip: float = 0.0) -> pd.DataFrame:
    """1-minute bars from 09:15 today, moving linearly from start to end price.
    `dip` lowers each bar's low by that many rupees below its close."""
    start = datetime.combine(now_ist().date(), time(9, 15), IST)
    idx = pd.DatetimeIndex([start + timedelta(minutes=i) for i in range(minutes)])
    close = np.linspace(start_price, end_price, minutes)
    return pd.DataFrame(
        {"open": close, "high": close + 0.1, "low": close - dip, "close": close, "volume": volume},
        index=idx,
    )


class FakeSource:
    def __init__(self, bars: dict, adv: float = 1_000_000):
        self.bars = bars
        self.adv = adv
        self.price_override: dict[str, float] = {}

    def intraday(self, symbol):
        return self.bars[symbol]

    def avg_daily_volume(self, symbol, days):
        return self.adv

    def last_price(self, symbol):
        return self.price_override.get(symbol, float(self.bars[symbol]["close"].iloc[-1]))


class FakeClock:
    open = time(9, 15)
    close = time(15, 30)

    def __init__(self, square_off=False):
        self.square_off = square_off

    def is_trading_day(self, d):
        return True

    def is_open(self, now=None):
        return True

    def can_scan(self, now=None):
        return True

    def must_square_off(self, now=None):
        return self.square_off

    def session_fraction(self, now=None):
        return 0.25


class FakeLLM:
    enabled = True

    def __init__(self, verdict="BUY"):
        self.verdict = verdict
        self.calls = []

    def json(self, system, user):
        self.calls.append(system[:10])
        if system.startswith("You are NEWS"):
            return {"reason": "Won a large order announced to NSE this morning.", "source_index": 0}
        return {"reasons": ["a", "b", "c"], "verdict": self.verdict}


class FakeAnnouncements:
    def __init__(self, items=None):
        self.items = items if items is not None else [
            {"when": "today", "subject": "Award of order", "text": "Large order", "url": "https://example.com/a.pdf"}
        ]

    def fetch(self, symbol, since):
        return self.items


class YesApprover:
    def __init__(self, answer=True):
        self.answer = answer
        self.notes = []

    def ask(self, order, ruling, note):
        return self.answer

    def notify(self, text):
        self.notes.append(text)
