#!/usr/bin/env python3
"""
trim_content.py — Create short versions of downloaded content videos.

Reads experiment.json for active titles, then for every file found at
static/content/<id>.mp4 it produces a trimmed copy in static/content_short/<id>.mp4
capped at TRIM_SEC (default 660 s = 11 min).  Originals in static/content/ are
never modified.

Usage:
  python scripts/trim_content.py                  # trim all active titles
  python scripts/trim_content.py --ids sintel     # trim specific titles
  python scripts/trim_content.py --force          # re-trim even if output exists
  python scripts/trim_content.py --trim-sec 600   # custom cap (seconds)

Requirements: ffmpeg on PATH
"""

import argparse
import json
import os
import subprocess
import sys

REPO     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP_PATH = os.path.join(REPO, "config", "experiment.json")
SRC_DIR  = os.path.join(REPO, "static", "content")
DST_DIR  = os.path.join(REPO, "static", "content_short")
DEFAULT_TRIM_SEC = 660  # 11 minutes


def get_duration(path):
    """Return duration in seconds via ffprobe, or None on failure."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def trim(src, dst, trim_sec):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-t", str(trim_sec), "-c", "copy", dst],
        check=True,
    )


def load_active_titles(filter_ids=None):
    with open(EXP_PATH) as f:
        exp = json.load(f)
    inactive_note = exp["_notes"].get("inactive_titles", "")
    inactive = {s.strip() for s in inactive_note.split(",")} if inactive_note else set()

    titles = []
    for tid, entry in exp["catalog"]["titles"].items():
        if tid.startswith("_") or tid in inactive:
            continue
        if not isinstance(entry, dict):
            continue
        video_url = entry.get("video_url", "")
        if "/static/content/" not in video_url:
            continue
        if filter_ids and tid not in filter_ids:
            continue
        titles.append(tid)
    return titles


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", nargs="+", metavar="ID", help="Only trim these title IDs")
    ap.add_argument("--force", action="store_true", help="Re-trim even if output already exists")
    ap.add_argument("--trim-sec", type=int, default=DEFAULT_TRIM_SEC,
                    help=f"Cap in seconds (default {DEFAULT_TRIM_SEC})")
    args = ap.parse_args()

    filter_ids = set(args.ids) if args.ids else None
    titles = load_active_titles(filter_ids)

    print(f"\nTrimming to {args.trim_sec} s → {DST_DIR}\n")
    os.makedirs(DST_DIR, exist_ok=True)

    ok = skipped = missing = 0
    for tid in titles:
        src = os.path.join(SRC_DIR, f"{tid}.mp4")
        dst = os.path.join(DST_DIR, f"{tid}.mp4")

        if not os.path.exists(src):
            print(f"  [miss]  {tid} — {src} not found, skipping")
            missing += 1
            continue

        if os.path.exists(dst) and not args.force:
            print(f"  [skip]  {tid} — output already exists")
            skipped += 1
            continue

        dur = get_duration(src)
        dur_str = f"{dur:.0f}s" if dur else "unknown"

        if dur is not None and dur <= args.trim_sec:
            print(f"  [copy]  {tid} ({dur_str} ≤ {args.trim_sec}s, copying as-is)")
        else:
            print(f"  [trim]  {tid} ({dur_str} → {args.trim_sec}s)")

        try:
            trim(src, dst, args.trim_sec)
            size_mb = os.path.getsize(dst) / 1_048_576
            print(f"          OK ({size_mb:.1f} MB) → {dst}")
            ok += 1
        except subprocess.CalledProcessError as exc:
            print(f"          ERROR: {exc}", file=sys.stderr)

    print(f"\nDone: {ok} trimmed, {skipped} skipped, {missing} missing source.")
    if ok:
        print(f'\nTo switch the experiment to short clips, set in experiment.json:')
        print(f'  "content_version": "short"')
    sys.exit(0)


if __name__ == "__main__":
    main()
