"""EXECUTOR (plain code): ask you, place the order, and close positions at stop, target or square-off.

Stops are checked once per cycle (every few minutes), so a fast fall can fill well below the stop.
For live trading, add an exchange-side stop-loss order (see broker/kite.py)."""
from __future__ import annotations

import logging

from desk.models import NewsNote, Order, Position, Ruling

log = logging.getLogger("desk")


class Executor:
    def __init__(self, broker, approver, source, clock, db, cfg):
        self.broker, self.approver, self.source = broker, approver, source
        self.clock, self.db, self.cfg = clock, db, cfg

    def propose(self, order: Order, ruling: Ruling, note: NewsNote) -> Position | None:
        if not self.approver.ask(order, ruling, note):
            self.db.post("EXECUTOR", "Not approved. Nothing placed.", order.symbol, tag="DECLINED")
            return None

        price = self.source.last_price(order.symbol)
        if price <= order.stop:
            self.db.post("EXECUTOR", f"Price {price} is already at or below the stop. Not placed.", order.symbol)
            return None
        if price > order.entry * (1 + self.cfg.max_chase_pct / 100):
            self.db.post("EXECUTOR", f"Price ran to {price}, past the chase limit. Not placed.", order.symbol)
            return None

        try:
            pos = self.broker.open(order, price)
        except Exception as e:
            self.db.post("EXECUTOR", f"Order failed: {e}", order.symbol, tag="ERROR")
            return None
        text = f"FILLED: BUY {pos.qty} at ₹{pos.entry}, stop ₹{pos.stop}, target ₹{pos.target} ({self.broker.mode})"
        self.db.post("EXECUTOR", text, pos.symbol, tag="FILL")
        self.approver.notify(f"{pos.symbol} {text}")
        return pos

    def manage(self) -> None:
        """Close anything at its stop or target, and everything at square-off time."""
        square_off = self.clock.must_square_off()
        for pos in self.broker.open_positions():
            try:
                price = self.source.last_price(pos.symbol)
            except Exception as e:
                log.error("EXECUTOR could not price %s: %s", pos.symbol, e)
                continue
            reason = None
            if square_off:
                reason = "square-off"
            elif price <= pos.stop:
                reason = "stop"
            elif price >= pos.target:
                reason = "target"
            if reason:
                pnl = self.broker.close(pos, price, reason)
                text = f"CLOSED ({reason}) {pos.qty} at ~₹{price}, P&L ₹{pnl:,.2f}"
                self.db.post("EXECUTOR", text, pos.symbol, tag="CLOSE")
                self.approver.notify(f"{pos.symbol} {text}")

    def open_value(self) -> float:
        total = 0.0
        for pos in self.broker.open_positions():
            try:
                total += self.source.last_price(pos.symbol) * pos.qty
            except Exception:
                total += pos.entry * pos.qty
        return total
