#!/usr/bin/env python3
"""
generate_ads.py — render synthetic 30-second ad MP4s.

Uses Pillow to render each frame (works regardless of ffmpeg build flags)
then encodes via ffmpeg.  Requires: Pillow, ffmpeg on PATH.

    pip install Pillow
    python scripts/generate_ads.py

Four ads are produced (static/ads/):

  Relevant to entertainment content:
    ad_relevant_screentime  — SCREENTIME streaming service
    ad_relevant_arcademax   — ARCADEMAX gaming platform

  Irrelevant to entertainment content:
    ad_irrelevant_crunchpop — CRUNCHPOP breakfast cereal
    ad_irrelevant_homesafe  — HOMESAFE home insurance

Visual structure per ad (1280×720, 30 s, 15 fps):
  0.0–1.5 s  brand name fades in
  1.5–3.0 s  tagline fades in
  22–25 s    CTA bar fades in at the bottom
  throughout subtle diagonal highlight sweep
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not found.  Run:  pip install Pillow")
    raise SystemExit(1)

BASE = Path(__file__).resolve().parent.parent
OUT  = BASE / "static" / "ads"

DURATION     = 30
FPS          = 15      # enough for smooth text fade; keeps frame count manageable
W, H         = 1280, 720

# ------------------------------------------------------------------ font setup
FONT_PATHS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

FONT_XL  = _load_font(96)
FONT_LG  = _load_font(42)
FONT_MD  = _load_font(28)

# ------------------------------------------------------------------ helpers
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#").lstrip("0x")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def blend_alpha(base: tuple, fg: tuple, alpha: float) -> tuple:
    r = int(base[0] * (1 - alpha) + fg[0] * alpha)
    g = int(base[1] * (1 - alpha) + fg[1] * alpha)
    b = int(base[2] * (1 - alpha) + fg[2] * alpha)
    return r, g, b

def draw_centered(draw: ImageDraw.Draw, text: str, font, y: int,
                  color: tuple[int, int, int], alpha: float, bg_rgb: tuple) -> None:
    if alpha <= 0:
        return
    c = blend_alpha(bg_rgb, color, alpha)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=c)

# ------------------------------------------------------------------ ads
ADS = [
    {
        "id":      "ad_relevant_screentime",
        "brand":   "SCREENTIME",
        "tagline": "Every story worth watching.",
        "cta":     "screentime.tv  —  free for 30 days",
        "bg":      "0D1B35",
        "accent":  "4FC3F7",
        "fg":      "FFFFFF",
        "cta_fg":  "0D1B35",
    },
    {
        "id":      "ad_relevant_arcademax",
        "brand":   "ARCADEMAX",
        "tagline": "Your next adventure starts here.",
        "cta":     "arcademax.io  —  play free",
        "bg":      "150A2E",
        "accent":  "E040FB",
        "fg":      "FFFFFF",
        "cta_fg":  "FFFFFF",
    },
    {
        "id":      "ad_irrelevant_crunchpop",
        "brand":   "CRUNCHPOP",
        "tagline": "The crunch that starts your day.",
        "cta":     "New flavours in stores now",
        "bg":      "7B1E00",
        "accent":  "FFD740",
        "fg":      "FFFFFF",
        "cta_fg":  "7B1E00",
    },
    {
        "id":      "ad_irrelevant_homesafe",
        "brand":   "HOMESAFE",
        "tagline": "Protect what matters most.",
        "cta":     "homesafe.com/quote  —  2 minutes",
        "bg":      "0F2318",
        "accent":  "A8D5A2",
        "fg":      "FFFFFF",
        "cta_fg":  "0F2318",
    },
]

# ------------------------------------------------------------------ renderer
def render_frame(t: float, ad: dict) -> Image.Image:
    bg_rgb     = hex_to_rgb(ad["bg"])
    accent_rgb = hex_to_rgb(ad["accent"])
    fg_rgb     = hex_to_rgb(ad["fg"])
    cta_fg_rgb = hex_to_rgb(ad["cta_fg"])

    img  = Image.new("RGB", (W, H), bg_rgb)
    draw = ImageDraw.Draw(img)

    # Diagonal highlight sweep (slowly crosses left→right over 30 s)
    sx = int((t / DURATION) * W * 1.5 - W * 0.15)
    for dx in range(220):
        a = max(0.0, 0.04 * (1 - abs(dx - 110) / 110))
        if 0 <= sx + dx < W:
            col = blend_alpha(bg_rgb, (255, 255, 255), a)
            draw.line([(sx + dx, 0), (sx + dx, H)], fill=col)

    # Top accent rule
    draw.rectangle([0, 0, W, 5], fill=accent_rgb)

    # Brand name — fades in 0→1.5 s
    alpha_brand = min(1.0, t / 1.5)
    draw_centered(draw, ad["brand"], FONT_XL, y=H // 2 - 85,
                  color=fg_rgb, alpha=alpha_brand, bg_rgb=bg_rgb)

    # Tagline — fades in 1.5→3 s
    alpha_tag = max(0.0, min(1.0, (t - 1.5) / 1.5))
    draw_centered(draw, ad["tagline"], FONT_LG, y=H // 2 + 32,
                  color=fg_rgb, alpha=alpha_tag * 0.88, bg_rgb=bg_rgb)

    # CTA bar — fades in 22→25 s
    alpha_cta = max(0.0, min(1.0, (t - 22.0) / 3.0))
    if alpha_cta > 0:
        for y in range(H - 72, H):
            row_color = blend_alpha(bg_rgb, accent_rgb, alpha_cta)
            draw.line([(0, y), (W, y)], fill=row_color)
        cta_y = H - 72 + (72 - 28) // 2
        draw_centered(draw, ad["cta"], FONT_MD, y=cta_y,
                      color=cta_fg_rgb, alpha=alpha_cta, bg_rgb=accent_rgb)

    return img


def render_ad(ad: dict, out_path: Path) -> None:
    frames_dir = Path(tempfile.mkdtemp())
    total      = DURATION * FPS

    print(f"  {ad['id']}:  rendering {total} frames … ", end="", flush=True)
    for n in range(total):
        t = n / FPS
        frame = render_frame(t, ad)
        frame.save(frames_dir / f"f{n:04d}.png")
    print("encoding … ", end="", flush=True)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "f%04d.png"),
        "-f", "lavfi", "-i", "anullsrc=cl=stereo:r=48000",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest", "-t", str(DURATION),
        "-movflags", "+faststart",
        str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(frames_dir)

    if res.returncode != 0:
        print("FAIL")
        print(res.stderr, file=sys.stderr)
        raise SystemExit(1)
    print("ok")


def main() -> None:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH.")
        raise SystemExit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(ADS)} ads → {OUT}\n")
    for ad in ADS:
        render_ad(ad, OUT / f"{ad['id']}.mp4")
    print(f"\nDone.")


if __name__ == "__main__":
    main()
