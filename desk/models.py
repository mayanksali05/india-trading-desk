"""Plain data objects passed from one role to the next."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Verdict(str, Enum):
    BUY = "BUY"
    WAIT = "WAIT"
    SKIP = "SKIP"


@dataclass
class Flag:
    """SCOUT: something moved."""
    symbol: str
    last_price: float
    move_pct: float
    rel_volume: float
    at: datetime


@dataclass
class NewsNote:
    """NEWS: why it moved. reason=None means 'No clear reason'."""
    symbol: str
    reason: str | None
    source_url: str | None = None


@dataclass
class Setup:
    """CHART: entry, stop and target."""
    symbol: str
    entry: float
    stop: float
    target: float

    @property
    def risk_per_share(self) -> float:
        return self.entry - self.stop

    @property
    def reward_risk(self) -> float:
        return (self.target - self.entry) / self.risk_per_share

    @property
    def stop_pct(self) -> float:
        return self.risk_per_share / self.entry * 100


@dataclass
class Ruling:
    """SKEPTIC: verdict plus the reasons against."""
    symbol: str
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)


@dataclass
class SizeDecision:
    """SIZER: how many shares (0 = don't trade) and why."""
    qty: int
    reason: str


@dataclass
class Order:
    symbol: str
    qty: int
    entry: float
    stop: float
    target: float


@dataclass
class Position:
    id: int
    mode: str
    symbol: str
    qty: int
    entry: float
    stop: float
    target: float
    opened_at: str
    charges: float = 0.0
    broker_order_id: str | None = None
