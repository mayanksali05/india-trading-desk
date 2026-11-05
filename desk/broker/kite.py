"""Zerodha Kite Connect: login session and a LIVE broker.

WARNING: LiveKiteBroker places real orders. It has not been run against a real account.
Read it line by line, test with a single share, and keep the paper month first.
Order placement needs a static IP registered in the Kite developer console."""
from __future__ import annotations

import json
import os
from datetime import date

from desk.config import resolve
from desk.models import Order, Position

SESSION_FILE = resolve("data/kite_session.json")


def get_kite():
    """Return a KiteConnect client using today's access token (run scripts/kite_login.py each morning)."""
    from kiteconnect import KiteConnect

    api_key = os.getenv("KITE_API_KEY")
    if not api_key:
        raise RuntimeError("KITE_API_KEY not set in .env")
    if not SESSION_FILE.exists():
        raise RuntimeError("No Kite session. Run: python scripts/kite_login.py")
    session = json.loads(SESSION_FILE.read_text())
    if session.get("date") != date.today().isoformat():
        raise RuntimeError("Kite session is from an earlier day. Run: python scripts/kite_login.py")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(session["access_token"])
    return kite


class LiveKiteBroker:
    mode = "live"

    def __init__(self, kite, db):
        if os.getenv("ALLOW_LIVE") != "1":
            raise RuntimeError("Live broker refused: ALLOW_LIVE is not 1")
        self.kite, self.db = kite, db

    def cash(self) -> float:
        return float(self.kite.margins("equity")["available"]["live_balance"])

    def open_positions(self) -> list[Position]:
        return self.db.open_positions(self.mode)

    def open(self, order: Order, last_price: float) -> Position:
        k = self.kite
        order_id = k.place_order(
            variety=k.VARIETY_REGULAR, exchange=k.EXCHANGE_NSE, tradingsymbol=order.symbol,
            transaction_type=k.TRANSACTION_TYPE_BUY, quantity=order.qty,
            product=k.PRODUCT_MIS, order_type=k.ORDER_TYPE_LIMIT, price=order.entry,
        )
        # TODO before going live: confirm the fill via k.order_history(order_id), handle partial
        # fills, and place an exchange-side stop-loss order so the stop works even if this program stops.
        pid = self.db.insert_position(self.mode, order.symbol, order.qty, order.entry, order.stop, order.target,
                                      0.0, str(order_id))
        return next(p for p in self.open_positions() if p.id == pid)

    def close(self, pos: Position, last_price: float, reason: str) -> float:
        k = self.kite
        k.place_order(
            variety=k.VARIETY_REGULAR, exchange=k.EXCHANGE_NSE, tradingsymbol=pos.symbol,
            transaction_type=k.TRANSACTION_TYPE_SELL, quantity=pos.qty,
            product=k.PRODUCT_MIS, order_type=k.ORDER_TYPE_MARKET,
        )
        # TODO: read the actual fill price and charges from the contract note / order history.
        pnl = round((last_price - pos.entry) * pos.qty, 2)
        self.db.close_position(pos.id, last_price, reason, pos.charges, pnl)
        return pnl
