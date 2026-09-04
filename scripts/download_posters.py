#!/usr/bin/env python3
"""
download_posters.py — Fetch film poster images into static/posters/.

Run once before deployment so the server never needs to reach out to
external hosts at runtime.

Usage:
    python scripts/download_posters.py            # download all missing
    python scripts/download_posters.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
import urllib.error

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "posters")

# Archive.org thumbnail service follows redirects to the item's cover image.
IA = "https://archive.org/services/img/{}"

POSTERS: dict[str, str] = {
    # ── Blender open movies ───────────────────────────────────────────────────
    "big_buck_bunny":     "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Big_buck_bunny_poster_big.jpg/800px-Big_buck_bunny_poster_big.jpg",
    "elephant_dream":     "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Elephants_Dream_s5_both.jpg/800px-Elephants_Dream_s5_both.jpg",
    "sintel":             "https://durian.blender.org/wp-content/uploads/2010/09/sintel-poster-front.jpg",
    "tears_of_steel":     IA.format("TearsOfSteel"),
    "spring_blender":     IA.format("SpringOpenMovieLaunchEdition"),
    "charge_blender":     IA.format("charge-2022-blender"),
    "coffee_run":         IA.format("coffee-run-2020-blender"),
    "hero_blender":       IA.format("Hero2018Blender"),
    "agent_327":          IA.format("Agent327OperationBarbershop"),
    "caminandes_llamigos":IA.format("caminandes-llamigos"),
    "cosmos_laundromat":  IA.format("CosmosLaundromatFirstCycle"),
    "sprite_fright":      IA.format("sprite-fright"),

    # ── Public-domain film library ────────────────────────────────────────────
    "pioneer_one":        IA.format("PioneerOneS01E01720pHD"),
    "doa_1950":           IA.format("D.o.a.VideoQualityUpgrade"),
    "captain_kidd":       IA.format("CaptainKidd1945"),
    "jackie_robinson":    IA.format("Jackie_Robinson_Story_The"),
    "blood_on_sun":       IA.format("BloodOnTheSun1945JAMESCAGNEY"),
    "hemo_magnificent":   IA.format("HemoTheMagnificent"),
    "unchained_goddess":  IA.format("TheUnchainedGoddess"),
    "his_girl_friday":    IA.format("his-girl-friday-1940_202109"),
    "jack_beanstalk":     IA.format("jack-and-the-beanstalk-1952-hd"),
    "inspector_general":  IA.format("TheInspectorGeneral720p1949"),
    "pied_piper":         IA.format("The_Pied_Piper_of_Hamelin"),
    "detour_1945":        IA.format("detour1945HD"),
    "suddenly_1954":      IA.format("Suddenly_1954"),
    "jigsaw_1949":        IA.format("Jigsaw720p1949"),
    "plan_9":             IA.format("plan-9-from-outer-space"),
    "night_of_living_dead": IA.format("night-of-the-living-dead_1968"),
    "decay_cern":         IA.format("Decay2012-TheLhcZombieFilmfullFilm"),
    "teenagers_outer_space": IA.format("TeenagersFromOuterSpace_1959"),
    "little_shop_horrors":   IA.format("the-little-shop-of-horrors-1960-colorized"),

    # ── Archival / educational shorts ────────────────────────────────────────
    "date_with_your_family": IA.format("DateWith1950"),
    "foundation_foods":      IA.format("Foundati1951"),
    "uncle_jim_dairy":       IA.format("UncleJim1963"),

    # ── Subaru / automotive content ───────────────────────────────────────────
    "subaru_outback": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/images/SubaruOutbackOnStreetAndDirt.jpg",
}


def download(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; avod-lab-poster-downloader/1.0)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 1000:
            print(f"    ✗ response too small ({len(data)} bytes) — likely a placeholder")
            return False
        ext = ".jpg"
        ct = resp.headers.get("Content-Type", "")
        if "png" in ct:
            ext = ".png"
        elif "webp" in ct:
            ext = ".webp"
        # always save as .jpg regardless — browsers handle it fine by content
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except urllib.error.HTTPError as e:
        print(f"    ✗ HTTP {e.code}")
        return False
    except Exception as e:
        print(f"    ✗ {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    ok = failed = skipped = 0

    for tid, url in POSTERS.items():
        dest = os.path.join(OUT_DIR, f"{tid}.jpg")
        if os.path.exists(dest) and not args.force:
            print(f"  skip  {tid}")
            skipped += 1
            continue
        print(f"  fetch {tid}")
        print(f"        {url[:80]}")
        if download(url, dest):
            size = os.path.getsize(dest)
            print(f"    ✓ {size // 1024} KB → {dest}")
            ok += 1
        else:
            failed += 1
        time.sleep(0.4)   # be polite to archive.org

    print(f"\nDone: {ok} downloaded, {skipped} skipped, {failed} failed.")
    if failed:
        print("Failed items will keep their current (external) poster URL.")
    sys.exit(0)


if __name__ == "__main__":
    main()
