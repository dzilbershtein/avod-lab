#!/usr/bin/env python3
"""
download_posters.py — Build every catalogue thumbnail in static/posters/:
download artwork where it is correct, otherwise take a frame of the clip.

Run once before deployment so the server never needs to reach out to
external hosts at runtime.

Usage:
    python scripts/download_posters.py            # download all missing
    python scripts/download_posters.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "posters")
CLIP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "content_short")

# Archive.org thumbnail service follows redirects to the item's cover image.
IA = "https://archive.org/services/img/{}"

# Titles whose downloadable artwork was wrong (Tears of Steel's archive item
# returns Big Buck Bunny art), unreachable, or only a credits card. Their
# posters are a frame of the served 8-minute clip instead, taken at the second
# given; this needs the clips in static/content_short/ and ffmpeg on PATH.
FRAME_POSTERS: dict[str, int] = {
    "tears_of_steel": 290,
    "sintel": 290,
    "elephant_dream": 45,
    "hemo_magnificent": 430,
    "unchained_goddess": 160,
    "detour_1945": 290,
    "doa_1950": 160,
    "jigsaw_1949": 290,
    "jack_beanstalk": 430,
    "blood_on_sun": 290,
    "pied_piper": 360,
    "sprite_fright": 220,
    "captain_kidd": 160,
}

POSTERS: dict[str, str] = {
    # ── Blender open movies ───────────────────────────────────────────────────
    "big_buck_bunny":     "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Big_buck_bunny_poster_big.jpg/800px-Big_buck_bunny_poster_big.jpg",
    # ── Public-domain film library ────────────────────────────────────────────
    "pioneer_one":        IA.format("PioneerOneS01E01720pHD"),
    "jackie_robinson":    IA.format("Jackie_Robinson_Story_The"),
    "his_girl_friday":    IA.format("his-girl-friday-1940_202109"),
    "inspector_general":  IA.format("TheInspectorGeneral720p1949"),
    "suddenly_1954":      IA.format("Suddenly_1954"),
}


def download(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; avod-lab-poster-downloader/1.0)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 1000:
            print(f"    ✗ response too small ({len(data)} bytes) — likely a placeholder")
            return False
        # Saved as .jpg whatever the format — browsers sniff the content.
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except urllib.error.HTTPError as e:
        print(f"    ✗ HTTP {e.code}")
        return False
    except Exception as e:
        print(f"    ✗ {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    ok = failed = skipped = 0

    for tid, sec in FRAME_POSTERS.items():
        dest = os.path.join(OUT_DIR, f"{tid}.jpg")
        if os.path.exists(dest) and not args.force:
            print(f"  skip  {tid}")
            skipped += 1
            continue
        clip = os.path.join(CLIP_DIR, f"{tid}.mp4")
        print(f"  frame {tid} @ {sec}s")
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(sec), "-i", clip,
             "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "3", dest])
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1

    for tid, url in POSTERS.items():
        dest = os.path.join(OUT_DIR, f"{tid}.jpg")
        if os.path.exists(dest) and not args.force:
            print(f"  skip  {tid}")
            skipped += 1
            continue
        print(f"  fetch {tid}")
        print(f"        {url[:80]}")
        if download(url, dest):
            size = os.path.getsize(dest)
            print(f"    ✓ {size // 1024} KB → {dest}")
            ok += 1
        else:
            failed += 1
        time.sleep(0.4)   # be polite to archive.org

    print(f"\nDone: {ok} written, {skipped} skipped, {failed} failed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
