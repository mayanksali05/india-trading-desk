"""SIZER (plain code): hard limits. If any limit is hit, the answer is zero."""
from __future__ import annotations

from desk.models import Setup, SizeDecision


def size(setup: Setup, equity: float, cash: float, open_trades: int, day_pnl: float, cfg) -> SizeDecision:
    if open_trades >= cfg.max_open_trades:
        return SizeDecision(0, f"{open_trades} of {cfg.max_open_trades} trades already open")
    if day_pnl <= -equity * cfg.max_daily_loss_pct / 100:
        return SizeDecision(0, f"daily loss limit hit (₹{day_pnl:,.0f})")

    budget = min(equity * cfg.max_position_pct / 100, cash)
    qty = int(budget // setup.entry)
    if qty < 1:
        return SizeDecision(0, f"budget ₹{budget:,.0f} is below one share at ₹{setup.entry}")
    value = qty * setup.entry
    return SizeDecision(
        qty,
        f"{qty} shares = ₹{value:,.0f} ({value / equity * 100:.1f}% of account). "
        f"Open trades after this one: {open_trades + 1} of {cfg.max_open_trades}",
    )
