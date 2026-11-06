"""Create data/demo.db with made-up desk activity so you can try the dashboard before the market opens.
    python scripts/demo_data.py
    streamlit run dashboard.py -- --db data/demo.db
Everything in it is fake. Your real data/desk.db is not touched."""
from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desk.config import resolve  # noqa: E402
from desk.market.clock import IST, now_ist  # noqa: E402
from desk.storage import DB  # noqa: E402

PATH = resolve("data/demo.db")


def at(day_offset: int, hh: int, mm: int) -> str:
    d = now_ist().date() + timedelta(days=day_offset)
    return datetime.combine(d, time(hh, mm), IST).isoformat(timespec="seconds")


def main() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(PATH) + suffix).unlink(missing_ok=True)
    db = DB(PATH)
    c = db.conn
    start = 100_000.0

    def post(ts, symbol, role, message, tag=None):
        c.execute("INSERT INTO journal (at, day, symbol, role, tag, message) VALUES (?, ?, ?, ?, ?, ?)",
                  (ts, ts[:10], symbol, role, tag, message))

    def position(symbol, qty, entry, stop, target, opened, closed=None, exit_price=None, reason=None, charges=0.0):
        pnl = round((exit_price - entry) * qty - charges, 2) if closed else None
        c.execute(
            "INSERT INTO positions (mode, symbol, qty, entry, stop, target, opened_at, status, exit_price,"
            " closed_at, exit_reason, charges, pnl) VALUES ('paper', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, qty, entry, stop, target, opened, "CLOSED" if closed else "OPEN", exit_price, closed,
             reason, charges, pnl))
        return pnl, entry * qty + charges

    # past closed trades
    realised = 0.0
    for d, sym, qty, entry, stop, target, exit_p, why in [
        (-9, "TATAMOTORS", 70, 712.4, 699.2, 738.8, 699.0, "stop"),
        (-8, "ICICIBANK", 3, 1402.0, 1378.0, 1450.0, 1450.5, "target"),
        (-6, "INFY", 3, 1630.0, 1601.0, 1688.0, 1641.2, "square-off"),
        (-3, "SBIN", 6, 842.0, 826.0, 874.0, 825.5, "stop"),
        (-2, "LT", 1, 3720.0, 3660.0, 3840.0, 3842.0, "target"),
    ]:
        pnl, _ = position(sym, qty, entry, stop, target, at(d, 11, 5), at(d, 14, 20), exit_p, why, charges=18.0)
        realised += pnl

    # today: one trade went through, one skipped for no news, one with no setup, one waiting for approval
    post(at(0, 10, 5), "RELIANCE", "SCOUT", "FLAG: +3.4% in the window, 2.6x normal volume, at 1418.2")
    post(at(0, 10, 5), "RELIANCE", "NEWS", "Board approved a new energy subsidiary investment, filed with NSE "
                                           "this morning.")
    post(at(0, 10, 6), "RELIANCE", "CHART", "entry 1418.2, target 1474.9, stop 1389.85")
    post(at(0, 10, 6), "RELIANCE", "SKEPTIC", "Most of the move may be done | Announcement is strategic, not "
         "earnings | Broad market is flat => BUY", tag="BUY")
    post(at(0, 10, 6), "RELIANCE", "SIZER", "3 shares = ₹4,255 (4.3% of account). Open trades after this one: 1 of 3")
    post(at(0, 10, 8), "RELIANCE", "EXECUTOR", "FILLED: BUY 3 at ₹1418.9, stop ₹1389.85, target ₹1474.9 (paper)",
         tag="FILL")
    _, cost = position("RELIANCE", 3, 1418.9, 1389.85, 1474.9, at(0, 10, 8), charges=2.1)

    post(at(0, 11, 20), "ITC", "SCOUT", "FLAG: +1.1% in the window, 2.3x normal volume, at 412.6")
    post(at(0, 11, 20), "ITC", "NEWS", "No clear reason")
    post(at(0, 11, 20), "ITC", "CHART", "entry 412.6, target 425.0, stop 406.4")
    post(at(0, 11, 20), "ITC", "SKEPTIC", "No clear reason from NEWS => SKIP", tag="SKIP")

    post(at(0, 12, 40), "AXISBANK", "SCOUT", "FLAG: +3.1% in the window, 1.4x normal volume, at 1188.0")
    post(at(0, 12, 40), "AXISBANK", "NEWS", "Brokerage upgrade reported; no exchange filing today.")
    post(at(0, 12, 41), "AXISBANK", "CHART", "No setup")

    post(at(0, 13, 55), "BHARTIARTL", "SCOUT", "FLAG: +3.6% in the window, 3.1x normal volume, at 1862.4")
    post(at(0, 13, 55), "BHARTIARTL", "NEWS", "Tariff increase announced to the exchange at 13:30.")
    post(at(0, 13, 56), "BHARTIARTL", "CHART", "entry 1862.4, target 1936.95, stop 1825.15")
    post(at(0, 13, 56), "BHARTIARTL", "SKEPTIC", "Late in the session | Gap already priced in | Telecom peers "
         "not confirming => WAIT", tag="WAIT")

    for sym, price, move, rv, hh, mm in [("RELIANCE", 1418.2, 3.4, 2.6, 10, 5), ("ITC", 412.6, 1.1, 2.3, 11, 20),
                                        ("AXISBANK", 1188.0, 3.1, 1.4, 12, 40),
                                        ("BHARTIARTL", 1862.4, 3.6, 3.1, 13, 55)]:
        ts = at(0, hh, mm)
        c.execute("INSERT INTO flags (day, symbol, last_price, move_pct, rel_volume, at) VALUES (?, ?, ?, ?, ?, ?)",
                  (ts[:10], sym, price, move, rv, ts))

    c.execute("INSERT INTO approvals (created_at, symbol, details) VALUES (?, ?, ?)", (
        at(0, 14, 2), "HDFCBANK",
        "Approval needed: BUY 2 HDFCBANK near ₹1712.3\nStop ₹1680.0 | Target ₹1776.9\n"
        "News: Q2 asset quality update filed with NSE.\nSkeptic ruled BUY, despite:\n"
        "  - Move started before the filing\n  - Banking index is weak\n  - Close to the 14:45 cut-off"))

    c.execute("INSERT INTO account (id, cash, starting_capital, started_on) VALUES (1, ?, ?, ?)",
              (round(start + realised - cost, 2), start, at(-10, 9, 15)[:10]))
    c.commit()
    print(f"Demo data written to {PATH}\nNow run: streamlit run dashboard.py -- --db data/demo.db")


if __name__ == "__main__":
    main()
