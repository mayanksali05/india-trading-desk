"""Daily Zerodha login. Kite access tokens expire every day, so run this each morning before 9:15.

1. Run: python scripts/kite_login.py
2. Open the printed URL, log in with your password and 2FA.
3. Paste the request_token from the redirect URL back here.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from kiteconnect import KiteConnect  # noqa: E402

from desk.broker.kite import SESSION_FILE  # noqa: E402
from desk.config import ROOT  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key, api_secret = os.getenv("KITE_API_KEY"), os.getenv("KITE_API_SECRET")
    if not api_key or not api_secret:
        sys.exit("Set KITE_API_KEY and KITE_API_SECRET in .env first.")
    kite = KiteConnect(api_key=api_key)
    print("Open this URL and log in:\n", kite.login_url())
    request_token = input("request_token from the redirect URL: ").strip()
    session = kite.generate_session(request_token, api_secret=api_secret)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"date": date.today().isoformat(),
                                        "access_token": session["access_token"]}))
    print("Saved today's session to", SESSION_FILE)


if __name__ == "__main__":
    main()
