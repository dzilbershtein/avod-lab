#!/usr/bin/env python3
"""
generate_ads_v3.py — Content-library-targeted synthetic ad set.

16 ads designed specifically for the AVOD-Lab content library, four per
viewer profile. Each advertises a product matching a topic the catalogue
actually contains, so the contextual relevance manipulation can fire for
every creative. Each ad has a product-specific drawn object, glow text, and
synthesized audio.

Viewer-profile → relevant ad pool
  thrill_seeker        → gravecrest (horror), vanguard (adventure),
                         apex (live sport), ranger (outdoor gear)
  intellectual_explorer → curiosity (science), horizon (sci-fi),
                         synapse (technology), renderlab (animation/VFX)
  content_chameleon    → toonbox (animation), stagecraft (classic film),
                         storybook (family musicals), tabletop (board games)
  investigative_viewer → nocturne (noir), deadlines (journalism),
                         caseroom (true crime), tribunal (courtroom)

Run:
    pip install Pillow
    python scripts/generate_ads_v3.py
    python scripts/generate_ads_v3.py --only ad_thrill_ranger ad_intel_horizon
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
# Gap-filling ads
#
# Each of these covers content the original 12 left without a well-matched
# relevant ad: sports (jackie_robinson), consumer technology (elephant_dream,
# tears_of_steel) and family/fantasy/music (pied_piper).
# ─────────────────────────────────────────────────────────────────────────────

def draw_compass(draw, cx, cy, r, col, alpha, phase=0.0):
    """Compass rose with a swinging needle — outdoor and adventure gear."""
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(*col, alpha), width=4)
    inner = int(r * 0.80)
    draw.ellipse([(cx - inner, cy - inner), (cx + inner, cy + inner)],
                 outline=(*col, int(alpha * 0.45)), width=2)
    for k in range(8):
        ang = math.pi * k / 4.0
        long_tick = (k % 2 == 0)
        r0 = int(r * (0.62 if long_tick else 0.74))
        draw.line([(cx + int(r0 * math.sin(ang)), cy - int(r0 * math.cos(ang))),
                   (cx + int(r * 0.92 * math.sin(ang)), cy - int(r * 0.92 * math.cos(ang)))],
                  fill=(*col, alpha if long_tick else int(alpha * 0.6)),
                  width=3 if long_tick else 2)
    na = math.radians(-32.0 + 14.0 * math.sin(phase * 1.3))
    tip, tail, half = int(r * 0.66), int(r * 0.46), int(r * 0.13)
    draw.polygon([(cx + int(tip * math.sin(na)), cy - int(tip * math.cos(na))),
                  (cx + int(half * math.cos(na)), cy + int(half * math.sin(na))),
                  (cx - int(half * math.cos(na)), cy - int(half * math.sin(na)))],
                 outline=(*col, alpha), width=3)
    draw.line([(cx, cy), (cx - int(tail * math.sin(na)), cy + int(tail * math.cos(na)))],
              fill=(*col, int(alpha * 0.7)), width=3)


def draw_wireframe_cube(draw, cx, cy, r, col, alpha, phase=0.0):
    """Rotating wireframe cube — 3D animation and VFX software."""
    if r <= 0:
        return  # first frames of the scale-in; nothing to draw yet
    s = r * 0.58
    a = phase * 0.6
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                x, y, z = sx * s, sy * s, sz * s
                xr = x * math.cos(a) - z * math.sin(a)
                zr = x * math.sin(a) + z * math.cos(a)
                yr = y * math.cos(0.42) - zr * math.sin(0.42)
                depth = zr * math.sin(0.42) + y * math.cos(0.42)
                k = 1.0 + depth / (r * 7.0)
                pts.append((cx + int(xr * k), cy + int(yr * k)))
    edges = [(0,1),(0,2),(0,4),(1,3),(1,5),(2,3),(2,6),(3,7),(4,5),(4,6),(5,7),(6,7)]
    for i, j in edges:
        draw.line([pts[i], pts[j]], fill=(*col, alpha), width=3)
    for p in pts:
        draw.ellipse([(p[0]-3, p[1]-3), (p[0]+3, p[1]+3)], outline=(*col, alpha), width=2)


def draw_dice(draw, cx, cy, r, col, alpha):
    """Two dice — family board games."""
    def die(ox, oy, side, pips):
        h = side // 2
        draw.rounded_rectangle([(ox - h, oy - h), (ox + h, oy + h)],
                               radius=max(4, side // 7), outline=(*col, alpha), width=4)
        step, pr = side // 4, max(3, side // 14)
        grid = {1: [(0,0)], 2: [(-1,-1),(1,1)], 3: [(-1,-1),(0,0),(1,1)],
                5: [(-1,-1),(1,-1),(0,0),(-1,1),(1,1)]}
        for gx, gy in grid[pips]:
            px, py = ox + gx * step, oy + gy * step
            draw.ellipse([(px-pr, py-pr), (px+pr, py+pr)], fill=(*col, alpha))
    big = int(r * 0.62)
    die(cx - int(r * 0.34), cy + int(r * 0.10), big, 5)
    die(cx + int(r * 0.40), cy - int(r * 0.26), int(big * 0.78), 3)

def draw_track_lanes(draw, cx, cy, r, col, alpha):
    """Concentric stadium ovals — running track, for live sport."""
    for i, scale in enumerate((1.0, 0.72, 0.44)):
        rx, ry = int(r * scale), int(r * scale * 0.56)
        a = int(alpha * (1.0 - i * 0.18))
        draw.rounded_rectangle(
            [(cx - rx, cy - ry), (cx + rx, cy + ry)],
            radius=ry, outline=(*col, a), width=4,
        )


def draw_microchip(draw, cx, cy, r, col, alpha):
    """Square die with pin rows and inner traces — consumer technology."""
    half = int(r * 0.62)
    draw.rounded_rectangle(
        [(cx - half, cy - half), (cx + half, cy + half)],
        radius=8, outline=(*col, alpha), width=4,
    )
    inner = int(half * 0.45)
    draw.rounded_rectangle(
        [(cx - inner, cy - inner), (cx + inner, cy + inner)],
        radius=4, outline=(*col, int(alpha * 0.8)), width=3,
    )
    pin, gap = int(r * 0.22), half // 2
    for k in (-1, 0, 1):
        off = k * gap
        draw.line([(cx + off, cy - half), (cx + off, cy - half - pin)],
                  fill=(*col, alpha), width=3)
        draw.line([(cx + off, cy + half), (cx + off, cy + half + pin)],
                  fill=(*col, alpha), width=3)
        draw.line([(cx - half, cy + off), (cx - half - pin, cy + off)],
                  fill=(*col, alpha), width=3)
        draw.line([(cx + half, cy + off), (cx + half + pin, cy + off)],
                  fill=(*col, alpha), width=3)


def draw_open_book(draw, cx, cy, r, col, alpha, sparkle_phase=0.0):
    """Open book with sparkles — family storytelling, fantasy and musicals."""
    w, h = int(r * 0.92), int(r * 0.60)
    for side in (-1, 1):
        ox = cx + side * w
        draw.polygon([(cx, cy - int(h * 0.45)), (ox, cy - int(h * 0.12)),
                      (ox, cy + int(h * 0.72)), (cx, cy + int(h * 0.45))],
                     outline=(*col, alpha), width=4)
        # Ruled lines read as text and stop the pages looking like wings.
        for k in (1, 2, 3):
            f = k / 4.0
            y0 = cy - int(h * 0.45) + int(h * 0.90 * f)
            y1 = cy - int(h * 0.12) + int(h * 0.84 * f)
            draw.line([(cx + side * int(w * 0.18), y0 + int(h * 0.06)),
                       (cx + side * int(w * 0.82), y1 + int(h * 0.06))],
                      fill=(*col, int(alpha * 0.55)), width=2)
    draw.line([(cx, cy - int(h * 0.45)), (cx, cy + int(h * 0.45))],
              fill=(*col, alpha), width=4)
    for i, (sx, sy, sr) in enumerate((
        (cx - int(w * 0.45), cy - int(h * 1.15), 7),
        (cx + int(w * 0.40), cy - int(h * 1.35), 9),
        (cx + int(w * 0.80), cy - int(h * 0.55), 6),
    )):
        tw = 0.55 + 0.45 * math.sin(sparkle_phase * 2.2 + i * 1.7)
        a = int(alpha * tw)
        draw.line([(sx - sr, sy), (sx + sr, sy)], fill=(*col, a), width=3)
        draw.line([(sx, sy - sr), (sx, sy + sr)], fill=(*col, a), width=3)


def draw_gavel(draw, cx, cy, r, col, alpha):
    """Gavel resting on its sound block — courtroom and legal drama."""
    if r <= 0:
        return
    # Mallet head, tilted, sitting up and left of centre.
    hw, hh = int(r * 0.86), int(r * 0.40)
    hx, hy = cx - int(r * 0.30), cy - int(r * 0.42)
    draw.rounded_rectangle([(hx - hw // 2, hy - hh // 2), (hx + hw // 2, hy + hh // 2)],
                           radius=hh // 3, outline=(*col, alpha), width=4)
    # Banded ends, so it reads as a mallet rather than a plain box.
    for sx in (-1, 1):
        bx = hx + sx * int(hw * 0.30)
        draw.line([(bx, hy - hh // 2), (bx, hy + hh // 2)],
                  fill=(*col, int(alpha * 0.75)), width=3)
    # Handle angling down to the right, with a collar where it meets the head.
    x0, y0 = hx + int(hw * 0.10), hy + hh // 2
    x1, y1 = cx + int(r * 0.62), cy + int(r * 0.30)
    draw.line([(x0, y0), (x1, y1)], fill=(*col, alpha), width=7)
    draw.line([(x0 - 7, y0 - 2), (x0 + 11, y0 + 8)], fill=(*col, alpha), width=4)
    draw.ellipse([(x1 - 7, y1 - 7), (x1 + 7, y1 + 7)], outline=(*col, alpha), width=4)
    # Sound block.
    bw, bh = int(r * 1.10), int(r * 0.22)
    by = cy + int(r * 0.66)
    draw.rounded_rectangle([(cx - bw // 2, by), (cx + bw // 2, by + bh)],
                           radius=bh // 2, outline=(*col, alpha), width=4)
    draw.line([(cx - int(bw * 0.34), by + bh // 2), (cx + int(bw * 0.34), by + bh // 2)],
              fill=(*col, int(alpha * 0.45)), width=2)


def tribunal_frame(fi, t):
    """TRIBUNAL — courtroom & legal drama. Deep amber; gavel object."""
    acc = (214, 150, 70)

    if t < 5.0:
        bg = gradient_bg([(14, 9, 2), (34, 22, 6), (16, 10, 3)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=26, seed=29, vy=-34, drift=16,
                  r_range=(2, 5), a_range=(0.22, 0.62))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_gavel(d, W // 2, H // 2 - 10, int(118 * prog), acc,
                   int(205 * min(prog, 1.0)))
        bg = scene_title(bg, "TRIBUNAL", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(18, 11, 3), (40, 26, 8)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=2.1, n=2, max_r=158)
        draw_gavel(d, int(W * 0.70), H // 2,
                   110 + int(6 * math.sin(t * 1.5)), acc, 210)
        bg = glow_text(bg, "Every case has two sides.", W // 2, H // 2 - 25,
                       try_font(46), (248, 232, 206, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(14, 9, 2), (36, 23, 7)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.5, n=3, max_r=198)
        draw_gavel(d, W // 2, H // 2 - 20, 124, acc, 220)
        bg = glow_text(bg, "TRIBUNAL", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Courtroom drama, every week.", W // 2, H - 90,
                       try_font(36), (240, 220, 190, 220), glow_color=acc, glow_r=12)

    return bg


def ranger_frame(fi, t):
    """RANGER — outdoor adventure gear. Vivid orange; compass object."""
    acc = (235, 110, 45)

    if t < 5.0:
        bg = gradient_bg([(18, 8, 2), (42, 20, 6), (20, 10, 3)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=30, seed=31, vy=-44, drift=24,
                  r_range=(2, 5), a_range=(0.25, 0.68))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_compass(d, W // 2, H // 2 - 10, int(112 * prog), acc,
                     int(205 * min(prog, 1.0)), phase=t)
        bg = scene_title(bg, "RANGER", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(22, 10, 4), (50, 24, 8)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.9, n=2, max_r=160)
        draw_compass(d, int(W * 0.70), H // 2,
                     104 + int(6 * math.sin(t * 1.6)), acc, 210, phase=t)
        bg = glow_text(bg, "Made for out there.", W // 2, H // 2 - 25,
                       try_font(50), (255, 232, 212, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(18, 8, 3), (46, 22, 7)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=200)
        draw_compass(d, W // 2, H // 2 - 20, 118, acc, 220, phase=t)
        bg = glow_text(bg, "RANGER", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Gear for the wild places.", W // 2, H - 90,
                       try_font(36), (255, 220, 198, 220), glow_color=acc, glow_r=12)

    return bg


def renderlab_frame(fi, t):
    """RENDERLAB — 3D animation & VFX software. Spring green; wireframe cube."""
    acc = (110, 225, 140)

    if t < 5.0:
        bg = gradient_bg([(3, 16, 9), (8, 38, 22), (4, 20, 12)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=28, seed=37, vy=-40, drift=18,
                  r_range=(2, 5), a_range=(0.25, 0.66))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_wireframe_cube(d, W // 2, H // 2 - 10, int(116 * prog), acc,
                            int(205 * min(prog, 1.0)), phase=t)
        bg = scene_title(bg, "RENDERLAB", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(5, 22, 13), (10, 46, 27)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.8, n=2, max_r=160)
        draw_wireframe_cube(d, int(W * 0.70), H // 2,
                            108 + int(6 * math.sin(t * 1.5)), acc, 210, phase=t)
        bg = glow_text(bg, "Build worlds, frame by frame.", W // 2, H // 2 - 25,
                       try_font(44), (220, 255, 232, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(3, 18, 10), (9, 42, 25)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=200)
        draw_wireframe_cube(d, W // 2, H // 2 - 20, 122, acc, 220, phase=t)
        bg = glow_text(bg, "RENDERLAB", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Animation studio, on your desk.", W // 2, H - 90,
                       try_font(36), (205, 250, 220, 220), glow_color=acc, glow_r=12)

    return bg


def tabletop_frame(fi, t):
    """TABLETOP — family board games. Coral; dice object."""
    acc = (255, 100, 100)

    if t < 5.0:
        bg = gradient_bg([(20, 6, 6), (46, 16, 16), (22, 8, 8)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=30, seed=41, vy=-36, drift=26,
                  r_range=(2, 6), a_range=(0.25, 0.70))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_dice(d, W // 2, H // 2 - 10, int(118 * prog), acc,
                  int(205 * min(prog, 1.0)))
        bg = scene_title(bg, "TABLETOP", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(26, 8, 8), (56, 20, 20)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.7, n=2, max_r=162)
        draw_dice(d, int(W * 0.70), H // 2,
                  110 + int(7 * math.sin(t * 1.7)), acc, 210)
        bg = glow_text(bg, "Everyone round the table.", W // 2, H // 2 - 25,
                       try_font(46), (255, 226, 226, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(20, 6, 6), (50, 18, 18)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=200)
        draw_dice(d, W // 2, H // 2 - 20, 124, acc, 220)
        bg = glow_text(bg, "TABLETOP", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Game night, sorted.", W // 2, H - 90,
                       try_font(36), (255, 215, 215, 220), glow_color=acc, glow_r=12)

    return bg

def apex_frame(fi, t):
    """APEX — live sports streaming. Turf lime; running-track object."""
    acc = (150, 205, 50)

    if t < 5.0:
        bg = gradient_bg([(6, 14, 4), (16, 38, 10), (8, 20, 6)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=34, seed=13, vy=-62, drift=26,
                  r_range=(2, 5), a_range=(0.25, 0.70))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_track_lanes(d, W // 2, H // 2 - 10, int(120 * prog), acc,
                         int(205 * min(prog, 1.0)))
        bg = scene_title(bg, "APEX", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(10, 22, 6), (22, 48, 14)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.7, n=2, max_r=165)
        draw_track_lanes(d, int(W * 0.70), H // 2,
                         112 + int(7 * math.sin(t * 2.1)), acc, 210)
        bg = glow_text(bg, "Every match. Live.", W // 2, H // 2 - 25,
                       try_font(50), (235, 250, 215, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(6, 16, 4), (18, 40, 12)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.2, n=3, max_r=205)
        draw_track_lanes(d, W // 2, H // 2 - 20, 126, acc, 220)
        bg = glow_text(bg, "APEX", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Every match. Every moment.", W // 2, H - 90,
                       try_font(36), (225, 245, 200, 220), glow_color=acc, glow_r=12)

    return bg


def synapse_frame(fi, t):
    """SYNAPSE — consumer technology. Cyan; microchip object."""
    acc = (0, 205, 255)

    if t < 5.0:
        bg = gradient_bg([(2, 10, 18), (6, 26, 44), (3, 14, 26)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=30, seed=17, vy=-46, drift=18,
                  r_range=(2, 5), a_range=(0.25, 0.68))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_microchip(d, W // 2, H // 2 - 10, int(118 * prog), acc,
                       int(205 * min(prog, 1.0)))
        bg = scene_title(bg, "SYNAPSE", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(4, 16, 28), (8, 34, 56)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.9, n=2, max_r=160)
        draw_microchip(d, int(W * 0.70), H // 2,
                       110 + int(6 * math.sin(t * 1.7)), acc, 210)
        bg = glow_text(bg, "Think faster.", W // 2, H // 2 - 25,
                       try_font(50), (215, 240, 255, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(2, 12, 22), (6, 30, 50)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=200)
        draw_microchip(d, W // 2, H // 2 - 20, 124, acc, 220)
        bg = glow_text(bg, "SYNAPSE", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Technology that keeps up.", W // 2, H - 90,
                       try_font(36), (200, 235, 255, 220), glow_color=acc, glow_r=12)

    return bg


def storybook_frame(fi, t):
    """STORYBOOK — family musicals & live shows. Warm pink; open-book object."""
    acc = (255, 120, 170)

    if t < 5.0:
        bg = gradient_bg([(20, 6, 14), (46, 14, 32), (24, 8, 18)])
        d = ImageDraw.Draw(bg)
        particles(d, t, acc, count=32, seed=23, vy=-38, drift=28,
                  r_range=(2, 6), a_range=(0.25, 0.70))
        prog = ease_back(min(t / 3.0, 1.0))
        draw_open_book(d, W // 2, H // 2 - 10, int(120 * prog), acc,
                       int(205 * min(prog, 1.0)), sparkle_phase=t)
        bg = scene_title(bg, "STORYBOOK", t, 1.0, acc)

    elif t < 10.0:
        bg = gradient_bg([(26, 8, 18), (56, 18, 40)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 4, H // 2, t, acc, period=1.8, n=2, max_r=162)
        draw_open_book(d, int(W * 0.70), H // 2,
                       112 + int(7 * math.sin(t * 1.6)), acc, 210, sparkle_phase=t)
        bg = glow_text(bg, "Where stories sing.", W // 2, H // 2 - 25,
                       try_font(50), (255, 230, 240, 215), glow_color=acc, glow_r=16)

    else:
        bg = gradient_bg([(20, 6, 16), (50, 16, 36)])
        d = ImageDraw.Draw(bg)
        pulse_rings(d, W // 2, H // 2, t, acc, period=1.4, n=3, max_r=200)
        draw_open_book(d, W // 2, H // 2 - 20, 126, acc, 220, sparkle_phase=t)
        bg = glow_text(bg, "STORYBOOK", W // 2, H - 165, try_font(66),
                       (255, 255, 255, 255), glow_color=acc, glow_r=22)
        bg = glow_text(bg, "Family tales, live on stage.", W // 2, H - 90,
                       try_font(36), (255, 220, 235, 220), glow_color=acc, glow_r=12)

    return bg


# ─────────────────────────────────────────────────────────────────────────────
# Ad registry
# ─────────────────────────────────────────────────────────────────────────────

ADS = [
    # (ad_id,                   frame_fn,          accent_rgb,     brand_char, category)
    ("ad_thrill_gravecrest",  gravecrest_frame,  (204,  0,  32), "G", "thrill_seeker"),
    ("ad_thrill_ranger",      ranger_frame,      (235,110,  45), "R", "thrill_seeker"),
    ("ad_thrill_vanguard",    vanguard_frame,    ( 64,128, 192), "V", "thrill_seeker"),
    ("ad_thrill_apex",        apex_frame,        (150,205,  50), "A", "thrill_seeker"),
    ("ad_intel_curiosity",    curiosity_frame,   ( 32,184, 160), "C", "intellectual_explorer"),
    ("ad_intel_horizon",      horizon_frame,     (144, 96, 224), "H", "intellectual_explorer"),
    ("ad_intel_renderlab",    renderlab_frame,   (110,225, 140), "R", "intellectual_explorer"),
    ("ad_intel_synapse",      synapse_frame,     (  0,205, 255), "S", "intellectual_explorer"),
    ("ad_chame_toonbox",      toonbox_frame,     ( 96, 64, 255), "T", "content_chameleon"),
    ("ad_chame_stagecraft",   stagecraft_frame,  (212,160,  32), "S", "content_chameleon"),
    ("ad_chame_tabletop",     tabletop_frame,    (255,100, 100), "T", "content_chameleon"),
    ("ad_chame_storybook",    storybook_frame,   (255,120, 170), "S", "content_chameleon"),
    ("ad_invest_nocturne",    nocturne_frame,    (184,112,  32), "N", "investigative_viewer"),
    ("ad_invest_deadlines",   deadlines_frame,   ( 96,128, 176), "D", "investigative_viewer"),
    ("ad_invest_caseroom",    caseroom_frame,    (144,  0,  24), "C", "investigative_viewer"),
    ("ad_invest_tribunal",    tribunal_frame,    (214,150,  70), "T", "investigative_viewer"),
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
