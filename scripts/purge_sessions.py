#!/usr/bin/env python3
"""
purge_sessions.py — Clear sessions from data/events.sqlite.

Usage:
  python scripts/purge_sessions.py --test-only   # delete only sessions started with ?test=1
  python scripts/purge_sessions.py --all         # delete every session and event (irreversible)

Use --all once, right before you send the real study link to participants,
to guarantee a clean slate. Use --test-only afterwards to clear out test
runs without touching real participant data.
"""

import argparse
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "data", "events.sqlite")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--test-only", action="store_true", help="Delete only sessions tagged is_test=1")
    group.add_argument("--all", action="store_true", help="Delete ALL sessions and events")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"No database found at {DB_PATH} — nothing to purge.")
        sys.exit(0)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if args.test_only:
        n_sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE is_test = 1").fetchone()["n"]
        n_events = conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE session_id IN "
            "(SELECT id FROM sessions WHERE is_test = 1)"
        ).fetchone()["n"]
        scope = f"{n_sessions} test session(s) and {n_events} associated event(s)"
    else:
        n_sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        n_events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        scope = f"ALL {n_sessions} session(s) and {n_events} event(s) — including real participant data if any exists"

    if n_sessions == 0 and n_events == 0:
        print("Nothing to delete.")
        sys.exit(0)

    print(f"About to delete: {scope}")
    if not args.yes:
        answer = input("Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(1)

    if args.test_only:
        conn.execute("DELETE FROM events WHERE session_id IN (SELECT id FROM sessions WHERE is_test = 1)")
        conn.execute("DELETE FROM sessions WHERE is_test = 1")
    else:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM sessions")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
