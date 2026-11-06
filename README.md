# India Trading Desk

A six-role paper trading desk for NSE stocks, based on the "AI trading desk in one group chat" idea,
rebuilt as a Python program. Four roles are plain code so the safety rules can't be argued with.
Two roles use an AI model, where judgment on text actually helps. Nothing is placed without your approval.

```
SCOUT  ->  NEWS  ->  CHART  ->  SKEPTIC  ->  SIZER  ->  EXECUTOR  ->  you approve
(code)     (AI)      (code)     (AI)         (code)     (code)
```

| Role | File | Job |
|---|---|---|
| Scout | `desk/roles/scout.py` | Flags stocks up ≥3% in the last hour, or ≥2x normal volume while rising. Max 5 a day, each stock once a day |
| News | `desk/roles/news.py` | Reads NSE corporate announcements and explains the move, or says "No clear reason" |
| Chart | `desk/roles/chart.py` | Entry, stop (at most 2% below), target (at least 2x the risk). "No setup" if price is below VWAP |
| Skeptic | `desk/roles/skeptic.py` | Three reasons the trade will fail, then BUY / WAIT / SKIP. No news or AI error = SKIP |
| Sizer | `desk/roles/sizer.py` | At most 5% per trade, 3 open trades, and stops for the day after a 2% realised loss |
| Executor | `desk/roles/executor.py` | Asks you, re-checks the price, places the trade, closes at stop / target / 15:15 square-off |

## Project layout

```
india-trading-desk/
├── config/
│   ├── settings.yaml        # watchlist, limits, mode, data source, approval method
│   └── nse_holidays.txt     # fill in from NSE's holiday list
├── desk/
│   ├── config.py            # loads settings.yaml + .env, refuses live mode without ALLOW_LIVE=1
│   ├── models.py            # Flag, NewsNote, Setup, Ruling, Order, Position
│   ├── desk.py              # wires the six roles into one cycle
│   ├── storage.py           # SQLite: paper cash, positions, flags, journal of every role's post
│   ├── llm.py               # Anthropic API wrapper, returns JSON or None (fails closed)
│   ├── prompts.py           # NEWS and SKEPTIC prompts
│   ├── approval.py          # observe / console / Telegram approvals
│   ├── market/
│   │   ├── clock.py         # NSE hours in IST, holidays, scan window, square-off time
│   │   └── data.py          # YFinanceSource (free, delayed) and KiteSource (paid Kite Connect)
│   ├── roles/               # scout, news, chart, skeptic, sizer, executor
│   └── broker/
│       ├── paper.py         # fake-money account with slippage and estimated charges
│       └── kite.py          # Kite login session + LIVE broker (untested, see warnings)
├── dashboard.py             # local web dashboard: desk chat, trades, P&L, approvals, emergency stop
├── scripts/
│   ├── run_desk.py          # main loop during market hours (--once for a single cycle)
│   ├── report.py            # daily log; --benchmark compares with NIFTY 50
│   ├── kite_login.py        # daily Zerodha login (only for data_source: kite or live mode)
│   ├── stop.py              # emergency stop: no new trades (--off to undo)
│   └── demo_data.py         # sample data to try the dashboard (writes data/demo.db)
├── tests/                   # 23 tests, including a full cycle with fake data and a fake AI
├── .env.example
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
copy .env.example .env            # then add your AI key (and Telegram details later)
python -m pytest -q               # should print 23 passed
```

**AI provider.** The default is Google Gemini's free tier: get a key at aistudio.google.com and put it
in `.env` as `GEMINI_API_KEY`. To use Groq (free), Ollama (free, runs on your PC) or Claude (paid),
switch the `llm:` block in `config/settings.yaml`. Free tiers are rate-limited, which is fine here:
the desk makes at most about 10 AI calls a day.

Edit `config/settings.yaml`: put 10–20 stocks you know in `watchlist` and add this year's NSE holidays
to `config/nse_holidays.txt`.

Run it on a weekday before 9:15 IST and leave it running:

```bash
python scripts/run_desk.py
```

Everything each role says is logged to the terminal, `logs/desk-YYYY-MM-DD.log` and the `journal`
table in `data/desk.db`. After the close it prints the day's log.

## Dashboard

A local web page to watch the desk. Open a second terminal (with the venv active) next to `run_desk.py`:

```bash
streamlit run dashboard.py
```

It opens at http://localhost:8501 and shows:

- **Desk chat**: each flagged stock as a thread (Scout → News → Chart → Skeptic → Sizer → Executor)
- **Trades**: open positions and the day's closed trades
- **Flags**: what Scout picked up and why
- **History**: win rate, average win/loss, cumulative P&L, and a NIFTY 50 comparison button
- **Approve / Reject** buttons when `approval: dashboard` is set in settings.yaml
- **Emergency stop** switch in the sidebar (same as `scripts/stop.py`)

To try it before the market opens, load sample data (your real `data/desk.db` is not touched):

```bash
python scripts/demo_data.py
streamlit run dashboard.py -- --db data/demo.db
```

## The one-month paper test

| When | Settings | What to check |
|---|---|---|
| Week 1 | `approval: observe` | Read every post. Is Skeptic refusing far more than it approves? If not, tighten `desk/prompts.py` |
| Weeks 2–4 | `approval: dashboard` (or `telegram` / `console`) | Approve the paper trades you agree with. Note the ones you'd skip, and why |
| End of month | `python scripts/report.py --benchmark` | Did the desk beat simply holding the NIFTY 50? If not on paper, real money won't fix it |

## Things to know

- **yfinance data is free but delayed and unofficial.** It's fine for testing the plumbing and the
  logic. For a serious paper month, switch to `data_source: kite` (Kite Connect paid plan, ₹500/month;
  the free Personal plan has no market data) and run `scripts/kite_login.py` every morning.
- **NSE announcements** come from NSE's website endpoint, which is unofficial and can change or block
  requests. When it fails, NEWS reports no reason and the trade is skipped. Watch the logs in week 1.
- **Stops are checked every cycle** (5 minutes by default), not tick by tick, so a fast drop can fill
  below the stop. Paper results will look a little better than reality for this reason.
- **Charges are estimates** (`paper:` section of settings). Replace them with Zerodha's charge sheet.
- **Paper capital is ₹1,00,000** so the 5% rule produces real position sizes. With a ₹1,000 live cap,
  5% is ₹50, which buys nothing. Rethink the sizing rules before going live with small capital.

## Going live (not before the paper month)

`desk/broker/kite.py` contains a `LiveKiteBroker` that places real MIS orders. It has **not** been run
against a real account. Before using it you need to:

1. Register a static IP in the Kite developer console (required for order placement).
2. Confirm fills with `order_history`, handle partial fills and rejected orders.
3. Add an exchange-side stop-loss order so the stop works even if your program crashes.
4. Set `mode: live` and `ALLOW_LIVE=1`, and start with one share.

This project is for learning. It is not financial advice.
