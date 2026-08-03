#!/usr/bin/env python3
"""
generate_ads.py — render synthetic 15-second ad MP4s via Pillow + ffmpeg.

Four ads, structured as 3-scene TV commercials (1280×720, 15 s, 20 fps):

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
DURATION = 15
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
    if t < 5:
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
    elif t < 10:
        pulse_rings(draw, W // 2, H // 2, t, acc)
        particles(draw, t, acc, count=25, seed=2, vy=-35)
        # scan-line sweep
        sweep_x = int(((t - 5) / 5.0) * W * 1.8 - W * 0.4)
        for sx in range(max(0, sweep_x - 60), min(W, sweep_x)):
            a = int(40 * (1 - abs(sx - sweep_x) / 60))
            draw.line([(sx, 0), (sx, H)], fill=(200, 220, 255, a))
        # shimmer on brand text (done via alpha pulse)
        fn_large = try_font(120)
        fn_med = try_font(52)
        slide = ease_out(min((t - 5) / 0.75, 1.0))
        by = int(lerp(H, H // 2 - 60, slide))
        shimmer_a = clamp(200 + 55 * math.sin(t * 4))
        text_center(draw, "SCREENTIME", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 220)
        text_center(draw, "Stream Everything.", W // 2, by + 90, fn_med, (200, 220, 255, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        particles(draw, t, acc, count=20, seed=3, vy=-30)
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)
        fn_large = try_font(120)
        fn_med = try_font(52)
        fn_cta = try_font(44)
        text_center(draw, "SCREENTIME", W // 2, H // 2 - 80, fn_large, (*acc, 230))
        text_center(draw, "Stream Everything.", W // 2, H // 2 + 10, fn_med, (200, 220, 255, 200))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 240)
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
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Pixel burst from center
        burst_rng = random.Random(42)
        n_pixels = int(min(t / 5 * 300 + 40, 300))
        for _ in range(n_pixels):
            angle = burst_rng.uniform(0, 2 * math.pi)
            speed = burst_rng.uniform(20, 260)
            px = W // 2 + int(math.cos(angle) * speed * t * 0.8)
            py = H // 2 + int(math.sin(angle) * speed * t * 0.8)
            sz = burst_rng.randint(2, 8)
            col_h = burst_rng.uniform(0, 1)
            pr, pg, pb = hsv_to_rgb(col_h, 1.0, 1.0)
            a = clamp((1 - t / 5) * 255)
            if 0 <= px < W and 0 <= py < H:
                draw.rectangle([px, py, px + sz, py + sz], fill=(pr, pg, pb, a))

        # Score counter
        score = int(ease_out(min(t / 4, 1.0)) * 9999)
        fn_score = try_font(90)
        text_center(draw, f"{score:04d}", W // 2, H // 2 + 80, fn_score, (*acc, 220))
        fn_pts = try_font(36)
        text_center(draw, "POINTS", W // 2, H // 2 + 160, fn_pts, (200, 255, 200, 180))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.4, max_r=260)

    # Scene 2 (10–22s): brand name with glitch effect + energy streaks
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
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
        slide = ease_out(min((t - 5) / 0.6, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))

        # Glitch layers: R and B offset slightly
        glitch = 0.06 < ((t * 7) % 1.0) < 0.12
        off = 6 if glitch else 0
        text_center(draw, "ARCADEMAX", W // 2 - off, by, fn_large, (255, 50, 50, 60 if glitch else 0))
        text_center(draw, "ARCADEMAX", W // 2 + off, by, fn_large, (50, 50, 255, 60 if glitch else 0))
        text_center(draw, "ARCADEMAX", W // 2, by, fn_large, (*acc, 240))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 220)
        text_center(draw, "LEVEL UP YOUR GAME", W // 2, by + 100, fn_med, (180, 255, 180, tag_a))

    # Scene 3 (22–30s): CTA + pulsing glow
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
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
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
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
    if t < 5:
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
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
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
        bounce_t = min((t - 5) / 0.5, 1.0)
        by = int(lerp(H + 100, H // 2 - 70, ease_back(bounce_t)))
        text_center(draw, "CRUNCHPOP", W // 2, by, fn_large, (60, 20, 0, 240))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.5, 1.0)) * 230)
        text_center(draw, "The Morning Crunch!", W // 2, by + 100, fn_med, (80, 30, 0, tag_a))

        particles(draw, t, acc, count=20, seed=7, vy=-30, r_range=(3, 9))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        fn_large = try_font(130)
        fn_med = try_font(54)
        fn_cta = try_font(46)
        text_center(draw, "CRUNCHPOP", W // 2, H // 2 - 80, fn_large, (60, 20, 0, 240))
        text_center(draw, "The Morning Crunch!", W // 2, H // 2 + 20, fn_med, (80, 30, 0, 220))
        particles(draw, t, acc, count=15, seed=8, vy=-25)
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
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
    if t < 5:
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
        shield_prog = ease_in_out(min(t / 4.0, 1.0))
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
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
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
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        text_center(draw, "HOMESAFE", W // 2, by, fn_large, (200, 240, 255, 235))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.5, 1.0)) * 220)
        text_center(draw, "Protect What Matters.", W // 2, by + 95, fn_med, (*acc, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
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
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 220, cta_y, W // 2 + 220, cta_y + cta_h],
                                radius=36, fill=(*acc, cta_a))
        text_center(draw, "GET A QUOTE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# NEONFLIX — movie streaming  (deep crimson/red)
# ---------------------------------------------------------------------------

def neonflix_frame(fi, t):
    acc = (230, 50, 80)
    bg = gradient_bg([(20, 5, 10), (60, 10, 20), (20, 5, 10)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): spinning film reel + film-grain flicker + curtain reveal
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Film reel spokes
        cx, cy, reel_r = W // 2, H // 2, 180
        n_spokes = 8
        for i in range(n_spokes):
            angle = 2 * math.pi * i / n_spokes + t * 2.2
            x0 = cx + int(math.cos(angle) * 30)
            y0 = cy + int(math.sin(angle) * 30)
            x1 = cx + int(math.cos(angle) * reel_r)
            y1 = cy + int(math.sin(angle) * reel_r)
            draw.line([(x0, y0), (x1, y1)], fill=(*acc, 200), width=5)
        draw.ellipse([cx - reel_r, cy - reel_r, cx + reel_r, cy + reel_r],
                     outline=(*acc, 180), width=6)
        draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30],
                     fill=(40, 10, 15, 255), outline=(*acc, 220), width=5)

        # Sprocket holes around reel edge
        for i in range(16):
            angle = 2 * math.pi * i / 16 + t * 2.2
            hx = cx + int(math.cos(angle) * (reel_r - 18))
            hy = cy + int(math.sin(angle) * (reel_r - 18))
            draw.ellipse([hx - 6, hy - 6, hx + 6, hy + 6], fill=(0, 0, 0, 220))

        # Curtain reveal (red drapes opening from centre)
        prog = ease_out(min(t / 4.0, 1.0))
        curtain_w = int((1 - prog) * W // 2)
        if curtain_w > 0:
            draw.rectangle([0, 0, curtain_w, H], fill=(60, 5, 10, 220))
            draw.rectangle([W - curtain_w, 0, W, H], fill=(60, 5, 10, 220))

        # Film grain
        grain_rng = random.Random(int(t * FPS))
        for _ in range(300):
            gx = grain_rng.randint(0, W - 1)
            gy = grain_rng.randint(0, H - 1)
            ga = grain_rng.randint(20, 70)
            draw.point((gx, gy), fill=(255, 255, 255, ga))

    # Scene 2 (10–22s): brand name + tagline + vertical scan + particles
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=30, seed=20, vy=-45, drift=25, r_range=(2, 6))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, max_r=240)

        # Vertical light scan
        scan_x = int(((t - 5) / 5.0) * W * 1.8 - W * 0.4)
        for sx in range(max(0, scan_x - 50), min(W, scan_x)):
            a = int(35 * (1 - abs(sx - scan_x) / 50))
            draw.line([(sx, 0), (sx, H)], fill=(255, 180, 180, a))

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.75, 1.0))
        by = int(lerp(H, H // 2 - 60, slide))
        glow_a = clamp(210 + 45 * math.sin(t * 3.5))
        text_center(draw, "NEONFLIX", W // 2, by, fn_large, (*acc, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Cinema Without Limits.", W // 2, by + 90, fn_med, (255, 180, 190, tag_a))

        # Film grain (lighter in scene 2)
        grain_rng = random.Random(int(t * FPS))
        for _ in range(120):
            gx = grain_rng.randint(0, W - 1)
            gy = grain_rng.randint(0, H - 1)
            ga = grain_rng.randint(10, 40)
            draw.point((gx, gy), fill=(255, 255, 255, ga))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=20, seed=21, vy=-40)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "NEONFLIX", W // 2, H // 2 - 80, fn_large, (*acc, 230))
        text_center(draw, "Cinema Without Limits.", W // 2, H // 2 + 10, fn_med, (255, 180, 190, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "WATCH NOW", W // 2, cta_y + cta_h // 2, fn_cta, (255, 240, 240, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# PIXELQUEST — adventure gaming  (deep purple/violet)
# ---------------------------------------------------------------------------

def pixelquest_frame(fi, t):
    acc = (180, 80, 255)
    bg = gradient_bg([(10, 5, 30), (25, 10, 60), (10, 5, 30)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): pixel grid wipe + map tiles + compass spin
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Pixel grid wipe (tiles reveal from top-left)
        tile_sz = 48
        cols = W // tile_sz + 1
        rows = H // tile_sz + 1
        wipe_prog = ease_in_out(min(t / 4.0, 1.0))
        total_tiles = cols * rows
        revealed = int(wipe_prog * total_tiles)
        tile_rng = random.Random(13)
        order = list(range(total_tiles))
        tile_rng.shuffle(order)
        revealed_set = set(order[:revealed])
        for idx in range(total_tiles):
            if idx in revealed_set:
                col = idx % cols
                row = idx // cols
                tx = col * tile_sz
                ty = row * tile_sz
                a = clamp(int(wipe_prog * 180))
                h_tile = (col * 0.04 + row * 0.07) % 1.0
                r, g, b = hsv_to_rgb(h_tile, 0.7, 0.4)
                draw.rectangle([tx, ty, tx + tile_sz - 2, ty + tile_sz - 2],
                                fill=(r, g, b, a))

        # Spinning compass
        cx, cy = W // 2, H // 2
        comp_r = 140
        draw.ellipse([cx - comp_r, cy - comp_r, cx + comp_r, cy + comp_r],
                     outline=(*acc, 180), width=5)
        # N/S/E/W ticks
        for angle_deg, label in [(0, "N"), (90, "E"), (180, "S"), (270, "W")]:
            rad = math.radians(angle_deg + t * 80)
            ix = cx + int(math.cos(rad) * (comp_r - 15))
            iy = cy + int(math.sin(rad) * (comp_r - 15))
            ox = cx + int(math.cos(rad) * comp_r)
            oy = cy + int(math.sin(rad) * comp_r)
            draw.line([(ix, iy), (ox, oy)], fill=(*acc, 200), width=4)
        # Needle
        needle_angle = math.radians(t * 80)
        nx = cx + int(math.cos(needle_angle) * (comp_r - 25))
        ny = cy + int(math.sin(needle_angle) * (comp_r - 25))
        draw.line([(cx, cy), (nx, ny)], fill=(255, 80, 80, 220), width=6)
        draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(*acc, 255))

    # Scene 2 (10–22s): brand name + adventure particles + map grid
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Faint scrolling map grid
        grid_off = int((t - 10) * 30) % 60
        for gx in range(-60 + grid_off, W + 60, 60):
            draw.line([(gx, 0), (gx, H)], fill=(*acc, 20))
        for gy in range(0, H + 60, 60):
            scroll_y = (gy - int((t - 10) * 20)) % (H + 60)
            draw.line([(0, scroll_y), (W, scroll_y)], fill=(*acc, 20))

        particles(draw, t, acc, count=35, seed=30, vy=-50, drift=30, r_range=(2, 8))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.6, max_r=250)

        fn_large = try_font(120)
        fn_med = try_font(52)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 65, slide))
        shimmer_a = clamp(205 + 50 * math.sin(t * 4.2))
        text_center(draw, "PIXELQUEST", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Your Adventure Awaits.", W // 2, by + 92, fn_med, (210, 170, 255, tag_a))

    # Scene 3 (22–30s): CTA + orbiting star sparks
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=22, seed=31, vy=-45)
        for i in range(10):
            angle = 2 * math.pi * i / 10 + t * 1.1
            orbit_r = 230 + 20 * math.sin(t + i)
            sx = W // 2 + int(math.cos(angle) * orbit_r)
            sy = H // 2 + int(math.sin(angle) * orbit_r)
            a = clamp(130 + 80 * math.sin(t * 2.5 + i))
            draw.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(*acc, a))

        fn_large = try_font(120)
        fn_med = try_font(52)
        fn_cta = try_font(46)
        text_center(draw, "PIXELQUEST", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Your Adventure Awaits.", W // 2, H // 2 + 12, fn_med, (210, 170, 255, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 215, cta_y, W // 2 + 215, cta_y + cta_h],
                                radius=36, fill=(*acc, cta_a))
        text_center(draw, "PLAY FREE", W // 2, cta_y + cta_h // 2, fn_cta, (255, 250, 255, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# FRESHMINT — oral care  (cool mint/white/blue)
# ---------------------------------------------------------------------------

def freshmint_frame(fi, t):
    acc = (80, 220, 200)
    bg = gradient_bg([(200, 240, 245), (230, 250, 252), (200, 240, 245)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): ripple waves + floating bubbles + foam splash
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Concentric ripple waves emanating from centre-bottom
        cx, cy_r = W // 2, H + 50
        for k in range(6):
            phase = ((t * 0.7 + k * 0.4) % 2.4) / 2.4
            r = int(phase * 700)
            a = clamp(int((1 - phase) * 100))
            if a > 0:
                draw.ellipse([cx - r, cy_r - r // 3, cx + r, cy_r + r // 3],
                             outline=(*acc, a), width=3)

        # Floating bubbles
        bubble_rng = random.Random(50)
        for i in range(20):
            bx = bubble_rng.uniform(80, W - 80)
            by_base = bubble_rng.uniform(H * 0.2, H * 0.9)
            spd = bubble_rng.uniform(0.6, 1.3)
            delay = bubble_rng.uniform(0, 6)
            local_t = max(0, t - delay)
            bx_drift = bx + 20 * math.sin(local_t * 0.9 + i)
            by_pos = (by_base - local_t * spd * 50) % H
            sz = bubble_rng.randint(10, 28)
            a = clamp(int(bubble_rng.uniform(0.4, 0.8) * 180))
            draw.ellipse([bx_drift - sz, by_pos - sz, bx_drift + sz, by_pos + sz],
                         outline=(*acc, a), width=2)
            # Highlight
            draw.ellipse([bx_drift - sz // 3, by_pos - sz // 2,
                          bx_drift + sz // 6, by_pos - sz // 5],
                         fill=(255, 255, 255, a // 2))

        # Foam splash at bottom
        splash_rng = random.Random(66)
        for i in range(15):
            sx = splash_rng.uniform(100, W - 100)
            sy_base = H - 40
            phase = (t * 1.1 + i * 0.4) % 1.2
            sy = sy_base - int(phase * 80)
            sz = splash_rng.randint(6, 18)
            a = clamp(int((1 - phase / 1.2) * 200))
            if a > 0:
                draw.ellipse([sx - sz, sy - sz, sx + sz, sy + sz],
                             fill=(255, 255, 255, a))

    # Scene 2 (10–22s): brand name + tagline + ripples continue
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        cx, cy_r = W // 2, H + 50
        for k in range(4):
            phase = ((t * 0.5 + k * 0.5) % 2.4) / 2.4
            r = int(phase * 700)
            a = clamp(int((1 - phase) * 60))
            if a > 0:
                draw.ellipse([cx - r, cy_r - r // 3, cx + r, cy_r + r // 3],
                             outline=(*acc, a), width=2)

        # Floating bubbles (lighter)
        bubble_rng = random.Random(50)
        for i in range(10):
            bx = bubble_rng.uniform(80, W - 80)
            by_base = bubble_rng.uniform(H * 0.2, H * 0.9)
            spd = bubble_rng.uniform(0.6, 1.3)
            delay = bubble_rng.uniform(0, 6)
            local_t = max(0, t - delay)
            bx_drift = bx + 20 * math.sin(local_t * 0.9 + i)
            by_pos = (by_base - local_t * spd * 50) % H
            sz = bubble_rng.randint(10, 28)
            a = clamp(int(bubble_rng.uniform(0.3, 0.6) * 120))
            draw.ellipse([bx_drift - sz, by_pos - sz, bx_drift + sz, by_pos + sz],
                         outline=(*acc, a), width=2)

        fn_large = try_font(120)
        fn_med = try_font(52)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H, H // 2 - 60, slide))
        text_center(draw, "FRESHMINT", W // 2, by, fn_large, (20, 80, 90, 230))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Breathe Fresh. Live Bold.", W // 2, by + 90, fn_med, (30, 120, 130, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Bubbles still rising
        bubble_rng = random.Random(50)
        for i in range(8):
            bx = bubble_rng.uniform(80, W - 80) + bubble_rng.uniform(0, 0)
            by_base = bubble_rng.uniform(H * 0.2, H * 0.9)
            spd = bubble_rng.uniform(0.6, 1.3)
            bx_drift = bx + 20 * math.sin(t * 0.9 + i)
            by_pos = (by_base - t * spd * 50) % H
            sz = bubble_rng.randint(10, 28)
            a = clamp(int(bubble_rng.uniform(0.2, 0.5) * 100))
            draw.ellipse([bx_drift - sz, by_pos - sz, bx_drift + sz, by_pos + sz],
                         outline=(*acc, a), width=2)

        fn_large = try_font(120)
        fn_med = try_font(52)
        fn_cta = try_font(46)
        text_center(draw, "FRESHMINT", W // 2, H // 2 - 80, fn_large, (20, 80, 90, 230))
        text_center(draw, "Breathe Fresh. Live Bold.", W // 2, H // 2 + 10, fn_med, (30, 120, 130, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "FIND YOURS", W // 2, cta_y + cta_h // 2, fn_cta, (255, 255, 255, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# BUILDRIGHT — power tools  (dark slate + orange sparks)
# ---------------------------------------------------------------------------

def buildright_frame(fi, t):
    acc = (255, 140, 20)
    bg = gradient_bg([(15, 15, 15), (35, 30, 20), (15, 15, 15)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): blueprint grid reveal + hammer swing arc + sparks
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Blueprint grid (fades in)
        grid_a = clamp(ease_out(min(t / 1.5, 1.0)) * 50)
        for gx in range(0, W, 60):
            draw.line([(gx, 0), (gx, H)], fill=(80, 140, 200, grid_a))
        for gy in range(0, H, 60):
            draw.line([(0, gy), (W, gy)], fill=(80, 140, 200, grid_a))

        # Hammer swing arc
        hcx, hcy = W // 2, H // 2 + 60
        arm_len = 160
        max_swing = 55
        swing = math.sin(t * 3.5) * max_swing
        angle = math.radians(-90 + swing)
        hx = hcx + int(math.cos(angle) * arm_len)
        hy = hcy + int(math.sin(angle) * arm_len)
        draw.line([(hcx, hcy), (hx, hy)], fill=(180, 150, 100, 200), width=12)
        # Hammer head
        perp = math.radians(-90 + swing + 90)
        head_w = 35
        hh_x0 = hx + int(math.cos(perp) * head_w)
        hh_y0 = hy + int(math.sin(perp) * head_w)
        hh_x1 = hx - int(math.cos(perp) * head_w)
        hh_y1 = hy - int(math.sin(perp) * head_w)
        draw.line([(hh_x0, hh_y0), (hh_x1, hh_y1)], fill=(*acc, 220), width=22)
        # Pivot point
        draw.ellipse([hcx - 10, hcy - 10, hcx + 10, hcy + 10], fill=(*acc, 255))

        # Sparks flying on downswing
        if swing < -20:
            spark_rng = random.Random(int(t * 50))
            for _ in range(25):
                angle_s = spark_rng.uniform(math.pi * 0.8, math.pi * 2.2)
                dist = spark_rng.uniform(10, 120) * abs(swing) / max_swing
                sx = hx + int(math.cos(angle_s) * dist)
                sy = hy + int(math.sin(angle_s) * dist)
                sz = spark_rng.randint(2, 6)
                a = spark_rng.randint(150, 255)
                draw.ellipse([sx - sz, sy - sz, sx + sz, sy + sz],
                             fill=(*acc, a))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, max_r=240)

    # Scene 2 (10–22s): brand name + tagline + geometric shapes + sparks
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Faint blueprint grid
        for gx in range(0, W, 60):
            draw.line([(gx, 0), (gx, H)], fill=(80, 140, 200, 18))
        for gy in range(0, H, 60):
            draw.line([(0, gy), (W, gy)], fill=(80, 140, 200, 18))

        particles(draw, t, acc, count=25, seed=40, vy=-60, drift=20, r_range=(2, 5))

        # Floating geometric shapes (hex/diamond outlines)
        shape_rng = random.Random(88)
        for i in range(6):
            sx = shape_rng.uniform(100, W - 100)
            sy = shape_rng.uniform(80, H - 80) + 15 * math.sin(t * 0.8 + i)
            sr = shape_rng.randint(25, 55)
            a = clamp(int(shape_rng.uniform(0.2, 0.5) * 160))
            n_sides = shape_rng.choice([4, 6])
            offset_angle = t * 0.5 + i * 0.8
            pts = []
            for s in range(n_sides):
                ang = 2 * math.pi * s / n_sides + offset_angle
                pts.append((sx + math.cos(ang) * sr, sy + math.sin(ang) * sr))
            draw.polygon(pts, outline=(*acc, a))

        fn_large = try_font(120)
        fn_med = try_font(52)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 65, slide))
        text_center(draw, "BUILDRIGHT", W // 2, by, fn_large, (*acc, 235))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Built Tough. Built Right.", W // 2, by + 92, fn_med, (200, 190, 170, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=18, seed=41, vy=-55, r_range=(2, 5))

        fn_large = try_font(120)
        fn_med = try_font(52)
        fn_cta = try_font(46)
        text_center(draw, "BUILDRIGHT", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Built Tough. Built Right.", W // 2, H // 2 + 10, fn_med, (200, 190, 170, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 72
        cta_y = H - 120
        draw.rounded_rectangle([W // 2 - 215, cta_y, W // 2 + 215, cta_y + cta_h],
                                radius=36, fill=(*acc, cta_a))
        text_center(draw, "SHOP NOW", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# DRIVEPRO — GPS/navigation app  (dark road blue + orange route highlight)
# ---------------------------------------------------------------------------

def drivepro_frame(fi, t):
    acc = (255, 160, 30)
    bg = gradient_bg([(8, 14, 30), (15, 28, 55), (8, 14, 30)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): scrolling road map grid + animated route + pulsing location pin
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Scrolling map grid (moves as if driving)
        scroll = int(t * 80) % 60
        for gx in range(0, W + 60, 60):
            draw.line([(gx - scroll, 0), (gx - scroll, H)], fill=(40, 80, 140, 40))
        for gy in range(0, H + 60, 60):
            draw.line([(0, gy - scroll // 2), (W, gy - scroll // 2)], fill=(40, 80, 140, 40))

        # Animated route line (thick orange path drawn progressively)
        route_pts = [
            (150, H - 80), (280, 420), (420, 360), (560, H // 2),
            (700, 300), (840, H // 2 - 30), (W - 150, 200)
        ]
        drawn = int(ease_out(min(t / 4, 1.0)) * (len(route_pts) - 1))
        for i in range(min(drawn, len(route_pts) - 1)):
            draw.line([route_pts[i], route_pts[i + 1]], fill=(*acc, 200), width=7)
        # Route dots
        for i in range(min(drawn + 1, len(route_pts))):
            d_r = 8 if i in (0, len(route_pts) - 1) else 5
            draw.ellipse([route_pts[i][0] - d_r, route_pts[i][1] - d_r,
                          route_pts[i][0] + d_r, route_pts[i][1] + d_r],
                         fill=(*acc, 220))

        # Pulsing location pin at end of route
        end = route_pts[min(drawn, len(route_pts) - 1)]
        pin_scale = ease_back(min(t / 1.5, 1.0))
        pin_r = int(28 * pin_scale)
        pulse_a = clamp(int((0.5 + 0.5 * math.sin(t * 4)) * 160))
        draw.ellipse([end[0] - pin_r - 15, end[1] - pin_r - 15,
                      end[0] + pin_r + 15, end[1] + pin_r + 15],
                     outline=(*acc, pulse_a), width=4)
        draw.ellipse([end[0] - pin_r, end[1] - pin_r * 2,
                      end[0] + pin_r, end[1]], fill=(*acc, 220))
        draw.ellipse([end[0] - 10, end[1] - pin_r - 10,
                      end[0] + 10, end[1] - pin_r + 10], fill=(255, 255, 255, 220))

    # Scene 2 (10–22s): brand name + speed readout ticker + particles
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Map grid still visible
        scroll = int(t * 80) % 60
        for gx in range(0, W + 60, 60):
            draw.line([(gx - scroll, 0), (gx - scroll, H)], fill=(40, 80, 140, 25))
        for gy in range(0, H + 60, 60):
            draw.line([(0, gy - scroll // 2), (W, gy - scroll // 2)], fill=(40, 80, 140, 25))

        particles(draw, t, acc, count=22, seed=60, vy=-45, drift=20)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, max_r=240)

        # Speed ticker (counts up then settles)
        speed = int(ease_out(min((t - 5) / 2.0, 1.0)) * 87)
        fn_speed = try_font(70)
        fn_unit = try_font(36)
        text_center(draw, f"{speed}", W // 2 + 10, H // 2 + 80, fn_speed, (*acc, 210))
        text_center(draw, "km/h", W // 2 + 65, H // 2 + 110, fn_unit, (200, 200, 220, 160))

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        glow_a = clamp(210 + 45 * math.sin(t * 3.5))
        text_center(draw, "DRIVEPRO", W // 2, by, fn_large, (*acc, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Navigate Every Road.", W // 2, by + 90, fn_med, (200, 210, 240, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=18, seed=61, vy=-40)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "DRIVEPRO", W // 2, H // 2 - 80, fn_large, (*acc, 230))
        text_center(draw, "Navigate Every Road.", W // 2, H // 2 + 10, fn_med, (200, 210, 240, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "GET DIRECTIONS", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# SPEEDLANE — electric vehicle brand  (deep black + electric cyan/white)
# ---------------------------------------------------------------------------

def speedlane_frame(fi, t):
    acc = (60, 230, 255)
    bg = gradient_bg([(5, 5, 10), (10, 15, 30), (5, 5, 10)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Scene 1 (0–10s): charging animation + lightning bolts + EV silhouette
    if t < 5:
        if t < 0.15:
            flash_alpha = int(255 * (1 - t / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        # Car silhouette (simple trapezoid body)
        car_y = H // 2 + 40
        prog = ease_out(min(t / 2.5, 1.0))
        car_a = clamp(int(prog * 200))
        car_pts = [
            (W // 2 - 260, car_y + 40),
            (W // 2 - 200, car_y),
            (W // 2 - 120, car_y - 60),
            (W // 2 + 120, car_y - 60),
            (W // 2 + 200, car_y),
            (W // 2 + 260, car_y + 40),
        ]
        draw.polygon(car_pts, outline=(*acc, car_a), fill=(0, 0, 0, min(car_a, 180)))
        # Wheels
        for wx in [W // 2 - 170, W // 2 + 170]:
            draw.ellipse([wx - 35, car_y + 20, wx + 35, car_y + 90],
                         outline=(*acc, car_a), width=5, fill=(0, 0, 0, min(car_a, 160)))
            draw.ellipse([wx - 18, car_y + 37, wx + 18, car_y + 73], fill=(*acc, car_a))

        # Charging cable + progress bar
        cable_a = clamp(ease_out(min(t / 2.0, 1.0)) * 200)
        draw.line([(W // 2 + 260, car_y + 20), (W // 2 + 340, car_y - 30)],
                  fill=(*acc, cable_a), width=5)
        bar_w = 120
        bar_h = 20
        charge_prog = ease_in_out(min(t / 4.0, 1.0))
        bx = W // 2 + 340
        by = car_y - 60
        draw.rounded_rectangle([bx, by, bx + bar_w, by + bar_h],
                                radius=8, outline=(*acc, cable_a), width=2)
        draw.rounded_rectangle([bx + 2, by + 2, bx + 2 + int((bar_w - 4) * charge_prog), by + bar_h - 2],
                                radius=6, fill=(*acc, cable_a))

        # Lightning bolt symbol
        lightning_a = clamp(int(abs(math.sin(t * 5)) * 255))
        bolt = [(W // 2, car_y - 110), (W // 2 - 20, car_y - 70), (W // 2 + 5, car_y - 70),
                (W // 2 - 15, car_y - 25), (W // 2 + 30, car_y - 80), (W // 2 + 5, car_y - 80)]
        draw.polygon(bolt, fill=(*acc, lightning_a))

        pulse_rings(draw, W // 2, car_y + 20, t, acc, period=1.5, max_r=200)

    # Scene 2 (10–22s): brand name + EV specs stats + particles
    elif t < 10:
        if t < 5.15:
            flash_alpha = int(200 * (1 - (t - 5) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=28, seed=70, vy=-50, drift=25, r_range=(2, 7))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.5, max_r=240)

        # Stat counters
        fn_stat = try_font(56)
        fn_unit2 = try_font(30)
        stats = [
            (int(ease_out(min((t - 5) / 1.5, 1.0)) * 480), "km range", W // 2 - 260),
            (int(ease_out(min((t - 5.5) / 1.5, 1.0)) * 2.8 * 10) / 10, "s 0-100", W // 2),
            (int(ease_out(min((t - 6) / 1.5, 1.0)) * 150), "kW charge", W // 2 + 260),
        ]
        for val, unit, sx in stats:
            text_center(draw, str(val), sx, H // 2 + 80, fn_stat, (*acc, 210))
            text_center(draw, unit, sx, H // 2 + 125, fn_unit2, (180, 220, 240, 170))

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        shimmer_a = clamp(205 + 50 * math.sin(t * 4))
        text_center(draw, "SPEEDLANE", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Drive the Future.", W // 2, by + 90, fn_med, (180, 230, 255, tag_a))

    # Scene 3 (22–30s): CTA
    else:
        if t < 10.15:
            flash_alpha = int(200 * (1 - (t - 10) / 0.15))
            fl = Image.new("RGBA", (W, H), (255, 255, 255, flash_alpha))
            bg = Image.alpha_composite(bg, fl)

        particles(draw, t, acc, count=20, seed=71, vy=-48)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "SPEEDLANE", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Drive the Future.", W // 2, H // 2 + 10, fn_med, (180, 230, 255, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 205, cta_y, W // 2 + 205, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "BOOK A TEST DRIVE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# ENERGYBLAST — sports energy drink  (electric red / black / yellow)
# thrill_seeker category
# ---------------------------------------------------------------------------

def energyblast_frame(fi, t):
    acc = (255, 40, 60)
    yel = (255, 210, 30)
    bg = gradient_bg([(8, 2, 4), (30, 8, 12), (8, 2, 4)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        for i in range(28):
            angle = 2 * math.pi * i / 28 + t * 0.4
            r0 = 70 + 25 * math.sin(t * 3 + i)
            r1 = 360 + 50 * math.sin(t * 1.5 + i)
            x0 = W // 2 + int(math.cos(angle) * r0)
            y0 = H // 2 + int(math.sin(angle) * r0)
            x1 = W // 2 + int(math.cos(angle) * r1)
            y1 = H // 2 + int(math.sin(angle) * r1)
            a = clamp(50 + 35 * math.sin(i + t * 4))
            draw.line([(x0, y0), (x1, y1)], fill=(*acc, a), width=2)
        bolt_a = clamp(int(abs(math.sin(t * 4)) * 240))
        bolt = [(W // 2 + 18, 80), (W // 2 - 20, H // 2 - 60),
                (W // 2 + 22, H // 2 - 60), (W // 2 - 18, H - 90)]
        if bolt_a > 20:
            draw.line(bolt, fill=(*yel, bolt_a), width=6)
            draw.line(bolt, fill=(255, 255, 255, bolt_a // 4), width=14)
        energy = int(ease_out(min(t / 3.5, 1.0)) * 8500)
        fn_e = try_font(76)
        text_center(draw, f"{energy} J", W // 2, H // 2 + 100, fn_e, (*acc, 200))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.1, max_r=240)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, yel, count=28, seed=80, vy=-55, drift=20)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.1, max_r=230)
        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        glow_a = clamp(210 + 45 * math.sin(t * 5))
        text_center(draw, "ENERGYBLAST", W // 2, by, fn_large, (*acc, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Fuel Your Fire.", W // 2, by + 90, fn_med, (*yel, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, yel, count=20, seed=81, vy=-50)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "ENERGYBLAST", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Fuel Your Fire.", W // 2, H // 2 + 10, fn_med, (*yel, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 190, cta_y, W // 2 + 190, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "GRAB YOURS", W // 2, cta_y + cta_h // 2, fn_cta, (255, 255, 255, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# BATTLECAST — esports streaming platform  (dark purple / cyan)
# thrill_seeker category
# ---------------------------------------------------------------------------

def battlecast_frame(fi, t):
    acc = (0, 220, 200)
    bg = gradient_bg([(8, 2, 20), (20, 5, 40), (8, 2, 20)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        prog = ease_out(min(t / 4.5, 1.0))
        bracket_segs = [
            ((200, 200), (200, 300)), ((200, 400), (200, 500)),
            ((200, 250), (380, 350)), ((200, 450), (380, 350)),
            ((1080, 200), (1080, 300)), ((1080, 400), (1080, 500)),
            ((1080, 250), (900, 350)), ((1080, 450), (900, 350)),
            ((380, 350), (W // 2, H // 2)), ((900, 350), (W // 2, H // 2)),
        ]
        for i, (p0, p1) in enumerate(bracket_segs):
            frac = (i + 1) / len(bracket_segs)
            if prog >= frac:
                a = clamp(int(min((prog - frac) / 0.08 + 1, 1.0) * 200))
                draw.line([p0, p1], fill=(*acc, a), width=3)
        trophy_a = clamp(int(ease_out(min(t / 3, 1.0)) * 220))
        cx, cy = W // 2, H // 2
        draw.ellipse([cx - 42, cy - 58, cx + 42, cy + 8], outline=(255, 180, 0, trophy_a), width=5)
        draw.line([(cx, cy + 8), (cx, cy + 42)], fill=(255, 180, 0, trophy_a), width=5)
        draw.line([(cx - 30, cy + 42), (cx + 30, cy + 42)], fill=(255, 180, 0, trophy_a), width=5)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.4, max_r=250)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=30, seed=90, vy=-50, drift=25)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.4, max_r=240)
        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        shimmer_a = clamp(210 + 45 * math.sin(t * 4))
        text_center(draw, "BATTLECAST", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Where Champions Stream.", W // 2, by + 92, fn_med, (200, 255, 240, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=91, vy=-45)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "BATTLECAST", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Where Champions Stream.", W // 2, H // 2 + 10, fn_med, (200, 255, 240, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 185, cta_y, W // 2 + 185, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "JOIN FREE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# MINDSPAN — documentary / educational streaming  (deep navy / amber)
# intellectual_explorer category
# ---------------------------------------------------------------------------

def mindspan_frame(fi, t):
    acc = (255, 185, 30)
    bg = gradient_bg([(2, 8, 28), (5, 18, 55), (2, 8, 28)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        cx, cy, globe_r = W // 2, H // 2, 180
        draw.ellipse([cx - globe_r, cy - globe_r, cx + globe_r, cy + globe_r],
                     outline=(*acc, 200), width=4)
        for lat_frac in [0.25, 0.5, 0.75]:
            y_lat = cy - globe_r + int(2 * globe_r * lat_frac)
            ry_lat = int(math.sqrt(max(0, globe_r ** 2 - (y_lat - cy) ** 2)))
            draw.ellipse([cx - ry_lat, y_lat - 3, cx + ry_lat, y_lat + 3],
                         outline=(*acc, 70), width=2)
        for k in range(4):
            angle = math.radians(k * 45 + t * 30)
            rx = int(globe_r * abs(math.cos(angle)))
            a_lon = clamp(90 * abs(math.cos(angle)))
            draw.ellipse([cx - rx, cy - globe_r, cx + rx, cy + globe_r],
                         outline=(*acc, a_lon), width=2)
        pulse_rings(draw, cx, cy, t, acc, period=2.0, n=3, max_r=280)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=25, seed=100, vy=-40, drift=30)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=260)
        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        shimmer_a = clamp(205 + 50 * math.sin(t * 3.5))
        text_center(draw, "MINDSPAN", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Discover. Learn. Explore.", W // 2, by + 90, fn_med, (220, 200, 140, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=18, seed=101, vy=-38)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(44)
        text_center(draw, "MINDSPAN", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Discover. Learn. Explore.", W // 2, H // 2 + 10, fn_med, (220, 200, 140, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 215, cta_y, W // 2 + 215, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "EXPLORE FREE", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# WANDERSCOUT — adventure travel booking  (emerald green / sky blue)
# intellectual_explorer category
# ---------------------------------------------------------------------------

def wanderscout_frame(fi, t):
    acc = (40, 200, 140)
    sky = (100, 190, 230)
    bg = gradient_bg([(4, 28, 20), (8, 50, 36), (4, 28, 20)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        cx, cy, comp_r = W // 2, H // 2, 160
        draw.ellipse([cx - comp_r, cy - comp_r, cx + comp_r, cy + comp_r],
                     outline=(*acc, 200), width=5)
        for d in range(4):
            angle = math.radians(d * 90 + t * 60)
            ix = cx + int(math.cos(angle) * (comp_r - 22))
            iy = cy + int(math.sin(angle) * (comp_r - 22))
            ox = cx + int(math.cos(angle) * comp_r)
            oy = cy + int(math.sin(angle) * comp_r)
            draw.line([(ix, iy), (ox, oy)], fill=(*acc, 200), width=4)
        n_angle = math.radians(t * 60)
        nx = cx + int(math.cos(n_angle) * (comp_r - 30))
        ny = cy + int(math.sin(n_angle) * (comp_r - 30))
        draw.line([(cx, cy), (nx, ny)], fill=(255, 80, 80, 240), width=7)
        sx = cx - int(math.cos(n_angle) * (comp_r - 30))
        sy = cy - int(math.sin(n_angle) * (comp_r - 30))
        draw.line([(cx, cy), (sx, sy)], fill=(*sky, 200), width=5)
        draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(*acc, 255))
        lat = 40.7 + t * 0.8
        lon = 74.0 - t * 1.2
        fn_coord = try_font(36)
        coord_a = clamp(ease_out(min(t / 2, 1.0)) * 200)
        text_center(draw, f"{lat:.1f}°N  {lon:.1f}°W", W // 2, H // 2 + 120, fn_coord, (*sky, coord_a))
        pulse_rings(draw, cx, cy, t, acc, period=1.8, n=3, max_r=250)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, sky, count=28, seed=110, vy=-45, drift=25)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, n=2, max_r=240)
        fn_large = try_font(110)
        fn_med = try_font(48)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        shimmer_a = clamp(205 + 50 * math.sin(t * 4))
        text_center(draw, "WANDERSCOUT", W // 2, by, fn_large, (*acc, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Find Your Next Adventure.", W // 2, by + 92, fn_med, (*sky, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, sky, count=18, seed=111, vy=-42)
        fn_large = try_font(110)
        fn_med = try_font(48)
        fn_cta = try_font(46)
        text_center(draw, "WANDERSCOUT", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Find Your Next Adventure.", W // 2, H // 2 + 10, fn_med, (*sky, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 185, cta_y, W // 2 + 185, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "BOOK NOW", W // 2, cta_y + cta_h // 2, fn_cta, (0, 0, 0, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# COMFYHOME — home décor / lifestyle brand  (warm brown / sage / terracotta)
# content_chameleon category
# ---------------------------------------------------------------------------

def comfyhome_frame(fi, t):
    acc = (74, 140, 90)
    ter = (192, 89, 61)
    cream = (245, 220, 180)
    bg = gradient_bg([(38, 28, 18), (55, 42, 28), (38, 28, 18)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        tile_data = [
            (220, 260, 160, 110, ter, "SOFA"),
            (640, 180, 120, 120, acc, "PLANT"),
            (1040, 250, 140, 100, (180, 140, 90), "LAMP"),
            (380, 440, 130, 100, (140, 100, 70), "TABLE"),
            (860, 400, 120, 110, ter, "CHAIR"),
        ]
        for i, (tx, ty, tw, th, col, label) in enumerate(tile_data):
            float_y = ty + int(10 * math.sin(t * 0.9 + i * 1.4))
            a = clamp(ease_out(t / 2.0 - i * 0.12) * 190)
            tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            td = ImageDraw.Draw(tile)
            td.rounded_rectangle([0, 0, tw - 1, th - 1], radius=10,
                                  fill=(*col, min(a, 100)), outline=(*col, a), width=2)
            fn_tile = try_font(24)
            text_center(td, label, tw // 2, th // 2, fn_tile, (*cream, a))
            ov.alpha_composite(tile, (tx - tw // 2, float_y - th // 2))
        pulse_rings(draw, W // 2, H // 2, t, cream, period=2.2, n=2, max_r=240)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, cream, count=22, seed=120, vy=-35, drift=20, r_range=(3, 8))
        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        glow_a = clamp(210 + 30 * math.sin(t * 3))
        text_center(draw, "COMFYHOME", W // 2, by, fn_large, (*acc, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Make Every Room Yours.", W // 2, by + 90, fn_med, (*cream, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, cream, count=16, seed=121, vy=-32)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "COMFYHOME", W // 2, H // 2 - 80, fn_large, (*acc, 230))
        text_center(draw, "Make Every Room Yours.", W // 2, H // 2 + 10, fn_med, (*cream, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*ter, cta_a))
        text_center(draw, "SHOP ONLINE", W // 2, cta_y + cta_h // 2, fn_cta, (255, 250, 240, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# FUNSTREAM — family entertainment streaming  (coral / yellow / teal)
# content_chameleon category
# ---------------------------------------------------------------------------

def funstream_frame(fi, t):
    acc = (255, 100, 65)
    yel = (255, 225, 60)
    tea = (0, 185, 210)
    bg = gradient_bg([(40, 10, 5), (90, 25, 15), (40, 10, 5)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        conf_rng = random.Random(55)
        n_conf = int(ease_out(min(t / 5, 1.0)) * 120)
        for _ in range(n_conf):
            angle = conf_rng.uniform(0, 2 * math.pi)
            dist = conf_rng.uniform(10, 360) * min(t / 2, 1.0)
            cx = W // 2 + int(math.cos(angle) * dist)
            cy = H // 2 + int(math.sin(angle) * dist) - int(80 * (t / 5) ** 2)
            size = conf_rng.randint(8, 20)
            col = [acc, yel, tea][conf_rng.randint(0, 2)]
            a = clamp(int(conf_rng.uniform(0.5, 0.9) * 220))
            if 0 <= cx <= W and 0 <= cy <= H:
                if conf_rng.random() > 0.5:
                    draw.rectangle([cx - size // 2, cy - size // 4,
                                    cx + size // 2, cy + size // 4], fill=(*col, a))
                else:
                    draw.ellipse([cx - size // 2, cy - size // 2,
                                  cx + size // 2, cy + size // 2], fill=(*col, a))
        for i in range(6):
            bx = 160 + i * 195
            period = 1.2 + i * 0.15
            by = H // 2 + int(120 * abs(math.sin(t * 2 * math.pi / period + i)))
            r = 30 + i % 3 * 10
            col = [acc, yel, tea][i % 3]
            draw.ellipse([bx - r, by - r, bx + r, by + r], fill=(*col, 180))
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, yel, count=30, seed=130, vy=-45, drift=25, r_range=(3, 10))
        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        glow_a = clamp(210 + 45 * math.sin(t * 4))
        text_center(draw, "FUNSTREAM", W // 2, by, fn_large, (*acc, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Something For Everyone.", W // 2, by + 90, fn_med, (*yel, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, yel, count=20, seed=131, vy=-40)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "FUNSTREAM", W // 2, H // 2 - 80, fn_large, (*acc, 235))
        text_center(draw, "Something For Everyone.", W // 2, H // 2 + 10, fn_med, (*yel, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 185, cta_y, W // 2 + 185, cta_y + cta_h],
                                radius=35, fill=(*tea, cta_a))
        text_center(draw, "WATCH FREE", W // 2, cta_y + cta_h // 2, fn_cta, (255, 255, 255, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# TRUEVIEW — true crime & drama streaming  (dark crimson / slate / yellow tape)
# investigative_viewer category
# ---------------------------------------------------------------------------

def trueview_frame(fi, t):
    acc = (180, 20, 30)
    yel = (255, 210, 0)
    bg = gradient_bg([(10, 2, 2), (25, 5, 8), (10, 2, 2)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        tape_prog = ease_out(min(t / 4, 1.0))
        tape_reach = int(tape_prog * (W + H))
        for i in range(0, tape_reach + 80, 80):
            x0 = i - H
            y0 = 0
            x1 = i
            y1 = H
            a = clamp(int(tape_prog * 160))
            if a > 0:
                draw.line([(x0, y0), (x1, y1)], fill=(*yel, a), width=28)
                draw.line([(x0 + 14, y0), (x1 + 14, y1)], fill=(0, 0, 0, a // 2), width=4)
        mg_prog = ease_back(min(t / 3, 1.0))
        mg_cx = W // 2 + int((1 - mg_prog) * 280)
        mg_cy = H // 2 - int((1 - mg_prog) * 180)
        mg_r = int(100 * mg_prog)
        mg_a = clamp(int(mg_prog * 220))
        if mg_r > 5:
            draw.ellipse([mg_cx - mg_r, mg_cy - mg_r, mg_cx + mg_r, mg_cy + mg_r],
                         outline=(200, 200, 220, mg_a), width=8)
            hdx = int(mg_r * 0.7)
            draw.line([(mg_cx + mg_r - 5, mg_cy + mg_r - 5),
                       (mg_cx + mg_r + hdx, mg_cy + mg_r + hdx)],
                      fill=(160, 160, 180, mg_a), width=10)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.6, max_r=260)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        for i in range(0, W + H, 80):
            draw.line([(i - H, 0), (i, H)], fill=(*yel, 18), width=28)
        particles(draw, t, acc, count=22, seed=140, vy=-40, drift=15, r_range=(2, 6))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.6, n=2, max_r=240)
        fn_large = try_font(120)
        fn_med = try_font(46)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        glow_a = clamp(205 + 50 * math.sin(t * 3.8))
        text_center(draw, "TRUEVIEW", W // 2, by, fn_large, (220, 220, 235, glow_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "The Truth Is Closer Than You Think.", W // 2, by + 88,
                    fn_med, (180, 190, 210, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=16, seed=141, vy=-38)
        fn_large = try_font(120)
        fn_med = try_font(46)
        fn_cta = try_font(46)
        text_center(draw, "TRUEVIEW", W // 2, H // 2 - 80, fn_large, (220, 220, 235, 235))
        text_center(draw, "The Truth Is Closer Than You Think.", W // 2, H // 2 + 10,
                    fn_med, (180, 190, 210, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 190, cta_y, W // 2 + 190, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "WATCH NOW", W // 2, cta_y + cta_h // 2, fn_cta, (255, 255, 255, cta_a))
    return Image.alpha_composite(bg, ov)


# ---------------------------------------------------------------------------
# NEWSDESK — news & current affairs platform  (navy / white / red)
# investigative_viewer category
# ---------------------------------------------------------------------------

def newsdesk_frame(fi, t):
    acc = (0, 80, 180)
    red = (200, 20, 30)
    lite = (200, 220, 255)
    bg = gradient_bg([(2, 6, 22), (5, 14, 46), (2, 6, 22)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        for k in range(4):
            phase = ((t * 0.8 + k * 0.5) % 2.0) / 2.0
            r = int(phase * 320)
            a = clamp(int((1 - phase) * 140))
            if a > 0 and r > 10:
                draw.arc([W // 2 - r, H // 2 - r // 2, W // 2 + r, H // 2 + r // 2],
                         start=-60, end=60, fill=(*lite, a), width=4)
                draw.arc([W // 2 - r, H // 2 - r // 2, W // 2 + r, H // 2 + r // 2],
                         start=120, end=240, fill=(*lite, a), width=4)
        draw.rectangle([0, H - 80, W, H - 42], fill=(*red, 200))
        font_tick = try_font(26)
        ticker_items = "BREAKING NEWS  ·  LIVE  ·  WORLD  ·  SCIENCE  ·  POLITICS  ·  SOCIETY  ·  "
        offset = int(t * 150) % 800
        for rep in range(3):
            draw.text((rep * 800 - offset, H - 74), ticker_items,
                      font=font_tick, fill=(255, 255, 255, 230))
        cx, cy, gr = W // 2, H // 2 - 20, 130
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], outline=(*lite, 180), width=3)
        for lat_frac in [0.3, 0.5, 0.7]:
            y_lat = cy - gr + int(2 * gr * lat_frac)
            ry_lat = int(math.sqrt(max(0, gr ** 2 - (y_lat - cy) ** 2)))
            draw.ellipse([cx - ry_lat, y_lat - 2, cx + ry_lat, y_lat + 2],
                         outline=(*lite, 55), width=2)
        pulse_rings(draw, cx, cy, t, lite, period=2.2, n=2, max_r=210)
    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        bar_a = clamp(ease_out(min((t - 5) / 0.5, 1.0)) * 200)
        bar_y = H // 2 + 45
        draw.rectangle([W // 2 - 250, bar_y, W // 2 + 250, bar_y + 5], fill=(*red, bar_a))
        particles(draw, t, lite, count=20, seed=150, vy=-38, drift=20)
        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 75, slide))
        shimmer_a = clamp(210 + 45 * math.sin(t * 3.5))
        text_center(draw, "NEWSDESK", W // 2, by, fn_large, (*lite, shimmer_a))
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Stay Informed. Stay Ahead.", W // 2, by + 92, fn_med, (180, 200, 240, tag_a))
    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, lite, count=16, seed=151, vy=-35)
        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        text_center(draw, "NEWSDESK", W // 2, H // 2 - 80, fn_large, (*lite, 235))
        text_center(draw, "Stay Informed. Stay Ahead.", W // 2, H // 2 + 10, fn_med, (180, 200, 240, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 180, cta_y, W // 2 + 180, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "READ NOW", W // 2, cta_y + cta_h // 2, fn_cta, (255, 255, 255, cta_a))
    return Image.alpha_composite(bg, ov)


ADS = [
    ("ad_relevant_screentime", screentime_frame),
    ("ad_relevant_arcademax", arcademax_frame),
    ("ad_irrelevant_crunchpop", crunchpop_frame),
    ("ad_irrelevant_homesafe", homesafe_frame),
    ("ad_relevant_neonflix", neonflix_frame),
    ("ad_relevant_pixelquest", pixelquest_frame),
    ("ad_irrelevant_freshmint", freshmint_frame),
    ("ad_irrelevant_buildright", buildright_frame),
    ("ad_auto_drivepro", drivepro_frame),
    ("ad_auto_speedlane", speedlane_frame),
    # Viewer-profile synthetic ads
    ("ad_thrill_energyblast", energyblast_frame),
    ("ad_thrill_battlecast", battlecast_frame),
    ("ad_intel_mindspan", mindspan_frame),
    ("ad_intel_wanderscout", wanderscout_frame),
    ("ad_chame_comfyhome", comfyhome_frame),
    ("ad_chame_funstream", funstream_frame),
    ("ad_invest_trueview", trueview_frame),
    ("ad_invest_newsdesk", newsdesk_frame),
]

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for ad_id, fn in ADS:
        print(f"\n=== {ad_id} ===")
        render_and_encode(fn, ad_id)
    print("\nDone.")
