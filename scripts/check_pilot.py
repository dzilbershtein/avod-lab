#!/usr/bin/env python3
"""
check_pilot.py — Compare an ad-relevance pilot against the app's relevance mechanism.

Diagnostic only. Pilot ratings are not used by the app: they show where the
tag-based assignment and lay viewers' perception disagree, so ads can be
improved before the next round.

Usage:
  python scripts/check_pilot.py <qualtrics_export.csv> --codes pilot/codes_2026-10-14.json
  python scripts/check_pilot.py export.csv --codes codes.json --min-duration 240 --min-type-sd 1.0

The codes file maps survey codes (A01, ...) to ad ids and lists the expected
attention-check answers. Exclusions: survey previews, failed attention checks,
completions faster than --min-duration seconds and, with --min-type-sd, raters
who barely told the four types apart (mean within-ad SD across the four type
ratings below the cut-off).

Which ads the app can draw as relevant or irrelevant for each clip is obtained
by running the shipping tagFit and resolveAdByRelevance from static/player.js
in Node, so the check always reflects the real mechanism. Requires node on PATH.
"""

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENRES = "ABCD"
CATEGORY_LETTER = {
    "thrill_seeker": "A",
    "intellectual_explorer": "B",
    "content_chameleon": "C",
    "investigative_viewer": "D",
}

NODE_PROGRAM = r"""
const fs = require('fs'), vm = require('vm');
const repo = process.argv[1];
const src = fs.readFileSync(repo + '/static/player.js', 'utf8');
const grab = (re, name) => {
  const m = src.match(re);
  if (!m) { throw new Error('could not find ' + name + ' in player.js'); }
  return m[0].replace(/^  /gm, '');
};
const program =
  grab(/const RELEVANT_FIT_MARGIN[\s\S]*?const IRRELEVANT_FIT_MARGIN = \d+;/, 'fit margins') + '\n' +
  grab(/function tagFit\([\s\S]*?\n  \}/, 'tagFit') + '\n' +
  grab(/function resolveAdByRelevance\(slot, title\) \{[\s\S]*?\n  \}\n/, 'resolveAdByRelevance') + '\n' +
  'globalThis.__resolve = resolveAdByRelevance;' +
  'globalThis.__setRotation = (o, n) => { sessionCreativeOffset = o; sessionVideoCount = n; };';
const ctx = { window: { experiment: { cfg: {} } }, Math, Set, Object, Array };
vm.createContext(ctx);
vm.runInContext('let sessionAdRelevance = null, sessionCreativeOffset = null, sessionVideoCount = 0;' + program, ctx);

const lib = JSON.parse(fs.readFileSync(repo + '/config/ad_library.json', 'utf8')).ads;
const exp = JSON.parse(fs.readFileSync(repo + '/config/experiment.json', 'utf8'));
const clips = Object.entries(exp.catalog.titles)
  .filter(([id, t]) => !id.startsWith('_') && typeof t === 'object');
ctx.window.experiment.cfg._ad_library = { ads: lib };

const out = { relevant: {}, irrelevant: {} };
for (const [clipId, clip] of clips) {
  for (const arm of ['relevant', 'irrelevant']) {
    ctx.window.experiment.cfg.resolved_ad_relevance = arm;
    for (let offset = 0; offset < 60; offset++) {
      for (let video = 0; video < 4; video++) {
        ctx.__setRotation(offset, video);
        const ad = ctx.__resolve({ ad_relevance: 'balanced' }, clip);
        const entry = (out[arm][ad.id] = out[arm][ad.id] || {});
        entry[clip.relevant_ad_category] = entry[clip.relevant_ad_category] || [];
        if (!entry[clip.relevant_ad_category].includes(clipId)) entry[clip.relevant_ad_category].push(clipId);
      }
    }
  }
}
process.stdout.write(JSON.stringify(out));
"""


def rating(value):
    return int(value.split(" ")[0])


def type_separation(r, codes):
    """Mean over ads of the population SD of the rater's four type ratings."""
    return statistics.mean(statistics.pstdev([rating(r[f"{c}_{k}"]) for k in range(1, 5)]) for c in codes)


def load_responses(path, attention, min_duration, codes, min_type_sd):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ResponseId", "").startswith("R_")]
    valid, excluded = [], []
    for r in rows:
        if r["Status"] != "IP Address":
            excluded.append((r["ResponseId"], "survey preview"))
        elif any(rating(r[col]) != want for col, want in attention.items()):
            excluded.append((r["ResponseId"], "failed attention check"))
        elif int(r["Duration (in seconds)"]) < min_duration:
            excluded.append((r["ResponseId"], f"speeder ({r['Duration (in seconds)']} s)"))
        elif min_type_sd and type_separation(r, codes) < min_type_sd:
            excluded.append((r["ResponseId"], f"low type separation (SD {type_separation(r, codes):.2f})"))
        else:
            valid.append(r)
    return valid, excluded


def mechanism_draws():
    try:
        result = subprocess.run(["node", "-e", NODE_PROGRAM, REPO],
                                capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("node is required to run the shipping player.js logic")
    except subprocess.CalledProcessError as exc:
        sys.exit("running player.js logic failed:\n" + exc.stderr)
    return json.loads(result.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="Qualtrics CSV export")
    ap.add_argument("--codes", required=True, help="JSON file mapping survey codes to ad ids")
    ap.add_argument("--min-duration", type=int, default=180, help="seconds; faster completions are excluded")
    ap.add_argument("--min-type-sd", type=float, default=0.0,
                    help="exclude raters whose mean within-ad SD is below this (default off)")
    ap.add_argument("--threshold", type=float, default=3.0,
                    help="flag an irrelevant pairing whose mean fit is above this (default 3)")
    args = ap.parse_args()

    spec = json.load(open(args.codes))
    library = {a["id"]: a for a in json.load(open(os.path.join(REPO, "config", "ad_library.json")))["ads"]}
    valid, excluded = load_responses(args.csv, spec["attention"], args.min_duration,
                                     spec["codes"], args.min_type_sd)

    print(f"Responses: {len(valid)} valid, {len(excluded)} excluded")
    for rid, why in excluded:
        print(f"  excluded {rid}: {why}")
    if not valid:
        sys.exit("no valid responses")

    means = {}
    for code in spec["codes"]:
        means[code] = [statistics.mean(rating(r[f"{code}_{k}"]) for r in valid) for k in range(1, 5)]

    draws = mechanism_draws()
    irr_flags, rel_flags = [], []

    print(f"\nMean fit per ad (1-7, N = {len(valid)})")
    print(f"  {'code':5s}{'ad':24s}{'int':5s}{'A':>6s}{'B':>6s}{'C':>6s}{'D':>6s}   status")
    for code, info in spec["codes"].items():
        ad_id, intended = info["ad_id"], info["intended"]
        m = means[code]
        in_library = ad_id in library
        changed = ad_id in spec.get("changed_since_pilot", [])
        status = ("retired (not in current library)" if not in_library
                  else "redesigned since this pilot" if changed else "in library")
        print(f"  {code:5s}{ad_id:24s}{intended:5s}" + "".join(f"{x:6.2f}" for x in m) + f"   {status}")
        if not in_library or changed:
            continue
        top = max(range(4), key=lambda i: m[i])
        if GENRES[top] != intended:
            rel_flags.append(f"{code} {ad_id}: rated highest on {GENRES[top]} ({m[top]:.2f}), "
                             f"not its intended {intended} ({m[GENRES.index(intended)]:.2f})")
        for category, clips in draws["irrelevant"].get(ad_id, {}).items():
            g = CATEGORY_LETTER[category]
            if m[GENRES.index(g)] > args.threshold:
                irr_flags.append(f"{code} {ad_id}: drawn as irrelevant for {g} ({len(clips)} clips), "
                                 f"but rated {m[GENRES.index(g)]:.2f} on {g}")

    print(f"\nIrrelevant arm: pairings the mechanism draws that raters scored above {args.threshold:g}")
    for line in irr_flags or ["none"]:
        print("  " + line)
    print("\nRelevant arm: ads raters did not place highest in their intended category")
    for line in rel_flags or ["none"]:
        print("  " + line)

    rated = {info["ad_id"] for info in spec["codes"].values()}
    unrated = sorted((set(library) - rated) | (set(library) & set(spec.get("changed_since_pilot", []))))
    print("\nAds whose current version has no ratings in this pilot")
    print("  " + (", ".join(unrated) if unrated else "none"))


if __name__ == "__main__":
    main()
