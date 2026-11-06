"""Wires the six roles together. One call to Desk.cycle() = one pass of the assembly line:

    EXECUTOR manages open trades -> SCOUT flags -> NEWS explains -> CHART sets levels
    -> SKEPTIC rules -> SIZER sizes -> EXECUTOR asks you, then places
"""
from __future__ import annotations

import logging
import os

from desk.approval import ConsoleApprover, DashboardApprover, ObserveApprover, TelegramApprover
from desk.broker.paper import PaperBroker
from desk.config import ROOT, resolve
from desk.llm import LLM
from desk.market.clock import MarketClock, load_holidays
from desk.models import Order, Verdict
from desk.roles.chart import make_setup
from desk.roles.executor import Executor
from desk.roles.news import News
from desk.roles.scout import Scout
from desk.roles.sizer import size
from desk.roles.skeptic import Skeptic
from desk.storage import DB, today

log = logging.getLogger("desk")
KILL_SWITCH = ROOT / "STOP"   # create this file (or run scripts/stop.py) to block new trades


class Desk:
    def __init__(self, s, *, source=None, broker=None, approver=None, llm=None, db=None, news=None, clock=None):
        self.s = s
        self.db = db or DB(resolve(s.db_path))
        self.clock = clock or MarketClock(s.market, load_holidays(resolve(s.market.holidays_file)))
        self.source = source or self._make_source()
        self.broker = broker or self._make_broker()
        self.approver = approver or self._make_approver()
        llm = llm or LLM(s.llm)
        self.scout = Scout(s.scout, self.source, self.clock, self.db)
        self.news = news or News(llm)
        self.skeptic = Skeptic(llm)
        self.executor = Executor(self.broker, self.approver, self.source, self.clock, self.db, s.executor)

    # ---- construction ----
    def _make_source(self):
        if self.s.data_source == "kite":
            from desk.broker.kite import get_kite
            from desk.market.data import KiteSource
            return KiteSource(get_kite())
        from desk.market.data import YFinanceSource
        return YFinanceSource()

    def _make_broker(self):
        if self.s.mode == "live":
            from desk.broker.kite import LiveKiteBroker, get_kite
            return LiveKiteBroker(get_kite(), self.db)
        return PaperBroker(self.db, self.s.paper, self.s.sizer.starting_capital)

    def _make_approver(self):
        mode = self.s.approval
        if mode == "console":
            return ConsoleApprover()
        if mode == "dashboard":
            return DashboardApprover(self.db, self.s.executor.approval_timeout_minutes)
        if mode == "telegram":
            return TelegramApprover(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""),
                                    self.s.executor.approval_timeout_minutes)
        if self.s.mode == "live" and mode == "observe":
            log.warning("Live mode with approval: observe will never place anything.")
        return ObserveApprover()

    # ---- the loop body ----
    def equity(self) -> float:
        return self.broker.cash() + self.executor.open_value()

    def cycle(self) -> str:
        if not self.clock.is_open():
            return "market closed"
        self.executor.manage()

        if KILL_SWITCH.exists():
            return "kill switch on: managing open trades only"
        if not self.clock.can_scan():
            return "outside scan window"

        for flag in self.scout.scan(self.s.watchlist):
            note = self.news.explain(flag)
            self.db.post("NEWS", note.reason or "No clear reason", flag.symbol)

            try:
                bars = self.source.intraday(flag.symbol)
            except Exception as e:
                self.db.post("CHART", f"Could not read chart: {e}", flag.symbol)
                continue
            setup = make_setup(flag.symbol, bars, self.s.chart)
            if setup is None:
                self.db.post("CHART", "No setup", flag.symbol)
                continue
            self.db.post("CHART", f"entry {setup.entry}, target {setup.target}, stop {setup.stop}", flag.symbol)

            ruling = self.skeptic.rule(flag, note, setup, self.db.verdict_counts())
            self.db.post("SKEPTIC", f"{' | '.join(ruling.reasons)} => {ruling.verdict.value}", flag.symbol,
                         tag=ruling.verdict.value)
            if ruling.verdict is not Verdict.BUY:
                continue

            equity = self.equity()
            decision = size(setup, equity, self.broker.cash(), len(self.broker.open_positions()),
                            self.db.realised_pnl(self.broker.mode, today()), self.s.sizer)
            self.db.post("SIZER", decision.reason if decision.qty else f"0: {decision.reason}", flag.symbol)
            if decision.qty == 0:
                continue

            order = Order(flag.symbol, decision.qty, setup.entry, setup.stop, setup.target)
            self.executor.propose(order, ruling, note)
        return "cycle done"
