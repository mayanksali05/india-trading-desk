"""SQLite store: paper cash, positions, Scout flags and the desk journal (every role's post)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from desk.market.clock import now_ist
from desk.models import Flag, Position

log = logging.getLogger("desk")

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL,
    starting_capital REAL NOT NULL,
    started_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty INTEGER NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    opened_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_price REAL,
    closed_at TEXT,
    exit_reason TEXT,
    charges REAL NOT NULL DEFAULT 0,
    pnl REAL,
    broker_order_id TEXT
);
CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    symbol TEXT NOT NULL,
    last_price REAL,
    move_pct REAL,
    rel_volume REAL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    day TEXT NOT NULL,
    symbol TEXT,
    role TEXT NOT NULL,
    tag TEXT,
    message TEXT NOT NULL
);
"""


def today() -> str:
    return now_ist().date().isoformat()


class DB:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- account ----
    def init_account(self, capital: float) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO account (id, cash, starting_capital, started_on) VALUES (1, ?, ?, ?)",
            (capital, capital, today()),
        )
        self.conn.commit()

    def account(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM account WHERE id = 1").fetchone()

    def cash(self) -> float:
        return float(self.account()["cash"])

    def set_cash(self, cash: float) -> None:
        self.conn.execute("UPDATE account SET cash = ? WHERE id = 1", (cash,))
        self.conn.commit()

    # ---- journal ----
    def post(self, role: str, message: str, symbol: str | None = None, tag: str | None = None) -> None:
        now = now_ist()
        self.conn.execute(
            "INSERT INTO journal (at, day, symbol, role, tag, message) VALUES (?, ?, ?, ?, ?, ?)",
            (now.isoformat(timespec="seconds"), now.date().isoformat(), symbol, role, tag, message),
        )
        self.conn.commit()
        log.info("%-8s %-10s %s", role, symbol or "", message)

    def verdict_counts(self, day: str | None = None) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT tag, COUNT(*) n FROM journal WHERE day = ? AND role = 'SKEPTIC' GROUP BY tag",
            (day or today(),),
        ).fetchall()
        counts = {"BUY": 0, "WAIT": 0, "SKIP": 0}
        counts.update({r["tag"]: r["n"] for r in rows if r["tag"]})
        return counts

    def journal_for(self, day: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM journal WHERE day = ? ORDER BY id", (day,)).fetchall()

    # ---- flags ----
    def record_flag(self, f: Flag) -> None:
        self.conn.execute(
            "INSERT INTO flags (day, symbol, last_price, move_pct, rel_volume, at) VALUES (?, ?, ?, ?, ?, ?)",
            (f.at.date().isoformat(), f.symbol, f.last_price, f.move_pct, f.rel_volume, f.at.isoformat()),
        )
        self.conn.commit()

    def flags_today(self, day: str | None = None) -> set[str]:
        rows = self.conn.execute("SELECT symbol FROM flags WHERE day = ?", (day or today(),)).fetchall()
        return {r["symbol"] for r in rows}

    def flag_count(self, day: str | None = None) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM flags WHERE day = ?", (day or today(),)).fetchone()[0]

    # ---- positions ----
    def insert_position(self, mode, symbol, qty, entry, stop, target, charges, broker_order_id=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO positions (mode, symbol, qty, entry, stop, target, opened_at, charges, broker_order_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mode, symbol, qty, entry, stop, target, now_ist().isoformat(timespec="seconds"), charges, broker_order_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def open_positions(self, mode: str) -> list[Position]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE mode = ? AND status = 'OPEN' ORDER BY id", (mode,)
        ).fetchall()
        return [
            Position(r["id"], r["mode"], r["symbol"], r["qty"], r["entry"], r["stop"], r["target"],
                     r["opened_at"], r["charges"], r["broker_order_id"])
            for r in rows
        ]

    def close_position(self, pid: int, exit_price: float, reason: str, total_charges: float, pnl: float) -> None:
        self.conn.execute(
            "UPDATE positions SET status = 'CLOSED', exit_price = ?, closed_at = ?, exit_reason = ?,"
            " charges = ?, pnl = ? WHERE id = ?",
            (exit_price, now_ist().isoformat(timespec="seconds"), reason, total_charges, pnl, pid),
        )
        self.conn.commit()

    def realised_pnl(self, mode: str, day: str | None = None) -> float:
        q = "SELECT COALESCE(SUM(pnl), 0) FROM positions WHERE mode = ? AND status = 'CLOSED'"
        args: list = [mode]
        if day:
            q += " AND substr(closed_at, 1, 10) = ?"
            args.append(day)
        return float(self.conn.execute(q, args).fetchone()[0])

    def positions_on(self, mode: str, day: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM positions WHERE mode = ? AND (substr(opened_at, 1, 10) = ? OR substr(closed_at, 1, 10) = ?)"
            " ORDER BY id",
            (mode, day, day),
        ).fetchall()
