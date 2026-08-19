#!/usr/bin/env python3
"""
generate_ads_v2.py — Alternative synthetic ad set with richer visual language.

12 ads, 1280×720, 15 s @ 20 fps.  Same viewer-profile relevance mapping
as generate_ads.py but with new brand identities, product-specific objects
drawn in every scene, glow text (GaussianBlur halo), and multi-layer
backgrounds.

Viewer-profile → relevant ad pool
  thrill_seeker        → ad_thrill_vortex, ad_thrill_freefall, ad_thrill_blitzrace
  intellectual_explorer → ad_intel_neuralpath, ad_intel_solarsail, ad_intel_archivum
  content_chameleon    → ad_chame_velvetbox, ad_chame_groovepod, ad_chame_zestplate
  investigative_viewer → ad_invest_cipher, ad_invest_tribunal, ad_invest_eyewitness

Run:
    pip install Pillow
    python scripts/generate_ads_v2.py
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


# ─────────────────────────────────────────────────────────────────────────────
# Core utilities (shared with v1, extended)
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


def dot_grid_overlay(t, acc, spacing=55, radius=2, alpha=30):
    """Animated dot-grid layer — dots breathe in phase with t."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for gy in range(0, H + spacing, spacing):
        for gx in range(0, W + spacing, spacing):
            pulse = 0.5 + 0.5 * math.sin(t * 1.2 + gx * 0.01 + gy * 0.015)
            a = int(alpha * pulse)
            r = int(radius * (0.7 + 0.3 * pulse))
            d.ellipse([gx - r, gy - r, gx + r, gy + r], fill=(*acc, a))
    return ov


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


def glow_text(base: Image.Image, text: str, cx: int, cy: int,
              font, color, glow_color=None, glow_r: int = 14) -> Image.Image:
    """Render text with a soft Gaussian glow halo."""
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


def _text_origin(img, text, cx, cy, font):
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2, cy - (bbox[3] - bbox[1]) // 2)


# ─────────────────────────────────────────────────────────────────────────────
# Global post-processing (vignette, grain, badge, CTA glow, sweep, tint)
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

        # Audio
        audio_path = None
        if category:
            try:
                import sys as _sys
                _sys.path.insert(0, os.path.dirname(__file__))
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

def draw_camera_lens(draw, cx, cy, r, col, alpha):
    """Action-camera body with multi-ring lens."""
    bw, bh = int(r * 2.2), int(r * 1.5)
    draw.rounded_rectangle(
        [cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2],
        radius=10, outline=(*col, alpha), width=4)
    for ring_r, ring_a in [(int(r * 0.65), alpha),
                            (int(r * 0.44), alpha // 2),
                            (int(r * 0.22), alpha // 3)]:
        draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                     outline=(*col, ring_a), width=3)
    draw.ellipse([cx - int(r * 0.12), cy - int(r * 0.12),
                  cx + int(r * 0.12), cy + int(r * 0.12)],
                 fill=(*col, alpha))
    # mount bumps top
    for mx in [cx - bw // 3, cx, cx + bw // 3]:
        draw.ellipse([mx - 5, cy - bh // 2 - 7, mx + 5, cy - bh // 2 + 1],
                     fill=(*col, alpha))


def draw_parachute(draw, cx, cy, r, col, alpha, sway=0.0):
    """Parachute canopy + rigging lines."""
    # Canopy: arc
    cx = int(cx + sway)
    draw.arc([cx - r, cy - r // 2, cx + r, cy + r // 2],
             start=200, end=340, fill=(*col, alpha), width=6)
    # Panels
    for k in range(5):
        angle = math.radians(200 + k * 28)
        ex = cx + int(math.cos(angle) * r)
        ey = cy + int(math.sin(angle) * (r // 2))
        draw.line([(cx, cy + r // 4), (ex, ey)], fill=(*col, alpha // 2), width=2)
    # Harness point
    draw.line([(cx - 20, cy + r // 4), (cx, cy + r + 30)],
              fill=(*col, alpha), width=3)
    draw.line([(cx + 20, cy + r // 4), (cx, cy + r + 30)],
              fill=(*col, alpha), width=3)
    # Person
    draw.ellipse([cx - 12, cy + r + 22, cx + 12, cy + r + 46],
                 outline=(*col, alpha), width=3)


def draw_race_car(draw, cx, cy, scale, col, alpha, angle_deg=0.0):
    """Simple race car side silhouette."""
    angle = math.radians(angle_deg)
    hw = int(scale * 1.1)
    hh = int(scale * 0.38)
    # Body
    pts = [
        (cx - hw, cy + hh),
        (cx - hw + int(scale * 0.3), cy - hh),
        (cx + int(scale * 0.1), cy - hh * 2),
        (cx + hw - int(scale * 0.2), cy - hh),
        (cx + hw, cy + hh),
    ]
    draw.polygon(pts, outline=(*col, alpha), fill=(*col, alpha // 5))
    # Wheels
    wr = int(scale * 0.32)
    for wx in [cx - int(scale * 0.6), cx + int(scale * 0.6)]:
        wy = cy + hh - wr // 2
        draw.ellipse([wx - wr, wy - wr, wx + wr, wy + wr],
                     outline=(*col, alpha), width=4)
        draw.ellipse([wx - wr // 3, wy - wr // 3, wx + wr // 3, wy + wr // 3],
                     fill=(*col, alpha // 2))
    # Exhaust flame
    flame_a = clamp(abs(math.sin(angle * 5)) * alpha)
    if flame_a > 10:
        draw.ellipse([cx + hw - 5, cy + hh // 2 - 8,
                      cx + hw + 30, cy + hh // 2 + 8],
                     fill=(255, 160, 30, flame_a))


def draw_neural_net(draw, cx, cy, r, col, alpha, prog=1.0):
    """3-layer neural network graph."""
    layers = [3, 5, 3]
    coords = []
    total_layers = len(layers)
    for li, n in enumerate(layers):
        layer_x = cx - r + int(li * 2 * r / (total_layers - 1))
        lc = []
        for ni in range(n):
            ny = cy - int((n - 1) * r * 0.28) + ni * int(r * 0.56)
            lc.append((layer_x, ny))
        coords.append(lc)
    # Connections
    max_conn = int(prog * (sum(layers[i] * layers[i + 1]
                               for i in range(len(layers) - 1))))
    conn_drawn = 0
    for li in range(len(coords) - 1):
        if conn_drawn >= max_conn:
            break
        for n0 in coords[li]:
            for n1 in coords[li + 1]:
                if conn_drawn >= max_conn:
                    break
                draw.line([n0, n1], fill=(*col, alpha // 3), width=1)
                conn_drawn += 1
    # Nodes
    n_nodes = int(prog * sum(layers))
    node_drawn = 0
    for lc in coords:
        for nx, ny in lc:
            if node_drawn >= n_nodes:
                break
            draw.ellipse([nx - 10, ny - 10, nx + 10, ny + 10],
                         fill=(*col, alpha), outline=(255, 255, 255, alpha // 2), width=2)
            node_drawn += 1


def draw_solar_system(draw, cx, cy, t, col, alpha):
    """Animated solar system with 3 orbiting planets."""
    # Sun
    sun_r = 50
    for sr in range(sun_r + 20, sun_r - 1, -3):
        a = int(alpha * (1 - (sr - sun_r) / 20) * 0.6)
        draw.ellipse([cx - sr, cy - sr, cx + sr, cy + sr],
                     fill=(255, 200, 60, a))
    draw.ellipse([cx - sun_r, cy - sun_r, cx + sun_r, cy + sun_r],
                 fill=(255, 220, 80, alpha))
    # Orbits + planets
    orbits = [(140, 0.4, 10, (100, 180, 255)),
              (220, 0.25, 14, col),
              (310, 0.15, 8, (255, 140, 60))]
    for orbit_r, speed, planet_r, pcol in orbits:
        draw.ellipse([cx - orbit_r, cy - orbit_r // 3,
                      cx + orbit_r, cy + orbit_r // 3],
                     outline=(*col, alpha // 5), width=1)
        angle = t * speed * math.pi * 2
        px = cx + int(math.cos(angle) * orbit_r)
        py = cy + int(math.sin(angle) * orbit_r // 3)
        draw.ellipse([px - planet_r, py - planet_r,
                      px + planet_r, py + planet_r],
                     fill=(*pcol, alpha))


def draw_scroll(draw, cx, cy, w, h, col, alpha, unroll=1.0):
    """Unfurling scroll."""
    uw = int(w * unroll)
    # Body
    draw.rounded_rectangle([cx - uw // 2, cy - h // 2,
                             cx + uw // 2, cy + h // 2],
                            radius=6, outline=(*col, alpha), width=3,
                            fill=(*col, alpha // 8))
    # End rolls
    for side in [-1, 1]:
        ex = cx + side * uw // 2
        draw.ellipse([ex - 14, cy - h // 2, ex + 14, cy + h // 2],
                     outline=(*col, alpha), fill=(*col, alpha // 6), width=3)
    # Text lines on scroll
    if unroll > 0.3:
        for li in range(4):
            lx0 = cx - uw // 2 + 30
            lx1 = cx + uw // 2 - 30
            ly = cy - h // 4 + li * (h // 5)
            la = int(alpha * min((unroll - 0.3) / 0.7, 1.0))
            draw.line([(lx0, ly), (lx1, ly)], fill=(*col, la), width=2)


def draw_gift_box(draw, cx, cy, s, col, alpha, open_frac=0.0):
    """Gift box with lid opening."""
    # Box body
    draw.rectangle([cx - s, cy, cx + s, cy + s],
                   outline=(*col, alpha), width=4,
                   fill=(*col, alpha // 8))
    # Ribbon vertical
    draw.line([(cx, cy), (cx, cy + s)], fill=(*col, alpha), width=5)
    # Lid (rotates open)
    lid_angle = math.radians(-open_frac * 70)
    lid_pts = [
        (cx - s, cy),
        (cx + s, cy),
        (cx + s + int(math.sin(lid_angle) * s * 0.1),
         cy - int(s * 0.4 * math.cos(lid_angle))),
        (cx - s + int(math.sin(lid_angle) * s * 0.1),
         cy - int(s * 0.4 * math.cos(lid_angle))),
    ]
    draw.polygon(lid_pts, outline=(*col, alpha),
                 fill=(*col, alpha // 6))
    # Ribbon horizontal
    draw.line([(cx - s, cy - int(s * 0.4 * math.cos(lid_angle)) // 2),
               (cx + s, cy - int(s * 0.4 * math.cos(lid_angle)) // 2)],
              fill=(*col, alpha), width=4)


def draw_headphones(draw, cx, cy, r, col, alpha):
    """Over-ear headphones outline."""
    # Headband arc
    draw.arc([cx - r, cy - r, cx + r, cy + r],
             start=200, end=340, fill=(*col, alpha), width=7)
    # Ear cups
    for side in [-1, 1]:
        ex = cx + side * int(r * 0.92)
        ey = cy + int(r * 0.15)
        draw.ellipse([ex - 22, ey - 34, ex + 22, ey + 34],
                     outline=(*col, alpha), width=5,
                     fill=(*col, alpha // 5))
        draw.ellipse([ex - 10, ey - 15, ex + 10, ey + 15],
                     fill=(*col, alpha // 2))


def draw_music_note(draw, cx, cy, r, col, alpha):
    """Single musical note."""
    draw.ellipse([cx - r, cy + r // 2, cx + r, cy + r * 2],
                 fill=(*col, alpha))
    draw.line([(cx + r, cy + r), (cx + r, cy - r * 3)],
              fill=(*col, alpha), width=max(2, r // 3))
    draw.line([(cx + r, cy - r * 3), (cx + r * 3, cy - r * 2)],
              fill=(*col, alpha), width=max(2, r // 3))


def draw_fork_knife(draw, cx, cy, h, col, alpha):
    """Fork on left, knife on right."""
    # Fork
    fx = cx - 22
    draw.line([(fx, cy - h // 2), (fx, cy + h // 2)], fill=(*col, alpha), width=4)
    for i in [-1, 0, 1]:
        tx = fx + i * 7
        draw.line([(tx, cy - h // 2), (tx, cy - h // 5)],
                  fill=(*col, alpha), width=3)
    # Knife
    kx = cx + 22
    draw.line([(kx, cy - h // 2), (kx, cy + h // 2)], fill=(*col, alpha), width=5)
    draw.polygon([(kx, cy - h // 2), (kx + 10, cy - h // 6), (kx, cy - h // 6)],
                 fill=(*col, alpha))


def draw_cipher_wheel(draw, cx, cy, r, col, alpha, t):
    """Rotating cipher disk with letter segments."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = len(letters)
    # Outer ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(*col, alpha), width=4)
    # Inner ring (rotates)
    ir = int(r * 0.65)
    inner_offset = t * 0.3
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir],
                 outline=(*col, alpha // 2), width=3)
    # Segment ticks
    for i in range(n):
        angle = 2 * math.pi * i / n
        ox = cx + int(math.cos(angle) * (r - 8))
        oy = cy + int(math.sin(angle) * (r - 8))
        ix_o = cx + int(math.cos(angle) * (r - 20))
        iy_o = cy + int(math.sin(angle) * (r - 20))
        draw.line([(ix_o, iy_o), (ox, oy)], fill=(*col, alpha // 3), width=1)
        # Inner ring offset
        angle2 = 2 * math.pi * i / n + inner_offset
        ix = cx + int(math.cos(angle2) * (ir - 8))
        iy = cy + int(math.sin(angle2) * (ir - 8))
        draw.line([(cx + int(math.cos(angle2) * (ir - 18)),
                    cy + int(math.sin(angle2) * (ir - 18))),
                   (ix, iy)], fill=(*col, alpha // 4), width=1)
    # Pointer
    draw.line([(cx, cy - r - 12), (cx, cy - r + 5)],
              fill=(*col, alpha), width=4)


def draw_scales(draw, cx, cy, r, col, alpha, tilt=0.0):
    """Scales of justice with animated tilt."""
    # Central pillar
    draw.line([(cx, cy - r), (cx, cy + r)], fill=(*col, alpha), width=6)
    # Crossbar
    draw.line([(cx - r, cy - r // 2), (cx + r, cy - r // 2)],
              fill=(*col, alpha), width=5)
    # Pans
    for side in [-1, 1]:
        px = cx + side * r
        py_top = cy - r // 2
        pan_tilt = int(tilt * side * 30)
        # Chains
        draw.line([(px, py_top), (px - 20, py_top + 60 + pan_tilt)],
                  fill=(*col, alpha // 2), width=2)
        draw.line([(px, py_top), (px + 20, py_top + 60 + pan_tilt)],
                  fill=(*col, alpha // 2), width=2)
        # Pan
        draw.arc([px - 30, py_top + 50 + pan_tilt,
                  px + 30, py_top + 80 + pan_tilt],
                 start=0, end=180, fill=(*col, alpha), width=4)
    # Base
    draw.line([(cx - 30, cy + r), (cx + 30, cy + r)],
              fill=(*col, alpha), width=6)


def draw_gavel(draw, cx, cy, r, col, alpha, angle_deg=30.0):
    """Courtroom gavel."""
    angle = math.radians(angle_deg)
    # Handle
    hlen = int(r * 1.6)
    hx1 = cx - int(math.cos(angle) * hlen)
    hy1 = cy - int(math.sin(angle) * hlen)
    hx2 = cx + int(math.cos(angle) * hlen // 2)
    hy2 = cy + int(math.sin(angle) * hlen // 2)
    draw.line([(hx1, hy1), (hx2, hy2)], fill=(*col, alpha), width=10)
    # Head perpendicular
    perp = math.radians(angle_deg + 90)
    hw = int(r * 0.55)
    for ox, oy, wa in [(hx1, hy1, hw), (hx2, hy2, hw // 2)]:
        ex = ox + int(math.cos(perp) * wa)
        ey = oy + int(math.sin(perp) * wa)
        fx = ox - int(math.cos(perp) * wa)
        fy = oy - int(math.sin(perp) * wa)
        draw.line([(ex, ey), (fx, fy)], fill=(*col, alpha), width=22)


def draw_aperture(draw, cx, cy, r, col, alpha, open_frac=1.0):
    """Camera aperture iris."""
    n_blades = 7
    inner_r = int(r * (1.0 - open_frac) * 0.7)
    for i in range(n_blades):
        a0 = 2 * math.pi * i / n_blades
        a1 = 2 * math.pi * (i + 0.5) / n_blades
        pts = [
            (cx + int(math.cos(a0) * r), cy + int(math.sin(a0) * r)),
            (cx + int(math.cos(a1) * r), cy + int(math.sin(a1) * r)),
            (cx + int(math.cos(a1) * inner_r), cy + int(math.sin(a1) * inner_r)),
            (cx + int(math.cos(a0) * inner_r), cy + int(math.sin(a0) * inner_r)),
        ]
        draw.polygon(pts, fill=(*col, alpha // 6), outline=(*col, alpha), )


# ─────────────────────────────────────────────────────────────────────────────
# thrill_seeker ads
# ─────────────────────────────────────────────────────────────────────────────

def vortex_frame(fi, t):
    """VORTEX — action camera brand. Electric cyan / black."""
    acc = (0, 210, 255)
    bg = gradient_bg([(4, 8, 18), (8, 18, 38), (4, 8, 18)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Camera lens — scale in + rotation rings
        prog = ease_back(min(t / 1.8, 1.0))
        cam_r = int(prog * 110)
        cam_a = clamp(int(prog * 220))
        draw_camera_lens(draw, W // 2, H // 2, cam_r, acc, cam_a)

        # Chromatic-aberration rings (R/B offset)
        for offset, col in [(-6, (255, 50, 80)), (6, (80, 50, 255))]:
            phase = ((t * 0.6) % 1.6) / 1.6
            cr = int(120 + phase * 220)
            ca = int((1 - phase) * 80)
            draw.ellipse([W // 2 + offset - cr, H // 2 - cr,
                          W // 2 + offset + cr, H // 2 + cr],
                         outline=(*col, ca), width=2)

        # Speed trails radiating out
        for i in range(24):
            angle = 2 * math.pi * i / 24 + t * 0.15
            r0 = int(120 + cam_r * 0.1)
            r1 = int(r0 + 80 + 60 * math.sin(t * 2.5 + i))
            x0 = W // 2 + int(math.cos(angle) * r0)
            y0 = H // 2 + int(math.sin(angle) * r0)
            x1 = W // 2 + int(math.cos(angle) * r1)
            y1 = H // 2 + int(math.sin(angle) * r1)
            a = clamp(40 + 25 * math.sin(i + t * 3))
            draw.line([(x0, y0), (x1, y1)], fill=(*acc, a), width=2)

        # FPS counter
        fps_val = int(ease_out(min(t / 3.5, 1.0)) * 240)
        fn_fps = try_font(72)
        fn_unit = try_font(30)
        text_center(draw, f"{fps_val}", W // 2, H // 2 + 155, fn_fps, (*acc, 210))
        text_center(draw, "FPS", W // 2 + 65, H // 2 + 180, fn_unit, (180, 230, 255, 170))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.3, max_r=240)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=30, seed=10, vy=-50, drift=22)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.3, max_r=230)
        # Smaller camera badge in corner of scene
        draw_camera_lens(draw, W - 160, 140, 44, acc, 100)

        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "VORTEX", W // 2, by, fn_large, (*acc, 240), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Capture Every Moment.", W // 2, by + 95, fn_med,
                    (200, 235, 255, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=11, vy=-48)
        draw_camera_lens(draw, W // 2, H // 2 - 160, 50, acc, 130)
        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "VORTEX", W // 2, H // 2 - 60, fn_large, (*acc, 240), acc, 14)
        text_center(draw, "Capture Every Moment.", W // 2, H // 2 + 30, fn_med,
                    (200, 235, 255, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 220, cta_y, W // 2 + 220, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "SHOOT IT ALL", W // 2, cta_y + cta_h // 2,
                    fn_cta, (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


def freefall_frame(fi, t):
    """FREEFALL — extreme experiences. Hot pink / sky blue / white."""
    acc = (255, 55, 120)
    sky = (80, 180, 255)
    bg = gradient_bg([(5, 12, 35), (20, 50, 100), (80, 140, 200)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Altitude counter (falling)
        alt = int((1 - ease_in_out(min(t / 4.5, 1.0))) * 4200 + 800)
        fn_alt = try_font(60)
        text_center(draw, f"{alt} m", W // 2, 80, fn_alt, (255, 255, 255, 200))

        # Parachute (swaying, descending)
        sway = 30 * math.sin(t * 1.8)
        para_y = int(lerp(80, H // 2 - 60, ease_out(min(t / 4.0, 1.0))))
        draw_parachute(draw, W // 2, para_y, 140, acc, 230, sway)

        # Wind-rush particles streaming upward
        rush_rng = random.Random(55)
        for _ in range(50):
            rx = rush_rng.uniform(0, W)
            ry = rush_rng.uniform(0, H)
            spd = rush_rng.uniform(1.5, 3.0)
            length = rush_rng.randint(15, 40)
            x = (rx + rush_rng.uniform(-10, 10)) % W
            y = (ry - t * spd * 80) % H
            a = rush_rng.randint(30, 80)
            draw.line([(x, y), (x, y + length)], fill=(*sky, a), width=1)

        # Cloud puffs (ground getting closer = clouds moving up)
        cloud_y_base = H + int(t * 40)
        for ci in range(5):
            cxi = 160 + ci * 240
            cyi = cloud_y_base - ci * 30
            for cr, ca in [(55, 40), (45, 60), (38, 80)]:
                draw.ellipse([cxi - cr, cyi - cr // 2,
                              cxi + cr, cyi + cr // 2],
                             fill=(255, 255, 255, ca))

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=28, seed=20, vy=-45, drift=30)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.5, max_r=240)
        draw_parachute(draw, W - 180, 160, 55, acc, 90, 0.0)

        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "FREEFALL", W // 2, by, fn_large, (*acc, 240), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Life at Full Speed.", W // 2, by + 95, fn_med,
                    (255, 200, 220, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=18, seed=21, vy=-42)
        draw_parachute(draw, W // 2, H // 2 - 175, 65, acc, 120)
        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "FREEFALL", W // 2, H // 2 - 50, fn_large, (*acc, 240), acc, 14)
        text_center(draw, "Life at Full Speed.", W // 2, H // 2 + 40, fn_med,
                    (255, 200, 220, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "BOOK NOW", W // 2, cta_y + cta_h // 2, fn_cta,
                    (255, 255, 255, cta_a))

    return Image.alpha_composite(bg, ov)


def blitzrace_frame(fi, t):
    """BLITZRACE — motorsport streaming. Racing yellow / dark."""
    acc = (255, 185, 0)
    bg = gradient_bg([(6, 4, 2), (18, 12, 4), (6, 4, 2)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Checkered flag pattern (sweeping in from right)
        flag_prog = ease_out(min(t / 4.0, 1.0))
        flag_w = int(flag_prog * W * 0.3)
        sq = 40
        for row in range(H // sq + 1):
            for col in range(flag_w // sq + 1):
                fx = W - flag_w + col * sq
                fy = row * sq
                if (row + col) % 2 == 0:
                    draw.rectangle([fx, fy, fx + sq - 1, fy + sq - 1],
                                   fill=(255, 255, 255, 60))

        # Race car moving across
        car_x = int(lerp(-150, W // 2 - 50, ease_out(min(t / 2.5, 1.0))))
        car_a = clamp(ease_out(min(t / 2.0, 1.0)) * 230)
        draw_race_car(draw, car_x, H // 2 + 20, 100, acc, car_a)

        # Speed-blur horizontal streaks behind car
        streak_rng = random.Random(77)
        for _ in range(20):
            sy = streak_rng.randint(H // 2 - 50, H // 2 + 70)
            sw = streak_rng.randint(40, 200)
            sa = streak_rng.randint(20, 70)
            draw.line([(car_x - sw - 150, sy), (car_x - 120, sy)],
                      fill=(*acc, sa), width=streak_rng.randint(1, 3))

        # Lap timer
        lap = min(t / 4.5, 1.0)
        lap_str = f"1:{int(lap * 38.4 + 12):05.2f}"
        fn_lap = try_font(60)
        text_center(draw, lap_str, W // 2, H - 100, fn_lap, (*acc, 200))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.0, max_r=250)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=30, seed=30, vy=-55, drift=20)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.0, max_r=240)
        draw_race_car(draw, W - 200, H - 160, 55, acc, 100)

        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "BLITZRACE", W // 2, by, fn_large, (*acc, 240), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 215)
        text_center(draw, "Every Race. Every Second.", W // 2, by + 95, fn_med,
                    (255, 230, 150, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=31, vy=-50)
        draw_race_car(draw, W // 2, H // 2 - 155, 55, acc, 120)
        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "BLITZRACE", W // 2, H // 2 - 60, fn_large, (*acc, 240), acc, 14)
        text_center(draw, "Every Race. Every Second.", W // 2, H // 2 + 30, fn_med,
                    (255, 230, 150, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "RACE TO WATCH", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ─────────────────────────────────────────────────────────────────────────────
# intellectual_explorer ads
# ─────────────────────────────────────────────────────────────────────────────

def neuralpath_frame(fi, t):
    """NEURALPATH — online learning. Cool blue / white."""
    acc = (80, 200, 255)
    bg = gradient_bg([(2, 6, 22), (5, 14, 46), (2, 6, 22)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    bg = Image.alpha_composite(bg, dot_grid_overlay(t, acc, spacing=60, alpha=20))

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        prog = ease_out(min(t / 4.5, 1.0))
        draw_neural_net(draw, W // 2, H // 2, 270, acc, 210, prog)

        # Progress bar (knowledge fill)
        bar_w = 400
        bar_h = 16
        bx = W // 2 - bar_w // 2
        by = H - 130
        bar_prog = ease_in_out(min(t / 4.0, 1.0))
        draw.rounded_rectangle([bx, by, bx + bar_w, by + bar_h],
                                radius=8, outline=(*acc, 120), width=2)
        draw.rounded_rectangle([bx + 2, by + 2,
                                 bx + 2 + int((bar_w - 4) * bar_prog), by + bar_h - 2],
                                radius=6, fill=(*acc, 200))
        fn_pct = try_font(28)
        text_center(draw, f"{int(bar_prog * 100)}% Complete", W // 2, by + 36,
                    fn_pct, (*acc, 180))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=300)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=28, seed=40, vy=-42, drift=25)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=260)
        draw_neural_net(draw, W - 180, 150, 90, acc, 70, 1.0)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "NEURALPATH", W // 2, by, fn_large, (*acc, 235), acc, 14)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Learn Anything. Become Anyone.", W // 2, by + 92, fn_med,
                    (190, 230, 255, tag_a))
        # Course counter
        n_courses = int(ease_out(min((t - 5) / 2.5, 1.0)) * 1400)
        fn_ct = try_font(36)
        text_center(draw, f"{n_courses:,}+ courses", W // 2, by + 150, fn_ct,
                    (*acc, clamp(tag_a * 0.7)))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=18, seed=41, vy=-40)
        draw_neural_net(draw, W // 2, H // 2 - 170, 80, acc, 90, 1.0)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "NEURALPATH", W // 2, H // 2 - 60, fn_large, (*acc, 235), acc, 12)
        text_center(draw, "Learn Anything. Become Anyone.", W // 2, H // 2 + 30, fn_med,
                    (190, 230, 255, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 215, cta_y, W // 2 + 215, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "START LEARNING", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


def solarsail_frame(fi, t):
    """SOLARSAIL — space documentary streaming. Solar orange / deep navy."""
    acc = (255, 145, 50)
    bg = gradient_bg([(0, 2, 15), (4, 10, 38), (0, 2, 15)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    # Starfield (static)
    star_rng = random.Random(99)
    for _ in range(250):
        sx = star_rng.randint(0, W)
        sy = star_rng.randint(0, H)
        sr = star_rng.randint(1, 3)
        sa = star_rng.randint(60, 210)
        twinkle = 0.7 + 0.3 * math.sin(t * 1.5 + sx * 0.03 + sy * 0.02)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr],
                     fill=(255, 255, 255, int(sa * twinkle)))

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        prog = ease_in_out(min(t / 4.0, 1.0))
        draw_solar_system(draw, W // 2, H // 2, t, acc, int(prog * 220))

        # Solar flare burst
        flare_a = clamp(int(abs(math.sin(t * 1.2)) * 120))
        for i in range(8):
            angle = 2 * math.pi * i / 8 + t * 0.3
            fl_len = int(55 + 30 * math.sin(t * 2 + i))
            fx0 = W // 2 + int(math.cos(angle) * 52)
            fy0 = H // 2 + int(math.sin(angle) * 52)
            fx1 = W // 2 + int(math.cos(angle) * (52 + fl_len))
            fy1 = H // 2 + int(math.sin(angle) * (52 + fl_len))
            draw.line([(fx0, fy0), (fx1, fy1)], fill=(*acc, flare_a), width=3)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=22, seed=50, vy=-38, drift=28, r_range=(2, 5))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.2, n=2, max_r=260)
        draw_solar_system(draw, W - 200, 150, t, acc, 80)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "SOLARSAIL", W // 2, by, fn_large, (*acc, 235), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "The Universe Is Waiting.", W // 2, by + 92, fn_med,
                    (255, 210, 170, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=15, seed=51, vy=-35)
        draw_solar_system(draw, W // 2, H // 2 - 175, t, acc, 80)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "SOLARSAIL", W // 2, H // 2 - 55, fn_large, (*acc, 235), acc, 14)
        text_center(draw, "The Universe Is Waiting.", W // 2, H // 2 + 35, fn_med,
                    (255, 210, 170, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 205, cta_y, W // 2 + 205, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "EXPLORE NOW", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


def archivum_frame(fi, t):
    """ARCHIVUM — history streaming. Aged gold / parchment / slate."""
    acc = (200, 165, 90)
    bg = gradient_bg([(18, 12, 6), (38, 28, 14), (18, 12, 6)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Ancient columns (left and right)
        col_a = clamp(ease_out(min(t / 2.5, 1.0)) * 160)
        for cx_col in [200, W - 200]:
            col_w = 60
            draw.rectangle([cx_col - col_w // 2, 80, cx_col + col_w // 2, H - 60],
                            outline=(*acc, col_a), fill=(*acc, col_a // 6), width=3)
            draw.ellipse([cx_col - col_w // 2 - 10, 60,
                          cx_col + col_w // 2 + 10, 110],
                         outline=(*acc, col_a), fill=(*acc, col_a // 6), width=3)
            draw.rectangle([cx_col - col_w // 2 - 10, H - 80,
                             cx_col + col_w // 2 + 10, H - 60],
                            outline=(*acc, col_a), fill=(*acc, col_a // 6), width=3)
            # Fluting lines on column
            for fl_x in range(-col_w // 2 + 6, col_w // 2, 10):
                draw.line([(cx_col + fl_x, 110), (cx_col + fl_x, H - 80)],
                          fill=(*acc, col_a // 3), width=2)

        # Scroll unfurling in centre
        scroll_prog = ease_out(min(t / 3.5, 1.0))
        draw_scroll(draw, W // 2, H // 2, 500, 200, acc, 200, scroll_prog)

        # Dust motes
        dust_rng = random.Random(33)
        for _ in range(30):
            dx = dust_rng.uniform(250, W - 250)
            dy = dust_rng.uniform(100, H - 100)
            dr = dust_rng.randint(2, 6)
            da = dust_rng.randint(20, 70)
            px_d = (dx + 15 * math.sin(t * 0.7 + dx * 0.01)) % W
            py_d = (dy - t * 8) % H
            draw.ellipse([px_d - dr, py_d - dr, px_d + dr, py_d + dr],
                         fill=(*acc, da))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.5, n=2, max_r=280)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=60, vy=-30, drift=20, r_range=(2, 5))
        draw_scroll(draw, W - 160, 140, 200, 80, acc, 80, 1.0)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "ARCHIVUM", W // 2, by, fn_large, (*acc, 230), acc, 14)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "History. Rediscovered.", W // 2, by + 90, fn_med,
                    (230, 210, 160, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=14, seed=61, vy=-28)
        draw_scroll(draw, W // 2, H // 2 - 170, 220, 80, acc, 90, 1.0)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "ARCHIVUM", W // 2, H // 2 - 55, fn_large, (*acc, 230), acc, 12)
        text_center(draw, "History. Rediscovered.", W // 2, H // 2 + 32, fn_med,
                    (230, 210, 160, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "TRAVEL BACK", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ─────────────────────────────────────────────────────────────────────────────
# content_chameleon ads
# ─────────────────────────────────────────────────────────────────────────────

def velvetbox_frame(fi, t):
    """VELVETBOX — mystery subscription box. Deep purple / gold."""
    acc = (180, 80, 230)
    gold = (255, 200, 60)
    bg = gradient_bg([(14, 4, 28), (30, 10, 55), (14, 4, 28)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Box opening
        open_frac = ease_out(min(t / 4.0, 1.0))
        box_a = clamp(ease_out(min(t / 1.5, 1.0)) * 220)
        draw_gift_box(draw, W // 2, H // 2, 130, acc, box_a, open_frac)

        # Sparkles and items bursting out of box as it opens
        if open_frac > 0.3:
            burst_rng = random.Random(88)
            n_items = int((open_frac - 0.3) / 0.7 * 40)
            for _ in range(n_items):
                angle = burst_rng.uniform(0, math.pi)  # upward only
                dist = burst_rng.uniform(30, 200) * (open_frac - 0.3)
                bx = W // 2 + int(math.cos(angle) * dist)
                by = H // 2 - int(abs(math.sin(angle)) * dist)
                br = burst_rng.randint(4, 14)
                col_choice = [acc, gold, (255, 255, 255)][burst_rng.randint(0, 2)]
                ba = burst_rng.randint(100, 220)
                if burst_rng.random() > 0.5:
                    draw.ellipse([bx - br, by - br, bx + br, by + br],
                                 fill=(*col_choice, ba))
                else:
                    pts = [(bx, by - br), (bx + br, by), (bx, by + br), (bx - br, by)]
                    draw.polygon(pts, fill=(*col_choice, ba))

        # Light burst from box opening
        if open_frac > 0.5:
            burst_a = int((open_frac - 0.5) / 0.5 * 140)
            for i in range(16):
                angle = math.radians(270 - 80 + i * 10)
                bl = int(80 + 60 * i / 16)
                bx0 = W // 2 + int(math.cos(angle) * 20)
                by0 = H // 2 - int(abs(math.sin(angle)) * 20)
                bx1 = W // 2 + int(math.cos(angle) * (20 + bl))
                by1 = H // 2 - int(abs(math.sin(angle)) * (20 + bl))
                draw.line([(bx0, by0), (bx1, by1)], fill=(*gold, burst_a), width=2)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.6, n=2, max_r=250)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, gold, count=30, seed=70, vy=-45, drift=25, r_range=(3, 8))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.6, n=2, max_r=240)
        draw_gift_box(draw, W - 160, 150, 55, acc, 90, 1.0)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "VELVETBOX", W // 2, by, fn_large, (*acc, 235), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Surprise Yourself.", W // 2, by + 92, fn_med,
                    (*gold, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, gold, count=20, seed=71, vy=-40)
        draw_gift_box(draw, W // 2, H // 2 - 175, 65, acc, 120, 1.0)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "VELVETBOX", W // 2, H // 2 - 55, fn_large, (*acc, 235), acc, 14)
        text_center(draw, "Surprise Yourself.", W // 2, H // 2 + 32, fn_med, (*gold, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 195, cta_y, W // 2 + 195, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "SUBSCRIBE", W // 2, cta_y + cta_h // 2, fn_cta,
                    (255, 255, 255, cta_a))

    return Image.alpha_composite(bg, ov)


def groovepod_frame(fi, t):
    """GROOVEPOD — music streaming. Magenta / white / dark."""
    acc = (255, 70, 195)
    bg = gradient_bg([(8, 2, 18), (22, 6, 42), (8, 2, 18)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Headphones (big, centre)
        hp_prog = ease_back(min(t / 2.0, 1.0))
        hp_r = int(hp_prog * 150)
        hp_a = clamp(int(hp_prog * 230))
        draw_headphones(draw, W // 2, H // 2, hp_r, acc, hp_a)

        # Audio waveform equalizer bars
        n_bars = 24
        for i in range(n_bars):
            bx = W // 2 - n_bars * 16 // 2 + i * 16
            amp = 0.3 + 0.7 * abs(math.sin(t * 3.5 + i * 0.6))
            bh_bar = int(amp * 180)
            by_top = H // 2 + 80 - bh_bar
            col = hsv_to_rgb((t * 0.05 + i / n_bars) % 1.0, 0.7, 1.0)
            a = clamp(160 + 60 * amp)
            draw.rectangle([bx - 5, by_top, bx + 5, H // 2 + 80], fill=(*col, a))

        # Floating music notes
        note_rng = random.Random(44)
        for i in range(8):
            nx = note_rng.randint(100, W - 100)
            ny_base = note_rng.randint(80, H - 80)
            nt = (t + i * 0.5) % 5
            note_x = nx + int(30 * math.sin(nt + i))
            note_y = int(ny_base - nt * 40) % H
            nr = note_rng.randint(8, 16)
            na = clamp(int((1 - nt / 5) * 200))
            if na > 10:
                draw_music_note(draw, note_x, note_y, nr, acc, na)

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.3, n=3, max_r=260)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=30, seed=80, vy=-48, drift=22)
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.3, n=2, max_r=240)
        draw_headphones(draw, W - 160, 140, 60, acc, 90)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "GROOVEPOD", W // 2, by, fn_large, (*acc, 240), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Your Music. Your World.", W // 2, by + 92, fn_med,
                    (255, 190, 235, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=81, vy=-45)
        draw_headphones(draw, W // 2, H // 2 - 175, 70, acc, 120)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "GROOVEPOD", W // 2, H // 2 - 55, fn_large, (*acc, 240), acc, 14)
        text_center(draw, "Your Music. Your World.", W // 2, H // 2 + 32, fn_med,
                    (255, 190, 235, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "LISTEN FREE", W // 2, cta_y + cta_h // 2, fn_cta,
                    (255, 255, 255, cta_a))

    return Image.alpha_composite(bg, ov)


def zestplate_frame(fi, t):
    """ZESTPLATE — meal-kit delivery. Warm saffron / fresh green."""
    acc = (255, 155, 30)
    grn = (80, 195, 90)
    bg = gradient_bg([(30, 18, 4), (65, 38, 10), (30, 18, 4)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Plate (circle)
        plate_prog = ease_back(min(t / 1.8, 1.0))
        plate_r = int(plate_prog * 160)
        plate_a = clamp(plate_prog * 200)
        draw.ellipse([W // 2 - plate_r, H // 2 - plate_r,
                      W // 2 + plate_r, H // 2 + plate_r],
                     outline=(230, 220, 210, plate_a), width=6)
        if plate_r > 14:
            draw.ellipse([W // 2 - plate_r + 14, H // 2 - plate_r + 14,
                          W // 2 + plate_r - 14, H // 2 + plate_r - 14],
                         outline=(230, 220, 210, plate_a // 2), width=2)

        # Fork and knife beside plate
        utensil_a = clamp(ease_out(min((t - 0.5) / 2.0, 1.0)) * 210)
        draw_fork_knife(draw, W // 2, H // 2, 180, (230, 220, 210), utensil_a)

        # Floating ingredients orbiting the plate
        ingredients = [
            (acc, "CARROT"), (grn, "HERB"), ((220, 60, 60), "TOMATO"),
            ((255, 220, 100), "LEMON"), (grn, "LETTUCE"),
        ]
        for i, (col, _) in enumerate(ingredients):
            angle = 2 * math.pi * i / len(ingredients) + t * 0.5
            orbit_r = 220 + 20 * math.sin(t * 0.8 + i)
            ix = W // 2 + int(math.cos(angle) * orbit_r)
            iy = H // 2 + int(math.sin(angle) * orbit_r * 0.6)
            ir = 22 + int(8 * math.sin(t + i))
            ia = clamp(ease_out(min(t / 2.0 - i * 0.15, 1.0)) * 200)
            draw.ellipse([ix - ir, iy - ir, ix + ir, iy + ir],
                         fill=(*col, ia), outline=(255, 255, 255, ia // 3), width=2)

        # Steam wisps from plate
        steam_rng = random.Random(66)
        for i in range(5):
            sx = W // 2 + steam_rng.randint(-60, 60)
            sy_base = H // 2 - plate_r
            phase = (t * 1.2 + i * 0.4) % 2.0
            sy = sy_base - int(phase * 80)
            sa = clamp(int((1 - phase / 2.0) * 100))
            sr = int(8 + phase * 12)
            if sa > 5:
                draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr],
                             fill=(255, 255, 255, sa))

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=25, seed=90, vy=-38, drift=22, r_range=(3, 8))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=240)
        draw_fork_knife(draw, W - 130, 140, 90, acc, 90)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "ZESTPLATE", W // 2, by, fn_large, (*acc, 235), acc, 14)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Chef-Made. Doorstep-Delivered.", W // 2, by + 92, fn_med,
                    (255, 225, 170, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=16, seed=91, vy=-35)
        draw_fork_knife(draw, W // 2, H // 2 - 165, 90, acc, 110)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "ZESTPLATE", W // 2, H // 2 - 45, fn_large, (*acc, 235), acc, 12)
        text_center(draw, "Chef-Made. Doorstep-Delivered.", W // 2, H // 2 + 42, fn_med,
                    (255, 225, 170, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 200, cta_y, W // 2 + 200, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "ORDER NOW", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ─────────────────────────────────────────────────────────────────────────────
# investigative_viewer ads
# ─────────────────────────────────────────────────────────────────────────────

def cipher_frame(fi, t):
    """CIPHER — true crime podcast. Cryptic green / dark charcoal."""
    acc = (60, 230, 130)
    bg = gradient_bg([(4, 10, 6), (8, 22, 12), (4, 10, 6)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Cipher wheel (large, centre)
        wheel_prog = ease_out(min(t / 2.0, 1.0))
        wheel_a = clamp(wheel_prog * 220)
        draw_cipher_wheel(draw, W // 2, H // 2, 170, acc, wheel_a, t)

        # "Decoding" text — letters cycling randomly then settling
        fn_code = try_font(36)
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        msg = "CRACK THE CASE"
        code_rng = random.Random(int(t * 15))
        decoded = int(ease_out(min(t / 4.0, 1.0)) * len(msg))
        display = ""
        for i, ch in enumerate(msg):
            if i < decoded:
                display += ch
            elif ch == " ":
                display += " "
            else:
                display += code_rng.choice(chars)
        text_center(draw, display, W // 2, H // 2 + 210, fn_code,
                    (*acc, clamp(ease_out(min(t / 1.5, 1.0)) * 220)))

        # Code rain on sides
        rain_rng = random.Random(77)
        for _ in range(40):
            rx = rain_rng.randint(0, 200)
            col_side = rain_rng.choice([0, W - 200])
            ry = (rain_rng.randint(0, H) + int(t * 80)) % H
            ch = rain_rng.choice(chars)
            draw.text((col_side + rx, ry), ch,
                      font=try_font(20), fill=(*acc, rain_rng.randint(20, 80)))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, n=2, max_r=260)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=22, seed=100, vy=-40, drift=15, r_range=(1, 4))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, n=2, max_r=240)
        draw_cipher_wheel(draw, W - 170, 140, 80, acc, 80, t)

        fn_large = try_font(130)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.65, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "CIPHER", W // 2, by, fn_large, (*acc, 235), acc, 16)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Every Crime Has a Pattern.", W // 2, by + 90, fn_med,
                    (180, 240, 200, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=14, seed=101, vy=-38)
        draw_cipher_wheel(draw, W // 2, H // 2 - 185, 75, acc, 100, t)
        fn_large = try_font(130)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "CIPHER", W // 2, H // 2 - 60, fn_large, (*acc, 235), acc, 14)
        text_center(draw, "Every Crime Has a Pattern.", W // 2, H // 2 + 28, fn_med,
                    (180, 240, 200, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 210, cta_y, W // 2 + 210, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "CRACK THE CASE", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


def tribunal_frame(fi, t):
    """TRIBUNAL — legal drama streaming. Silver / crimson / dark slate."""
    acc = (200, 205, 225)
    red = (180, 20, 35)
    bg = gradient_bg([(8, 8, 12), (18, 16, 22), (8, 8, 12)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Scales of justice (animated tilt)
        scales_prog = ease_out(min(t / 2.5, 1.0))
        scales_a = clamp(scales_prog * 220)
        tilt = math.sin(t * 0.8) * 0.4
        draw_scales(draw, W // 2, H // 2, 160, acc, scales_a, tilt)

        # Gavel (striking animation)
        gavel_cycle = (t * 0.7) % 2.0
        gavel_angle = -40 + 70 * ease_in_out(min(gavel_cycle, 1.0))
        if gavel_cycle > 1.2:
            gavel_angle = -40 + 70 * ease_in_out(min((2.0 - gavel_cycle) / 0.8, 1.0))
        gavel_a = clamp(ease_out(min(t / 1.5, 1.0)) * 200)
        draw_gavel(draw, W // 2 + 250, H // 2 + 80, 50, acc, gavel_a, gavel_angle)

        # "VERDICT" stamp appearing
        verdict_prog = ease_out(min((t - 2.5) / 1.5, 1.0)) if t > 2.5 else 0
        if verdict_prog > 0.05:
            fn_v = try_font(72)
            stamp_a = clamp(verdict_prog * 200)
            stamp_angle = int((1 - verdict_prog) * 20)
            text_center(draw, "VERDICT", W // 2, H // 2 + 50, fn_v, (*red, stamp_a))

        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=270)

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=18, seed=110, vy=-35, drift=12, r_range=(1, 4))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=2.0, n=2, max_r=250)
        draw_scales(draw, W - 180, 150, 75, acc, 80, 0.0)

        fn_large = try_font(130)
        fn_med = try_font(48)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "TRIBUNAL", W // 2, by, fn_large, (*acc, 235), acc, 14)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "Justice Is Never Simple.", W // 2, by + 90, fn_med,
                    (180, 190, 215, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=12, seed=111, vy=-32)
        draw_scales(draw, W // 2, H // 2 - 185, 70, acc, 90, math.sin(t * 0.8) * 0.3)
        fn_large = try_font(130)
        fn_med = try_font(48)
        fn_cta = try_font(46)
        bg = glow_text(bg, "TRIBUNAL", W // 2, H // 2 - 58, fn_large, (*acc, 235), acc, 12)
        text_center(draw, "Justice Is Never Simple.", W // 2, H // 2 + 30, fn_med,
                    (180, 190, 215, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 190, cta_y, W // 2 + 190, cta_y + cta_h],
                                radius=35, fill=(*red, cta_a))
        text_center(draw, "WATCH NOW", W // 2, cta_y + cta_h // 2, fn_cta,
                    (255, 255, 255, cta_a))

    return Image.alpha_composite(bg, ov)


def eyewitness_frame(fi, t):
    """EYEWITNESS — investigative documentary. Documentary gold / dark."""
    acc = (255, 200, 55)
    bg = gradient_bg([(10, 8, 4), (24, 18, 8), (10, 8, 4)])
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if t < 5:
        if t < 0.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(255 * (1 - t / 0.15))))
            bg = Image.alpha_composite(bg, fl)

        # Camera aperture opening
        open_frac = ease_out(min(t / 3.5, 1.0))
        draw_aperture(draw, W // 2, H // 2, 180, acc, 200, open_frac)

        # Cinematic letterbox bars (fade in, then out as aperture opens)
        bar_h = int((1 - open_frac * 0.8) * 80)
        if bar_h > 4:
            bar_a = clamp((1 - open_frac) * 200)
            draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0, bar_a))
            draw.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0, bar_a))

        # Crosshair + focus bracket (inside aperture)
        ch_a = clamp(ease_out(min(t / 2.0, 1.0)) * 180)
        ch_r = int(open_frac * 60)
        for cx_off, cy_off in [(-ch_r, 0), (ch_r, 0), (0, -ch_r), (0, ch_r)]:
            draw.line([(W // 2 + cx_off - 15, H // 2 + cy_off),
                       (W // 2 + cx_off + 15, H // 2 + cy_off)],
                      fill=(*acc, ch_a), width=2)
            draw.line([(W // 2 + cx_off, H // 2 + cy_off - 15),
                       (W // 2 + cx_off, H // 2 + cy_off + 15)],
                      fill=(*acc, ch_a), width=2)

        # Documentary-style lower-third bar
        lt_prog = ease_out(min((t - 1.5) / 1.5, 1.0)) if t > 1.5 else 0
        lt_w = int(lt_prog * 500)
        if lt_w > 10:
            lt_y = H - 180
            draw.rectangle([120, lt_y, 120 + lt_w, lt_y + 50], fill=(*acc, 200))
            if lt_w > 200:
                fn_lt = try_font(26)
                draw.text((130, lt_y + 12), "INSIDE THE INVESTIGATION",
                          font=fn_lt, fill=(0, 0, 0, 220))

        # Film grain overlay (heavy — documentary feel)
        grain_rng = random.Random(fi * 1009)
        for _ in range(600):
            gx = grain_rng.randint(0, W - 1)
            gy = grain_rng.randint(0, H - 1)
            ga = grain_rng.randint(5, 35)
            draw.point((gx, gy), fill=(255, 255, 255, ga))

    elif t < 10:
        if t < 5.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 5) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=20, seed=120, vy=-38, drift=18, r_range=(2, 5))
        pulse_rings(draw, W // 2, H // 2, t, acc, period=1.8, n=2, max_r=250)
        draw_aperture(draw, W - 170, 140, 70, acc, 80, 0.8)

        fn_large = try_font(120)
        fn_med = try_font(50)
        slide = ease_out(min((t - 5) / 0.7, 1.0))
        by = int(lerp(H + 80, H // 2 - 70, slide))
        bg = glow_text(bg, "EYEWITNESS", W // 2, by, fn_large, (*acc, 235), acc, 14)
        tag_a = clamp(ease_out(min((t - 6.5) / 0.6, 1.0)) * 210)
        text_center(draw, "The Story Behind the Story.", W // 2, by + 90, fn_med,
                    (255, 230, 170, tag_a))

    else:
        if t < 10.15:
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - 10) / 0.15))))
            bg = Image.alpha_composite(bg, fl)
        particles(draw, t, acc, count=14, seed=121, vy=-35)
        draw_aperture(draw, W // 2, H // 2 - 185, 75, acc, 100, 0.9)
        fn_large = try_font(120)
        fn_med = try_font(50)
        fn_cta = try_font(46)
        bg = glow_text(bg, "EYEWITNESS", W // 2, H // 2 - 55, fn_large, (*acc, 235), acc, 12)
        text_center(draw, "The Story Behind the Story.", W // 2, H // 2 + 32, fn_med,
                    (255, 230, 170, 210))
        cta_a = clamp(ease_out(min((t - 11) / 0.5, 1.0)) * 245)
        cta_h = 70
        cta_y = H - 115
        draw.rounded_rectangle([W // 2 - 205, cta_y, W // 2 + 205, cta_y + cta_h],
                                radius=35, fill=(*acc, cta_a))
        text_center(draw, "WITNESS IT", W // 2, cta_y + cta_h // 2, fn_cta,
                    (0, 0, 0, cta_a))

    return Image.alpha_composite(bg, ov)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

ADS = [
    # (ad_id, frame_fn, accent_rgb, brand_initial, category)
    # thrill_seeker
    ("ad_thrill_vortex",     vortex_frame,     (0, 210, 255),   "V", "thrill_seeker"),
    ("ad_thrill_freefall",   freefall_frame,   (255, 55, 120),  "F", "thrill_seeker"),
    ("ad_thrill_blitzrace",  blitzrace_frame,  (255, 185, 0),   "B", "thrill_seeker"),
    # intellectual_explorer
    ("ad_intel_neuralpath",  neuralpath_frame, (80, 200, 255),  "N", "intellectual_explorer"),
    ("ad_intel_solarsail",   solarsail_frame,  (255, 145, 50),  "S", "intellectual_explorer"),
    ("ad_intel_archivum",    archivum_frame,   (200, 165, 90),  "A", "intellectual_explorer"),
    # content_chameleon
    ("ad_chame_velvetbox",   velvetbox_frame,  (180, 80, 230),  "V", "content_chameleon"),
    ("ad_chame_groovepod",   groovepod_frame,  (255, 70, 195),  "G", "content_chameleon"),
    ("ad_chame_zestplate",   zestplate_frame,  (255, 155, 30),  "Z", "content_chameleon"),
    # investigative_viewer
    ("ad_invest_cipher",     cipher_frame,     (60, 230, 130),  "C", "investigative_viewer"),
    ("ad_invest_tribunal",   tribunal_frame,   (200, 205, 225), "T", "investigative_viewer"),
    ("ad_invest_eyewitness", eyewitness_frame, (255, 200, 55),  "E", "investigative_viewer"),
]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="ad_ids to render (default: all)")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    targets = {ad_id: (fn, acc, ch, cat) for ad_id, fn, acc, ch, cat in ADS}
    to_render = args.only if args.only else list(targets)

    for ad_id in to_render:
        if ad_id not in targets:
            print(f"  unknown ad_id: {ad_id}")
            continue
        fn, acc, ch, cat = targets[ad_id]
        print(f"\n=== {ad_id} ===")
        render_and_encode(fn, ad_id, accent=acc, brand_char=ch, category=cat)
    print("\nDone.")
