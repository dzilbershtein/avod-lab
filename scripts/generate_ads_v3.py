#!/usr/bin/env python3
"""
generate_ads_v3.py — Content-library-targeted synthetic ad set.

16 ads designed specifically for the AVOD-Lab content library, four per
viewer profile. Each advertises a product matching a topic the catalogue
actually contains, so the contextual relevance manipulation can fire for
every creative. Each ad has a product-specific drawn object, glow text, and
synthesized audio.

Viewer-profile → relevant ad pool
  thrill_seeker        → gravecrest (THUNDERDROP rollercoaster park), adrenaline
                         (energy drink), apex (running shoes), ranger (climbing gear)
  intellectual_explorer → curiosity (science), horizon (sci-fi),
                         synapse (technology), renderlab (animation/VFX)
  content_chameleon    → toonbox (funny cartoons), stagecraft (classic comedy),
                         singalong (family musicals), chuckle (family comedy)
  investigative_viewer → whodunit (detective audiobooks), deadlines (NIGHTWATCH
                         doorbell camera), caseroom (crime-fiction magazine),
                         tribunal (legal-advice app)

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


def ease_back(t):
    t = min(max(t, 0.0), 1.0)
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


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

# ─────────────────────────────────────────────────────────────────────────────
# Scene-title utility
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# THRILL_SEEKER ads
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# INTELLECTUAL_EXPLORER ads
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# CONTENT_CHAMELEON ads
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# INVESTIGATIVE_VIEWER ads
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Gap-filling ads
#
# Each of these covers content the original 12 left without a well-matched
# relevant ad: sports (jackie_robinson), consumer technology (elephant_dream,
# tears_of_steel) and family/fantasy/music (pied_piper).
# ─────────────────────────────────────────────────────────────────────────────

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


def draw_explosion(draw, cx, cy, r, col, alpha, phase=0.0):
    """Jagged starburst with a hot core — explosions, for action movies."""
    if r <= 0:
        return
    n = 14
    pts = []
    for k in range(n * 2):
        ang = math.pi * k / n + phase * 0.35
        rr = r * (1.0 if k % 2 == 0 else 0.52 + 0.08 * math.sin(phase * 3 + k))
        pts.append((cx + int(rr * math.cos(ang)), cy + int(rr * math.sin(ang))))
    draw.polygon(pts, outline=(*col, alpha), width=4)
    core = int(r * 0.34)
    draw.ellipse([(cx - core, cy - core), (cx + core, cy + core)],
                 outline=(255, 235, 170, alpha), width=4)


def draw_speed_streaks(draw, t, col, alpha, n=14, seed=7):
    """Horizontal motion streaks crossing the frame — speed and chases."""
    rng = random.Random(seed)
    for _ in range(n):
        y = rng.randint(int(H * 0.08), int(H * 0.92))
        length = rng.randint(120, 320)
        speed = rng.uniform(900, 1500)
        x = (rng.uniform(0, W) + t * speed) % (W + length) - length
        a = int(alpha * rng.uniform(0.25, 0.7))
        draw.line([(x, y), (x + length, y)], fill=(*col, a), width=rng.choice((2, 3, 4)))


def draw_climbing_gear(draw, cx, cy, r, col, alpha, phase=0.0):
    """Mountain peak with a carabiner in front — extreme adventure gear."""
    if r <= 0:
        return
    base = cy + int(r * 0.70)
    draw.polygon([(cx - int(r * 1.15), base), (cx - int(r * 0.25), cy - int(r * 0.85)),
                  (cx + int(r * 0.25), cy - int(r * 0.30)), (cx + int(r * 0.55), cy - int(r * 0.65)),
                  (cx + int(r * 1.15), base)], outline=(*col, int(alpha * 0.55)), width=3)
    w, h = int(r * 0.52), int(r * 0.92)
    tilt = int(r * 0.06 * math.sin(phase * 2.5))
    x0, y0 = cx - w // 2 + tilt, cy - h // 2 + int(r * 0.10)
    draw.rounded_rectangle([(x0, y0), (x0 + w, y0 + h)], radius=w // 2,
                           outline=(*col, alpha), width=6)
    draw.line([(x0 + w - 3, y0 + int(h * 0.30)), (x0 + int(w * 0.35), y0 + int(h * 0.58))],
              fill=(*col, alpha), width=5)


def draw_laughing_cartoon(draw, cx, cy, r, col, alpha, phase=0.0):
    """Round cartoon face laughing — squinted eyes, wide open mouth."""
    if r <= 0:
        return
    bob = int(r * 0.05 * math.sin(phase * 8))
    cy = cy + bob
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(*col, alpha), width=5)
    for ex in (-0.38, 0.38):
        x = cx + int(r * ex)
        draw.arc([(x - int(r * 0.18), cy - int(r * 0.42)), (x + int(r * 0.18), cy - int(r * 0.12))],
                 start=200, end=340, fill=(*col, alpha), width=5)
    draw.chord([(cx - int(r * 0.55), cy - int(r * 0.10)), (cx + int(r * 0.55), cy + int(r * 0.70))],
               start=0, end=180, outline=(*col, alpha), width=5)
    draw.arc([(cx - int(r * 0.30), cy + int(r * 0.25)), (cx + int(r * 0.30), cy + int(r * 0.62))],
             start=200, end=340, fill=(*col, int(alpha * 0.6)), width=3)


# ─────────────────────────────────────────────────────────────────────────────
# Ad registry
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Product ads
#
# Every ad sells a fictitious product in the style of a real AVOD spot: the
# product is the hero, with a benefit line, a call to action and sometimes a
# price. The content genre it belongs to is carried only by the graphics and
# mood around the product — the copy never names a genre.
# ─────────────────────────────────────────────────────────────────────────────

def shade(c, f):
    return tuple(clamp(int(x * f)) for x in c)


def tint(c, f=0.45):
    return tuple(clamp(int(x + (255 - x) * f)) for x in c)


def draw_note(draw, x, y, s, col, alpha):
    draw.ellipse([(x - s, y - int(s * 0.75)), (x + s, y + int(s * 0.75))], fill=(*col, alpha))
    draw.line([(x + s - 1, y), (x + s - 1, y - 4 * s)], fill=(*col, alpha), width=3)
    draw.line([(x + s - 1, y - 4 * s), (x + s + int(s * 1.3), y - 3 * s)], fill=(*col, alpha), width=3)


# ── genre-mood backdrops ─────────────────────────────────────────────────────


def mood_heights(d, t, acc):
    draw_speed_streaks(d, t, tint(acc, 0.4), 120, n=10, seed=31)


def mood_space(d, t, acc):
    rng = random.Random(11)
    for k in range(70):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        tw = 0.4 + 0.6 * abs(math.sin(t * 2 + k))
        rr = rng.choice((1, 1, 2))
        d.ellipse([(x - rr, y - rr), (x + rr, y + rr)], fill=(255, 255, 255, int(200 * tw)))
    px, py = 160, 140
    d.ellipse([(px - 40, py - 40), (px + 40, py + 40)], outline=(*tint(acc, 0.5), 160), width=3)
    d.arc([(px - 78, py - 18), (px + 78, py + 18)], start=150, end=390, fill=(*tint(acc, 0.5), 160), width=3)


def mood_circuit(d, t, acc):
    rng = random.Random(17)
    for k in range(14):
        x0, y0 = rng.uniform(0, W), rng.uniform(0, H)
        x1 = x0 + rng.choice((-1, 1)) * rng.uniform(60, 180)
        a = int(60 + 40 * math.sin(t * 2 + k))
        d.line([(x0, y0), (x1, y0), (x1, y0 + rng.uniform(-80, 80))], fill=(*tint(acc, 0.3), a), width=2)
        d.ellipse([(x1 - 4, y0 - 4), (x1 + 4, y0 + 4)], fill=(*tint(acc, 0.3), a))


def mood_grid(d, t, acc):
    hz = int(H * 0.62)
    for k in range(-12, 13):
        d.line([(W // 2 + k * 30, hz), (W // 2 + k * 160, H)], fill=(*acc, 50), width=1)
    for k in range(8):
        y = hz + int((k / 8) ** 1.8 * (H - hz))
        d.line([(0, y), (W, y)], fill=(*acc, 50), width=1)


def mood_party(d, t, acc):
    rng = random.Random(23)
    cols = [(255, 214, 90), (255, 120, 140), (120, 210, 255), (150, 235, 150)]
    for k in range(40):
        x = rng.uniform(0, W) + 30 * math.sin(t * 2 + k)
        y = (rng.uniform(0, H) + t * rng.uniform(40, 90)) % H
        c = cols[k % 4]
        d.rectangle([(x, y), (x + 8, y + 4)], fill=(*c, 170))


def mood_spotlight(d, t, acc):
    sway = int(60 * math.sin(t * 0.9))
    d.polygon([(W // 2 - 40 + sway, 0), (W // 2 + 40 + sway, 0), (W // 2 + 320, H), (W // 2 - 320, H)],
              fill=(255, 245, 210, 18))
    for side in (-1, 1):
        edge = 0 if side < 0 else W
        d.polygon([(edge, 0), (W // 2 + side * 420, 0), (W // 2 + side * 520, H), (edge, H)],
                  fill=(*shade(acc, 0.55), 120))
        for k in range(4):
            x = W // 2 + side * (440 + k * 40)
            d.line([(x, 0), (x + side * 20, H)], fill=(*shade(acc, 0.35), 120), width=3)


def mood_music(d, t, acc):
    mood_party(d, t, acc)
    for k in range(6):
        x = 120 + k * 200
        y = int(130 + 40 * math.sin(t * 2.4 + k))
        draw_note(d, x, y, 9, tint(acc, 0.5), 120)


def mood_rain(d, t, acc):
    rng = random.Random(7)
    for _ in range(90):
        x = rng.uniform(0, W)
        y = (rng.uniform(0, H) + t * rng.uniform(500, 800)) % H
        d.line([(x, y), (x - 6, y + 22)], fill=(170, 190, 220, 70), width=1)
    lx = W - 170
    d.line([(lx, H), (lx, 150)], fill=(60, 60, 70, 255), width=8)
    d.line([(lx, 150), (lx - 70, 150)], fill=(60, 60, 70, 255), width=8)
    d.polygon([(lx - 90, 160), (lx - 50, 160), (lx + 40, H), (lx - 220, H)], fill=(255, 220, 150, 22))


def mood_court(d, t, acc):
    for k in range(6):
        x = 110 + k * 212
        d.rectangle([(x - 14, 120), (x + 14, H - 60)], outline=(*tint(acc, 0.3), 60), width=2)
    d.line([(60, 110), (W - 60, 110)], fill=(*tint(acc, 0.3), 70), width=3)


# ── products ─────────────────────────────────────────────────────────────────


def product_can(d, cx, cy, r, col, a, ph):
    """Energy-drink can with a lightning bolt."""
    w, h = int(r * 0.62), int(r * 1.3)
    d.rounded_rectangle([(cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2)], radius=w // 4,
                        outline=(*col, a), width=5)
    d.ellipse([(cx - w // 2 + 6, cy - h // 2 - 6), (cx + w // 2 - 6, cy - h // 2 + 14)], outline=(*col, a), width=3)
    b = int(r * 0.32)
    d.polygon([(cx + int(b * 0.2), cy - b), (cx - int(b * 0.55), cy + int(b * 0.12)), (cx - int(b * 0.02), cy + int(b * 0.12)),
               (cx - int(b * 0.3), cy + b), (cx + int(b * 0.55), cy - int(b * 0.18)), (cx + int(b * 0.05), cy - int(b * 0.18))],
              fill=(255, 220, 90, a))


def product_shoe(d, cx, cy, r, col, a, ph):
    """Running shoe in profile with laces and a cushioned sole."""
    P = [(-0.95, 0.20), (-0.98, -0.22), (-0.62, -0.30), (-0.25, -0.58), (0.05, -0.46),
         (0.42, -0.18), (0.88, -0.02), (1.02, 0.20)]
    d.polygon([(cx + int(x * r), cy + int(y * r)) for x, y in P], outline=(*col, a), width=5)
    d.rounded_rectangle([(cx - int(1.0 * r), cy + int(0.20 * r)), (cx + int(1.06 * r), cy + int(0.40 * r))],
                        radius=int(0.1 * r), outline=(*col, a), width=5)
    for k in range(4):
        x = cx - int(0.18 * r) + k * int(0.13 * r)
        d.line([(x, cy - int(0.44 * r) + k * int(0.07 * r)), (x + int(0.12 * r), cy - int(0.30 * r) + k * int(0.07 * r))],
               fill=(*col, a), width=3)
    for k in range(3):
        y = cy - int(0.2 * r) + k * int(0.18 * r)
        d.line([(cx - int(1.6 * r) - k * 20, y), (cx - int(1.15 * r), y)], fill=(*col, a // 2), width=3)


def product_climbing(d, cx, cy, r, col, a, ph):
    draw_climbing_gear(d, cx, cy, r, col, a, phase=ph)


def product_phone(d, cx, cy, r, col, a, ph, icon=None):
    """Smartphone with a lit screen and app tiles."""
    w, h = int(r * 0.66), int(r * 1.32)
    d.rounded_rectangle([(cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2)], radius=w // 6,
                        outline=(*col, a), width=5)
    d.rounded_rectangle([(cx - w // 2 + 9, cy - h // 2 + 18), (cx + w // 2 - 9, cy + h // 2 - 18)], radius=w // 10,
                        fill=(*col, 30))
    d.ellipse([(cx - 5, cy - h // 2 + 6), (cx + 5, cy - h // 2 + 14)], fill=(*col, a))
    if icon:
        icon(d, cx, cy, int(r * 0.45), col, a, ph)
        return
    tile = max(6, w // 6)
    for i in range(3):
        for j in range(4):
            x = cx - int(tile * 1.6) + i * int(tile * 1.6)
            y = cy - int(h * 0.30) + j * int(tile * 1.6)
            glow = int(a * (0.45 + 0.55 * abs(math.sin(ph * 2 + i + j))))
            d.rounded_rectangle([(x - tile // 2, y - tile // 2), (x + tile // 2, y + tile // 2)], radius=3,
                                fill=(*col, glow))


def product_render(d, cx, cy, r, col, a, ph):
    """Laptop with a rotating wireframe model on screen."""
    w, h = int(r * 1.5), int(r * 0.92)
    d.rounded_rectangle([(cx - w // 2, cy - h // 2 - int(r * 0.15)), (cx + w // 2, cy + h // 2 - int(r * 0.15))],
                        radius=8, outline=(*col, a), width=5)
    d.polygon([(cx - w // 2 - 24, cy + h // 2 - int(r * 0.15) + 6), (cx + w // 2 + 24, cy + h // 2 - int(r * 0.15) + 6),
               (cx + w // 2 + 44, cy + h // 2 + 14), (cx - w // 2 - 44, cy + h // 2 + 14)], outline=(*col, a), width=4)
    draw_wireframe_cube(d, cx, cy - int(r * 0.15), int(r * 0.42), col, a, phase=ph)


def product_telescope(d, cx, cy, r, col, a, ph):
    """Telescope on a tripod, aimed at the sky."""
    ang = math.radians(-32)
    dx, dy = math.cos(ang), math.sin(ang)
    nx, ny = -dy, dx
    L, T = r * 1.1, r * 0.17
    x0, y0 = cx - dx * L * 0.45, cy - dy * L * 0.45 - int(r * 0.25)
    x1, y1 = x0 + dx * L, y0 + dy * L
    quad = [(x0 - nx * T * 0.8, y0 - ny * T * 0.8), (x1 - nx * T, y1 - ny * T),
            (x1 + nx * T, y1 + ny * T), (x0 + nx * T * 0.8, y0 + ny * T * 0.8)]
    d.polygon([(int(x), int(y)) for x, y in quad], outline=(*col, a), width=5)
    d.ellipse([(int(x1 - T * 1.1), int(y1 - T * 1.1)), (int(x1 + T * 1.1), int(y1 + T * 1.1))], outline=(*col, a), width=4)
    mx, my = int(x0 + dx * L * 0.45), int(y0 + dy * L * 0.45)
    for fx in (-0.55, 0.0, 0.55):
        d.line([(mx, my + int(T)), (mx + int(fx * r), cy + int(r * 0.95))], fill=(*col, a), width=4)


def product_vr(d, cx, cy, r, col, a, ph):
    """VR headset with a strap and a glowing visor."""
    w, h = int(r * 1.4), int(r * 0.66)
    d.arc([(cx - int(w * 0.72), cy - int(h * 0.95)), (cx + int(w * 0.72), cy + int(h * 0.55))],
          start=180, end=360, fill=(*col, a // 2), width=6)
    d.rounded_rectangle([(cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2)], radius=h // 3,
                        outline=(*col, a), width=6)
    d.chord([(cx - int(r * 0.18), cy + int(h * 0.18)), (cx + int(r * 0.18), cy + int(h * 0.75))],
            start=180, end=360, fill=(10, 10, 20, 255))
    sweep = int((w - 40) * ((ph * 0.5) % 1.0))
    d.line([(cx - w // 2 + 20 + sweep, cy - h // 2 + 12), (cx - w // 2 + 20 + sweep, cy + h // 2 - 12)],
           fill=(255, 255, 255, 110), width=6)


def product_popcorn(d, cx, cy, r, col, a, ph):
    """Striped popcorn bucket, overflowing, with kernels popping out."""
    top, bot = cy - int(r * 0.25), cy + int(r * 0.85)
    tw, bw = int(r * 0.62), int(r * 0.45)
    d.polygon([(cx - tw, top), (cx + tw, top), (cx + bw, bot), (cx - bw, bot)], outline=(*col, a), width=5)
    for k in range(-2, 3):
        xt, xb = cx + int(k * tw / 2.5), cx + int(k * bw / 2.5)
        d.line([(xt, top), (xb, bot)], fill=(*col, a // 2), width=8)
    rng = random.Random(5)
    for k in range(13):
        px = cx + int(rng.uniform(-tw, tw))
        py = top - int(rng.uniform(0, r * 0.35))
        pr = int(r * rng.uniform(0.10, 0.16))
        d.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(255, 245, 210, a), outline=(220, 190, 120, a), width=2)
    for k in range(4):
        hop = (ph * 1.3 + k * 0.27) % 1.0
        px = cx + int((k - 1.5) * r * 0.45)
        py = top - int(r * 0.4) - int(math.sin(hop * math.pi) * r * 0.7)
        pr = int(r * 0.09)
        d.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(255, 245, 210, a))


def product_cereal(d, cx, cy, r, col, a, ph):
    """Cereal box with a laughing cartoon mascot, beside a bowl."""
    w, h = int(r * 0.92), int(r * 1.32)
    bx = cx - int(r * 0.35)
    d.rounded_rectangle([(bx - w // 2, cy - h // 2), (bx + w // 2, cy + h // 2)], radius=6, outline=(*col, a), width=5)
    draw_laughing_cartoon(d, bx, cy - int(h * 0.08), int(r * 0.30), col, a, phase=ph)
    d.rectangle([(bx - w // 2 + 10, cy + int(h * 0.30)), (bx + w // 2 - 10, cy + int(h * 0.40))], fill=(*col, a // 2))
    ox, oy = cx + int(r * 0.70), cy + int(r * 0.45)
    d.chord([(ox - int(r * 0.42), oy - int(r * 0.28)), (ox + int(r * 0.42), oy + int(r * 0.32))],
            start=0, end=180, outline=(*col, a), width=5)
    for k in range(5):
        lx = ox - int(r * 0.30) + k * int(r * 0.15)
        d.ellipse([(lx - 9, oy - 12 - 4 * (k % 2)), (lx + 9, oy + 4 - 4 * (k % 2))], outline=(255, 210, 120, a), width=3)


def product_mic(d, cx, cy, r, col, a, ph):
    """Karaoke microphone with notes rising from it."""
    hr = int(r * 0.34)
    hx, hy = cx, cy - int(r * 0.45)
    d.ellipse([(hx - hr, hy - hr), (hx + hr, hy + hr)], outline=(*col, a), width=5)
    for k in range(-2, 3):
        d.line([(hx + k * hr // 3, hy - hr + 6), (hx + k * hr // 3, hy + hr - 6)], fill=(*col, a // 2), width=2)
        d.line([(hx - hr + 6, hy + k * hr // 3), (hx + hr - 6, hy + k * hr // 3)], fill=(*col, a // 2), width=2)
    d.polygon([(hx - int(hr * 0.55), hy + hr), (hx + int(hr * 0.55), hy + hr),
               (hx + int(hr * 0.25), cy + int(r * 0.95)), (hx - int(hr * 0.25), cy + int(r * 0.95))],
              outline=(*col, a), width=5)
    for k in range(3):
        rise = (ph * 0.8 + k * 0.33) % 1.0
        draw_note(d, hx + int(r * 0.55) + k * 18, hy - int(rise * r * 0.9), 8, col, int(a * (1 - rise)))


def product_tickets(d, cx, cy, r, col, a, ph):
    """Two theatre tickets with notched edges and perforations."""
    for k, (dx, ang) in enumerate(((-0.18, -8), (0.18, 7))):
        w, h = int(r * 1.25), int(r * 0.62)
        img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
        g = ImageDraw.Draw(img)
        g.rounded_rectangle([(10, 10), (w + 10, h + 10)], radius=10, outline=(*col, a), width=5)
        for yy in (10, h + 10):
            g.ellipse([(int(w * 0.70) - 10, yy - 10), (int(w * 0.70) + 10, yy + 10)], fill=(0, 0, 0, 0), outline=(*col, a), width=4)
        for yy in range(26, h, 14):
            g.line([(int(w * 0.70) + 10, yy), (int(w * 0.70) + 10, yy + 6)], fill=(*col, a), width=2)
        sx, sy, sr = int(w * 0.35) + 10, h // 2 + 10, int(h * 0.22)
        star = [(sx + int(sr * (1 if q % 2 == 0 else 0.45) * math.cos(math.pi * q / 5 - math.pi / 2)),
                 sy + int(sr * (1 if q % 2 == 0 else 0.45) * math.sin(math.pi * q / 5 - math.pi / 2))) for q in range(10)]
        g.polygon(star, fill=(*col, a))
        img = img.rotate(ang, resample=Image.BICUBIC, expand=True)
        d._image.paste(img, (cx + int(dx * r) - img.width // 2, cy - img.height // 2 + k * int(r * 0.12)), img)


def product_doorbell(d, cx, cy, r, col, a, ph):
    """Smart doorbell camera with a recording light."""
    w, h = int(r * 0.48), int(r * 1.25)
    d.rounded_rectangle([(cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2)], radius=w // 2, outline=(*col, a), width=5)
    lr = int(w * 0.32)
    ly = cy - int(h * 0.22)
    d.ellipse([(cx - lr, ly - lr), (cx + lr, ly + lr)], outline=(*col, a), width=5)
    d.ellipse([(cx - lr // 3, ly - lr // 3), (cx + lr // 3, ly + lr // 3)], fill=(*col, a))
    br = int(w * 0.24)
    by = cy + int(h * 0.25)
    pulse = int(br + 10 + 8 * math.sin(ph * 5))
    d.ellipse([(cx - pulse, by - pulse), (cx + pulse, by + pulse)], outline=(*col, a // 3), width=2)
    d.ellipse([(cx - br, by - br), (cx + br, by + br)], outline=(*col, a), width=4)
    if int(ph * 2) % 2 == 0:
        d.ellipse([(cx + w // 2 - 18, cy - h // 2 + 12), (cx + w // 2 - 8, cy - h // 2 + 22)], fill=(255, 60, 60, a))


def _scales(d, cx, cy, r, col, a, ph):
    tilt = int(r * 0.12 * math.sin(ph * 1.5))
    d.line([(cx, cy - int(r * 0.75)), (cx, cy + int(r * 0.80))], fill=(*col, a), width=4)
    d.line([(cx - int(r * 0.42), cy + int(r * 0.80)), (cx + int(r * 0.42), cy + int(r * 0.80))], fill=(*col, a), width=4)
    lx, ly = cx - int(r * 0.85), cy - int(r * 0.55) + tilt
    rx, ry = cx + int(r * 0.85), cy - int(r * 0.55) - tilt
    d.line([(lx, ly), (rx, ry)], fill=(*col, a), width=4)
    for px, py in ((lx, ly), (rx, ry)):
        d.line([(px, py), (px - int(r * 0.22), py + int(r * 0.45))], fill=(*col, a), width=2)
        d.line([(px, py), (px + int(r * 0.22), py + int(r * 0.45))], fill=(*col, a), width=2)
        d.chord([(px - int(r * 0.26), py + int(r * 0.30)), (px + int(r * 0.26), py + int(r * 0.60))],
                start=0, end=180, outline=(*col, a), width=3)


def product_legal_app(d, cx, cy, r, col, a, ph):
    """Phone running a legal-advice app — scales of justice on screen."""
    product_phone(d, cx, cy, r, col, a, ph, icon=_scales)


def product_audiobook(d, cx, cy, r, col, a, ph):
    """Headphones over an open book, with sound waves."""
    w, h = int(r * 0.95), int(r * 0.55)
    by = cy + int(r * 0.30)
    for side in (-1, 1):
        ox = cx + side * w
        d.polygon([(cx, by - int(h * 0.35)), (ox, by - int(h * 0.55)), (ox, by + int(h * 0.55)), (cx, by + int(h * 0.40))],
                  outline=(*col, a), width=4)
        for k in (1, 2, 3):
            f = k / 4
            d.line([(cx + side * int(w * 0.18), by - int(h * 0.35) + int(h * 0.75 * f)),
                    (cx + side * int(w * 0.80), by - int(h * 0.55) + int(h * 1.0 * f))],
                   fill=(*col, a // 2), width=2)
    d.arc([(cx - int(r * 0.80), cy - int(r * 1.05)), (cx + int(r * 0.80), cy + int(r * 0.35))],
          start=190, end=350, fill=(*col, a), width=7)
    for side in (-1, 1):
        ex = cx + side * int(r * 0.78)
        d.rounded_rectangle([(ex - 16, cy - int(r * 0.48)), (ex + 16, cy - int(r * 0.08))], radius=10, outline=(*col, a), width=4)
        for k in range(2):
            rr = 26 + k * 16 + int(6 * math.sin(ph * 4))
            d.arc([(ex - rr, cy - int(r * 0.28) - rr), (ex + rr, cy - int(r * 0.28) + rr)],
                  start=(-40 if side > 0 else 140), end=(40 if side > 0 else 220), fill=(*col, a // 2), width=2)


# ── pilot-2 tweaks: moods and products ───────────────────────────────────────

def draw_laugh_marks(draw, cx, cy, spread, col, alpha, phase=0.0, n=3, size=30):
    """Bobbing "ha" marks — visible laughter."""
    for k in range(n):
        tw = 0.55 + 0.45 * math.sin(phase * 4 + k * 2.1)
        x = cx - spread + k * spread
        y = cy - int(10 * (k % 2)) + int(4 * math.sin(phase * 6 + k))
        draw.text((x, y), "ha", fill=(*col, int(alpha * tw)), font=try_font(size))


def mood_funfair(d, t, acc):
    d.ellipse([(W - 230, 40), (W - 110, 160)], fill=(255, 235, 140, 210))
    for k in range(12):
        ang = math.pi * 2 * k / 12 + t * 0.3
        d.line([(W - 170 + int(70 * math.cos(ang)), 100 + int(70 * math.sin(ang))),
                (W - 170 + int(105 * math.cos(ang)), 100 + int(105 * math.sin(ang)))], fill=(255, 235, 140, 150), width=4)
    cols = [(255, 80, 80), (80, 170, 255), (255, 220, 60), (120, 220, 120)]
    for row, y0 in enumerate((70, 120)):
        for k in range(18):
            x = 40 + k * 70 + (35 if row else 0)
            sag = int(14 * math.sin(math.pi * (k % 6) / 6))
            d.polygon([(x, y0 + sag), (x + 40, y0 + sag), (x + 20, y0 + sag + 30)], fill=(*cols[(k + row) % 4], 200))
    for k, x in enumerate((90, W - 230)):
        y = H - 190 + int(18 * math.sin(t * 3 + k))
        d.text((x + int(14 * math.sin(t * 2 + k)), y), "WHOOO!", fill=(255, 255, 255, 190), font=try_font(34))


def mood_extreme(d, t, acc):
    draw_speed_streaks(d, t, (255, 170, 80), 140, n=14, seed=5)
    d.polygon([(0, H), (260, H), (260, H - 120)], fill=(*shade(acc, 0.5), 230))
    hop = (t * 0.45) % 1.0
    x = 220 + int(hop * 520)
    y = H - 130 - int(math.sin(hop * math.pi) * 260)
    rc = (255, 205, 160, 235)
    for wx in (x - 40, x + 40):
        d.ellipse([(wx - 24, y - 24), (wx + 24, y + 24)], outline=rc, width=5)
    d.line([(x - 40, y), (x, y - 38), (x + 40, y)], fill=rc, width=6)
    d.line([(x, y - 38), (x - 6, y - 98)], fill=rc, width=8)
    d.ellipse([(x - 24, y - 136), (x + 12, y - 100)], fill=rc)
    for k, (ex, ey) in enumerate(((0.88, 0.22), (0.82, 0.74))):
        pulse = 0.6 + 0.4 * math.sin(t * 4 + k * 2)
        draw_explosion(d, int(W * ex), int(H * ey), int(55 * pulse), (255, 170, 60), 150, phase=t + k)


def _runner(d, x, y, s, ph, col):
    swing = math.sin(ph * 12)
    d.ellipse([(x - s * 0.18, y - s * 1.05), (x + s * 0.18, y - s * 0.7)], fill=col)
    d.line([(x, y - s * 0.7), (x + s * 0.12, y - s * 0.15)], fill=col, width=6)
    for sg in (1, -1):
        d.line([(x + s * 0.12, y - s * 0.15), (x + s * 0.12 + sg * swing * s * 0.4, y + s * 0.35)], fill=col, width=6)
        d.line([(x + s * 0.04, y - s * 0.55), (x + s * 0.04 - sg * swing * s * 0.35, y - s * 0.2)], fill=col, width=5)


def mood_race(d, t, acc):
    for k in range(5):
        y0 = H - 230 + k * 50
        d.line([(0, y0), (W, y0 + 28)], fill=(255, 255, 255, 60), width=2)
    fx = W - 220
    for k in range(12):
        c = (255, 255, 255, 180) if k % 2 == 0 else (30, 30, 30, 180)
        d.rectangle([(fx, H - 240 + k * 20), (fx + 14, H - 220 + k * 20)], fill=c)
    for k in range(3):
        x = int(((t * 160 + k * 230) % (W + 200)) - 100)
        _runner(d, x, H - 40 - k * 60, 110, t + k * 0.4, (*tint(acc, 0.55), 210))
    rng = random.Random(9)
    for _ in range(140):
        x, y = rng.uniform(0, W), rng.uniform(20, 110)
        d.ellipse([(x - 3, y - 3), (x + 3, y + 3)], fill=(*tint(acc, 0.5), 110))


def mood_detective(d, t, acc):
    mood_rain(d, t, acc)
    mx, my, mr = 150, H - 200, 70
    d.ellipse([(mx - mr, my - mr), (mx + mr, my + mr)], outline=(*tint(acc, 0.4), 150), width=6)
    d.line([(mx + int(mr * 0.7), my + int(mr * 0.7)), (mx + 140, my + 140)], fill=(*tint(acc, 0.4), 150), width=12)
    for k in range(4):
        rr = 12 + k * 11
        d.arc([(mx - rr, my - int(rr * 1.3)), (mx + rr, my + int(rr * 1.3))], start=200, end=520, fill=(*tint(acc, 0.4), 120), width=2)
    hx, hy = W - 330, H - 300
    d.ellipse([(hx - 26, hy - 26), (hx + 26, hy + 26)], fill=(10, 8, 6, 230))
    d.line([(hx - 54, hy - 22), (hx + 54, hy - 22)], fill=(10, 8, 6, 230), width=9)
    d.rectangle([(hx - 30, hy - 54), (hx + 30, hy - 22)], fill=(10, 8, 6, 230))
    d.polygon([(hx - 40, hy + 26), (hx + 40, hy + 26), (hx + 70, H), (hx - 70, H)], fill=(10, 8, 6, 230))


def mood_crime_tape(d, t, acc):
    mood_rain(d, t, acc)
    y = H - 18
    d.rectangle([(0, y - 22), (W, y + 18)], fill=(240, 200, 40, 235))
    off = int(t * 30) % 420
    for k in range(-420, W + 420, 420):
        d.text((k + off, y - 13), "POLICE LINE   DO NOT CROSS", fill=(20, 20, 20, 255), font=try_font(22))


def mood_burglary(d, t, acc):
    mood_rain(d, t, acc)
    for k in range(5):
        x = 60 + k * 260
        d.rectangle([(x, H - 170), (x + 200, H)], fill=(14, 16, 24, 255))
        d.polygon([(x - 10, H - 170), (x + 100, H - 250), (x + 210, H - 170)], fill=(14, 16, 24, 255))
        if (k + int(t)) % 3:
            d.rectangle([(x + 30, H - 130), (x + 70, H - 90)], fill=(255, 210, 120, 140))
    bx = 120 + int((t * 40) % 900)
    d.ellipse([(bx - 18, H - 220), (bx + 18, H - 184)], fill=(4, 4, 6, 255))
    d.polygon([(bx - 30, H - 184), (bx + 30, H - 184), (bx + 38, H - 110), (bx - 38, H - 110)], fill=(4, 4, 6, 255))
    d.ellipse([(bx + 26, H - 190), (bx + 80, H - 136)], fill=(4, 4, 6, 255))
    lit = (255, 40, 40) if int(t * 4) % 2 == 0 else (40, 90, 255)
    for rr, al in ((110, 45), (70, 90)):
        d.ellipse([(120 - rr, 90 - rr), (120 + rr, 90 + rr)], fill=(*lit, al))
    d.chord([(84, 54), (156, 126)], 180, 360, fill=(*lit, 255))
    d.rectangle([(76, 90), (164, 106)], fill=(60, 60, 70, 255))
    d.text((120, 128), "POLICE", fill=(255, 255, 255, 230), font=try_font(22), anchor="mm")


def mood_comedy_show(d, t, acc):
    mood_spotlight(d, t, acc)
    for k in range(16):
        x = 40 + k * 80
        bob = int(6 * abs(math.sin(t * 8 + k)))
        d.ellipse([(x - 22, H - 44 - bob), (x + 22, H - 2 - bob)], fill=(14, 10, 4, 255))
        d.rectangle([(x - 32, H - 16), (x + 32, H)], fill=(14, 10, 4, 255))
    draw_laugh_marks(d, 150, H - 120, 50, (255, 240, 200), 210, phase=t)
    draw_laugh_marks(d, W - 250, H - 120, 50, (255, 240, 200), 210, phase=t + 1)


def mood_singalong(d, t, acc):
    mood_music(d, t, acc)
    bx, by, br = W // 2, 50, 34
    d.line([(bx, 0), (bx, by - br)], fill=(220, 220, 220, 200), width=3)
    d.ellipse([(bx - br, by - br), (bx + br, by + br)], fill=(200, 200, 215, 230))
    for k in range(-2, 3):
        d.line([(bx - br + 6, by + k * 12), (bx + br - 6, by + k * 12)], fill=(120, 120, 140, 230), width=2)
    for k in range(10):
        ang = math.pi * 2 * k / 10 + t * 1.2
        d.line([(bx, by), (bx + int(420 * math.cos(ang)), by + int(420 * abs(math.sin(ang))))],
               fill=(*tint(acc, 0.6), 22), width=18)
    for k, x in enumerate((180, W - 180)):
        bob = int(8 * math.sin(t * 6 + k))
        d.ellipse([(x - 30, H - 230 + bob), (x + 30, H - 170 + bob)], fill=(*shade(acc, 0.3), 230))
        d.polygon([(x - 46, H - 170 + bob), (x + 46, H - 170 + bob), (x + 60, H), (x - 60, H)], fill=(*shade(acc, 0.3), 230))
        d.chord([(x - 12, H - 205 + bob), (x + 12, H - 180 + bob)], start=0, end=180, fill=(255, 255, 255, 220))


def product_coaster(d, cx, cy, r, col, a, ph):
    """Rollercoaster: a loop, a peak and a steep drop, with a car racing round."""
    pts = []
    def seg(p0, p1, n=10):
        for i in range(n):
            f = i / n
            pts.append((p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f))
    lx, ly, lr = cx - 0.2 * r, cy - 0.05 * r, 0.45 * r
    seg((cx - 1.25 * r, cy + 0.6 * r), (lx, ly + lr))
    for i in range(37):
        ang = math.pi / 2 + 2 * math.pi * i / 36
        pts.append((lx - lr * math.cos(ang - math.pi / 2) * 0 + lr * math.cos(ang), ly + lr * math.sin(ang)))
    seg((lx, ly + lr), (cx + 0.45 * r, cy + 0.5 * r))
    seg((cx + 0.45 * r, cy + 0.5 * r), (cx + 0.85 * r, cy - 0.8 * r))
    seg((cx + 0.85 * r, cy - 0.8 * r), (cx + 1.25 * r, cy + 0.6 * r))
    ipts = [(int(x), int(y)) for x, y in pts]
    for k in range(0, len(ipts), 6):
        x, y = ipts[k]
        if y < cy + 0.8 * r:
            d.line([(x, y), (x, int(cy + 0.85 * r))], fill=(*col, a // 3), width=3)
    d.line(ipts, fill=(*col, a), width=6, joint="curve")
    i = int(((ph * 0.35) % 1.0) * (len(ipts) - 1))
    x, y = ipts[i]
    d.rounded_rectangle([(x - 18, y - 16), (x + 18, y + 4)], radius=6, fill=(255, 80, 80, a))
    for k in (-8, 8):
        d.line([(x + k, y - 16), (x + k - 4, y - 32)], fill=(255, 255, 255, a), width=3)


def product_magazine(d, cx, cy, r, col, a, ph):
    """Crime-fiction magazine cover: masthead, a fedora silhouette, cover lines."""
    w, h = int(r * 1.15), int(r * 1.5)
    x0, y0 = cx - w // 2, cy - h // 2
    d.rectangle([(x0, y0), (x0 + w, y0 + h)], fill=(18, 14, 12, 255), outline=(*col, a), width=5)
    d.rectangle([(x0, y0), (x0 + w, y0 + int(h * 0.17))], fill=(*col, a))
    d.text((cx, y0 + int(h * 0.085)), "CASEROOM", fill=(20, 10, 10, a), font=try_font(max(10, int(r * 0.17))), anchor="mm")
    hx, hy = cx, cy - int(h * 0.02)
    d.ellipse([(hx - int(r * 0.13), hy - int(r * 0.13)), (hx + int(r * 0.13), hy + int(r * 0.13))], fill=(*col, a))
    d.line([(hx - int(r * 0.3), hy - int(r * 0.11)), (hx + int(r * 0.3), hy - int(r * 0.11))], fill=(*col, a), width=6)
    d.rectangle([(hx - int(r * 0.15), hy - int(r * 0.27)), (hx + int(r * 0.15), hy - int(r * 0.11))], fill=(*col, a))
    d.polygon([(hx - int(r * 0.2), hy + int(r * 0.13)), (hx + int(r * 0.2), hy + int(r * 0.13)),
               (hx + int(r * 0.34), hy + int(r * 0.42)), (hx - int(r * 0.34), hy + int(r * 0.42))], fill=(*col, a))
    for k in range(3):
        yy = y0 + int(h * 0.78) + k * int(h * 0.06)
        d.line([(x0 + int(w * 0.12), yy), (x0 + int(w * (0.88 - 0.15 * k)), yy)], fill=(*col, a), width=4)
    fx, fy = x0 + int(w * 0.82), y0 + int(h * 0.3)
    for k in range(4):
        rr = 5 + k * 5
        d.arc([(fx - rr, fy - int(rr * 1.3)), (fx + rr, fy + int(rr * 1.3))], start=200, end=520, fill=(*col, a), width=2)


# ── the template ─────────────────────────────────────────────────────────────

def cta_pill(img, text, cy, acc):
    font = try_font(28)
    box = font.getbbox(text)
    tw = box[2] - box[0]
    pad_x, ph = 34, 54
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle([(W // 2 - tw // 2 - pad_x, cy - ph // 2), (W // 2 + tw // 2 + pad_x, cy + ph // 2)],
                                         radius=ph // 2, fill=(*acc, 210), outline=(255, 255, 255, 200), width=2)
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    return glow_text(img, text, W // 2, cy, font, (255, 255, 255, 255), glow_color=acc, glow_r=6)


def product_ad(spec):
    acc, bright = spec["acc"], spec.get("bright", 1.0)
    pcol = spec.get("pcol", tint(acc, 0.45))
    bgs = [[shade(acc, 0.06 * bright), shade(acc, 0.17 * bright), shade(acc, 0.08 * bright)],
           [shade(acc, 0.08 * bright), shade(acc, 0.21 * bright)],
           [shade(acc, 0.06 * bright), shade(acc, 0.19 * bright)]]
    size = spec.get("size", 135)

    def frame(fi, t):
        scene = 0 if t < 5.0 else 1 if t < 10.0 else 2
        bg = gradient_bg(bgs[scene]).convert("RGB")
        d = ImageDraw.Draw(bg, "RGBA")  # blends only onto an RGB canvas
        spec["mood"](d, t, acc)
        if scene == 0:
            prog = ease_back(min(t / 2.6, 1.0))
            r = int(size * 0.9 * prog)
            if r >= 40:  # the first frames of the scale-in are too small to draw
                spec["product"](d, W // 2, H // 2 - 115, r, pcol, int(230 * min(prog, 1.0)), t)
            bg = bg if t < 2.0 else glow_text(bg, spec["brand"], W // 2, H // 2 + 75, try_font(62),
                                               (255, 255, 255, int(255 * min((t - 2.0) / 0.6, 1.0))), glow_color=acc, glow_r=18)
        elif scene == 1:
            spec["product"](d, W // 2, H // 2 + 75, size, pcol, 230, t)
            bg = glow_text(bg, spec["benefit"], W // 2, H // 2 - 165, try_font(46),
                           (255, 255, 255, 235), glow_color=acc, glow_r=16)
        else:
            spec["product"](d, W // 2, 205, int(size * 0.9), pcol, 235, t)
            bg = glow_text(bg, spec["brand"], W // 2, 425, try_font(64), (255, 255, 255, 255), glow_color=acc, glow_r=22)
            bg = glow_text(bg, spec["tagline"], W // 2, 485, try_font(30), (*tint(acc, 0.7), 235), glow_color=acc, glow_r=10)
            bg = cta_pill(bg, spec["cta"], H - 82, shade(acc, 0.85))
        return bg

    frame.__doc__ = f"{spec['brand']} — {spec['what']}"
    return frame


SPECS = {
    # Action and thrills
    "ad_thrill_gravecrest": dict(brand="THUNDERDROP", what="rollercoaster park", acc=(255, 160, 30), mood=mood_funfair, bright=3.4,
        product=product_coaster, size=185, benefit="Europe's fastest drop. Can you take it?",
        tagline="Feel the rush. Scream if you want to.", cta="Book tickets · from €39"),
    "ad_thrill_adrenaline": dict(brand="ADRENALINE", what="energy drink", acc=(230, 70, 30), mood=mood_extreme, bright=1.6,
        product=product_can, benefit="Pure rush in every can.",
        tagline="Fuel for your biggest jumps.", cta="Grab a can"),
    "ad_thrill_apex": dict(brand="APEX", what="running shoes", acc=(150, 205, 50), mood=mood_race, bright=1.8,
        product=product_shoe, benefit="Fastest off the line.",
        tagline="Race-day speed, every day.", cta="Shop now · €89"),
    "ad_thrill_ranger": dict(brand="RANGER", what="climbing gear", acc=(235, 110, 45), mood=mood_heights,
        product=product_climbing, benefit="Tested on the toughest walls.",
        tagline="Gear you can trust at the top.", cta="Shop the range"),
    # Science and discovery
    "ad_intel_synapse": dict(brand="SYNAPSE", what="smartphone", acc=(0, 205, 255), mood=mood_circuit,
        product=product_phone, benefit="A chip that learns how you work.",
        tagline="The phone that thinks ahead.", cta="Pre-order today"),
    "ad_intel_renderlab": dict(brand="RENDERLAB", what="3D animation software", acc=(110, 225, 140), mood=mood_grid,
        product=product_render, benefit="Build any world, frame by frame.",
        tagline="Pro 3D tools on your laptop.", cta="Free 30-day trial"),
    "ad_intel_curiosity": dict(brand="CURIOSITY", what="home telescope", acc=(32, 184, 160), mood=mood_space,
        product=product_telescope, benefit="See Saturn's rings from your garden.",
        tagline="Your first telescope, set up in minutes.", cta="Order now · €149"),
    "ad_intel_horizon": dict(brand="HORIZON", what="VR headset", acc=(144, 96, 224), mood=mood_space,
        product=product_vr, benefit="Step into another world.",
        tagline="Wireless VR. No cables, no limits.", cta="Try it in store"),
    # Comedy and lifestyle
    "ad_chame_chuckle": dict(brand="CHUCKLE", what="popcorn", acc=(255, 120, 90), mood=mood_party, bright=1.6,
        product=product_popcorn, benefit="Movie night just got louder.",
        tagline="Sweet, salty, and gone in minutes.", cta="In stores now"),
    "ad_chame_toonbox": dict(brand="TOONBOX", what="breakfast cereal", acc=(96, 64, 255), mood=mood_party, bright=1.5,
        product=product_cereal, benefit="The breakfast that grins back!",
        tagline="Crunchy loops, goofy mornings.", cta="Find it in the cereal aisle"),
    "ad_chame_storybook": dict(brand="SINGALONG", what="karaoke machine", acc=(255, 120, 170), mood=mood_singalong, bright=2.3,
        product=product_mic, benefit="Everyone's a star. Even Dad.",
        tagline="Sing, dance and laugh together.", cta="Order now · €59"),
    "ad_chame_stagecraft": dict(brand="STAGECRAFT", what="theatre tickets", acc=(212, 160, 32), mood=mood_comedy_show, bright=1.6,
        product=product_tickets, benefit="The funniest night out in town.",
        tagline="Comedy shows and musicals, live on stage.", cta="Book now"),
    # Drama and crime
    "ad_invest_deadlines": dict(brand="NIGHTWATCH", what="smart doorbell camera", acc=(96, 128, 176), mood=mood_burglary,
        product=product_doorbell, benefit="Catch burglars in the act.",
        tagline="Keep your street safe, day or night.", cta="Order now · €99"),
    "ad_invest_tribunal": dict(brand="TRIBUNAL", what="legal-advice app", acc=(214, 150, 70), mood=mood_court,
        product=product_legal_app, benefit="Wronged? Know your rights.",
        tagline="Legal advice in minutes, not months.", cta="Download free"),
    "ad_invest_whodunit": dict(brand="WHODUNIT", what="detective audiobooks", acc=(214, 162, 40), mood=mood_detective,
        product=product_audiobook, benefit="Solve the case before the detective does.",
        tagline="Detective mysteries to listen to anywhere.", cta="First month free"),
    "ad_invest_caseroom": dict(brand="CASEROOM", what="crime-fiction magazine", acc=(190, 30, 40), mood=mood_crime_tape,
        product=product_magazine, pcol=(235, 215, 200), size=165, benefit="A new case to crack every month.",
        tagline="Gripping crime stories, delivered to your door.", cta="Subscribe · €4.99 an issue"),
}


ADS = [
    # (ad_id,                  frame_fn,                                  accent_rgb,      badge, category)
    ("ad_thrill_gravecrest", product_ad(SPECS["ad_thrill_gravecrest"]), (255, 160,  30), "T", "thrill_seeker"),
    ("ad_thrill_ranger",     product_ad(SPECS["ad_thrill_ranger"]),     (235, 110,  45), "R", "thrill_seeker"),
    ("ad_thrill_adrenaline", product_ad(SPECS["ad_thrill_adrenaline"]), (230,  70,  30), "A", "thrill_seeker"),
    ("ad_thrill_apex",       product_ad(SPECS["ad_thrill_apex"]),       (150, 205,  50), "A", "thrill_seeker"),
    ("ad_intel_curiosity",   product_ad(SPECS["ad_intel_curiosity"]),   ( 32, 184, 160), "C", "intellectual_explorer"),
    ("ad_intel_horizon",     product_ad(SPECS["ad_intel_horizon"]),     (144,  96, 224), "H", "intellectual_explorer"),
    ("ad_intel_renderlab",   product_ad(SPECS["ad_intel_renderlab"]),   (110, 225, 140), "R", "intellectual_explorer"),
    ("ad_intel_synapse",     product_ad(SPECS["ad_intel_synapse"]),     (  0, 205, 255), "S", "intellectual_explorer"),
    ("ad_chame_toonbox",     product_ad(SPECS["ad_chame_toonbox"]),     ( 96,  64, 255), "T", "content_chameleon"),
    ("ad_chame_stagecraft",  product_ad(SPECS["ad_chame_stagecraft"]),  (212, 160,  32), "S", "content_chameleon"),
    ("ad_chame_chuckle",     product_ad(SPECS["ad_chame_chuckle"]),     (255, 120,  90), "C", "content_chameleon"),
    ("ad_chame_storybook",   product_ad(SPECS["ad_chame_storybook"]),   (255, 120, 170), "S", "content_chameleon"),
    ("ad_invest_whodunit",   product_ad(SPECS["ad_invest_whodunit"]),   (214, 162,  40), "W", "investigative_viewer"),
    ("ad_invest_deadlines",  product_ad(SPECS["ad_invest_deadlines"]),  ( 96, 128, 176), "N", "investigative_viewer"),
    ("ad_invest_caseroom",   product_ad(SPECS["ad_invest_caseroom"]),   (190,  30,  40), "C", "investigative_viewer"),
    ("ad_invest_tribunal",   product_ad(SPECS["ad_invest_tribunal"]),   (214, 150,  70), "T", "investigative_viewer"),
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
