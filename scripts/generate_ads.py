#!/usr/bin/env python3
"""
generate_ads.py — render synthetic 30-second ad MP4s via Pillow + ffmpeg.

Four ads, structured as 3-scene TV commercials (1280×720, 30 s, 15 fps):

  Relevant to entertainment content:
    ad_relevant_screentime  — SCREENTIME streaming service
    ad_relevant_arcademax   — ARCADEMAX gaming platform

  Irrelevant to entertainment content:
    ad_irrelevant_crunchpop — CRUNCHPOP breakfast cereal
    ad_irrelevant_homesafe  — HOMESAFE home insurance

Visual language per ad:
  Scene 1  0–8 s    product icon appears with glow / animation
  Scene 2  8–22 s   brand name (slides up + fades in), tagline
  Scene 3  22–30 s  CTA bar rises, brand name stays

Run:
    pip install Pillow
    python scripts/generate_ads.py
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("Pillow not found.  Run:  pip install Pillow")
    raise SystemExit(1)

BASE = Path(__file__).resolve().parent.parent
OUT  = BASE / "static" / "ads"

W, H      = 1280, 720
DURATION  = 30
FPS       = 15

# ──────────────────────────────────────────────── fonts
_FONT_PATHS_BOLD = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),   # Bold index
    ("/System/Library/Fonts/Helvetica.ttc",     1),
    ("/Library/Fonts/Arial Bold.ttf",           0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
]
_FONT_PATHS_REG = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/System/Library/Fonts/Helvetica.ttc",     0),
    ("/Library/Fonts/Arial.ttf",                0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
]

def _load(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REG
    for path, index in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    return ImageFont.load_default()

F_BRAND   = _load(112, bold=True)
F_TAGLINE = _load(44,  bold=False)
F_CTA     = _load(30,  bold=True)
F_BADGE   = _load(20,  bold=True)

# ──────────────────────────────────────────────── helpers
def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def lerp_color(a, b, t):
    return tuple(int(a[i] * (1-t) + b[i] * t) for i in range(3))

def ease_out(t):
    return 1 - (1 - min(t, 1.0)) ** 2

def ease_in_out(t):
    t = min(t, 1.0)
    return t * t * (3 - 2 * t)

def centered_x(draw, text, font) -> int:
    bb = font.getbbox(text)
    return (W - (bb[2] - bb[0])) // 2

def draw_text_shadow(draw, text, font, x, y, fill, shadow_alpha=90):
    """Draw text with a drop shadow underneath."""
    off = 3
    shadow_col = (0, 0, 0, shadow_alpha)
    draw.text((x + off, y + off), text, font=font, fill=shadow_col)
    draw.text((x, y), text, font=font, fill=fill)

def draw_centered_text(draw, text, font, y, fill, shadow=True, alpha=1.0):
    x = centered_x(draw, text, font)
    fa = tuple(list(fill[:3]) + [int(255 * alpha)])
    if shadow and alpha > 0.05:
        sa = int(90 * alpha)
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, sa))
    draw.text((x, y), text, font=font, fill=fa)

def gradient_bg(img_array, draw, top_col, bot_col):
    """Fill img with a vertical gradient from top_col to bot_col."""
    for y in range(H):
        t = y / (H - 1)
        c = lerp_color(top_col, bot_col, t)
        draw.line([(0, y), (W, y)], fill=c)

def composite_overlay(base: Image.Image, layer: Image.Image) -> Image.Image:
    base_rgba = base.convert("RGBA")
    return Image.alpha_composite(base_rgba, layer).convert("RGB")

def make_layer() -> tuple[Image.Image, ImageDraw.Draw]:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)

# ──────────────────────────────────────────────── icon drawers
def draw_tv_icon(draw, cx, cy, size, accent, alpha):
    a = int(alpha * 255)
    if a <= 0:
        return
    c = (*accent, a)
    dim = int(alpha * 30)
    # TV body
    tw, th = size, int(size * 0.62)
    r = 12
    draw.rounded_rectangle([cx-tw//2, cy-th//2, cx+tw//2, cy+th//2],
                             radius=r, outline=c, width=4)
    # Screen inner
    m = 18
    draw.rounded_rectangle([cx-tw//2+m, cy-th//2+m, cx+tw//2-m, cy+th//2-m],
                             radius=6, fill=(*accent, int(alpha * 40)), outline=c, width=2)
    # Stand
    sy = cy + th // 2
    draw.line([(cx, sy), (cx, sy + 30)], fill=c, width=5)
    draw.line([(cx - 40, sy + 30), (cx + 40, sy + 30)], fill=c, width=5)
    # Play triangle inside screen
    ps = int(size * 0.13)
    pts = [(cx - ps//2, cy - ps), (cx + ps, cy), (cx - ps//2, cy + ps)]
    draw.polygon(pts, fill=c)
    # Glow rings (pulsing via alpha)
    for ring, pulse_phase in [(size * 0.7, 0.0), (size * 0.9, 0.3)]:
        ring_a = int(alpha * max(0, 70 * math.sin(math.pi * 2 * pulse_phase + 0.5)))
        draw.ellipse([cx - ring, cy - ring * 0.62,
                      cx + ring, cy + ring * 0.62],
                     outline=(*accent, ring_a), width=2)


def draw_controller_icon(draw, cx, cy, size, accent, alpha):
    a = int(alpha * 255)
    if a <= 0:
        return
    c = (*accent, a)
    # Body
    w, h = size, int(size * 0.52)
    r = int(size * 0.25)
    draw.rounded_rectangle([cx-w//2, cy-h//2, cx+w//2, cy+h//2],
                             radius=r, outline=c, width=4)
    # Left grip
    draw.rounded_rectangle([cx-w//2-15, cy, cx-w//4, cy+h],
                             radius=15, outline=c, width=4)
    # Right grip
    draw.rounded_rectangle([cx+w//4, cy, cx+w//2+15, cy+h],
                             radius=15, outline=c, width=4)
    # D-pad (left side) — cross
    dp = int(size * 0.07)
    dx = cx - int(size * 0.3)
    dy = cy
    draw.rectangle([dx - dp//2, dy - dp*2, dx + dp//2, dy + dp*2], fill=c)
    draw.rectangle([dx - dp*2, dy - dp//2, dx + dp*2, dy + dp//2], fill=c)
    # Face buttons (right side) — 4 circles
    bx, by, br = cx + int(size * 0.27), cy, int(size * 0.05)
    offsets = [(0, -int(size*0.12)), (int(size*0.12), 0),
               (0, int(size*0.12)), (-int(size*0.12), 0)]
    for ox, oy in offsets:
        draw.ellipse([bx+ox-br, by+oy-br, bx+ox+br, by+oy+br],
                     fill=(*accent, int(alpha*180)), outline=c, width=2)
    # Analog sticks
    for sx in [cx - int(size*0.1), cx + int(size*0.1)]:
        sr = int(size * 0.07)
        draw.ellipse([sx-sr, cy+h//2-sr, sx+sr, cy+h//2+sr],
                     outline=c, width=3)


def draw_cereal_icon(draw, cx, cy, size, accent, alpha, t_anim):
    a = int(alpha * 255)
    if a <= 0:
        return
    c = (*accent, a)
    # Sunburst rays
    num_rays = 16
    for i in range(num_rays):
        angle = math.radians(360 * i / num_rays + t_anim * 30)
        r_in  = size * 0.42
        r_out = size * 0.62 + (0.08 * size * math.sin(t_anim * 3 + i))
        x1 = cx + int(r_in  * math.cos(angle))
        y1 = cy + int(r_in  * math.sin(angle))
        x2 = cx + int(r_out * math.cos(angle))
        y2 = cy + int(r_out * math.sin(angle))
        draw.line([(x1, y1), (x2, y2)], fill=c, width=5)
    # Bowl (ellipse)
    bw, bh = int(size * 0.72), int(size * 0.44)
    draw.ellipse([cx-bw//2, cy-bh//4, cx+bw//2, cy+bh], outline=c, width=5)
    # Rim (top arc — just the top half of a slightly larger ellipse)
    draw.arc([cx-bw//2-4, cy-bh//4-4, cx+bw//2+4, cy+bh+4],
             start=200, end=340, fill=c, width=5)
    # Spoon
    spoon_x = cx + int(size * 0.47)
    draw.line([(spoon_x, cy - int(size*0.1)), (spoon_x, cy + int(size*0.38))],
              fill=c, width=6)
    draw.ellipse([spoon_x-12, cy - int(size*0.1)-18,
                  spoon_x+12, cy - int(size*0.1)+4], fill=c)
    # Some "puffs" floating above bowl
    for i, (ox, oy) in enumerate([(-40, -30), (0, -40), (40, -30)]):
        pr = int(10 + 3 * math.sin(t_anim * 2 + i))
        draw.ellipse([cx+ox-pr, cy+oy-pr, cx+ox+pr, cy+oy+pr],
                     fill=(*accent, int(alpha * 160)))


def draw_house_shield(draw, cx, cy, size, accent, alpha, t_anim):
    a = int(alpha * 255)
    if a <= 0:
        return
    c = (*accent, a)
    # House outline — walls
    hw, hh = int(size * 0.5), int(size * 0.4)
    wall_y = cy + int(size * 0.02)
    draw.rectangle([cx-hw//2, wall_y, cx+hw//2, wall_y+hh],
                   outline=c, width=4)
    # Roof triangle
    draw.polygon([(cx-hw//2-15, wall_y),
                  (cx, wall_y - int(size*0.38)),
                  (cx+hw//2+15, wall_y)],
                 outline=c, width=4, fill=(0, 0, 0, 0))
    # Door
    dw, dh = int(hw * 0.28), int(hh * 0.5)
    draw.rectangle([cx-dw//2, wall_y+hh-dh, cx+dw//2, wall_y+hh],
                   outline=c, width=3)
    # Shield around house — expands in during scene 1
    shield_scale = ease_out(min(1.0, t_anim / 4.0))
    sw = int((hw + 80) * shield_scale)
    sh = int((hh + int(size*0.38) + 50) * shield_scale)
    shield_top = cy - int(size * 0.38) - 30
    # Shield shape: top rectangle + bottom triangle
    sx0, sx1 = cx - sw, cx + sw
    sy0, sy1 = shield_top - 20, shield_top + sh
    draw.line([(sx0, sy0), (sx1, sy0), (sx1, sy1), (cx, sy1+int(sh*0.3)), (sx0, sy1), (sx0, sy0)],
              fill=(*accent, int(alpha * 100)), width=3)
    # Tick / checkmark in shield bottom
    ck_y = sy1 + int(sh * 0.12)
    tk = int(size * 0.06)
    draw.line([(cx - tk, ck_y), (cx, ck_y + tk), (cx + tk*2, ck_y - tk)],
              fill=c, width=4)


# ──────────────────────────────────────────────── scene renderers
def scene1_screentime(t, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    # Icon
    icon_alpha = ease_out(min(t / 2.0, 1.0))
    layer, ld = make_layer()
    draw_tv_icon(ld, W//2, H//2 - 20, 260, acc, icon_alpha)
    return composite_overlay(img, layer)

def scene2_screentime(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    # Subtle TV icon (faded) in background
    layer, ld = make_layer()
    draw_tv_icon(ld, W//2, H//2 - 40, 260, acc, 0.08)
    img = composite_overlay(img, layer)
    draw = ImageDraw.Draw(img.convert("RGBA")).im  # reinit draw
    img_rgba = img.convert("RGBA")
    draw2 = ImageDraw.Draw(img_rgba)
    # Accent top bar
    draw2.rectangle([0, 0, W, 5], fill=(*acc, 255))
    # Brand name slides up
    brand_a = ease_out(min(t / 2.0, 1.0))
    brand_offset = int(30 * (1 - brand_a))
    by = H//2 - 75 + brand_offset
    draw_centered_text(draw2, ad["brand"], F_BRAND, by, rgb("FFFFFF"), alpha=brand_a)
    # Tagline
    tag_a = ease_out(max(0.0, (t - 2.0) / 1.5))
    ty = H//2 + 60
    draw_centered_text(draw2, ad["tagline"], F_TAGLINE, ty, rgb("CCDDEE"), alpha=tag_a)
    # Category badge
    badge_a = ease_in_out(max(0.0, (t - 1.0) / 1.5))
    draw2.rounded_rectangle([30, 20, 230, 52], radius=16,
                              fill=(*acc, int(badge_a * 50)),
                              outline=(*acc, int(badge_a * 200)), width=2)
    draw2.text((50, 27), "STREAMING", font=F_BADGE,
               fill=(*acc, int(badge_a * 255)))
    return img_rgba.convert("RGB")

def scene3_screentime(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = scene2_screentime(8.0, ad, acc, bg_top, bg_bot)  # hold scene 2 fully revealed
    draw = ImageDraw.Draw(img.convert("RGBA"))
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    # CTA bar slides up
    bar_h = 80
    bar_a = ease_out(min(t / 2.5, 1.0))
    bar_y = H - int(bar_h * bar_a)
    d.rectangle([0, bar_y, W, H], fill=(*acc, int(bar_a * 230)))
    text_a = ease_out(max(0.0, (t - 0.5) / 2.0))
    cta_y = bar_y + (H - bar_y - 30) // 2
    cx2 = centered_x(d, ad["cta"], F_CTA)
    d.text((cx2, cta_y), ad["cta"], font=F_CTA,
           fill=(*rgb(ad["cta_fg"]), int(text_a * 255)))
    return img_rgba.convert("RGB")


def scene1_arcademax(t, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    icon_alpha = ease_out(min(t / 2.0, 1.0))
    # Pulsing glow circles
    for r_mult, a_mult in [(1.2, 0.08), (1.0, 0.12)]:
        glow_r = int(160 * r_mult * (0.97 + 0.03 * math.sin(t * 3)))
        layer, ld = make_layer()
        ld.ellipse([W//2-glow_r, H//2-glow_r, W//2+glow_r, H//2+glow_r],
                   fill=(*acc, int(icon_alpha * a_mult * 255)))
        img = composite_overlay(img, layer)
    layer2, ld2 = make_layer()
    draw_controller_icon(ld2, W//2, H//2 - 10, 280, acc, icon_alpha)
    return composite_overlay(img, layer2)

def scene2_arcademax(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    d.rectangle([0, 0, W, 5], fill=(*acc, 255))
    # Brand — slight glow by drawing it twice with offset at low alpha
    brand_a = ease_out(min(t / 2.0, 1.0))
    brand_offset = int(25 * (1 - brand_a))
    by = H//2 - 75 + brand_offset
    # glow pass
    for gx_off in [-2, 2, 0]:
        gx = centered_x(d, ad["brand"], F_BRAND) + gx_off
        d.text((gx, by), ad["brand"], font=F_BRAND,
               fill=(*acc, int(brand_a * 80)))
    draw_centered_text(d, ad["brand"], F_BRAND, by, rgb("FFFFFF"), alpha=brand_a)
    tag_a = ease_out(max(0.0, (t - 2.0) / 1.5))
    draw_centered_text(d, ad["tagline"], F_TAGLINE, H//2 + 60, rgb("CCBBDD"), alpha=tag_a)
    badge_a = ease_in_out(max(0.0, (t - 1.0) / 1.5))
    d.rounded_rectangle([30, 20, 210, 52], radius=16,
                          fill=(*acc, int(badge_a * 50)),
                          outline=(*acc, int(badge_a * 200)), width=2)
    d.text((50, 27), "GAMING", font=F_BADGE,
           fill=(*acc, int(badge_a * 255)))
    return img_rgba.convert("RGB")

def scene3_arcademax(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = scene2_arcademax(8.0, ad, acc, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    bar_h, bar_a = 80, ease_out(min(t / 2.5, 1.0))
    bar_y = H - int(bar_h * bar_a)
    d.rectangle([0, bar_y, W, H], fill=(*acc, int(bar_a * 230)))
    text_a = ease_out(max(0.0, (t - 0.5) / 2.0))
    cta_y = bar_y + (H - bar_y - 30) // 2
    cx2 = centered_x(d, ad["cta"], F_CTA)
    d.text((cx2, cta_y), ad["cta"], font=F_CTA,
           fill=(*rgb(ad["cta_fg"]), int(text_a * 255)))
    return img_rgba.convert("RGB")


def scene1_crunchpop(t, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    icon_alpha = ease_out(min(t / 2.0, 1.0))
    layer, ld = make_layer()
    draw_cereal_icon(ld, W//2, H//2 - 10, 260, acc, icon_alpha, t)
    return composite_overlay(img, layer)

def scene2_crunchpop(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    d.rectangle([0, 0, W, 5], fill=(*acc, 255))
    brand_a = ease_out(min(t / 2.0, 1.0))
    brand_offset = int(25 * (1 - brand_a))
    draw_centered_text(d, ad["brand"], F_BRAND, H//2 - 75 + brand_offset,
                       rgb("FFFFFF"), alpha=brand_a)
    tag_a = ease_out(max(0.0, (t - 2.0) / 1.5))
    draw_centered_text(d, ad["tagline"], F_TAGLINE, H//2 + 60, rgb("FFE0B0"), alpha=tag_a)
    badge_a = ease_in_out(max(0.0, (t - 1.0) / 1.5))
    d.rounded_rectangle([30, 20, 260, 52], radius=16,
                          fill=(*acc, int(badge_a * 50)),
                          outline=(*acc, int(badge_a * 200)), width=2)
    d.text((50, 27), "FOOD & DRINK", font=F_BADGE,
           fill=(*acc, int(badge_a * 255)))
    return img_rgba.convert("RGB")

def scene3_crunchpop(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = scene2_crunchpop(8.0, ad, acc, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    bar_h, bar_a = 80, ease_out(min(t / 2.5, 1.0))
    bar_y = H - int(bar_h * bar_a)
    d.rectangle([0, bar_y, W, H], fill=(*acc, int(bar_a * 230)))
    text_a = ease_out(max(0.0, (t - 0.5) / 2.0))
    cta_y = bar_y + (H - bar_y - 30) // 2
    cx2 = centered_x(d, ad["cta"], F_CTA)
    d.text((cx2, cta_y), ad["cta"], font=F_CTA,
           fill=(*rgb(ad["cta_fg"]), int(text_a * 255)))
    return img_rgba.convert("RGB")


def scene1_homesafe(t, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    icon_alpha = ease_out(min(t / 2.5, 1.0))
    layer, ld = make_layer()
    draw_house_shield(ld, W//2, H//2 - 10, 260, acc, icon_alpha, t)
    return composite_overlay(img, layer)

def scene2_homesafe(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    gradient_bg(img, draw, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    d.rectangle([0, 0, W, 5], fill=(*acc, 255))
    brand_a = ease_out(min(t / 2.0, 1.0))
    brand_offset = int(25 * (1 - brand_a))
    draw_centered_text(d, ad["brand"], F_BRAND, H//2 - 75 + brand_offset,
                       rgb("FFFFFF"), alpha=brand_a)
    tag_a = ease_out(max(0.0, (t - 2.0) / 1.5))
    draw_centered_text(d, ad["tagline"], F_TAGLINE, H//2 + 60, rgb("C8E6C0"), alpha=tag_a)
    badge_a = ease_in_out(max(0.0, (t - 1.0) / 1.5))
    d.rounded_rectangle([30, 20, 230, 52], radius=16,
                          fill=(*acc, int(badge_a * 50)),
                          outline=(*acc, int(badge_a * 200)), width=2)
    d.text((50, 27), "INSURANCE", font=F_BADGE,
           fill=(*acc, int(badge_a * 255)))
    return img_rgba.convert("RGB")

def scene3_homesafe(t, ad, acc, bg_top, bg_bot) -> Image.Image:
    img = scene2_homesafe(8.0, ad, acc, bg_top, bg_bot)
    img_rgba = img.convert("RGBA")
    d = ImageDraw.Draw(img_rgba)
    bar_h, bar_a = 80, ease_out(min(t / 2.5, 1.0))
    bar_y = H - int(bar_h * bar_a)
    d.rectangle([0, bar_y, W, H], fill=(*acc, int(bar_a * 230)))
    text_a = ease_out(max(0.0, (t - 0.5) / 2.0))
    cta_y = bar_y + (H - bar_y - 30) // 2
    cx2 = centered_x(d, ad["cta"], F_CTA)
    d.text((cx2, cta_y), ad["cta"], font=F_CTA,
           fill=(*rgb(ad["cta_fg"]), int(text_a * 255)))
    return img_rgba.convert("RGB")


# ──────────────────────────────────────────────── ad specs
ADS = [
    {
        "id":      "ad_relevant_screentime",
        "brand":   "SCREENTIME",
        "tagline": "Every story worth watching.",
        "cta":     "screentime.tv  —  free for 30 days",
        "bg_top":  "0A0F1F",
        "bg_bot":  "152D4B",
        "accent":  "4FC3F7",
        "cta_fg":  "0A0F1F",
        "scenes":  [scene1_screentime, scene2_screentime, scene3_screentime],
    },
    {
        "id":      "ad_relevant_arcademax",
        "brand":   "ARCADEMAX",
        "tagline": "Your next adventure starts here.",
        "cta":     "arcademax.io  —  play free",
        "bg_top":  "08040F",
        "bg_bot":  "1A0A2E",
        "accent":  "E040FB",
        "cta_fg":  "FFFFFF",
        "scenes":  [scene1_arcademax, scene2_arcademax, scene3_arcademax],
    },
    {
        "id":      "ad_irrelevant_crunchpop",
        "brand":   "CRUNCHPOP",
        "tagline": "The crunch that starts your day.",
        "cta":     "New flavours in stores now",
        "bg_top":  "CC3700",
        "bg_bot":  "6B1200",
        "accent":  "FFD740",
        "cta_fg":  "7B1E00",
        "scenes":  [scene1_crunchpop, scene2_crunchpop, scene3_crunchpop],
    },
    {
        "id":      "ad_irrelevant_homesafe",
        "brand":   "HOMESAFE",
        "tagline": "Protect what matters most.",
        "cta":     "homesafe.com/quote  —  2 minutes",
        "bg_top":  "071510",
        "bg_bot":  "142820",
        "accent":  "A8D5A2",
        "cta_fg":  "071510",
        "scenes":  [scene1_homesafe, scene2_homesafe, scene3_homesafe],
    },
]

SCENE_CUTS = [8.0, 22.0, 30.0]   # scene 1 ends at 8s, scene 2 ends at 22s


def render_frame(t: float, ad: dict) -> Image.Image:
    acc     = rgb(ad["accent"])
    bg_top  = rgb(ad["bg_top"])
    bg_bot  = rgb(ad["bg_bot"])
    s1, s2, s3 = ad["scenes"]

    if t < SCENE_CUTS[0]:
        return s1(t, acc, bg_top, bg_bot)
    elif t < SCENE_CUTS[1]:
        return s2(t - SCENE_CUTS[0], ad, acc, bg_top, bg_bot)
    else:
        return s3(t - SCENE_CUTS[1], ad, acc, bg_top, bg_bot)


def render_ad(ad: dict, out_path: Path) -> None:
    frames_dir = Path(tempfile.mkdtemp())
    total = DURATION * FPS

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
