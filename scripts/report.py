"""Daily log and the month-end test: did the desk beat simply holding the NIFTY 50?
Usage:
    python scripts/report.py                 # today's log
    python scripts/report.py --day 2026-11-06
    python scripts/report.py --benchmark     # account return vs NIFTY 50 since the desk started
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desk.config import load_settings, resolve  # noqa: E402
from desk.storage import DB, today  # noqa: E402


def daily_report(db: DB, s, day: str) -> str:
    mode = s.mode
    lines = [f"DESK LOG {day} ({mode})"]

    counts = db.verdict_counts(day)
    total = sum(counts.values())
    lines.append(f"Skeptic: BUY {counts['BUY']}, WAIT {counts['WAIT']}, SKIP {counts['SKIP']} of {total} setups")
    if total >= 3 and counts["BUY"] / total > 0.5:
        lines.append("WARNING: Skeptic approved more than half today. Tighten its prompt.")

    for p in db.positions_on(mode, day):
        if p["status"] == "CLOSED":
            lines.append(f"  {p['symbol']}: {p['qty']} @ {p['entry']} -> {p['exit_price']} "
                         f"({p['exit_reason']}), P&L ₹{p['pnl']:,.2f}")
        else:
            lines.append(f"  {p['symbol']}: {p['qty']} @ {p['entry']} still OPEN")

    lines.append(f"Realised P&L today: ₹{db.realised_pnl(mode, day):,.2f}")
    if mode == "paper":
        acct = db.account()
        if acct:
            lines.append(f"Paper cash: ₹{acct['cash']:,.2f} (started with ₹{acct['starting_capital']:,.2f})")
    return "\n".join(lines)


def benchmark(db: DB, s) -> str:
    """Compare realised account return with NIFTY 50 over the same period (Yahoo symbol ^NSEI)."""
    import yfinance as yf

    acct = db.account()
    if acct is None:
        return "No paper account yet."
    start = acct["started_on"]
    desk_return = db.realised_pnl("paper") / acct["starting_capital"] * 100
    nifty = yf.Ticker("^NSEI").history(start=start)["Close"]
    if len(nifty) < 2:
        return f"Not enough NIFTY data since {start} yet."
    nifty_return = (nifty.iloc[-1] / nifty.iloc[0] - 1) * 100
    verdict = "beat" if desk_return > nifty_return else "did NOT beat"
    return (f"Since {start}: desk {desk_return:+.2f}% (realised), NIFTY 50 {nifty_return:+.2f}%. "
            f"The desk {verdict} simply holding the index.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default=today())
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    s = load_settings()
    db = DB(resolve(s.db_path))
    print(benchmark(db, s) if args.benchmark else daily_report(db, s, args.day))


if __name__ == "__main__":
    main()
