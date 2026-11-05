"""Run the desk during NSE hours. Usage:
    python scripts/run_desk.py          # loop all day, posts the daily log after the close
    python scripts/run_desk.py --once   # one cycle, then exit (handy for testing)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desk.config import load_settings, resolve  # noqa: E402
from desk.desk import Desk  # noqa: E402
from desk.market.clock import now_ist  # noqa: E402
from scripts.report import daily_report  # noqa: E402


def setup_logging() -> None:
    logs = resolve("logs")
    logs.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(logs / f"desk-{now_ist():%Y-%m-%d}.log")],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    setup_logging()
    s = load_settings()
    desk = Desk(s)
    log = logging.getLogger("desk")
    log.info("Desk started: mode=%s data=%s approval=%s", s.mode, s.data_source, s.approval)

    if args.once:
        log.info(desk.cycle())
        return

    reported_on = None
    while True:
        now = now_ist()
        status = desk.cycle()
        log.debug(status)
        if desk.clock.is_trading_day(now.date()) and now.time() >= desk.clock.close and reported_on != now.date():
            report = daily_report(desk.db, s, now.date().isoformat())
            print(report)
            desk.approver.notify(report)
            reported_on = now.date()
        time.sleep(s.market.scan_every_minutes * 60)


if __name__ == "__main__":
    main()
