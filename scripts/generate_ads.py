#!/usr/bin/env python3
"""
generate_ads.py — render the synthetic ads listed in config/ad_library.json
as 15-second MP4 clips using ffmpeg.

Each generated clip is a coloured gradient + brand text + category tag, with
silent stereo audio so the player path is identical to a real ad.  Categories
get distinct colour palettes so a participant who sees several ads of the same
category recognises the visual family.

Run:
    python scripts/generate_ads.py
    (requires ffmpeg on PATH)

Outputs land in static/ads/.

Why we generate rather than scraping more real ads:
- Real ad clips that are legally redistributable are scarce.  The Pitts ads
  dataset (Hussain et al., CVPR 2017) and the AdsQA benchmark (2025) both
  reference real ads via YouTube ID, not as downloadable MP4s.
- Synthetic ads give us tight experimental control: identical length, identical
  audio dynamic range, identical visual complexity across categories.
- We pair the synthetic set with a couple of verified public-domain real clips
  (Coca-Cola 1954, Chromecast promos) so the experiment has at least one real
  ad per major category.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LIB = BASE / "config" / "ad_library.json"
OUT = BASE / "static" / "ads"

# Distinct palette per category — keeps category visually identifiable.
PALETTE = {
    "food_beverage":   {"bg": "0xCC2B2B", "fg": "white",  "accent": "0xFFD24D"},
    "automotive":      {"bg": "0x1B3A5B", "fg": "white",  "accent": "0xE8C547"},
    "electronics_tech":{"bg": "0x222831", "fg": "white",  "accent": "0x4FC3F7"},
    "public_service":  {"bg": "0x2C7A4B", "fg": "white",  "accent": "0xFFE066"},
}

# Per-ad copy: brand line and tagline.  Edit freely; re-run the script.
COPY = {
    "fb_synth_freshpress":  ("FRESHPRESS", "Cold-pressed in 60 seconds."),
    "fb_synth_pizzania":    ("PIZZANIA",   "Pizza, made simple."),
    "auto_synth_velora":    ("VELORA EV",  "Quiet roads, brighter mornings."),
    "auto_synth_routely":   ("ROUTELY",    "Roadside help, on demand."),
    "tech_synth_pixela":    ("PIXELA",     "Earbuds that disappear."),
    "psa_synth_screenbreak":("SCREEN BREAK","Every 30 minutes, look at something 6 metres away."),
    "psa_synth_recycle":    ("RECYCLE RIGHT","Two seconds at the bin saves a tonne at the plant."),
    "psa_synth_hydrate":    ("STAY HYDRATED","Half a litre, before the day starts."),
}


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def category_for(ad_id: str) -> str:
    if ad_id.startswith("fb_"):   return "food_beverage"
    if ad_id.startswith("auto_"): return "automotive"
    if ad_id.startswith("tech_"): return "electronics_tech"
    if ad_id.startswith("psa_"):  return "public_service"
    return "food_beverage"


def render_one(ad_id: str, brand: str, tagline: str, out_path: Path) -> None:
    cat = category_for(ad_id)
    pal = PALETTE[cat]
    duration = 15

    # Build the filtergraph.  Two-layer drawtext: brand line (large), tagline
    # (small).  A faint accent bar across the bottom marks the category.
    drawtext_brand = (
        f"drawtext=text='{brand}'"
        f":fontcolor={pal['fg']}:fontsize=88:x=(w-text_w)/2:y=(h/2)-90"
        f":box=1:boxcolor=black@0.0:boxborderw=10"
    )
    drawtext_tag = (
        f"drawtext=text='{tagline.replace(chr(39), '')}'"
        f":fontcolor={pal['fg']}:fontsize=36:x=(w-text_w)/2:y=(h/2)+20"
    )
    drawtext_cat = (
        f"drawtext=text='{cat.replace('_', ' ').upper()}'"
        f":fontcolor={pal['accent']}:fontsize=22:x=(w-text_w)/2:y=h-70"
    )
    accent_bar = f"drawbox=x=0:y=h-30:w=iw:h=8:color={pal['accent']}:t=fill"

    vf = ",".join([drawtext_brand, drawtext_tag, drawtext_cat, accent_bar])

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={pal['bg']}:s=1280x720:d={duration}",
        "-f", "lavfi", "-i", f"anullsrc=cl=stereo:r=48000",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        "-t", str(duration),
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"  rendering {out_path.name} ... ", end="", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("FAIL")
        print(res.stderr, file=sys.stderr)
        raise SystemExit(1)
    print("ok")


def main() -> None:
    if not have_ffmpeg():
        print("ffmpeg not found on PATH.")
        print("Install on macOS:  brew install ffmpeg")
        print("Install on Ubuntu: sudo apt install ffmpeg")
        raise SystemExit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    library = json.loads(LIB.read_text())
    synthetic = [a for a in library["ads"] if a.get("source") == "synthetic"]

    print(f"Generating {len(synthetic)} synthetic ads -> {OUT}")
    for ad in synthetic:
        ad_id = ad["id"]
        if ad_id not in COPY:
            print(f"  skipping {ad_id} (no COPY entry)")
            continue
        brand, tagline = COPY[ad_id]
        out_path = OUT / f"{ad_id}.mp4"
        render_one(ad_id, brand, tagline, out_path)

    print(f"\nDone.  {len(synthetic)} files written to {OUT}.")


if __name__ == "__main__":
    main()
