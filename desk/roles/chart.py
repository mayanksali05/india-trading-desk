"""CHART (plain code): turn a flagged move into entry, stop and target, or 'No setup'."""
from __future__ import annotations

import math

import pandas as pd

from desk.models import Setup


def _round_up(x: float, tick: float) -> float:
    return round(math.ceil(round(x / tick, 6)) * tick, 2)


def _round_down(x: float, tick: float) -> float:
    return round(math.floor(round(x / tick, 6)) * tick, 2)


def make_setup(symbol: str, bars: pd.DataFrame, cfg) -> Setup | None:
    """Long-only rules:
    - price must be above today's VWAP (otherwise the move is already fading)
    - stop = recent swing low, but never more than max_stop_pct below entry
      and never closer than min_stop_pct
    - target = entry + min_reward_risk x (entry - stop)
    """
    if len(bars) < cfg.lookback_bars:
        return None
    entry = float(bars["close"].iloc[-1])
    vol = float(bars["volume"].sum())
    vwap = float((bars["close"] * bars["volume"]).sum() / vol) if vol > 0 else entry
    if entry < vwap:
        return None

    swing_low = float(bars.tail(cfg.lookback_bars)["low"].min())
    floor_stop = entry * (1 - cfg.max_stop_pct / 100)
    stop = max(swing_low, floor_stop)
    if entry - stop < entry * cfg.min_stop_pct / 100:
        stop = entry * (1 - cfg.min_stop_pct / 100)

    tick = cfg.tick_size
    entry_r = _round_down(entry, tick)
    stop_r = _round_up(stop, tick)                    # rounding up keeps the stop within max_stop_pct
    if stop_r >= entry_r:
        return None
    target_r = _round_up(entry_r + cfg.min_reward_risk * (entry_r - stop_r), tick)
    return Setup(symbol, entry_r, stop_r, target_r)
