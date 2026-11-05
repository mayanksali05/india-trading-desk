from datetime import datetime

from conftest import FakeLLM, make_bars

from desk.market.clock import IST
from desk.models import Flag, NewsNote, Setup, Verdict
from desk.roles.chart import make_setup
from desk.roles.scout import evaluate
from desk.roles.sizer import size
from desk.roles.skeptic import Skeptic


# ---------- SCOUT ----------
def test_scout_flags_a_big_move(settings):
    bars = make_bars(100, 104)   # +4% over the day, but only about +2.6% in the last hour, low volume
    flag = evaluate("ABC", bars, avg_daily_volume=10_000_000, session_fraction=0.25, cfg=settings.scout)
    assert flag is None

    bars = make_bars(100, 106)   # last hour about +3.9%
    flag = evaluate("ABC", bars, avg_daily_volume=10_000_000, session_fraction=0.25, cfg=settings.scout)
    assert flag is not None and flag.move_pct >= 3


def test_scout_flags_volume_spike_only_when_price_is_up(settings):
    up = make_bars(100, 101, volume=100_000)          # 9M traded vs 2.5M expected at 25% of session
    assert evaluate("ABC", up, 10_000_000, 0.25, settings.scout) is not None
    down = make_bars(101, 100, volume=100_000)
    assert evaluate("ABC", down, 10_000_000, 0.25, settings.scout) is None


# ---------- CHART ----------
def test_chart_stop_never_more_than_2pct(settings):
    bars = make_bars(100, 104, dip=5)                 # swing low far below: stop must be capped at 2%
    setup = make_setup("ABC", bars, settings.chart)
    assert setup is not None
    assert setup.stop_pct <= settings.chart.max_stop_pct + 1e-9
    assert setup.reward_risk >= settings.chart.min_reward_risk - 1e-9


def test_chart_no_setup_below_vwap(settings):
    bars = make_bars(104, 100)                        # falling all day: last price under VWAP
    assert make_setup("ABC", bars, settings.chart) is None


def test_chart_prices_on_tick(settings):
    setup = make_setup("ABC", make_bars(100, 103.37), settings.chart)
    for p in (setup.entry, setup.stop, setup.target):
        assert abs(p / 0.05 - round(p / 0.05)) < 1e-6


# ---------- SIZER ----------
SETUP = Setup("ABC", entry=500, stop=490, target=520)


def test_sizer_caps_at_5pct(settings):
    d = size(SETUP, equity=100_000, cash=100_000, open_trades=0, day_pnl=0, cfg=settings.sizer)
    assert d.qty == 10                                # ₹5,000 / ₹500


def test_sizer_zero_when_limits_hit(settings):
    assert size(SETUP, 100_000, 100_000, 3, 0, settings.sizer).qty == 0          # max open trades
    assert size(SETUP, 100_000, 100_000, 0, -2_500, settings.sizer).qty == 0     # daily loss limit
    assert size(SETUP, 1_000, 1_000, 0, 0, settings.sizer).qty == 0              # ₹50 budget < 1 share


# ---------- SKEPTIC ----------
FLAG = Flag("ABC", 104, 3.5, 2.1, datetime(2026, 11, 6, 11, 0, tzinfo=IST))
COUNTS = {"BUY": 0, "WAIT": 0, "SKIP": 0}


def test_skeptic_skips_without_news_and_never_calls_ai():
    llm = FakeLLM("BUY")
    r = Skeptic(llm).rule(FLAG, NewsNote("ABC", None), SETUP, COUNTS)
    assert r.verdict is Verdict.SKIP and llm.calls == []


def test_skeptic_fails_closed():
    class Broken:
        def json(self, s, u):
            return None
    r = Skeptic(Broken()).rule(FLAG, NewsNote("ABC", "order win"), SETUP, COUNTS)
    assert r.verdict is Verdict.SKIP

    class Garbage:
        def json(self, s, u):
            return {"verdict": "DEFINITELY"}
    assert Skeptic(Garbage()).rule(FLAG, NewsNote("ABC", "x"), SETUP, COUNTS).verdict is Verdict.SKIP
