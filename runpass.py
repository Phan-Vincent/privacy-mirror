"""Headless single-pass runner for PrivacyMirror.

Runs exactly one scheduler pass (recurring re-generation + sending + follow-ups,
honoring your saved settings) and then exits — no web server, no background loop.

This is what the Windows Scheduled Task invokes, so removals keep happening even
when the dashboard isn't open. Run it manually any time too:

    python runpass.py

Output is appended to runpass.log (handy because the scheduled task runs windowless),
and every action is also recorded in the app's activity timeline.
"""

import os
import sys
from datetime import datetime, timezone

import db
import mailer

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runpass.log")


def _log(line):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = f"{stamp}  {line}"
    print(msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def main():
    db.init_db(seed_brokers=True)
    try:
        result = mailer.run_pass()
        _log(f"pass: {result}")
        return 0
    except Exception as e:  # noqa: BLE001 — never crash the scheduled task silently
        _log(f"ERROR: {e}")
        try:
            db.log_event(None, "error", f"runpass error: {e}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
