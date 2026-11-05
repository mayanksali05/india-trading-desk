from conftest import FakeAnnouncements, FakeClock, FakeLLM, FakeSource, YesApprover, make_bars

from desk.broker.paper import PaperBroker
from desk.desk import Desk
from desk.models import Order
from desk.roles.news import News
from desk.storage import DB, today


def test_paper_round_trip_charges_and_pnl(settings):
    db = DB(":memory:")
    broker = PaperBroker(db, settings.paper, 100_000)
    pos = broker.open(Order("ABC", 10, 500, 490, 520), last_price=500)
    assert broker.cash() < 100_000 - 5_000              # paid for shares plus charges
    pnl = broker.close(pos, last_price=520, reason="target")
    assert 0 < pnl < 200                                # ₹200 gross minus slippage and charges
    assert broker.open_positions() == []


def _desk(settings, source, verdict="BUY", approve=True, announcements=None, clock=None):
    db = DB(":memory:")
    llm = FakeLLM(verdict)
    return Desk(
        settings, source=source, db=db, llm=llm, clock=clock or FakeClock(),
        broker=PaperBroker(db, settings.paper, settings.sizer.starting_capital),
        approver=YesApprover(approve),
        news=News(llm, announcements or FakeAnnouncements()),
    )


def test_full_cycle_opens_then_stops_out(settings):
    source = FakeSource({"RELIANCE": make_bars(100, 106)})
    settings.watchlist = ["RELIANCE"]
    desk = _desk(settings, source)

    desk.cycle()
    [pos] = desk.broker.open_positions()
    assert pos.symbol == "RELIANCE" and pos.qty == 47   # 5% of ₹1,00,000 at ~₹106

    source.price_override["RELIANCE"] = pos.stop - 0.5
    desk.cycle()
    assert desk.broker.open_positions() == []
    assert desk.db.realised_pnl("paper") < 0

    roles = [r["role"] for r in desk.db.journal_for(today())]
    for role in ("SCOUT", "NEWS", "CHART", "SKEPTIC", "SIZER", "EXECUTOR"):
        assert role in roles


def test_no_trade_when_no_news(settings):
    source = FakeSource({"RELIANCE": make_bars(100, 106)})
    settings.watchlist = ["RELIANCE"]
    desk = _desk(settings, source, announcements=FakeAnnouncements(items=[]))
    desk.cycle()
    assert desk.broker.open_positions() == []
    assert desk.db.verdict_counts()["SKIP"] == 1


def test_no_trade_when_declined_and_flag_not_repeated(settings):
    source = FakeSource({"RELIANCE": make_bars(100, 106)})
    settings.watchlist = ["RELIANCE"]
    desk = _desk(settings, source, approve=False)
    desk.cycle()
    desk.cycle()
    assert desk.broker.open_positions() == []
    assert desk.db.flag_count() == 1                     # same stock is flagged once per day


def test_square_off_closes_everything(settings):
    source = FakeSource({"RELIANCE": make_bars(100, 106)})
    settings.watchlist = ["RELIANCE"]
    clock = FakeClock()
    desk = _desk(settings, source, clock=clock)
    desk.cycle()
    assert len(desk.broker.open_positions()) == 1
    clock.square_off = True
    desk.executor.manage()
    assert desk.broker.open_positions() == []
