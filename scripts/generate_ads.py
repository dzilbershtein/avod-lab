#!/usr/bin/env python3
"""
generate_ads.py — render synthetic 30-second ad MP4s via Pillow + ffmpeg.

Four ads, structured as 3-scene TV commercials (1280×720, 30 s, 20 fps):

  Relevant to entertainment content:
    ad_relevant_screentime  — SCREENTIME streaming service
    ad_relevant_arcademax   — ARCADEMAX gaming platform

  Irrelevant to entertainment content:
    ad_irrelevant_crunchpop — CRUNCHPOP breakfast cereal
    ad_irrelevant_homesafe  — HOMESAFE home insurance

Visual features per ad:
  SCREENTIME  — floating content tiles, TV scan-line sweep, shimmer on brand text,
                pulse rings, star particles
  ARCADEMAX   — RGB cycling border, pixel burst explosion, score counter 0→9999,
                glitch text effect, energy streaks, pulsing glow
  CRUNCHPOP   — spinning sunburst, bouncing cereal puffs (parabolic physics),
                milk splash rings, brand bounce-in with overshoot ease
  HOMESAFE    — falling rain, sonar pulse rings, shield animation, orbiting sparks

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
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
FPS = 20
DURATION = 30
TOTAL_FRAMES = FPS * DURATION
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "ads")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

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
    """Cubic ease-out with overshoot (settle back)."""
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
    r, g, b = [(v, _t, p), (q, v, p), (p, v, _t), (p, q, v), (_t, p, v), (v, p, q)][i % 6]
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
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), text, font=font, fill=fill)


def gradient_bg(colors, w=W, h=H):
    img = Image.new("RGBA", (w, h))
    px = img.load()
    n = len(colors) - 1
    for y in range(h):
        t = y / (h - 1)
        seg = min(int(t * n), n - 1)
        lt = t * n - seg
        c0 = colors[seg]
        c1 = colors[seg + 1]
        r = clamp(lerp(c0[0], c1[0], lt))
        g = clamp(lerp(c0[1], c1[1], lt))
        b = clamp(lerp(c0[2], c1[2], lt))
        for x in range(w):
            px[x, y] = (r, g, b, 255)
    return img


def scene_flash(base, intensity=0.85):
    """White flash overlay for scene cuts."""
    overlay = Image.new("RGBA", base.size, (255, 255, 255, int(255 * intensity)))
    return Image.alpha_composite(base, overlay)


def particles(draw, t, acc, count=35, seed=0, vy=-55, drift=25, r_range=(2, 7), a_range=(0.3, 0.85)):
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
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*acc, a), width=2)


def render_and_encode(frames_fn, ad_id):
    tmp = tempfile.mkdtemp(prefix=f"ad_{ad_id}_")
    try:
        print(f"  rendering {TOTAL_FRAMES} frames …")
        for fi in range(TOTAL_FRAMES):
            t = fi / FPS
            img = frames_fn(fi, t)
            img.convert("RGB").save(os.path.join(tmp, f"f{fi:04d}.png"))
        out_path = os.path.join(OUT_DIR, f"{ad_id}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", os.path.join(tmp, "f%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "22",
            "-movflags", "+faststart",
            out_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  → {out_path}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# SCREENTIME — streaming service  (blues/purples)
# ---------------------------------------------------------------------------

def screentime_frame(fi, t):
    acc = (80, 160, 255)
    bg = gradient_bg([(5, 10, 40), (20, 30, 80), (5, 10, 40)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene boundaries
    if t < 0.15:
        flash_alpha = int(255 * (1 - t / 0.15))
        fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
        bg = Image.alpha_composite(bg, fl)

    # Scene 1 (0–10s): floating content tiles + pulse rings
    if t < 10:
        pulse_rings(draw, W // 2, H // 2, t, acc)
        particles(draw, t, acc, count=40, seed=1, vy=-40, drift=30)
        tile_positions = [(200, 200), (640, 150), (1050, 220), (320, 420), (900, 380)]
        tile_sizes = [(220, 130), (200, 120), (180, 110), (200, 115), (210, 120)]
        for i, ((tx, ty), (tw, th)) in enumerate(zip(tile_positions, tile_sizes)):
            float_y = ty + int(12 * math.sin(t * 1.1 + i * 1.3))
            alpha = clamp(ease_out(t / 2.0 - i * 0.15) * 200)
            tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            td = ImageDraw.Draw(tile)
            td.rounded_rectangle([0, 0, tw - 1, th - 1], radius=12,
                                  fill=(20, 40, 100, alpha), outline=(*acc, alpha // 2), width=2)
            ov.alpha_composite(tile, (tx - tw // 2, float_y - th // 2))

    # Scene 2 (10–22s): brand name + tagline + scan-line sweep
    elif t < 22:
        pulse_rings(draw, W // 2, H // 2, t, acc)
        particles(draw, t, acc, count=25, seed=2, vy=-35)
        # scan-line sweep
        sweep_x = int(((t - 10) / 12.0) * W * 1.8 - W * 0.4)
        for sx in range(max(0, sweep_x - 60), min(W, sweep_x)):
            a = int(40 * (1 - abs(sx - sweep_x) / 60))
            draw.line([(sx, 0), (sx, H)], fill=(200, 220, 255, a))
        # shimmer on brand text (done via alpha pulse)
        fn_large = try_font(120)
        fn_med = try_font(52)
        slide = ease_out(min((t - 10) / 1.5, 1.0))
        by = int(lerp(H, H // 2 - 60, slide))
        shimmer_a = clamp(200 + 55 * math.sin(t * 4))
        text_center(draw, "SCREENTIME", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 11.5) / 1.2, 1.0)) * 220)
        text_center(draw, "Stream Everything.", W // 2, by + 90, fn_med, (200, 220, 255, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        particles(draw, t, acc, count=20, seed=3, vy=-30)
        if t < 22.15:
            flash_alpha = int(200 * (1 - (t - 22) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)
        fn_large = try_font(120)
        fn_med = try_font(52)
        fn_cta = try_font(44)
        text_center(draw, "SCREENTIME", W // 2, H // 2 - 80, fn_large, (*acc, 230))
        text_center(draw, "Stream Everything.", W // 2, H // 2 + 10, fn_med, (200, 220, 255, 200))
        cta_a = clamp(ease_out(min((t - 23) / 1.0, 1.0)) * 240)
        cta_h = 70
        cta_y = H - 110
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "TRY FREE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# ARCADEMAX — gaming platform  (dark/neon green-yellow)
# ---------------------------------------------------------------------------

def arcademax_frame(fi, t):
    acc = (50, 255, 120)
    bg = gradient_bg([(5, 5, 20), (10, 20, 10), (5, 5, 20)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # RGB cycling border
    hue = (t * 0.12) % 1.0
    br, bg_c, bb = hsv_to_rgb(hue, 1.0, 1.0)
    border_w = 8
    for bw in range(border_w):
        a = clamp(200 - bw * 18)
        draw.rectangle([bw, bw, W - 1 - bw, H - 1 - bw], outline=(br, bg_c, bb, a))

    # Scene 1 (0–10s): pixel burst + score counter
    if t < 10:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Pixel burst from center
        burst_rng = random.Random(42)
        n_pixels = int(min(t / 10 * 300 + 40, 300))
        for _ in range(n_pixels):
            angle = burst_rng.uniform(0, 2 * math.pi)
            speed = burst_rng.uniform(20, 260)
            px = W // 2 + int(math.cos(angle) * speed * t * 0.8)
            py = H // 2 + int(math.sin(angle) * speed * t * 0.8)
            sz = burst_rng.randint(2, 8)
            col_h = burst_rng.uniform(0, 1)
            pr, pg, pb = hsv_to_rgb(col_h, 1.0, 1.0)
            a = clamp((1 - t / 10) * 255)
            if 0 <= px < W and 0 <= py < H:
                draw.rectangle([px, py, px + sz, py + sz], fill=(pr, pg, pb, a))

        # Score counter
        score = int(ease_out(min(t / 8, 1.0)) * 9999)
        fn_score = try_font(90)
        text_center(draw, f"{score:04d}", W // 2, H // 2 + 80, fn_score, (*acc, 220))
        fn_pts = try_font(36)
        text_center(draw, "POINTS", W // 2, H // 2 + 160, fn_pts, (200, 255, 200, 180))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.4, max_r=260)

    # Scene 2 (10–22s): brand name with glitch effect + energy streaks
    elif t < 22:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.4, max_r=260)
        particles(draw, t, acc, count=30, seed=10, vy=-50, drift=20)

        # Energy streaks
        streak_rng = random.Random(99)
        for _ in range(8):
            sx = streak_rng.randint(0, W)
            sy = streak_rng.randint(0, H)
            ex = sx + streak_rng.randint(-200, 200)
            ey = sy + streak_rng.randint(-100, 100)
            phase = (t * 2.3 + streak_rng.random() * 6) % 2
            a = clamp(int((1 - abs(phase - 1)) * 180))
            draw.line([(sx, sy), (ex, ey)], fill=(*acc, a), width=2)

        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 10) / 1.2, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))

        # Glitch layers: R and B offset slightly
        glitch = 0.06 < ((t * 7) % 1.0) < 0.12
        off = 6 if glitch else 0
        text_center(draw, "ARCADEMAX", W // 2 - off, by, fn_large, (255, 50, 50, 60 if glitch else 0))
        text_center(draw, "ARCADEMAX", W // 2 + off, by, fn_large, (50, 50, 255, 60 if glitch else 0))
        text_center(draw, "ARCADEMAX", W // 2, by, fn_large, (*acc, 240))
        tag_a = clamp(ease_out(min((t - 11.5) / 1.2, 1.0)) * 220)
        text_center(draw, "LEVEL UP YOUR GAME", W // 2, by + 100, fn_med, (180, 255, 180, tag_a))

    # Scene 3 (22–30s): CTA + pulsing glow
    else:
        if t < 22.15:
            flash_alpha = int(200 * (1 - (t - 22) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=20, seed=11, vy=-45)
        pulse_rings(draw, W // 2, H - 100, t, acc, period=1.2, max_r=150)

        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        glow_a = clamp(180 + 75 * math.sin(t * 5))
        text_center(draw, "ARCADEMAX", W // 2, H // 2 - 90, fn_large, (*acc, glow_a))
        text_center(draw, "LEVEL UP YOUR GAME", W // 2, H // 2 + 10, fn_med, (180, 255, 180, 200))
        cta_a = clamp(ease_out(min((t - 23) / 1.0, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=36, fill=(*acc, cta_a))
        text_center(draw, "PLAY FREE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# CRUNCHPOP — breakfast cereal  (warm orange/yellow)
# ---------------------------------------------------------------------------

def crunchpop_frame(fi, t):
    acc = (255, 180, 30)
    bg = gradient_bg([(255, 120, 10), (255, 200, 50), (255, 120, 10)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): spinning sunburst + bouncing puffs
    if t < 10:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Spinning sunburst
        n_rays = 24
        for i in range(n_rays):
            angle = 2 * math.pi * i / n_rays + t * 1.5
            r_inner = 80
            r_outer = 280 + 20 * math.sin(t * 3 + i)
            x0 = W // 2 + int(math.cos(angle) * r_inner)
            y0 = H // 2 + int(math.sin(angle) * r_inner)
            x1 = W // 2 + int(math.cos(angle) * r_outer)
            y1 = H // 2 + int(math.sin(angle) * r_outer)
            a = clamp(80 + 30 * math.sin(i + t * 2))
            draw.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, a), width=3)

        # Bouncing cereal puffs (parabolic physics)
        puff_rng = random.Random(77)
        for i in range(12):
            x0 = puff_rng.uniform(100, W - 100)
            vy0 = puff_rng.uniform(-300, -150)
            delay = puff_rng.uniform(0, 6)
            local_t = max(0, t - delay)
            if local_t > 0:
                g = 400
                x = x0 + puff_rng.uniform(-20, 20) * local_t
                y = H - 80 + vy0 * local_t + 0.5 * g * local_t ** 2
                # bounce
                bounce_floor = H - 80
                while y > bounce_floor and local_t > 0:
                    local_t *= 0.6
                    y = H - 80 + vy0 * local_t + 0.5 * g * local_t ** 2
                sz = puff_rng.randint(18, 38)
                a = clamp(200 - local_t * 20)
                if 0 <= x <= W and -50 <= y <= H + 50:
                    draw.ellipse([x - sz, y - sz, x + sz, y + sz],
                                 fill=(255, 220, 100, a), outline=(200, 100, 0, a), width=3)

        # Milk splash rings
        splash_rng = random.Random(55)
        for i in range(3):
            cx = splash_rng.randint(200, W - 200)
            cy = H - 60
            phase = (t * 0.8 + i * 0.6) % 1.8
            r = int(phase * 120)
            a = clamp(int((1 - phase / 1.8) * 180))
            if a > 0:
                draw.ellipse([cx - r, cy - r // 3, cx + r, cy + r // 3],
                             outline=(255, 255, 255, a), width=3)

    # Scene 2 (10–22s): brand name bounce-in + tagline
    elif t < 22:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Continued sunburst (slower)
        for i in range(16):
            angle = 2 * math.pi * i / 16 + t * 0.6
            r_outer = 320
            x0 = W // 2 + int(math.cos(angle) * 60)
            y0 = H // 2 + int(math.sin(angle) * 60)
            x1 = W // 2 + int(math.cos(angle) * r_outer)
            y1 = H // 2 + int(math.sin(angle) * r_outer)
            draw.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 50), width=2)

        fn_large = try_font(130)
        fn_med = try_font(54)
        bounce_t = min((t - 10) / 1.0, 1.0)
        by = int(lerp(H + 100, H // 2 - 70, ease_back(bounce_t)))
        text_center(draw, "CRUNCHPOP", W // 2, by, fn_large, (60, 20, 0, 240))
        tag_a = clamp(ease_out(min((t - 11.5) / 1.0, 1.0)) * 230)
        text_center(draw, "The Morning Crunch!", W // 2, by + 100, fn_med, (80, 30, 0, tag_a))

        particles(draw, t, acc, count=20, seed=7, vy=-30, r_range=(3, 9))

    # Scene 3 (22–30s): CTA
    else:
        if t < 22.15:
            flash_alpha = int(200 * (1 - (t - 22) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        fn_large = try_font(130)
        fn_med = try_font(54)
        fn_cta = try_font(46)
        text_center(draw, "CRUNCHPOP", W // 2, H // 2 - 80, fn_large, (60, 20, 0, 240))
        text_center(draw, "The Morning Crunch!", W // 2, H // 2 + 20, fn_med, (80, 30, 0, 220))
        particles(draw, t, acc, count=15, seed=8, vy=-25)
        cta_a = clamp(ease_out(min((t - 23) / 1.0, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=36, fill=(60, 20, 0, cta_a))
        text_center(draw, "FIND IN STORES", W // 2, cta_y + cta_h // 2, fn_cta, (255, 220, 50, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# HOMESAFE — home insurance  (deep blue/teal)
# ---------------------------------------------------------------------------

def _ctrl(d, cx, cy, c):
    w2, h2 = 70, 50
    d.rounded_rectangle([cx - w2, cy - h2, cx + w2, cy + h2], radius=12, outline=c, width=4)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=c, width=4)
    for side in [-1, 1]:
        gx0 = min(cx + side * w2 // 4, cx + side * (w2 // 2 + 15))
        gx1 = max(cx + side * w2 // 4, cx + side * (w2 // 2 + 15))
        d.rounded_rectangle([gx0, cy - h2 + 8, gx1, cy + h2 - 8], radius=15, outline=c, width=4)


def homesafe_frame(fi, t):
    acc = (60, 200, 220)
    bg = gradient_bg([(5, 20, 50), (10, 60, 80), (5, 20, 50)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): falling rain + sonar pulse rings
    if t < 10:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Falling rain (angled lines)
        rain_rng = random.Random(33)
        for _ in range(80):
            rx = rain_rng.uniform(0, W + 200)
            ry = rain_rng.uniform(0, H)
            spd = rain_rng.uniform(0.8, 1.4)
            length = rain_rng.randint(20, 50)
            x = (rx - t * 120 * spd) % (W + 200)
            y = (ry + t * 350 * spd) % H
            a = rain_rng.randint(60, 140)
            draw.line([(x, y), (x - length * 0.3, y + length)], fill=(*acc, a), width=1)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=4, max_r=280)

        # Shield forming (arc progress)
        shield_prog = ease_in_out(min(t / 8.0, 1.0))
        shield_r = 160
        start_a = -90
        end_a = start_a + int(360 * shield_prog)
        draw.arc([W // 2 - shield_r, H // 2 - shield_r, W // 2 + shield_r, H // 2 + shield_r],
                 start=start_a, end=end_a, fill=(*acc, 200), width=8)
        # Shield "tick" glow
        if shield_prog > 0.98:
            draw.ellipse([W // 2 - 8, H // 2 - 8, W // 2 + 8, H // 2 + 8],
                         fill=(*acc, 255))

    # Scene 2 (10–22s): brand name + tagline + orbiting sparks
    elif t < 22:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=3, max_r=260)

        # Orbiting sparks
        for i in range(8):
            angle = 2 * math.pi * i / 8 + t * 1.3
            orbit_r = 200 + 30 * math.sin(t * 0.8 + i)
            sx = W // 2 + int(math.cos(angle) * orbit_r)
            sy = H // 2 + int(math.sin(angle) * orbit_r)
            a = clamp(150 + 80 * math.sin(t * 2 + i))
            draw.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(*acc, a))

        # Continued rain (lighter)
        rain_rng = random.Random(33)
        for _ in range(30):
            rx = rain_rng.uniform(0, W + 200)
            ry = rain_rng.uniform(0, H)
            spd = rain_rng.uniform(0.8, 1.4)
            length = rain_rng.randint(15, 35)
            x = (rx - t * 120 * spd) % (W + 200)
            y = (ry + t * 350 * spd) % H
            draw.line([(x, y), (x - length * 0.3, y + length)], fill=(*acc, 50), width=1)

        fn_large = try_font(130)
        fn_med = try_font(52)
        slide = ease_out(min((t - 10) / 1.3, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        text_center(draw, "HOMESAFE", W // 2, by, fn_large, (200, 240, 255, 235))
        tag_a = clamp(ease_out(min((t - 11.5) / 1.0, 1.0)) * 220)
        text_center(draw, "Protect What Matters.", W // 2, by + 95, fn_med, (*acc, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 22.15:
            flash_alpha = int(200 * (1 - (t - 22) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=240)
        # Orbiting sparks
        for i in range(6):
            angle = 2 * math.pi * i / 6 + t * 1.3
            orbit_r = 220
            sx = W // 2 + int(math.cos(angle) * orbit_r)
            sy = H // 2 + int(math.sin(angle) * orbit_r)
            a = clamp(120 + 80 * math.sin(t * 2 + i))
            draw.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(*acc, a))

        fn_large = try_font(130)
        fn_med = try_font(52)
        fn_cta = try_font(46)
        text_center(draw, "HOMESAFE", W // 2, H // 2 - 80, fn_large, (200, 240, 255, 235))
        text_center(draw, "Protect What Matters.", W // 2, H // 2 + 10, fn_med, (*acc, 210))
        cta_a = clamp(ease_out(min((t - 23) / 1.0, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 220, cta_y, W // 2 + 220, cta_y + cta_h],
                                radius=36, fill=(*acc, cta_a))
        text_center(draw, "GET A QUOTE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

ADS = [
    ("ad_relevant_screentime", screentime_frame),
    ("ad_relevant_arcademax", arcademax_frame),
    ("ad_irrelevant_crunchpop", crunchpop_frame),
    ("ad_irrelevant_homesafe", homesafe_frame),
]

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for ad_id, fn in ADS:
        print(f"\n=== {ad_id} ===")
        render_and_encode(fn, ad_id)
    print("\nDone.")
