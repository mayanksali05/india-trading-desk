"""SKEPTIC (AI): argue against every setup, then rule BUY, WAIT or SKIP. Fails closed to SKIP."""
from __future__ import annotations

from desk.models import Flag, NewsNote, Ruling, Setup, Verdict
from desk.prompts import SKEPTIC_SYSTEM


class Skeptic:
    def __init__(self, llm):
        self.llm = llm

    def rule(self, flag: Flag, note: NewsNote, setup: Setup, counts_today: dict[str, int]) -> Ruling:
        if note.reason is None:
            return Ruling(flag.symbol, Verdict.SKIP, ["No clear reason from NEWS"])

        user = (
            f"Stock: {flag.symbol} (NSE), time {flag.at:%H:%M} IST\n"
            f"Move: +{flag.move_pct}% in the last hour, {flag.rel_volume}x normal volume\n"
            f"NEWS: {note.reason}\n"
            f"CHART: entry {setup.entry}, stop {setup.stop} ({setup.stop_pct:.2f}% risk), "
            f"target {setup.target} (reward/risk {setup.reward_risk:.1f})\n"
            f"Your rulings so far today: BUY {counts_today['BUY']}, WAIT {counts_today['WAIT']}, "
            f"SKIP {counts_today['SKIP']}"
        )
        data = self.llm.json(SKEPTIC_SYSTEM, user)
        if not data:
            return Ruling(flag.symbol, Verdict.SKIP, ["SKEPTIC unavailable, so default SKIP"])
        try:
            verdict = Verdict(str(data.get("verdict", "SKIP")).upper())
        except ValueError:
            verdict = Verdict.SKIP
        reasons = [str(r) for r in data.get("reasons", [])][:3]
        return Ruling(flag.symbol, verdict, reasons)
