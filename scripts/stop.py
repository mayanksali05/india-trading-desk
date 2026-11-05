"""Emergency stop. Blocks new trades; open trades are still managed (stop, target, square-off).
    python scripts/stop.py        # turn the kill switch on
    python scripts/stop.py --off  # turn it off
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
flag = ROOT / "STOP"

if "--off" in sys.argv:
    flag.unlink(missing_ok=True)
    print("Kill switch OFF: the desk can open new trades.")
else:
    flag.touch()
    print("Kill switch ON: no new trades. Open trades are still managed.")
