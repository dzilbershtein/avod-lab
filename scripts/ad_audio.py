"""
ad_audio.py — Synthetic audio generation for AVOD-Lab ads.

Pure Python / stdlib only (math, random, wave, struct).
Generates a 15-second mono WAV tuned to each viewer-profile category.

Usage:
    from ad_audio import synthesize_audio, write_wav, SAMPLE_RATE

    samples = synthesize_audio("thrill_seeker")   # list[float] in [-1, 1]
    write_wav(samples, SAMPLE_RATE, "/tmp/track.wav")
"""

from __future__ import annotations

import math
import random
import struct
import wave

SAMPLE_RATE = 44100


# ─────────────────────────────────────────────────────────────────────────────
# Low-level synthesis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _add_kick(audio: list[float], t_start: float, sr: int, level: float = 0.9) -> None:
    """Low-frequency sine sweep (120→50 Hz) with exponential decay."""
    start = int(t_start * sr)
    dur_n = int(0.15 * sr)
    n = len(audio)
    phase = 0.0
    for j in range(dur_n):
        idx = start + j
        if idx >= n:
            break
        freq = 120.0 - 70.0 * j / dur_n
        phase += 2 * math.pi * freq / sr
        env = math.exp(-j / sr * 20)
        audio[idx] += math.sin(phase) * env * level


def _add_snare(audio: list[float], t_start: float, sr: int, level: float = 0.7,
               seed: int = 0) -> None:
    """White noise + 200 Hz tone with medium decay."""
    start = int(t_start * sr)
    dur_n = int(0.12 * sr)
    n = len(audio)
    rng = random.Random(seed ^ int(t_start * 1000))
    for j in range(dur_n):
        idx = start + j
        if idx >= n:
            break
        env = math.exp(-j / sr * 30)
        noise = rng.uniform(-1.0, 1.0)
        tone = math.sin(2 * math.pi * 200 * j / sr)
        audio[idx] += (0.7 * noise + 0.3 * tone) * env * level


def _add_hihat(audio: list[float], t_start: float, sr: int, level: float = 0.2,
               seed: int = 1) -> None:
    """Very-short noise burst — closed hi-hat."""
    start = int(t_start * sr)
    dur_n = int(0.035 * sr)
    n = len(audio)
    rng = random.Random(seed ^ int(t_start * 10000))
    for j in range(dur_n):
        idx = start + j
        if idx >= n:
            break
        env = math.exp(-j / sr * 120)
        audio[idx] += rng.uniform(-1.0, 1.0) * env * level


def _add_impact(audio: list[float], t_start: float, sr: int, level: float = 0.8,
                seed: int = 2) -> None:
    """Low boom + noise — used at scene cuts."""
    start = int(t_start * sr)
    dur_n = int(0.35 * sr)
    n = len(audio)
    rng = random.Random(seed ^ int(t_start * 333))
    for j in range(dur_n):
        idx = start + j
        if idx >= n:
            break
        env = math.exp(-j / sr * 14)
        boom = math.sin(2 * math.pi * 60 * j / sr)
        noise = rng.uniform(-0.5, 0.5) * math.exp(-j / sr * 28)
        audio[idx] += (boom + noise) * env * level


def _add_note(audio: list[float], t_start: float, dur_sec: float, freq: float,
              sr: int, level: float = 0.3, attack_r: float = 0.05,
              release_r: float = 0.15) -> None:
    """Single sine tone with simple attack/sustain/release envelope."""
    start = int(t_start * sr)
    note_n = int(dur_sec * sr)
    att_n = max(1, int(attack_r * note_n))
    rel_n = max(1, int(release_r * note_n))
    n = len(audio)
    for j in range(note_n):
        idx = start + j
        if idx >= n:
            break
        if j < att_n:
            env = j / att_n
        elif j >= note_n - rel_n:
            env = (note_n - j) / rel_n
        else:
            env = 1.0
        audio[idx] += math.sin(2 * math.pi * freq * j / sr) * env * level


# ─────────────────────────────────────────────────────────────────────────────
# Per-category synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _synth_thrill(audio: list[float], n: int, sr: int) -> None:
    """BPM 140 — punchy electronic with bass drop and synth lead swell."""
    bpm = 140
    beat = 60.0 / bpm

    # Percussion grid (2-beat measure = kick on 1, snare on 2)
    t = 0.0
    while t < n / sr:
        _add_kick(audio, t, sr, 0.9)
        _add_hihat(audio, t, sr, 0.18, seed=10)
        _add_hihat(audio, t + beat * 0.5, sr, 0.14, seed=11)
        _add_snare(audio, t + beat, sr, 0.70, seed=20)
        _add_hihat(audio, t + beat, sr, 0.16, seed=12)
        _add_hihat(audio, t + beat * 1.5, sr, 0.13, seed=13)
        _add_kick(audio, t + beat * 1.75, sr, 0.55)   # ghost kick before bar
        t += beat * 2

    # Continuous bass + lead (per-sample loop is ~3 s in CPython — acceptable)
    step_bass = 2 * math.pi * 80 / sr
    step_bass2 = 2 * math.pi * 160 / sr
    step_lead = 2 * math.pi * 440 / sr
    step_lead2 = 2 * math.pi * 880 / sr
    beat_samples = int(beat * sr)
    for i in range(n):
        t_i = i / sr
        # Bass with sidechain-style pumping
        beat_pos = (i % beat_samples) / beat_samples
        pump = max(0.3, math.exp(-beat_pos * 4))
        bass = (math.sin(step_bass * i) + 0.5 * math.sin(step_bass2 * i))
        audio[i] += bass * pump * 0.30

        # Synth lead swells in from scene 2 (t ≥ 5s)
        if t_i >= 5.0:
            swell = min((t_i - 5.0) / 2.5, 1.0) * 0.22
            lead = math.sin(step_lead * i) + 0.3 * math.sin(step_lead2 * i)
            audio[i] += lead * swell

    # Scene-cut impacts
    _add_impact(audio, 5.0, sr, 0.85, seed=30)
    _add_impact(audio, 10.0, sr, 0.85, seed=31)


def _synth_intellectual(audio: list[float], n: int, sr: int) -> None:
    """BPM 75 — ambient pad + C-major arpeggio + subtle build."""
    bpm = 75
    beat = 60.0 / bpm

    # Soft pad (slow attack, layered harmonics)
    step_a = 2 * math.pi * 220 / sr
    step_b = 2 * math.pi * 330 / sr
    step_c = 2 * math.pi * 440 / sr
    step_build = 2 * math.pi * 110 / sr
    for i in range(n):
        t_i = i / sr
        attack = min(t_i / 2.0, 1.0)
        breathe = 0.85 + 0.15 * math.sin(2 * math.pi * 0.3 * t_i)
        pad = (0.5 * math.sin(step_a * i) +
               0.3 * math.sin(step_b * i) +
               0.2 * math.sin(step_c * i))
        audio[i] += pad * attack * breathe * 0.32

        # Gentle swell toward the end
        build = max(0.0, (t_i - 10.0) / 5.0) * 0.15
        audio[i] += math.sin(step_build * i) * build

    # C-major arpeggio — [C4 E4 G4 B4 C5]
    arp_notes = [261.63, 329.63, 392.00, 493.88, 523.25]
    arp_dur = beat / 2
    arp_t = 0.4
    k = 0
    while arp_t < n / sr:
        _add_note(audio, arp_t, arp_dur * 0.72, arp_notes[k % len(arp_notes)],
                  sr, level=0.18, attack_r=0.08, release_r=0.25)
        arp_t += arp_dur
        k += 1

    # Very quiet hi-hat on off-beats
    t = beat * 0.5
    while t < n / sr:
        _add_hihat(audio, t, sr, 0.055, seed=40)
        t += beat


def _synth_chameleon(audio: list[float], n: int, sr: int) -> None:
    """BPM 118 — upbeat pop: kick/snare, bouncy bass, major-key melody."""
    bpm = 118
    beat = 60.0 / bpm

    # Drums
    t = 0.0
    while t < n / sr:
        _add_kick(audio, t, sr, 0.82)
        _add_hihat(audio, t, sr, 0.17, seed=50)
        _add_hihat(audio, t + beat * 0.5, sr, 0.12, seed=51)
        _add_snare(audio, t + beat, sr, 0.62, seed=52)
        _add_hihat(audio, t + beat, sr, 0.15, seed=53)
        _add_hihat(audio, t + beat * 1.5, sr, 0.11, seed=54)
        t += beat * 2

    # Bouncy bass [C2 D2 E2 F2 G2]
    bass_notes = [65.41, 73.42, 82.41, 87.31, 98.00]
    k = 0
    bt = 0.0
    while bt < n / sr:
        _add_note(audio, bt, beat * 0.55, bass_notes[k % len(bass_notes)],
                  sr, level=0.35, attack_r=0.04, release_r=0.12)
        bt += beat
        k += 1

    # Cheerful melody starts after 2 bars [C5 D5 E5 F5 G5 E5 D5 C5]
    mel_notes = [523.25, 587.33, 659.25, 698.46, 783.99, 659.25, 587.33, 523.25]
    k = 0
    mt = beat * 4   # starts after 2 full measures
    while mt < n / sr:
        _add_note(audio, mt, beat * 0.62, mel_notes[k % len(mel_notes)],
                  sr, level=0.20, attack_r=0.04, release_r=0.14)
        mt += beat
        k += 1


def _synth_investigative(audio: list[float], n: int, sr: int) -> None:
    """BPM 85 — tense: dark drone + staccato minor figures + impact hits."""
    # Sustained dark drone (A1 + E2 + A2 with LFO breathe)
    step_d1 = 2 * math.pi * 55 / sr
    step_d2 = 2 * math.pi * 82.5 / sr
    step_d3 = 2 * math.pi * 110 / sr
    step_ten = 2 * math.pi * 220 / sr
    duration_sec = n / sr
    for i in range(n):
        t_i = i / sr
        breathe = 0.30 + 0.15 * math.sin(2 * math.pi * 0.22 * t_i)
        drone = (0.6 * math.sin(step_d1 * i) +
                 0.4 * math.sin(step_d2 * i) +
                 0.2 * math.sin(step_d3 * i))
        audio[i] += drone * breathe

        # Tension ramp — upper harmonic that detuned slightly over time
        tension = min(t_i / duration_sec, 1.0)
        audio[i] += math.sin(step_ten * i + tension * math.pi) * tension * 0.10

    # Staccato A-minor figures [A3 C4 D4 B3]
    minor_notes = [220.00, 261.63, 293.66, 246.94]
    bpm = 85
    beat = 60.0 / bpm
    stac_dur = beat / 2
    k = 0
    st = 0.5
    while st < duration_sec:
        _add_note(audio, st, 0.07, minor_notes[k % len(minor_notes)],
                  sr, level=0.26, attack_r=0.03, release_r=0.50)
        st += stac_dur
        k += 1

    # Impact hits at scene cuts + end
    for it, seed in [(0.0, 60), (5.0, 61), (10.0, 62), (14.4, 63)]:
        _add_impact(audio, it, sr, 0.60, seed=seed)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "thrill_seeker":        _synth_thrill,
    "intellectual_explorer": _synth_intellectual,
    "content_chameleon":    _synth_chameleon,
    "investigative_viewer": _synth_investigative,
}


def synthesize_audio(category: str, duration_sec: float = 15.0,
                     sr: int = SAMPLE_RATE) -> list[float]:
    """Return a list of float samples in [-1, 1] for the given category."""
    n = int(duration_sec * sr)
    audio: list[float] = [0.0] * n

    fn = CATEGORY_MAP.get(category)
    if fn is None:
        # Generic: soft sine tone
        for i in range(n):
            audio[i] = math.sin(2 * math.pi * 440 * i / sr) * 0.2
    else:
        fn(audio, n, sr)

    # Global fade-in (0.25 s) and fade-out (0.5 s)
    fade_in_n = int(0.25 * sr)
    fade_out_n = int(0.50 * sr)
    for i in range(min(fade_in_n, n)):
        audio[i] *= i / fade_in_n
    for i in range(fade_out_n):
        idx = n - fade_out_n + i
        if 0 <= idx < n:
            audio[idx] *= (fade_out_n - i) / fade_out_n

    # Normalise to 0.85 peak
    peak = max((abs(s) for s in audio), default=0.0)
    if peak > 0:
        scale = 0.85 / peak
        for i in range(n):
            audio[i] *= scale

    return audio


def write_wav(samples: list[float], sr: int, path: str) -> None:
    """Write float samples [-1, 1] to a 16-bit mono WAV file."""
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        packed = struct.pack(
            f"<{len(samples)}h",
            *(max(-32768, min(32767, int(s * 32767))) for s in samples),
        )
        wf.writeframes(packed)
