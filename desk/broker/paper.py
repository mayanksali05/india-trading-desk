"""Paper account: fake money in SQLite, filled at the live price with slippage and estimated charges."""
from __future__ import annotations

from desk.models import Order, Position


class InsufficientFunds(Exception):
    pass


def estimate_charges(value: float, cfg) -> float:
    """Rough per-order cost. These are estimates; replace them with Zerodha's charge sheet."""
    brokerage = min(cfg.brokerage_cap, value * cfg.brokerage_pct / 100)
    return round(brokerage + value * cfg.other_charges_pct / 100, 2)


class PaperBroker:
    mode = "paper"

    def __init__(self, db, paper_cfg, starting_capital: float):
        self.db = db
        self.cfg = paper_cfg
        db.init_account(starting_capital)

    def cash(self) -> float:
        return self.db.cash()

    def open_positions(self) -> list[Position]:
        return self.db.open_positions(self.mode)

    def open(self, order: Order, last_price: float) -> Position:
        fill = round(last_price * (1 + self.cfg.slippage_pct / 100), 2)
        value = fill * order.qty
        charges = estimate_charges(value, self.cfg)
        cash = self.cash()
        if value + charges > cash:
            raise InsufficientFunds(f"need ₹{value + charges:,.2f}, have ₹{cash:,.2f}")
        self.db.set_cash(cash - value - charges)
        pid = self.db.insert_position(self.mode, order.symbol, order.qty, fill, order.stop, order.target, charges)
        return next(p for p in self.open_positions() if p.id == pid)

    def close(self, pos: Position, last_price: float, reason: str) -> float:
        fill = round(last_price * (1 - self.cfg.slippage_pct / 100), 2)
        value = fill * pos.qty
        charges = estimate_charges(value, self.cfg)
        self.db.set_cash(self.cash() + value - charges)
        total_charges = pos.charges + charges
        pnl = round((fill - pos.entry) * pos.qty - total_charges, 2)
        self.db.close_position(pos.id, fill, reason, total_charges, pnl)
        return pnl
