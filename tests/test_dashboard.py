import threading
import time

from desk.approval import DashboardApprover
from desk.models import NewsNote, Order, Ruling, Verdict
from desk.storage import DB

ORDER = Order("ABC", 5, 100.0, 98.0, 104.0)
RULING = Ruling("ABC", Verdict.BUY, ["a", "b", "c"])
NOTE = NewsNote("ABC", "order win")


def _answer_after(db, status, delay=0.2):
    def run():
        time.sleep(delay)
        [pending] = db.pending_approvals()
        db.decide_approval(pending["id"], status)
    threading.Thread(target=run, daemon=True).start()


def test_dashboard_approve(tmp_path):
    db = DB(tmp_path / "t.db")
    _answer_after(db, "APPROVED")
    assert DashboardApprover(db, timeout_minutes=0.1, poll_seconds=0.05).ask(ORDER, RULING, NOTE) is True
    assert db.pending_approvals() == []


def test_dashboard_reject(tmp_path):
    db = DB(tmp_path / "t.db")
    _answer_after(db, "REJECTED")
    assert DashboardApprover(db, timeout_minutes=0.1, poll_seconds=0.05).ask(ORDER, RULING, NOTE) is False


def test_dashboard_timeout_expires_and_late_click_is_ignored(tmp_path):
    db = DB(tmp_path / "t.db")
    assert DashboardApprover(db, timeout_minutes=0.003, poll_seconds=0.05).ask(ORDER, RULING, NOTE) is False
    row = db.conn.execute("SELECT id, status FROM approvals").fetchone()
    assert row["status"] == "EXPIRED"
    assert db.decide_approval(row["id"], "APPROVED") is False      # too late
    assert db.approval_status(row["id"]) == "EXPIRED"


def test_dashboard_page_renders_with_demo_data(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    import scripts.demo_data as demo
    monkeypatch.setattr(demo, "PATH", tmp_path / "demo.db")
    demo.main()
    monkeypatch.setenv("DESK_DB", str(tmp_path / "demo.db"))

    at = AppTest.from_file("../dashboard.py", default_timeout=30).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Open trades" in labels and "Skeptic said BUY" in labels
    assert any("HDFCBANK" in t.value for t in at.text)               # pending approval is shown

    approve = next(b for b in at.button if b.label == "Approve")
    approve.click().run()
    assert DB(tmp_path / "demo.db").pending_approvals() == []
