"""Local dashboard for the India Trading Desk. Opens in your browser at http://localhost:8501

    streamlit run dashboard.py                        # your desk (data/desk.db)
    python scripts/demo_data.py                       # make sample data, then:
    streamlit run dashboard.py -- --db data/demo.db   # look at the sample

Run it next to scripts/run_desk.py (two terminals). The dashboard only reads the database, except for
the Approve / Reject buttons and the emergency stop switch.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from desk.config import load_settings, resolve  # noqa: E402
from desk.storage import DB, today  # noqa: E402

KILL_SWITCH = ROOT / "STOP"
ROLE_ICON = {"SCOUT": "🔭", "NEWS": "📰", "CHART": "📈", "SKEPTIC": "🛑", "SIZER": "⚖️", "EXECUTOR": "✅"}

st.set_page_config(page_title="India Trading Desk", page_icon="📊", layout="wide")


def inr(x: float) -> str:
    return f"-₹{abs(x):,.0f}" if x < 0 else f"₹{x:,.0f}"


def db_path(settings) -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    args, _ = parser.parse_known_args()
    return resolve(args.db or os.getenv("DESK_DB") or settings.db_path)


@st.cache_resource
def get_db(path: str) -> DB:
    return DB(path)


try:
    s = load_settings()
except Exception as e:
    st.error(f"Could not load config/settings.yaml: {e}")
    st.stop()

path = db_path(s)
db = get_db(str(path))
mode = s.mode

# ---------------- sidebar ----------------
with st.sidebar:
    st.header("📊 Trading Desk")
    st.write(f"Mode **{mode}** · data **{s.data_source}** · approval **{s.approval}**")
    st.caption(f"Database: {path.name}")
    day = st.date_input("Show day", value=date.fromisoformat(today())).isoformat()

    st.divider()
    if KILL_SWITCH.exists():
        st.error("Emergency stop is ON. No new trades.")
        if st.button("Turn emergency stop off"):
            KILL_SWITCH.unlink(missing_ok=True)
            st.rerun()
    else:
        st.success("Desk can open new trades")
        if st.button("EMERGENCY STOP", type="primary", width="stretch"):
            KILL_SWITCH.touch()
            st.rerun()
    st.caption("Stop blocks new trades. Open trades are still closed at their stop, target or 15:15.")

    st.divider()
    st.caption("Watchlist: " + ", ".join(s.watchlist))
    if st.button("Refresh"):
        st.rerun()


# ---------------- approvals (refreshes itself every 3 seconds) ----------------
@st.fragment(run_every="3s")
def approvals_panel() -> None:
    pending = db.pending_approvals()
    if not pending:
        if s.approval == "dashboard":
            st.caption("No trades waiting for approval.")
        return
    st.subheader(f"⏳ Waiting for your approval ({len(pending)})")
    for a in pending:
        with st.container(border=True):
            st.text(a["details"])
            st.caption(f"Asked at {a['created_at'][11:16]} IST. "
                       f"Expires after {s.executor.approval_timeout_minutes} minutes with no answer.")
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("Approve", key=f"ok{a['id']}", type="primary"):
                db.decide_approval(a["id"], "APPROVED")
                st.rerun()
            if c2.button("Reject", key=f"no{a['id']}"):
                db.decide_approval(a["id"], "REJECTED")
                st.rerun()


st.title("India Trading Desk")
if path.name == "demo.db":
    st.info("You are looking at SAMPLE data from scripts/demo_data.py. None of these trades or news items are real.")
approvals_panel()

# ---------------- headline numbers ----------------
acct = db.account()
start_cap = float(acct["starting_capital"]) if acct else float(s.sizer.starting_capital)
cash = float(acct["cash"]) if acct else start_cap
open_pos = db.open_positions(mode)
open_value = sum(p.entry * p.qty for p in open_pos)
pnl_day = db.realised_pnl(mode, day)
pnl_all = db.realised_pnl(mode)
counts = db.verdict_counts(day)
ruled = sum(counts.values())

m = st.columns(5)
m[0].metric("Paper cash" if mode == "paper" else "Cash (see Kite)", inr(cash) if mode == "paper" else "n/a")
m[1].metric("Open trades", f"{len(open_pos)} of {s.sizer.max_open_trades}",
            help=f"{inr(open_value)} at entry prices")
m[2].metric(f"Realised P&L {day}", inr(pnl_day))
m[3].metric("Realised P&L since start", inr(pnl_all), f"{pnl_all / start_cap * 100:+.2f}%")
m[4].metric("Skeptic said BUY", f"{counts['BUY']} of {ruled}" if ruled else "no rulings",
            help=f"WAIT {counts['WAIT']}, SKIP {counts['SKIP']}")

if ruled >= 3 and counts["BUY"] / ruled > 0.5:
    st.warning("Skeptic approved more than half of today's setups. It should refuse far more than it approves: "
               "tighten SKEPTIC_SYSTEM in desk/prompts.py.")

chat, trades, flags_tab, history = st.tabs(["💬 Desk chat", "📂 Trades", "🔭 Flags", "📊 History"])

# ---------------- desk chat ----------------
with chat:
    rows = db.journal_for(day)
    if not rows:
        st.info("Nothing posted on this day. The desk looks for new trades 9:30–14:45 IST on market days.")
    else:
        general = [r for r in rows if not r["symbol"]]
        order: list[str] = []
        for r in rows:
            if r["symbol"] and r["symbol"] not in order:
                order.append(r["symbol"])

        for sym in order:
            thread = [r for r in rows if r["symbol"] == sym]
            outcome = next((r["tag"] for r in reversed(thread) if r["tag"]), None)
            if any(r["message"] == "No setup" for r in thread) and not outcome:
                outcome = "No setup"
            label = f"{sym} · {outcome or 'in progress'} · {thread[0]['at'][11:16]}"
            with st.expander(label, expanded=(outcome in ("FILL", "CLOSE"))):
                for r in thread:
                    with st.chat_message(r["role"].lower(), avatar=ROLE_ICON.get(r["role"], "🤖")):
                        st.markdown(f"**{r['role']}** · {r['at'][11:16]}")
                        st.text(r["message"])
        if general:
            with st.expander("Other desk messages"):
                for r in general:
                    st.text(f"{r['at'][11:16]} {r['role']}: {r['message']}")

# ---------------- trades ----------------
with trades:
    st.subheader("Open now")
    if open_pos:
        st.dataframe(pd.DataFrame([{
            "Stock": p.symbol, "Qty": p.qty, "Entry": p.entry, "Stop": p.stop, "Target": p.target,
            "Value at entry": round(p.entry * p.qty), "Opened": p.opened_at[11:16],
        } for p in open_pos]), hide_index=True, width="stretch")
    else:
        st.caption("No open trades.")

    st.subheader(f"Trades on {day}")
    day_rows = db.positions_on(mode, day)
    if day_rows:
        st.dataframe(pd.DataFrame([{
            "Stock": r["symbol"], "Qty": r["qty"], "Entry": r["entry"], "Exit": r["exit_price"],
            "Why closed": r["exit_reason"], "Charges": r["charges"], "P&L": r["pnl"], "Status": r["status"],
        } for r in day_rows]), hide_index=True, width="stretch")
    else:
        st.caption("No trades on this day.")

# ---------------- flags ----------------
with flags_tab:
    flags = pd.read_sql_query(
        "SELECT substr(at, 12, 5) AS time, symbol AS stock, last_price AS price, move_pct AS 'move %', "
        "rel_volume AS 'volume x normal' FROM flags WHERE day = ? ORDER BY id", db.conn, params=(day,))
    st.caption(f"Scout flags at most {s.scout.max_flags_per_day} a day: up ≥{s.scout.move_pct}% in "
               f"{s.scout.move_window_minutes} min, or ≥{s.scout.volume_multiple}x normal volume while rising.")
    if flags.empty:
        st.caption("No flags on this day.")
    else:
        st.dataframe(flags, hide_index=True, width="stretch")

# ---------------- history ----------------
with history:
    closed = db.closed_positions(mode)
    if not closed:
        st.info("No closed trades yet. The month-long paper test fills this in.")
    else:
        df = pd.DataFrame([dict(r) for r in closed])
        wins, losses = df[df["pnl"] > 0], df[df["pnl"] <= 0]
        c = st.columns(4)
        c[0].metric("Closed trades", len(df))
        c[1].metric("Win rate", f"{len(wins) / len(df) * 100:.0f}%")
        c[2].metric("Average win", inr(wins["pnl"].mean()) if len(wins) else "–")
        c[3].metric("Average loss", inr(losses["pnl"].mean()) if len(losses) else "–")

        curve = df[["closed_at", "pnl"]].copy()
        curve["closed_at"] = pd.to_datetime(curve["closed_at"])
        curve["Cumulative P&L (₹)"] = curve["pnl"].cumsum()
        st.line_chart(curve.set_index("closed_at")["Cumulative P&L (₹)"])

        st.dataframe(df[["symbol", "qty", "entry", "exit_price", "exit_reason", "charges", "pnl", "opened_at",
                         "closed_at"]].rename(columns={"exit_price": "exit", "exit_reason": "why closed"}),
                     hide_index=True, width="stretch")

    st.divider()
    st.subheader("The real test: did it beat the NIFTY 50?")
    if st.button("Compare with NIFTY 50 since the desk started"):
        with st.spinner("Fetching NIFTY 50 from Yahoo Finance..."):
            try:
                from scripts.report import benchmark
                st.write(benchmark(db, s))
            except Exception as e:
                st.error(f"Could not fetch NIFTY data: {e}")
