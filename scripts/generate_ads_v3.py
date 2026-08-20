#!/usr/bin/env python3
"""
generate_ads_v3.py — Content-library-targeted synthetic ad set.

12 ads designed specifically for the AVOD-Lab content library, closing
relevance gaps identified in the tag-Jaccard analysis.  Each ad has a
product-specific drawn object, glow text, and synthesized audio.

Viewer-profile → relevant ad pool
  thrill_seeker        → ad_thrill_gravecrest, ad_thrill_torque, ad_thrill_vanguard
  intellectual_explorer → ad_intel_curiosity, ad_intel_horizon, ad_intel_terra
  content_chameleon    → ad_chame_toonbox, ad_chame_stagecraft, ad_chame_pantry
  investigative_viewer → ad_invest_nocturne, ad_invest_deadlines, ad_invest_caseroom

Run:
    pip install Pillow
    python scripts/generate_ads_v3.py
    python scripts/generate_ads_v3.py --only ad_thrill_torque ad_intel_horizon
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
FPS = 20
DURATION = 15
TOTAL_FRAMES = FPS * DURATION
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "ads")


# ─────────────────────────────────────────────────────────────────────────────
# Core utilities
# ─────────────────────────────────────────────────────────────────────────────

def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ease_back(t):
    t = min(max(t, 0.0), 1.0)
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def hsv_to_rgb(h, s, v):
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    _t = v * (1 - (1 - f) * s)
    r, g, b = [(v, _t, p), (q, v, p), (p, v, _t),
               (p, q, v), (_t, p, v), (v, p, q)][i % 6]
    return clamp(r * 255), clamp(g * 255), clamp(b * 255)


def try_font(size):
    for name in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(name):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass
    return ImageFont.load_default()


def text_center(draw, text, cx, cy, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), text, font=font, fill=fill)


def _text_origin(img, text, cx, cy, font):
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2, cy - (bbox[3] - bbox[1]) // 2)


def glow_text(base: Image.Image, text: str, cx: int, cy: int,
              font, color, glow_color=None, glow_r: int = 14) -> Image.Image:
    if glow_color is None:
        glow_color = color
    txt = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(txt).text(
        _text_origin(txt, text, cx, cy, font), text, font=font,
        fill=(*glow_color[:3], 200))
    blurred = txt.filter(ImageFilter.GaussianBlur(radius=glow_r))
    base = Image.alpha_composite(base.convert("RGBA"), blurred)
    ImageDraw.Draw(base).text(
        _text_origin(base, text, cx, cy, font), text, font=font, fill=color)
    return base


def gradient_bg(colors, w=W, h=H):
    img = Image.new("RGBA", (w, h))
    px = img.load()
    n = len(colors) - 1
    for y in range(h):
        t = y / (h - 1)
        seg = min(int(t * n), n - 1)
        lt = t * n - seg
        c0, c1 = colors[seg], colors[seg + 1]
        r = clamp(lerp(c0[0], c1[0], lt))
        g = clamp(lerp(c0[1], c1[1], lt))
        b = clamp(lerp(c0[2], c1[2], lt))
        for x in range(w):
            px[x, y] = (r, g, b, 255)
    return img


def particles(draw, t, acc, count=35, seed=0, vy=-55, drift=25,
              r_range=(2, 7), a_range=(0.3, 0.85)):
    rng = random.Random(seed)
    for _ in range(count):
        x0 = rng.uniform(0, W)
        y0 = rng.uniform(0, H)
        spd = rng.uniform(0.6, 1.4)
        pha = rng.uniform(0, 2 * math.pi)
        r = rng.randint(*r_range)
        al = rng.uniform(*a_range)
        x = (x0 + drift * math.sin(t * 1.2 + pha)) % W
        y = (y0 + vy * spd * t) % H
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*acc, int(al * 255)))


def pulse_rings(draw, cx, cy, t, acc, period=1.6, n=3, max_r=220):
    for k in range(n):
        phase = ((t + k * period / n) % period) / period
        r = int(max_r * phase)
        a = int(255 * (1 - phase) * 0.55)
        if a > 0:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         outline=(*acc, a), width=2)


# ─────────────────────────────────────────────────────────────────────────────
# Global post-processing
# ─────────────────────────────────────────────────────────────────────────────

_VIGNETTE: "Image | None" = None


def _build_vignette(strength: float = 0.62) -> Image.Image:
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = vig.load()
    for y in range(H):
        for x in range(W):
            dx = (x - W / 2) / (W / 2)
            dy = (y - H / 2) / (H / 2)
            d = min(math.sqrt(dx * dx + dy * dy), 1.4143) / 1.4143
            a = int(255 * strength * d ** 2.4)
            px[x, y] = (0, 0, 0, min(a, 255))
    return vig


def apply_vignette(img: Image.Image) -> Image.Image:
    global _VIGNETTE
    if _VIGNETTE is None:
        print("  precomputing vignette …")
        _VIGNETTE = _build_vignette()
    return Image.alpha_composite(img.convert("RGBA"), _VIGNETTE)


def apply_grain(img: Image.Image, fi: int, strength: int = 18) -> Image.Image:
    grain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rng = random.Random(fi * 7919 + 31337)
    px = grain.load()
    for _ in range(2000):
        gx = rng.randint(0, W - 1)
        gy = rng.randint(0, H - 1)
        a = rng.randint(3, strength)
        v = rng.randint(160, 255)
        px[gx, gy] = (v, v, v, a)
    return Image.alpha_composite(img.convert("RGBA"), grain)


def brand_badge(draw, char: str, cx: int, cy: int, acc, t_local: float) -> None:
    r = 34
    badge_a = clamp(ease_out(min(t_local / 1.5, 1.0)) * 190)
    if badge_a < 5:
        return
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=(*acc, badge_a // 3), outline=(*acc, badge_a), width=3)
    text_center(draw, char, cx, cy, try_font(28), (255, 255, 255, badge_a))


def scan_sweep(draw, t: float, scene_start: float, acc, width: int = 55) -> None:
    sweep_x = int(((t - scene_start) / 5.0) * W * 1.8 - W * 0.4)
    for sx in range(max(0, sweep_x - width), min(W, sweep_x)):
        a = int(28 * (1 - abs(sx - sweep_x) / width))
        draw.line([(sx, 0), (sx, H)], fill=(*acc, a))


def cta_glow(draw, cx: int, cy: int, t: float, acc) -> None:
    pulse_rings(draw, cx, cy, t, acc, period=1.2, n=2, max_r=130)
    shim_prog = ((t - 10) % 1.4) / 1.4
    shim_x = int(cx - 200 + shim_prog * 420)
    for sx in range(max(cx - 200, shim_x - 35), min(cx + 200, shim_x + 1)):
        a = int(45 * (1 - abs(sx - shim_x) / 35))
        draw.line([(sx, cy - 32), (sx, cy + 32)], fill=(255, 255, 255, a))


def render_and_encode(frames_fn, ad_id: str,
                      accent=(100, 160, 255), brand_char: str = "A",
                      category: str = "") -> None:
    tmp = tempfile.mkdtemp(prefix=f"ad_{ad_id}_")
    try:
        print(f"  rendering {TOTAL_FRAMES} frames …")
        for fi in range(TOTAL_FRAMES):
            t = fi / FPS
            img = frames_fn(fi, t)

            img = apply_grain(img, fi)
            img = apply_vignette(img)

            breath_a = int(5 + 5 * math.sin(t * 0.45))
            tint = Image.new("RGBA", (W, H), (*accent, breath_a))
            img = Image.alpha_composite(img.convert("RGBA"), tint)

            if 5.0 <= t < 10.0:
                sw_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                scan_sweep(ImageDraw.Draw(sw_ov), t, 5.0, accent)
                img = Image.alpha_composite(img.convert("RGBA"), sw_ov)

            if t >= 5.0:
                badge_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                bd = ImageDraw.Draw(badge_ov)
                brand_badge(bd, brand_char, W - 72, 58, accent, t - 5.0)
                if t >= 10.0:
                    cta_glow(bd, W // 2, H - 82, t, accent)
                img = Image.alpha_composite(img.convert("RGBA"), badge_ov)

            img.convert("RGB").save(os.path.join(tmp, f"f{fi:04d}.png"))

        audio_path = None
        if category:
            try:
                sys.path.insert(0, os.path.dirname(__file__))
                from ad_audio import synthesize_audio, write_wav, SAMPLE_RATE
                print("  synthesizing audio …")
                samples = synthesize_audio(category, DURATION)
                audio_path = os.path.join(tmp, "audio.wav")
                write_wav(samples, SAMPLE_RATE, audio_path)
            except Exception as exc:
                print(f"  audio skipped ({exc})")
                audio_path = None

        out_path = os.path.join(OUT_DIR, f"{ad_id}.mp4")
        cmd = ["ffmpeg", "-y", "-framerate", str(FPS),
               "-i", os.path.join(tmp, "f%04d.png")]
        if audio_path:
            cmd += ["-i", audio_path]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22"]
        if audio_path:
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        cmd += ["-movflags", "+faststart", out_path]
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  → {out_path}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# Product-object drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def draw_skull_reel(draw, cx, cy, r, col, alpha):
    """Skull overlaid with a film-reel ring — horror streaming."""
    # Skull dome
    draw.arc([cx - r, cy - r, cx + r, cy + int(r * 0.3)],
             start=0, end=180, fill=(*col, alpha), width=5)
    # Jaw
    draw.arc([cx - int(r * 0.7), cy, cx + int(r * 0.7), cy + int(r * 0.8)],
             start=0, end=180, fill=(*col, alpha), width=4)
    # Eye sockets
    for ex in [cx - int(r * 0.3), cx + int(r * 0.3)]:
        er = int(r * 0.18)
        draw.ellipse([ex - er, cy - int(r * 0.2) - er,
                      ex + er, cy - int(r * 0.2) + er],
                     outline=(*col, alpha), width=3)
    # Film-reel outer ring
    rr = int(r * 1.3)
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                 outline=(*col, alpha // 2), width=3)
    # Sprocket holes around ring
    for k in range(8):
        angle = math.radians(k * 45)
        hx = cx + int(math.cos(angle) * rr)
        hy = cy + int(math.sin(angle) * rr)
        draw.ellipse([hx - 6, hy - 6, hx + 6, hy + 6],
                     fill=(*col, alpha // 3))


def draw_speedometer(draw, cx, cy, r, col, alpha, needle_angle=0.0):
    """Speedometer dial — automotive."""
    # Outer rim
    draw.arc([cx - r, cy - r, cx + r, cy + r],
             start=135, end=45, fill=(*col, alpha), width=5)
    # Tick marks
    for k in range(11):
        angle = math.radians(135 + k * 27)
        x0 = cx + int(math.cos(angle) * (r - 8))
        y0 = cy + int(math.sin(angle) * (r - 8))
        x1 = cx + int(math.cos(angle) * (r - 22 if k % 5 == 0 else r - 14))
        y1 = cy + int(math.sin(angle) * (r - 22 if k % 5 == 0 else r - 14))
        draw.line([(x0, y0), (x1, y1)], fill=(*col, alpha), width=3 if k % 5 == 0 else 1)
    # Needle
    na = math.radians(135 + needle_angle * 270)
    nx = cx + int(math.cos(na) * (r - 18))
    ny = cy + int(math.sin(na) * (r - 18))
    draw.line([(cx, cy), (nx, ny)], fill=(*col, alpha), width=4)
    draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(*col, alpha))


def draw_shield(draw, cx, cy, r, col, alpha):
    """Heraldic shield with cross inset — action/adventure streaming."""
    pts = [
        (cx, cy - r),
        (cx + r, cy - int(r * 0.4)),
        (cx + r, cy + int(r * 0.3)),
        (cx, cy + r),
        (cx - r, cy + int(r * 0.3)),
        (cx - r, cy - int(r * 0.4)),
    ]
    draw.polygon(pts, outline=(*col, alpha), width=4)
    # Cross
    arm = int(r * 0.45)
    draw.line([(cx, cy - arm), (cx, cy + arm)], fill=(*col, alpha), width=4)
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=(*col, alpha), width=4)


def draw_dna_helix(draw, cx, cy, r, col, alpha, phase=0.0):
    """Double-helix — science/education."""
    h = int(r * 2.8)
    steps = 40
    for i in range(steps):
        pf = i / (steps - 1)
        y = cy - h // 2 + int(pf * h)
        ang1 = phase + pf * 4 * math.pi
        ang2 = ang1 + math.pi
        x1 = cx + int(math.cos(ang1) * r * 0.55)
        x2 = cx + int(math.cos(ang2) * r * 0.55)
        # Backbone dots
        dot_a = alpha if i % 2 == 0 else alpha // 2
        draw.ellipse([x1 - 5, y - 5, x1 + 5, y + 5], fill=(*col, dot_a))
        draw.ellipse([x2 - 5, y - 5, x2 + 5, y + 5], fill=(*col, dot_a))
        # Rungs every 4 steps
        if i % 4 == 0:
            draw.line([(x1, y), (x2, y)], fill=(*col, alpha // 2), width=2)


def draw_wormhole(draw, cx, cy, r, col, alpha):
    """Concentric ellipses with perspective skew — wormhole/portal."""
    for k in range(6):
        frac = (k + 1) / 6
        rx = int(r * frac)
        ry = int(r * frac * 0.45)
        a = int(alpha * (1 - frac * 0.5))
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                     outline=(*col, a), width=2 + int((1 - frac) * 3))
    # Central bright dot
    draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(*col, alpha))
    # Radial spokes
    for k in range(8):
        ang = math.radians(k * 45)
        draw.line([(cx, cy),
                   (cx + int(math.cos(ang) * r * 0.9),
                    cy + int(math.sin(ang) * r * 0.45))],
                  fill=(*col, alpha // 4), width=1)


def draw_globe(draw, cx, cy, r, col, alpha):
    """Simplified globe — nature/travel."""
    # Outer circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(*col, alpha), width=4)
    # Latitude lines
    for lat in [-0.55, 0.0, 0.55]:
        ry = int(r * math.sqrt(max(0, 1 - lat ** 2)))
        yo = int(lat * r)
        if ry > 2:
            draw.arc([cx - ry, cy + yo - int(ry * 0.35),
                      cx + ry, cy + yo + int(ry * 0.35)],
                     start=0, end=360, fill=(*col, alpha // 2), width=2)
    # Longitude lines
    for lon in [-60, 0, 60]:
        ang = math.radians(lon)
        draw.arc([cx - r, cy - r, cx + r, cy + r],
                 start=lon - 90, end=lon + 90, fill=(*col, alpha // 2), width=2)
    # Stand
    draw.line([(cx, cy + r), (cx, cy + r + 22)], fill=(*col, alpha), width=4)
    draw.line([(cx - 25, cy + r + 22), (cx + 25, cy + r + 22)],
              fill=(*col, alpha), width=4)


def draw_clapperboard(draw, cx, cy, r, col, alpha):
    """Film clapperboard — animation streaming."""
    bw, bh = int(r * 2.2), int(r * 1.6)
    # Body
    draw.rectangle([cx - bw // 2, cy - bh // 4, cx + bw // 2, cy + bh * 3 // 4],
                   outline=(*col, alpha), width=4)
    # Lines inside body
    for k in range(1, 4):
        y = cy - bh // 4 + k * (bh // 4)
        draw.line([(cx - bw // 2 + 10, y), (cx + bw // 2 - 10, y)],
                  fill=(*col, alpha // 3), width=1)
    # Clapper strip (top bar with diagonal stripes)
    ty = cy - bh // 4
    draw.rectangle([cx - bw // 2, ty - int(r * 0.55), cx + bw // 2, ty],
                   outline=(*col, alpha), width=3)
    stripe_w = int(bw / 7)
    for k in range(7):
        x0 = cx - bw // 2 + k * stripe_w
        fill_col = (*col, alpha // 2) if k % 2 == 0 else (0, 0, 0, alpha // 3)
        draw.polygon([
            (x0, ty - int(r * 0.55)), (x0 + stripe_w, ty - int(r * 0.55)),
            (x0 + stripe_w, ty), (x0, ty)
        ], fill=fill_col)
    # Hinge circle
    draw.ellipse([cx - 12, ty - 12, cx + 12, ty + 12],
                 outline=(*col, alpha), width=3)


def draw_theater_masks(draw, cx, cy, r, col, alpha):
    """Comedy + tragedy masks — classic cinema/entertainment."""
    for i, (dx, expr, brow_dy) in enumerate([(-int(r * 0.65), "happy", -1),
                                              (int(r * 0.65), "sad", 1)]):
        mx = cx + dx
        mr = int(r * 0.6)
        draw.ellipse([mx - mr, cy - mr, mx + mr, cy + mr],
                     outline=(*col, alpha), width=3)
        # Eyes
        for ex in [mx - mr // 3, mx + mr // 3]:
            ey = cy - mr // 5
            draw.ellipse([ex - 7, ey - 5, ex + 7, ey + 5],
                         outline=(*col, alpha), width=2)
        # Mouth
        if expr == "happy":
            draw.arc([mx - mr // 2, cy, mx + mr // 2, cy + mr // 2],
                     start=0, end=180, fill=(*col, alpha), width=3)
        else:
            draw.arc([mx - mr // 2, cy + mr // 4, mx + mr // 2, cy + mr * 3 // 4],
                     start=180, end=360, fill=(*col, alpha), width=3)
        # Brow
        bwy = cy - mr // 2 + brow_dy * 8
        draw.line([(mx - mr // 3, bwy - brow_dy * 5),
                   (mx + mr // 3, bwy + brow_dy * 5)],
                  fill=(*col, alpha), width=3)


def draw_grocery_bag(draw, cx, cy, r, col, alpha):
    """Paper grocery bag with vegetable tops — food/grocery delivery."""
    bw, bh = int(r * 1.5), int(r * 1.8)
    # Bag body (trapezoid wider at top)
    pts = [
        (cx - bw // 2 - 10, cy - bh // 2),
        (cx + bw // 2 + 10, cy - bh // 2),
        (cx + bw // 2, cy + bh // 2),
        (cx - bw // 2, cy + bh // 2),
    ]
    draw.polygon(pts, outline=(*col, alpha), width=4)
    # Fold line at top
    draw.line([(cx - bw // 2 - 10, cy - bh // 2 + 22),
               (cx + bw // 2 + 10, cy - bh // 2 + 22)],
              fill=(*col, alpha // 2), width=2)
    # Handles
    for hx in [cx - bw // 4, cx + bw // 4]:
        draw.arc([hx - 18, cy - bh // 2 - 30, hx + 18, cy - bh // 2 + 10],
                 start=0, end=180, fill=(*col, alpha), width=4)
    # Veggie tops peeking out
    tops = [(cx - bw // 3, cy - bh // 2 - 5),
            (cx, cy - bh // 2 - 12),
            (cx + bw // 3, cy - bh // 2 - 6)]
    for tx, ty in tops:
        for ang in [-25, 0, 25]:
            ra = math.radians(ang - 90)
            draw.line([(tx, ty), (tx + int(math.cos(ra) * 22),
                                  ty + int(math.sin(ra) * 22))],
                      fill=(*col, alpha), width=3)


def draw_venetian_blinds(draw, cx, cy, r, col, alpha, tilt=0.15):
    """Venetian blinds with light-streak through gap — noir."""
    bw = int(r * 2.2)
    slat_h = 18
    slats = 8
    total_h = slats * slat_h
    y0 = cy - total_h // 2
    for k in range(slats):
        sy = y0 + k * slat_h
        # Slat outline with tilt
        off = int(tilt * bw)
        draw.polygon([
            (cx - bw // 2, sy + off),
            (cx + bw // 2, sy - off),
            (cx + bw // 2, sy - off + slat_h - 3),
            (cx - bw // 2, sy + off + slat_h - 3),
        ], outline=(*col, alpha // 2), width=2,
           fill=(0, 0, 0, alpha // 6))
    # Light streak through one gap (slat 3)
    gap_y = y0 + 3 * slat_h + slat_h // 2
    for lx in range(cx - bw // 2, cx + bw // 2):
        dist = abs(lx - cx)
        la = int(alpha * 0.6 * max(0, 1 - dist / (bw * 0.45)))
        draw.line([(lx, gap_y - 2), (lx, gap_y + 2)],
                  fill=(255, 230, 180, la))
    # Silhouette behind blinds (simplified head shape)
    draw.ellipse([cx - 28, cy - 28, cx + 28, cy + 28],
                 fill=(0, 0, 0, alpha // 2))


def draw_typewriter(draw, cx, cy, r, col, alpha):
    """Typewriter — investigative journalism."""
    bw, bh = int(r * 2.0), int(r * 1.2)
    # Body
    draw.rounded_rectangle([cx - bw // 2, cy - bh // 2,
                             cx + bw // 2, cy + bh // 2],
                            radius=8, outline=(*col, alpha), width=4)
    # Paper roll at top
    draw.rectangle([cx - bw // 3, cy - bh // 2 - 30,
                    cx + bw // 3, cy - bh // 2 + 5],
                   outline=(*col, alpha), width=3)
    # Text lines on paper
    for lk in range(3):
        lw = int(bw * (0.55 - lk * 0.08))
        ly = cy - bh // 2 - 20 + lk * 9
        draw.line([(cx - lw // 2, ly), (cx + lw // 2, ly)],
                  fill=(*col, alpha // 2), width=2)
    # Key rows (3 rows of circular keys)
    key_r = 8
    for row, (ny, n) in enumerate([(cy + 2, 10), (cy + 22, 10), (cy + 40, 8)]):
        x_start = cx - (n // 2) * (key_r * 2 + 4) + key_r
        for k in range(n):
            kx = x_start + k * (key_r * 2 + 4)
            draw.ellipse([kx - key_r, ny - key_r, kx + key_r, ny + key_r],
                         outline=(*col, alpha), width=2)
    # Carriage return lever
    draw.line([(cx + bw // 2 - 10, cy - bh // 2),
               (cx + bw // 2 + 22, cy - bh // 4)],
              fill=(*col, alpha), width=4)


def draw_evidence_board(draw, cx, cy, r, col, alpha):
    """Evidence board with cards and string lines — true crime."""
    # Board background
    bw, bh = int(r * 2.2), int(r * 1.6)
    draw.rectangle([cx - bw // 2, cy - bh // 2,
                    cx + bw // 2, cy + bh // 2],
                   outline=(*col, alpha // 3), width=3)
    # Cards (5 pinned rectangles at random-ish positions)
    card_positions = [
        (cx - bw // 3, cy - bh // 3),
        (cx + bw // 3, cy - bh // 4),
        (cx - bw // 4, cy + bh // 4),
        (cx + bw // 4, cy + bh // 5),
        (cx, cy - bh // 6),
    ]
    for px, py in card_positions:
        cw, ch = 48, 34
        draw.rectangle([px - cw // 2, py - ch // 2,
                        px + cw // 2, py + ch // 2],
                       outline=(*col, alpha), width=2)
        # Pin dot
        draw.ellipse([px - 4, py - ch // 2 - 4,
                      px + 4, py - ch // 2 + 4],
                     fill=(*col, alpha))
    # Red string connections
    for i in range(len(card_positions) - 1):
        ax, ay = card_positions[i]
        bx, by = card_positions[(i + 2) % len(card_positions)]
        draw.line([(ax, ay), (bx, by)],
                  fill=(204, 0, 32, alpha // 2), width=2)


# ─────────────────────────────────────────────────────────────────────────────
# Scene-title utility
# ─────────────────────────────────────────────────────────────────────────────

def scene_title(img, text, t, t_in, col, font_size=56):
    prog = ease_out(min((t - t_in) / 0.8, 1.0))
    a = int(prog * 255)
    if a < 4:
        return img
    font = try_font(font_size)
    return glow_text(img, text, W // 2, H // 2, font, (*col, a),
                     glow_color=col, glow_r=18)


# ─────────────────────────────────────────────────────────────────────────────
# THRILL_SEEKER ads
# ─────────────────────────────────────────────────────────────────────────────

def gravecrest_frame(fi, t):
    """GRAVECREST — horror streaming. Dark crimson; skull-reel object."""
    acc = (204, 0, 32)

    if t < 5.0:
        # Scene 1: blood-red fog + skull materialises
        bg = gradient_bg([(12, 0, 4), (40, 0, 12), (10, 0, 6)])
        d = ImageDraw.Draw(bg)
        # Drifting red particles (embers)
        particles(d, t, acc, count=40, seed=1, vy=-35, drift=18,
                  r_range=(1, 5), a_range=(0.25, 0.70))
        # Skull + reel materialises
        sk_prog = ease_out(min(t / 3.5, 1.0))
        draw_skull_reel(d, W // 2, H // 2 - 20, int(70 * sk_prog),
                        acc, int(200 * sk_prog))
        bg = scene_title(bg, "GRAVECREST", t, 1.0, acc)

    elif t < 10.0:
        # Scene 2: dark corridor with flickering scan
        prog = (t - 5.0) / 5.0
        bg = gradient_bg([(8, 0, 2), (25, 5, 8)])
        d = ImageDraw.Draw(bg)
        # Flicker effect
        flick = 0.7 + 0.3 * math.sin(t * 17.3)
        particles(d, t, acc, count=25, seed=2, vy=-20, drift=30,
                  r_range=(1, 4), a_range=(0.15 * flick, 0.55 * flick))
        draw_skull_reel(d, int(W * 0.72), H // 2,
                        int(55 + 8 * math.sin(t * 2.2)), acc,
                        int(150 + 40 * math.sin(t * 3.1)))
        bg = glow_text(bg, "Stream the darkness.", W // 2, H // 2 - 30,
                       try_font(48), (220, 220, 220, 210), glow_color=acc, glow_r=16)

    else:
        # Scene 3: CTA
        bg = gradient_bg([(5, 0, 2), (20, 0, 8)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=200)
        draw_skull_reel(d, W // 2, H // 2 - 20, 80, acc, 200)
        bg = glow_text(bg, "GRAVECREST", W // 2, H - 160, try_font(64),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Horror. Unleashed.", W // 2, H - 90, try_font(36),
                       (255, 200, 200, 220), glow_color=acc, glow_r=10)

    return bg


def torque_frame(fi, t):
    """TORQUE — automotive lifestyle. Burnt orange; speedometer object."""
    acc = (255, 85, 0)

    needle_pos = min(t / 12.0, 1.0)  # needle sweeps over duration

    if t < 5.0:
        bg = gradient_bg([(18, 10, 0), (45, 22, 0), (12, 6, 0)])
        d = ImageDraw.Draw(bg)
        # Speed lines (horizontal streaks)
        rng = random.Random(fi)
        for _ in range(18):
            ly = rng.randint(0, H)
            lw = rng.randint(80, 400)
            la = rng.randint(20, 70)
            d.line([(0, ly), (lw, ly)], fill=(*acc, la), width=2)
        draw_speedometer(d, W // 2, H // 2, 80, acc, 200, needle_pos * 0.4)
        bg = scene_title(bg, "TORQUE", t, 0.8, acc)

    elif t < 10.0:
        bg = gradient_bg([(25, 12, 0), (60, 30, 0)])
        d = ImageDraw.Draw(bg)
        # Asphalt texture dots
        rng = random.Random(42)
        for _ in range(300):
            gx = rng.randint(0, W)
            gy = rng.randint(0, H)
            d.ellipse([gx - 1, gy - 1, gx + 1, gy + 1],
                      fill=(80, 40, 10, 25))
        draw_speedometer(d, int(W * 0.68), H // 2, 70, acc, 220, needle_pos * 0.8)
        bg = glow_text(bg, "Built for the road.", W // 2, H // 2 - 20,
                       try_font(50), (255, 240, 220, 220), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(15, 7, 0), (40, 20, 0)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.0, n=3, max_r=190)
        draw_speedometer(d, W // 2, H // 2 - 20, 85, acc, 220, 0.95)
        bg = glow_text(bg, "TORQUE", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Drive further.", W // 2, H - 90, try_font(38),
                       (255, 210, 180, 220), glow_color=acc, glow_r=12)

    return bg


def vanguard_frame(fi, t):
    """VANGUARD — action/adventure streaming. Steel blue; shield object."""
    acc = (64, 128, 192)

    if t < 5.0:
        bg = gradient_bg([(5, 10, 22), (15, 30, 60), (8, 18, 40)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=30, seed=5, vy=-40, drift=22,
                  r_range=(2, 6), a_range=(0.25, 0.70))
        sh_prog = ease_back(min(t / 3.0, 1.0))
        draw_shield(d, W // 2, H // 2 - 10, int(75 * sh_prog), acc,
                    int(200 * min(sh_prog, 1.0)))
        bg = scene_title(bg, "VANGUARD", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(8, 16, 35), (20, 40, 80)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=2.0, n=2, max_r=160)
        draw_shield(d, int(W * 0.70), H // 2,
                    70 + int(5 * math.sin(t * 1.8)), acc, 210)
        bg = glow_text(bg, "Adventure awaits.", W // 2, H // 2 - 25,
                       try_font(50), (220, 235, 255, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(5, 10, 25), (14, 28, 58)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=200)
        draw_shield(d, W // 2, H // 2 - 20, 82, acc, 220)
        bg = glow_text(bg, "VANGUARD", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Stream bold. Stream brave.", W // 2, H - 90,
                       try_font(36), (200, 220, 255, 220), glow_color=acc, glow_r=12)

    return bg


# ─────────────────────────────────────────────────────────────────────────────
# INTELLECTUAL_EXPLORER ads
# ─────────────────────────────────────────────────────────────────────────────

def curiosity_frame(fi, t):
    """CURIOSITY — science & nature platform. Teal; DNA helix object."""
    acc = (32, 184, 160)

    if t < 5.0:
        bg = gradient_bg([(0, 18, 20), (0, 45, 50), (0, 22, 28)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=28, seed=10, vy=-30, drift=15,
                  r_range=(1, 4), a_range=(0.20, 0.60))
        dna_phase = t * 1.8
        draw_dna_helix(d, W // 2, H // 2, 45, acc, 200, dna_phase)
        bg = scene_title(bg, "CURIOSITY", t, 0.9, acc, font_size=58)

    elif t < 10.0:
        bg = gradient_bg([(0, 25, 28), (0, 60, 65)])
        d = ImageDraw.Draw(bg)
        dna_phase = t * 1.8
        draw_dna_helix(d, int(W * 0.72), H // 2, 42, acc, 215, dna_phase)
        # Floating formula-like text
        for k, label in enumerate(["DNA", "RNA", "ATP", "CO₂"]):
            lx = int(W * (0.1 + k * 0.2))
            ly = int(H * (0.25 + 0.12 * math.sin(t * 0.8 + k)))
            d.text((lx, ly), label, font=try_font(22),
                   fill=(*acc, int(80 + 40 * math.sin(t + k))))
        bg = glow_text(bg, "Science, beautifully told.", W // 2, H // 2 - 20,
                       try_font(46), (200, 255, 250, 215), glow_color=acc, glow_r=15)

    else:
        bg = gradient_bg([(0, 15, 18), (0, 40, 45)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.5, n=3, max_r=195)
        draw_dna_helix(d, W // 2, H // 2 - 15, 48, acc, 210, t * 1.8)
        bg = glow_text(bg, "CURIOSITY", W // 2, H - 165, try_font(64),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Feed your wonder.", W // 2, H - 90, try_font(38),
                       (180, 255, 245, 220), glow_color=acc, glow_r=12)

    return bg


def horizon_frame(fi, t):
    """HORIZON — sci-fi & fantasy streaming. Deep violet; wormhole object."""
    acc = (144, 96, 224)

    if t < 5.0:
        bg = gradient_bg([(8, 0, 20), (22, 0, 55), (12, 0, 30)])
        d = ImageDraw.Draw(bg)
        # Star field
        rng = random.Random(99)
        for _ in range(120):
            sx = rng.randint(0, W)
            sy = rng.randint(0, H)
            sa = int(rng.uniform(0.3, 0.9) * 255)
            d.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(255, 255, 255, sa))
        wh_prog = ease_out(min(t / 3.0, 1.0))
        draw_wormhole(d, W // 2, H // 2, int(80 * wh_prog), acc,
                      int(200 * wh_prog))
        bg = scene_title(bg, "HORIZON", t, 0.8, acc, font_size=62)

    elif t < 10.0:
        bg = gradient_bg([(10, 0, 25), (28, 0, 70)])
        d = ImageDraw.Draw(bg)
        rng = random.Random(77)
        for _ in range(80):
            sx = rng.randint(0, W)
            sy = rng.randint(0, H)
            d.ellipse([sx - 1, sy - 1, sx + 1, sy + 1],
                      fill=(255, 255, 255, rng.randint(60, 180)))
        draw_wormhole(d, int(W * 0.70), H // 2,
                      75 + int(6 * math.sin(t * 1.5)), acc, 210)
        bg = glow_text(bg, "Beyond the known.", W // 2, H // 2 - 20,
                       try_font(50), (220, 200, 255, 215), glow_color=acc, glow_r=18)

    else:
        bg = gradient_bg([(6, 0, 16), (18, 0, 45)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=200)
        draw_wormhole(d, W // 2, H // 2 - 18, 85, acc, 215)
        bg = glow_text(bg, "HORIZON", W // 2, H - 165, try_font(68),
                       (255, 255, 255, 255), glow_color=acc, glow_r=24)
        bg = glow_text(bg, "Stream the universe.", W // 2, H - 90, try_font(38),
                       (210, 190, 255, 220), glow_color=acc, glow_r=12)

    return bg


def terra_frame(fi, t):
    """TERRA — nature & travel docs. Forest green; globe object."""
    acc = (80, 160, 80)

    if t < 5.0:
        bg = gradient_bg([(5, 20, 5), (15, 50, 18), (8, 30, 10)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=22, seed=20, vy=-25, drift=20,
                  r_range=(2, 5), a_range=(0.20, 0.55))
        gl_prog = ease_out(min(t / 3.5, 1.0))
        # Globe rotates
        rot_d = ImageDraw.Draw(bg)
        draw_globe(rot_d, W // 2, H // 2 - 10, int(68 * gl_prog), acc,
                   int(195 * gl_prog))
        bg = scene_title(bg, "TERRA", t, 1.0, acc, font_size=68)

    elif t < 10.0:
        bg = gradient_bg([(8, 28, 10), (20, 65, 22)])
        d = ImageDraw.Draw(bg)
        draw_globe(d, int(W * 0.68), H // 2, 65, acc, 210)
        bg = glow_text(bg, "Every landscape. Every story.", W // 2, H // 2 - 25,
                       try_font(44), (210, 245, 210, 215), glow_color=acc, glow_r=14)

    else:
        bg = gradient_bg([(5, 18, 6), (14, 42, 16)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.5, n=3, max_r=195)
        draw_globe(d, W // 2, H // 2 - 18, 72, acc, 210)
        bg = glow_text(bg, "TERRA", W // 2, H - 165, try_font(70),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Explore. Discover. Wonder.", W // 2, H - 90,
                       try_font(36), (195, 240, 195, 220), glow_color=acc, glow_r=12)

    return bg


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT_CHAMELEON ads
# ─────────────────────────────────────────────────────────────────────────────

def toonbox_frame(fi, t):
    """TOONBOX — animation streaming. Indigo; clapperboard object."""
    acc = (96, 64, 255)

    if t < 5.0:
        bg = gradient_bg([(10, 5, 35), (30, 15, 80), (15, 8, 45)])
        d = ImageDraw.Draw(bg)
        # Bouncing color blobs (cartoon feel)
        for k in range(5):
            bx = int(W * (0.15 + k * 0.18) + 20 * math.sin(t * 2 + k))
            by = int(H * 0.5 + 30 * math.cos(t * 1.5 + k * 0.7))
            blob_col = hsv_to_rgb((k / 5.0 + t * 0.05) % 1.0, 0.8, 0.9)
            d.ellipse([bx - 18, by - 18, bx + 18, by + 18],
                      fill=(*blob_col, 60))
        cb_prog = ease_back(min(t / 3.0, 1.0))
        draw_clapperboard(d, W // 2, H // 2, int(65 * cb_prog), acc,
                          int(210 * min(cb_prog, 1.0)))
        bg = scene_title(bg, "TOONBOX", t, 0.9, acc, font_size=62)

    elif t < 10.0:
        bg = gradient_bg([(14, 8, 45), (35, 18, 90)])
        d = ImageDraw.Draw(bg)
        for k in range(5):
            bx = int(W * (0.12 + k * 0.19) + 25 * math.sin(t * 1.8 + k))
            by = int(H * 0.6 + 35 * math.cos(t * 1.2 + k))
            blob_col = hsv_to_rgb((k / 5.0 + t * 0.05) % 1.0, 0.8, 0.9)
            d.ellipse([bx - 22, by - 22, bx + 22, by + 22],
                      fill=(*blob_col, 50))
        draw_clapperboard(d, int(W * 0.70), H // 2, 62, acc, 215)
        bg = glow_text(bg, "Animation for everyone.", W // 2, H // 2 - 25,
                       try_font(46), (220, 210, 255, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(8, 4, 28), (22, 10, 58)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.2, n=3, max_r=195)
        draw_clapperboard(d, W // 2, H // 2 - 18, 68, acc, 215)
        bg = glow_text(bg, "TOONBOX", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Animated worlds await.", W // 2, H - 90,
                       try_font(36), (200, 190, 255, 220), glow_color=acc, glow_r=12)

    return bg


def stagecraft_frame(fi, t):
    """STAGECRAFT — classic film & comedy. Gold; theater masks object."""
    acc = (212, 160, 32)

    if t < 5.0:
        bg = gradient_bg([(22, 14, 0), (55, 35, 0), (28, 18, 0)])
        d = ImageDraw.Draw(bg)
        # Stage curtain columns (vertical bands)
        for k in range(6):
            cx_c = int(W * k / 5)
            wave = int(12 * math.sin(t * 0.6 + k * 0.9))
            d.line([(cx_c + wave, 0), (cx_c + wave, H)],
                   fill=(*acc, 18), width=28)
        tm_prog = ease_out(min(t / 3.5, 1.0))
        draw_theater_masks(d, W // 2, H // 2 - 5, int(55 * tm_prog), acc,
                           int(205 * tm_prog))
        bg = scene_title(bg, "STAGECRAFT", t, 0.8, acc, font_size=56)

    elif t < 10.0:
        bg = gradient_bg([(28, 18, 0), (65, 42, 0)])
        d = ImageDraw.Draw(bg)
        for k in range(6):
            cx_c = int(W * k / 5)
            wave = int(10 * math.sin(t * 0.5 + k))
            d.line([(cx_c + wave, 0), (cx_c + wave, H)],
                   fill=(*acc, 14), width=22)
        draw_theater_masks(d, int(W * 0.70), H // 2, 52, acc, 210)
        bg = glow_text(bg, "Classics reimagined.", W // 2, H // 2 - 22,
                       try_font(48), (255, 245, 200, 215), glow_color=acc, glow_r=15)

    else:
        bg = gradient_bg([(18, 11, 0), (45, 28, 0)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=195)
        draw_theater_masks(d, W // 2, H // 2 - 15, 58, acc, 215)
        bg = glow_text(bg, "STAGECRAFT", W // 2, H - 165, try_font(60),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Every era. Every laugh.", W // 2, H - 90,
                       try_font(36), (255, 240, 190, 220), glow_color=acc, glow_r=12)

    return bg


def pantry_frame(fi, t):
    """PANTRY — grocery delivery. Fresh green; grocery bag object."""
    acc = (80, 192, 96)

    if t < 5.0:
        bg = gradient_bg([(8, 28, 10), (22, 70, 26), (12, 38, 14)])
        d = ImageDraw.Draw(bg)
        # Falling produce dots (colorful)
        rng = random.Random(fi + 500)
        for _ in range(18):
            px_p = rng.randint(0, W)
            py_p = int((rng.randint(0, H) + t * 40) % H)
            pc = hsv_to_rgb(rng.uniform(0.0, 0.4), 0.8, 0.9)
            d.ellipse([px_p - 8, py_p - 8, px_p + 8, py_p + 8],
                      fill=(*pc, 80))
        bag_prog = ease_back(min(t / 3.0, 1.0))
        draw_grocery_bag(d, W // 2, H // 2, int(60 * bag_prog), acc,
                         int(210 * min(bag_prog, 1.0)))
        bg = scene_title(bg, "PANTRY", t, 0.9, acc, font_size=66)

    elif t < 10.0:
        bg = gradient_bg([(10, 35, 12), (28, 85, 32)])
        d = ImageDraw.Draw(bg)
        rng = random.Random(fi + 600)
        for _ in range(14):
            px_p = rng.randint(0, W)
            py_p = int((rng.randint(0, H) + t * 35) % H)
            pc = hsv_to_rgb(rng.uniform(0.0, 0.35), 0.75, 0.9)
            d.ellipse([px_p - 7, py_p - 7, px_p + 7, py_p + 7],
                      fill=(*pc, 65))
        draw_grocery_bag(d, int(W * 0.68), H // 2, 58, acc, 215)
        bg = glow_text(bg, "Fresh, fast, doorstep.", W // 2, H // 2 - 22,
                       try_font(46), (220, 255, 220, 215), glow_color=acc, glow_r=14)

    else:
        bg = gradient_bg([(6, 20, 8), (18, 55, 20)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=195)
        draw_grocery_bag(d, W // 2, H // 2 - 18, 64, acc, 215)
        bg = glow_text(bg, "PANTRY", W // 2, H - 165, try_font(70),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Good food, delivered.", W // 2, H - 90,
                       try_font(38), (200, 255, 205, 220), glow_color=acc, glow_r=12)

    return bg


# ─────────────────────────────────────────────────────────────────────────────
# INVESTIGATIVE_VIEWER ads
# ─────────────────────────────────────────────────────────────────────────────

def nocturne_frame(fi, t):
    """NOCTURNE — noir streaming. Amber-brown; venetian blinds object."""
    acc = (184, 112, 32)

    if t < 5.0:
        bg = gradient_bg([(10, 7, 0), (28, 18, 4), (12, 8, 0)])
        d = ImageDraw.Draw(bg)
        # Soft amber spotlight from above-left
        for radius in range(220, 20, -40):
            a = int(18 * (1 - radius / 220))
            d.ellipse([80 - radius, -80 - radius, 80 + radius, -80 + radius],
                      fill=(*acc, a))
        tilt = 0.10 + 0.05 * math.sin(t * 0.5)
        draw_venetian_blinds(d, W // 2, H // 2, 80, acc, 200, tilt)
        bg = scene_title(bg, "NOCTURNE", t, 0.9, acc, font_size=60)

    elif t < 10.0:
        bg = gradient_bg([(14, 9, 0), (38, 24, 5)])
        d = ImageDraw.Draw(bg)
        tilt = 0.08 + 0.06 * math.sin(t * 0.7)
        draw_venetian_blinds(d, int(W * 0.65), H // 2, 70, acc, 210, tilt)
        # Floating cigarette smoke wisps
        particles(d, t, (180, 140, 80), count=12, seed=30, vy=-18, drift=8,
                  r_range=(3, 8), a_range=(0.08, 0.25))
        bg = glow_text(bg, "The city never sleeps.", W // 2, H // 2 - 22,
                       try_font(46), (240, 220, 180, 215), glow_color=acc, glow_r=15)

    else:
        bg = gradient_bg([(8, 5, 0), (22, 14, 2)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.5, n=3, max_r=190)
        draw_venetian_blinds(d, W // 2, H // 2 - 15, 75, acc, 205)
        bg = glow_text(bg, "NOCTURNE", W // 2, H - 165, try_font(64),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Classic noir. Remastered.", W // 2, H - 90,
                       try_font(36), (240, 210, 160, 220), glow_color=acc, glow_r=12)

    return bg


def deadlines_frame(fi, t):
    """DEADLINES — investigative journalism. Slate blue; typewriter object."""
    acc = (96, 128, 176)

    if t < 5.0:
        bg = gradient_bg([(8, 10, 18), (20, 26, 48), (10, 14, 26)])
        d = ImageDraw.Draw(bg)
        # Scrolling headline text (left side)
        headlines = ["BREAKING:", "SOURCES SAY:", "EXCLUSIVE:", "REPORT:"]
        for k, hl in enumerate(headlines):
            ly = int((H * 0.2 + k * 60 - t * 15) % H)
            d.text((30, ly), hl, font=try_font(20), fill=(*acc, 55))
        tw_prog = ease_out(min(t / 3.5, 1.0))
        draw_typewriter(d, W // 2, H // 2 - 10, int(60 * tw_prog), acc,
                        int(205 * tw_prog))
        bg = scene_title(bg, "DEADLINES", t, 0.8, acc, font_size=58)

    elif t < 10.0:
        bg = gradient_bg([(12, 15, 28), (30, 38, 70)])
        d = ImageDraw.Draw(bg)
        for k, hl in enumerate(["BREAKING:", "SOURCES SAY:", "EXCLUSIVE:"]):
            ly = int((H * 0.15 + k * 70 - t * 12) % H)
            d.text((30, ly), hl, font=try_font(18), fill=(*acc, 45))
        draw_typewriter(d, int(W * 0.70), H // 2, 58, acc, 210)
        bg = glow_text(bg, "The truth demands urgency.", W // 2, H // 2 - 22,
                       try_font(43), (210, 220, 240, 215), glow_color=acc, glow_r=15)

    else:
        bg = gradient_bg([(6, 8, 16), (16, 22, 42)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=192)
        draw_typewriter(d, W // 2, H // 2 - 18, 64, acc, 210)
        bg = glow_text(bg, "DEADLINES", W // 2, H - 165, try_font(62),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Journalism that matters.", W // 2, H - 90,
                       try_font(36), (195, 210, 235, 220), glow_color=acc, glow_r=12)

    return bg


def caseroom_frame(fi, t):
    """CASEROOM — true crime podcast. Crimson-dark; evidence board object."""
    acc = (144, 0, 24)

    if t < 5.0:
        bg = gradient_bg([(10, 4, 4), (28, 8, 8), (12, 5, 5)])
        d = ImageDraw.Draw(bg)
        # Static noise texture
        rng = random.Random(fi * 3131)
        for _ in range(800):
            nx = rng.randint(0, W)
            ny = rng.randint(0, H)
            d.point((nx, ny), fill=(255, 255, 255, rng.randint(2, 12)))
        eb_prog = ease_out(min(t / 3.0, 1.0))
        draw_evidence_board(d, W // 2, H // 2, int(75 * eb_prog), acc,
                            int(200 * eb_prog))
        bg = scene_title(bg, "CASEROOM", t, 0.9, acc, font_size=62)

    elif t < 10.0:
        bg = gradient_bg([(14, 6, 6), (36, 10, 10)])
        d = ImageDraw.Draw(bg)
        rng = random.Random(fi * 2477)
        for _ in range(500):
            nx = rng.randint(0, W)
            ny = rng.randint(0, H)
            d.point((nx, ny), fill=(255, 255, 255, rng.randint(2, 9)))
        draw_evidence_board(d, int(W * 0.68), H // 2, 72, acc, 210)
        bg = glow_text(bg, "Every case. Every clue.", W // 2, H // 2 - 22,
                       try_font(46), (240, 200, 200, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(8, 2, 2), (22, 6, 6)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=192)
        draw_evidence_board(d, W // 2, H // 2 - 18, 78, acc, 210)
        bg = glow_text(bg, "CASEROOM", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "True crime. True depth.", W // 2, H - 90,
                       try_font(36), (240, 190, 190, 220), glow_color=acc, glow_r=12)

    return bg


# ─────────────────────────────────────────────────────────────────────────────
# Ad registry
# ─────────────────────────────────────────────────────────────────────────────

ADS = [
    # (ad_id,                   frame_fn,          accent_rgb,     brand_char, category)
    ("ad_thrill_gravecrest",  gravecrest_frame,  (204,  0,  32), "G", "thrill_seeker"),
    ("ad_thrill_torque",      torque_frame,      (255, 85,   0), "T", "thrill_seeker"),
    ("ad_thrill_vanguard",    vanguard_frame,    ( 64,128, 192), "V", "thrill_seeker"),
    ("ad_intel_curiosity",    curiosity_frame,   ( 32,184, 160), "C", "intellectual_explorer"),
    ("ad_intel_horizon",      horizon_frame,     (144, 96, 224), "H", "intellectual_explorer"),
    ("ad_intel_terra",        terra_frame,       ( 80,160,  80), "T", "intellectual_explorer"),
    ("ad_chame_toonbox",      toonbox_frame,     ( 96, 64, 255), "T", "content_chameleon"),
    ("ad_chame_stagecraft",   stagecraft_frame,  (212,160,  32), "S", "content_chameleon"),
    ("ad_chame_pantry",       pantry_frame,      ( 80,192,  96), "P", "content_chameleon"),
    ("ad_invest_nocturne",    nocturne_frame,    (184,112,  32), "N", "investigative_viewer"),
    ("ad_invest_deadlines",   deadlines_frame,   ( 96,128, 176), "D", "investigative_viewer"),
    ("ad_invest_caseroom",    caseroom_frame,    (144,  0,  24), "C", "investigative_viewer"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser_args = sys.argv[1:]
    to_render = [ad_id for ad_id, *_ in ADS]
    if "--only" in parser_args:
        idx = parser_args.index("--only")
        to_render = parser_args[idx + 1:]

    os.makedirs(OUT_DIR, exist_ok=True)
    targets = {ad_id: (fn, acc, ch, cat) for ad_id, fn, acc, ch, cat in ADS}

    for ad_id in to_render:
        if ad_id not in targets:
            print(f"  unknown ad_id: {ad_id}, skipping")
            continue
        fn, acc, ch, cat = targets[ad_id]
        print(f"\n[{ad_id}]")
        render_and_encode(
            lambda fi, t, _fn=fn: _fn(fi, t),
            ad_id,
            accent=acc,
            brand_char=ch,
            category=cat,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
