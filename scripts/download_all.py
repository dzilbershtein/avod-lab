#!/usr/bin/env python3
"""
Download all content videos and ad videos to their local static/ paths.

Usage:
  python scripts/download_all.py            # download everything missing
  python scripts/download_all.py --force    # re-download even if file exists
  python scripts/download_all.py --content-only
  python scripts/download_all.py --ads-only
  python scripts/download_all.py --ids big_buck_bunny sintel

Content is trimmed to CONTENT_TRIM_SEC (900 s = 15 min).
Ads are trimmed to AD_TRIM_SEC (30 s safety cap).

Requirements: yt-dlp, ffmpeg (both must be on PATH)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP_PATH = os.path.join(REPO, "config", "experiment.json")
LIB_PATH = os.path.join(REPO, "config", "ad_library.json")

CONTENT_TRIM_SEC = 900  # 15 minutes
AD_TRIM_SEC = 15


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def ytdlp_download(url, out_path, trim_sec):
    """Download via yt-dlp, trim to trim_sec using ffmpeg post-processor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_out = os.path.join(tmpdir, "video.%(ext)s")
        run(
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", tmp_out,
            url,
        )
        downloaded = next(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("video.")),
            None,
        )
        if not downloaded:
            raise FileNotFoundError(f"yt-dlp produced no output for {url}")
        ffmpeg_trim(downloaded, out_path, trim_sec)


def http_download(url, out_path, trim_sec):
    """Stream-copy the first trim_sec seconds directly from an HTTP URL via ffmpeg."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    run(
        "ffmpeg", "-y",
        "-t", str(trim_sec),
        "-i", url,
        "-c", "copy",
        out_path,
    )


def ffmpeg_trim(src, dst, trim_sec):
    """Re-encode src to dst, keeping only the first trim_sec seconds."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    run(
        "ffmpeg", "-y",
        "-i", src,
        "-t", str(trim_sec),
        "-c", "copy",
        dst,
    )


def download_item(item_id, source_url, local_path, trim_sec, force=False):
    abs_path = os.path.join(REPO, local_path.lstrip("/"))
    if os.path.exists(abs_path) and not force:
        print(f"  [skip]  {item_id} — already exists")
        return

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    print(f"  [fetch] {item_id}")
    print(f"          src: {source_url}")
    print(f"          dst: {abs_path}")

    is_youtube = "youtube.com" in source_url or "youtu.be" in source_url
    try:
        if is_youtube:
            ytdlp_download(source_url, abs_path, trim_sec)
        else:
            http_download(source_url, abs_path, trim_sec)
        print(f"          OK")
    except Exception as exc:
        print(f"          ERROR: {exc}", file=sys.stderr)


def load_content_items(filter_ids=None):
    with open(EXP_PATH) as f:
        exp = json.load(f)
    inactive_note = exp["_notes"].get("inactive_titles", "")
    inactive = {s.strip() for s in inactive_note.split(",")} if inactive_note else set()

    items = []
    for tid, title in exp["catalog"]["titles"].items():
        if tid.startswith("_"):
            continue
        if tid in inactive:
            continue
        local_path = title.get("video_url", "")
        source_url = title.get("source_url", "")
        if not local_path.startswith("/static/") or not source_url:
            continue
        if filter_ids and tid not in filter_ids:
            continue
        items.append((tid, source_url, local_path))
    return items


def load_ad_items(filter_ids=None):
    with open(LIB_PATH) as f:
        lib = json.load(f)

    items = []
    for ad in lib["ads"]:
        aid = ad.get("id", "")
        if ad.get("source") in ("synthetic", "synthetic_psa"):
            continue
        local_path = ad.get("video_url", "")
        source_url = ad.get("source_url", "")
        if not local_path.startswith("/static/") or not source_url:
            continue
        if filter_ids and aid not in filter_ids:
            continue
        items.append((aid, source_url, local_path))
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content-only", action="store_true")
    parser.add_argument("--ads-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    parser.add_argument("--ids", nargs="+", metavar="ID", help="Only download these IDs")
    args = parser.parse_args()

    filter_ids = set(args.ids) if args.ids else None
    do_content = not args.ads_only
    do_ads = not args.content_only

    if do_content:
        items = load_content_items(filter_ids)
        print(f"\n=== Content videos ({len(items)}) — trimmed to {CONTENT_TRIM_SEC}s ===")
        for item_id, source_url, local_path in items:
            download_item(item_id, source_url, local_path, CONTENT_TRIM_SEC, force=args.force)

    if do_ads:
        items = load_ad_items(filter_ids)
        print(f"\n=== Ad videos ({len(items)}) — trimmed to {AD_TRIM_SEC}s ===")
        for item_id, source_url, local_path in items:
            download_item(item_id, source_url, local_path, AD_TRIM_SEC, force=args.force)

    print("\nDone.")


if __name__ == "__main__":
    main()
