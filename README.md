# AVOD-Lab

Browser-based AVOD stimulus platform for Experiment 1 (ad placement × ad relevance) and Experiment 2 (ad explanation × placement). Runs as a Flask app; logs every behavioural and survey event to SQLite.

**Contents**

- [Quick start](#quick-start)
- [Content and ad videos](#content-and-ad-videos) — [catalogue](#content-catalogue) · [viewer profile ad categories](#viewer-profile-ad-categories)
- [Conditions and assignment](#conditions-and-assignment) — Exp 1 / Exp 2 condition URLs, balanced minimisation
- [Testing without polluting production data](#testing-without-polluting-production-data) — the `?test=1` flag
- [Testing pipeline](#testing-pipeline--experiment-1) — manual QA checklist, in **[TESTING.md](TESTING.md)**
- [Questionnaire — Experiment 1](#questionnaire--experiment-1) — full item battery
- [Configuring conditions](#configuring-conditions)
- [Deployment](#deployment)
- [Project layout](#project-layout)

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py          # starts on http://localhost:8000
```

Admin panel (session list, cell balance, CSV export):

```
http://localhost:8000/admin?token=dev-admin-token
```

`requirements.txt` is deliberately minimal — just Flask and gunicorn, which is all the **study server** ever needs.

Building the video assets happens on your own machine and needs extra tooling, installed separately:

```bash
pip install -r requirements-build.txt   # Pillow + yt-dlp
```

| Tool | Needed by |
|---|---|
| `Pillow` | `generate_ads_v3.py` |
| `ffmpeg` + `ffprobe` (on PATH) | `generate_ads_v3.py`, `download_all.py`, `trim_content.py` |
| `yt-dlp` | `download_all.py` |

---

## Content and ad videos

All video files are excluded from git. Before running the server, generate synthetic ads and download content:

```bash
# 1. Generate synthetic ad MP4s
python scripts/generate_ads_v3.py    # 16 ads — 4 per viewer profile

# Regenerate specific ads only
python scripts/generate_ads_v3.py --only ad_intel_horizon ad_thrill_ranger

# 2. Download the catalogue's content videos
python scripts/download_all.py

# Download selectively
python scripts/download_all.py --ids big_buck_bunny sintel
python scripts/download_all.py --force    # re-download even if file exists
```

`download_all.py` reads `source_url` from each active title in `config/experiment.json`. YouTube URLs are fetched via yt-dlp; HTTP URLs are stream-copied via ffmpeg. Content is trimmed to **15 minutes (900 s)**. Ads are never downloaded — all 12 creatives are generated locally.

`"content_version"` in `config/experiment.json` is set to `"short"` by default — the player serves **exactly 8 min (480 s)** copies from `static/content_short/`. These are **not** created by `download_all.py`; generate them separately:

```bash
python scripts/trim_content.py --trim-sec 480   # the 8 min cap the study uses
python scripts/trim_content.py --force          # re-trim even if output exists
```

The full 15-min files in `static/content/` are still downloaded by `download_all.py` and are left untouched. Set `"content_version"` back to `"full"` to serve those instead.

The 480 s cap is below the shortest source clip (629 s), so **every active clip is exactly 8:00** — the forced mid-roll therefore falls at exactly 240 s for every participant, with no clip-length variation to control for. `catalog.titles[].duration_sec` holds this served length, which is what the browse tiles display.

### Content catalogue

Titles under 10 min have been retired. **Source duration** below is the length as downloaded (capped at 15 min by `download_all.py`). Every clip is truncated to 8:00 at playback, so source length affects only how much of each film is available, not what participants see.

| ID | Title | Genre | Source duration | Viewer profile | Source |
|---|---|---|---|---|---|
| `big_buck_bunny` | Big Buck Bunny | Animated Comedy | 10:35 | content_chameleon | Internet Archive (CC BY 3.0) |
| `elephant_dream` | Elephant's Dream | Sci-Fi Animation | 10:54 | intellectual_explorer | Internet Archive (CC BY 2.5) |
| `sintel` | Sintel | Fantasy Drama | 14:48 | intellectual_explorer | Internet Archive (CC BY 3.0) |
| `tears_of_steel` | Tears of Steel | Sci-Fi Thriller | 12:14 | intellectual_explorer | Internet Archive (CC BY 3.0) |
| `pioneer_one` | Pioneer One (Ep. 1) | Sci-Fi Drama | 15:00 | intellectual_explorer | Internet Archive (CC BY-NC-SA 3.0) |
| `sprite_fright` | Sprite Fright | Horror · Comedy | 10:30 | thrill_seeker | YouTube (CC BY 4.0) |
| `doa_1950` | D.O.A. | Crime · Noir | 15:00 | investigative_viewer | Internet Archive (PD) |
| `captain_kidd` | Captain Kidd | Action · Adventure | 15:00 | thrill_seeker | Internet Archive (PD) |
| `jackie_robinson` | The Jackie Robinson Story | Drama · Sports | 15:00 | thrill_seeker | Internet Archive (PD) |
| `blood_on_sun` | Blood on the Sun | Action · Thriller | 15:00 | thrill_seeker | Internet Archive (PD) |
| `hemo_magnificent` | Hemo the Magnificent | Science · Documentary | 15:00 | intellectual_explorer | YouTube (PD) |
| `unchained_goddess` | The Unchained Goddess | Science · Documentary | 15:00 | intellectual_explorer | YouTube (PD) |
| `his_girl_friday` | His Girl Friday | Screwball Comedy | 15:00 | content_chameleon | Internet Archive (PD) |
| `jack_beanstalk` | Jack and the Beanstalk | Family · Comedy | 15:00 | content_chameleon | Internet Archive (PD) |
| `inspector_general` | The Inspector General | Musical Comedy | 15:00 | content_chameleon | Internet Archive (PD) |
| `pied_piper` | The Pied Piper of Hamelin | Family · Fantasy | 15:00 | content_chameleon | Internet Archive (PD) |
| `detour_1945` | Detour | Crime · Noir | 15:00 | investigative_viewer | Internet Archive (PD) |
| `suddenly_1954` | Suddenly | Crime · Thriller | 15:00 | investigative_viewer | Internet Archive (PD) |
| `jigsaw_1949` | Jigsaw | Crime · Drama | 15:00 | investigative_viewer | Internet Archive (PD) |

To add a title: add an entry under `catalog.titles` in `config/experiment.json` with a `source_url` (YouTube or direct HTTP), a `relevant_ad_category`, and `context_tags`; add its ID to the relevant `rows`; then run `download_all.py --ids <new_id>` followed by `trim_content.py --ids <new_id>`. Confirm the licence permits research reuse before adding it.

### Viewer profile ad categories

Every title carries a `relevant_ad_category` field using one of four **viewer-profile labels**. The player uses this field to pick synthetic ads from `config/ad_library.json`: the *relevant* arm selects an ad whose `category` matches the title's profile; the *irrelevant* arm selects one that does not.

**Single taxonomy:** every title and every ad uses one of these four labels and nothing else. A title tagged with a label that no ad matches would leave the relevant pool empty, and the player would silently fall back to an arbitrary ad — quietly breaking the relevance manipulation.

| Profile | Content genres | Ads (product) |
|---|---|---|
| `thrill_seeker` | Action, adventure, sports, horror | THUNDERDROP (rollercoaster-park tickets), ADRENALINE (energy drink), APEX (running shoes), RANGER (climbing gear) |
| `intellectual_explorer` | Sci-Fi, fantasy, science, technology | SYNAPSE (smartphone), RENDERLAB (3D animation software), CURIOSITY (home telescope), HORIZON (VR headset) |
| `content_chameleon` | Comedy, family, musicals, animation | CHUCKLE (popcorn), TOONBOX (breakfast cereal), SINGALONG (karaoke machine), STAGECRAFT (theatre tickets) |
| `investigative_viewer` | Crime, noir, thrillers, courtroom | NIGHTWATCH (doorbell camera), TRIBUNAL (legal-advice app), WHODUNIT (detective audiobooks), CASEROOM (crime-fiction magazine) |

These 16 ads are the **v3 set** (`source: "synthetic_v3"` in `ad_library.json`), generated by `scripts/generate_ads_v3.py`. Earlier v1/v2 sets have been removed — v3 is the only synthetic set, and the player selects from it unconditionally.

**Every ad is a product ad.** Each sells a fictitious product the way a real AVOD spot does: the product is the hero, followed by a benefit line, a call to action and sometimes a price. The genre an ad belongs to is carried only by the mood graphics around the product (funfair bunting, a BMX jump, a race track, a starfield, confetti, a laughing theatre audience, police tape in the rain) and never named in the copy, so relevance is a contextual product–content match rather than a genre announcement or a content recommendation. Products are chosen to match topics the catalogue actually contains, and each is designed from the core of its genre rather than an edge it shares with another (investigation, documentary, fantasy and animation all straddle two genres). Ids are kept across redesigns, so survey codes and the answer key carry over; on-screen brands have changed for three of them: `ad_thrill_gravecrest` is now THUNDERDROP, `ad_invest_deadlines` is NIGHTWATCH, and `ad_invest_caseroom` is CASEROOM again, now a crime-fiction magazine.

### How a creative is chosen

Within the arm's pool, the player scores each ad against the title's `context_tags` and keeps only the extremes: the **relevant** arm takes the best-fitting ads, the **irrelevant** arm the worst-fitting.

The two arms use different margins. The irrelevant arm draws from twelve ads and already has variety, so it takes the worst fit outright (`IRRELEVANT_FIT_MARGIN = 0`). The relevant arm draws from four, and its margin is capped at `RELEVANT_FIT_MARGIN = 0.20` to protect the *floor* of the manipulation rather than its average — at 0.25 or above the weakest drawable ad falls to 0.25, which is barely better than the unranked pool averaged.

Fit is the **overlap coefficient** — shared tags divided by the size of the *smaller* tag set — not Jaccard. Jaccard divides by the union and so penalises an ad for carrying more tags; it ranked a generic action ad above the classic-film ad for a screwball comedy purely on tag count.

This matters for the manipulation. Scored across all 19 active titles:

| | Mean fit | Worst drawable fit | Separation | Ads usable in both arms |
|---|---|---|---|---|
| no ranking (the earlier behaviour) | 0.295 | 0.00 | 0.214 | 16/16 |
| ranking, earlier ad set | 0.750 | 0.50 | 0.750 | 13/16 |
| **shipping** | **0.625** | **0.50** | **0.625** | **16/16** |

**Pilot ratings are diagnostic only.** The assignment rule uses tag overlap alone; lay-viewer ratings from the ad-relevance pilots never enter it. They are used to find ads whose genre is not legible and improve them, and to check the mechanism's draws against perception: `scripts/check_pilot.py <qualtrics_export.csv> --codes pilot/codes_<date>.json` applies the pilot exclusions (previews, attention checks, speeders, and with `--min-type-sd 1.0` raters who barely separated the four types), runs the shipping `player.js` selection logic in Node, and lists every pairing the mechanism draws as irrelevant that raters scored above 3 on that genre, plus any ad raters did not place highest in its intended genre.

Judge this on the worst drawable fit, not the mean — the mean can look healthy while a minority of participants still draw a weak match. Every relevant draw now scores at least 0.50, every irrelevant draw exactly 0, and every one of the sixteen creatives is reachable in **both** arms, so no creative's appeal is confined to one side of the manipulation.

Verified by extracting the shipping `tagFit` and `resolveAdByRelevance` source from `player.js` and exercising it over 12,160 draws (19 titles × 2 arms × 80 rotation offsets × 4 video positions), asserting category, `effective_relevance` label, fit bounds and payload completeness on each.

Previously the ranking never took effect — the pool held exactly three ads and the code sliced to the top three — so a relevant ad was drawn uniformly, and *Captain Kidd* had a one-in-three chance of a horror ad and one-in-three of a car ad.

---

## Conditions and assignment

Append `?cond=<code>` to any participant URL to override the balanced assignment. Use this for testing and for sending condition-specific Prolific links.

### Experiment 1 — condition URLs

Experiment 1 is a **4 × 2 between-subjects design**: four ad placement conditions crossed with ad relevance (relevant / irrelevant), both balanced independently across participants.

| Code | Label | URL | Design note |
|------|-------|-----|-------------|
| A0   | Post-roll (control)  | `/?cond=A0` | Ad after clip; baseline |
| A1   | Forced pre-roll      | `/?cond=A1` | Ad before clip; shallow interruption |
| A2   | Forced mid-roll      | `/?cond=A2` | Ad at midpoint (50% of clip duration); deep interruption |
| A3   | Viewer-chosen timing | `/?cond=A3` | Timing gate blocks playback; participant picks before / middle / after; exactly one ad |

### A3 — viewer-chosen timing: full flow

**1 — Ad resolved before the gate opens.** When the session config is loaded, `resolveAdByRelevance()` immediately picks a concrete creative from the ad pool (using `sessionCreativeOffset` for randomisation) and stores it as `userChoice`. The participant never sees this step.

**2 — Participant clicks a title.** Instead of the normal play path, `showTimingChoice()` is called. A fullscreen overlay appears over the player:

> *You will see one short ad during this video. When would you like it to play?*
> **Before the video** · **In the middle** · **After the video**

A `timing_gate_shown` event is logged at this moment (enables deliberation-latency computation).

**3 — Participant picks.** The choice is locked immediately (`userChoice` cleared, overlay hidden). An `ad_timing_chosen` event is logged with `{ choice, ad_id, effective_relevance }`. Deliberation latency = `ts(ad_timing_chosen) − ts(timing_gate_shown)`.

The slot is re-dispatched into the same machinery used by A0–A2:

| Choice | Dispatch |
|---|---|
| Before the video | `preroll = { ...slot, placement: "preroll" }` → `playAd()` → content follows |
| In the middle | `{ ...slot, placement: "midroll", start_at_frac: 0.5 }` pushed to queue → `playContent()` → pauses at 50% |
| After the video | `postroll = { ...slot, placement: "postroll" }` → `playContent()` → ad on `content_ended` |

**4 — Post-survey.** Identical to A0–A2. Page 5 includes `ctrl_1`–`ctrl_3` (perceived control, 7-point Likert) in all conditions — A3 is expected to score higher on this index than A0–A2, since the timing gate gives participants an actual choice.

### Condition and relevance assignment

Assignment happens in two phases separated by an HTTP round-trip:

**Phase 1 — page load (`GET /`).** `load_config()` runs without a database connection. It cannot query cell counts, so it falls back to a random draw from `random_pool`. This provisional config is embedded in the page HTML and used only for initial rendering. It is **not** the locked assignment.

**Phase 2 — session start (`POST /api/session/start`).** The client calls this immediately on page load (before the participant interacts). `load_config()` now runs with the database and performs two sequential minimisation steps:

**Step A — timing condition.** Counts sessions per code in `random_pool`, finds the minimum, and randomly picks among all tied minimums (standard minimisation).

**Step B — relevance arm.** Within the just-chosen condition, counts `relevant` vs `irrelevant` sessions, picks the minimum. This keeps all eight (condition × relevance) cells near-equal.

**Which sessions count.** A session counts once it has completed the post-survey (`sessions.completed_at`, set when the post-survey's `survey_complete` event arrives), or while it may still be in progress: for `ABANDON_AFTER_MIN` minutes (30, in `app.py`) after the participant opened a video (`sessions.video_opened_at`, set on the first `watch_start`), or, before they have opened one, after the session started. Past that an unfinished session is treated as abandoned and stops counting, so drop-out that differs by condition (at a pre-roll, say, or the A3 gate) does not leave completed cells unequal. From opening a video, the clip, the ad and the post-survey take about 12 minutes, so 30 leaves a wide margin. In-progress sessions count so that a burst of simultaneous Prolific starts is still spread across cells. Real sessions are counted against real ones only, and test sessions against test ones.

Both are written to `sessions` in one INSERT. The full resolved config is returned to the client, which discards the provisional page config and uses this response for the rest of the session.

| `condition_source` value | Meaning |
|---|---|
| `balanced` | Normal minimisation assignment |
| `override` | `?cond=` URL parameter used (filter from analysis) |
| `random` | DB unavailable at assignment time (should not occur in production) |
| `fixed` | `condition_assignment_mode = "fixed"` in config |

**Race condition note.** Two simultaneous `session_start` calls can both read the same counts before either INSERT commits, landing in the same arm. This self-corrects at scale and is inherent to minimisation without row-level locking. It is not a concern at the target sample size (N = 1000).

**Ad relevance assignment (Exp 1 only).** The chosen arm is stored in `sessions.ad_relevance_arm` and logged in the `ad_start` event as `effective_relevance`. The ad creative is picked at play time to match (or mismatch) the viewer profile of the specific video the participant chose.

### Experiment 2 — condition URLs

Experiment 2 is a **3 × 2 between-subjects design**: explanation type × placement. Ad relevance is fixed to *relevant* in all B conditions so that the explanation banners are truthful.

| Code | Label | URL |
|------|-------|-----|
| B0   | No explanation, Mid-roll                  | `/?cond=B0` |
| B1   | Content-based explanation, Mid-roll       | `/?cond=B1` |
| B2   | Data-based explanation, Mid-roll          | `/?cond=B2` |
| B3   | No explanation, User-initiated            | `/?cond=B3` |
| B4   | Content-based explanation, User-initiated | `/?cond=B4` |
| B5   | Data-based explanation, User-initiated    | `/?cond=B5` |

> **Note.** Switch the active experiment by changing `random_pool` in `config/experiment.json` — see [Configuring conditions](#configuring-conditions).

---

## Testing without polluting production data

Append `&test=1` to any URL to tag the session as test data:

```
http://localhost:8000/?cond=A0&test=1
```

Test sessions are stored like any other session but are flagged (`sessions.is_test = 1`) and automatically excluded from:

- **Balanced assignment** for real participants, and the cell-balance panel and 8-cell breakdown on `/admin`. Test sessions are balanced among themselves instead, so consecutive test runs rotate through the conditions and both relevance arms rather than all landing in whichever cell the real data leaves emptiest.
- The **data export** — the admin page's **Downloads** card has an *including test* link, or add `&include_test=1` to the export URL. The file is one row per session with assignment, behaviour, every survey answer and the full event log (`events_json`); its `is_test` and `condition_source` columns (`override` marks a `?cond=` link) and `post_survey_complete` / `completed_at` let analysis filter to completers and tabulate drop-out by cell. See TESTING.md §6 for the columns.

Test sessions still show up in the admin session list, marked with a red **TEST** badge, and the admin header shows a running count ("N test sessions excluded").

**Returning to the catalogue.** `allow_return_to_catalogue` in `config/experiment.json` is `false` for Experiment 1: once a participant opens a video there is no way back, and the Step 2 instruction says they must watch the full video. Set it to `true` to restore the *← Browse* button, which allows going back before the ad starts (never once it has started); the instruction's no-return sentence then hides itself.

**Before sending the real study link to participants**, set `prolific_completion_url` in `config/experiment.json` to the completion URL from Prolific (while it is empty, the final screen just tells participants to close the tab and they cannot confirm completion), then wipe out all accumulated test data for a guaranteed clean slate:

```bash
python scripts/purge_sessions.py --all         # deletes every session and event — irreversible
python scripts/purge_sessions.py --test-only   # deletes only is_test=1 sessions (safe to run anytime)
```

Both prompt for confirmation; pass `--yes` to skip the prompt.

---

## Testing pipeline — Experiment 1

The full manual QA checklist — pre-flight check, per-condition smoke test, timing-gate verification, attention-check validation, cell-balance check, and the event schema reference — lives in **[TESTING.md](TESTING.md)**.

---

## Questionnaire — Experiment 1

The full battery is implemented in [`static/survey.js`](static/survey.js). Items are rendered in-browser; responses are logged as `survey_page` events.

### Pre-exposure battery (4 pages)

**Page 1 — Informed consent**

Six required checkboxes. All must be ticked before the participant can advance. Responses are logged as `true`/`false`.

| Item ID | Required | Statement |
|---------|----------|-----------|
| `consent_read` | Yes | I confirm that I have read and understood the information about this study on the previous page … |
| `consent_age` | Yes | I am at least 18 years of age. |
| `consent_voluntary` | Yes | I understand that my participation is voluntary … |
| `consent_data` | Yes | I consent to the collection and processing of the data … |
| `consent_deletion` | Yes | I understand that I may request deletion of my data within 14 days … |
| `consent_publication` | Yes | I consent to the anonymous publication of the research results … |

**Page 2 — Demographics**

| Item ID | Question | Type |
|---------|----------|------|
| `age` | Your age group | Radio (18–24 / 25–34 / 35–44 / 45–54 / 55 or older) |
| `gender` | Gender | Radio (4 options) |
| `vod_freq` | How often do you watch ad-supported streaming? | Radio (5 options) |

**Page 3 — Persuasion knowledge**
*(Written for this study, informed by Friestad & Wright 1994; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement |
|---------|-----------|
| `pk_1` | Advertisers try to get people to buy things they don't really need. |
| `pk_2` | When I see an ad, I can tell it is designed to persuade me. |
| `pk_3` | I understand the techniques that advertisers use to influence people. |

**Page 4 — Privacy concern / IUIPC**
*(adapted from Malhotra et al. 2004; 3 items per subscale; 1 = Strongly disagree, 7 = Strongly agree)*

Provenance differs by subscale, so report it precisely rather than citing IUIPC wholesale:

- **Collection** — `iuipc_col_1`–`col_3` are three of Malhotra's four collection items, verbatim.
- **Awareness** — all three map to Malhotra's awareness items with simplified wording. These are deliberately *normative* ("companies should disclose…"), which is how IUIPC defines the dimension: concern that privacy practices be transparent, not self-reported knowledge of what companies actually do. If asked, the answer is that the awareness items follow Malhotra et al.'s normative formulation.
- **Control** — `iuipc_ctl_3` closely renders Malhotra's first control item; `iuipc_ctl_1` and `iuipc_ctl_2` were newly written in its place.

Re-check subscale reliability in your own sample rather than citing the original's.

| Item ID | Subscale | Statement |
|---------|----------|-----------|
| `iuipc_col_1` | Collection | It bothers me to give personal information to so many online companies. |
| `iuipc_col_2` | Collection | I am concerned that online companies are collecting too much personal information about me. |
| `iuipc_col_3` | Collection | When online companies ask me for personal information, I sometimes think twice before providing it. |
| `iuipc_ctl_1` | Control | Online companies should be required to get my permission before using my personal information for any purpose. |
| `iuipc_ctl_2` | Control | I want to have complete control over what online companies do with my personal information. |
| `iuipc_ctl_3` | Control | Consumer online privacy is really a matter of consumers' right to exercise control over how their information is collected, used, and shared. |
| `iuipc_awa_1` | Awareness | Online companies should clearly disclose how they use the personal information they collect from me. |
| `iuipc_awa_2` | Awareness | Online companies' privacy policies should be clear and easy to find. |
| `iuipc_awa_3` | Awareness | It is very important to me to be aware of what online companies do with my personal information. |
| `attn_pre` | — | **Attention check** — select "Agree" (6) |

---

### Post-exposure battery (5 pages)

**Page 1 — Intrusiveness**
*(Li, Edwards & Lee 2002, verbatim; 1 = Strongly disagree, 7 = Strongly agree)*

The original format: one stem, **"When the ad played, I thought it was…"** (the original reads "popped-up", for pop-up ads), followed by the seven adjectives in the published order, shown as a single grid. The adjectives are near-synonyms by design. Written out as seven separate sentences, pilot testers read them as the same question asked repeatedly; under one stem they read as one question.

| Item ID | Adjective (display order) |
|---------|-----------|
| `int_7` | distracting |
| `int_4` | disturbing |
| `int_2` | forced |
| `int_6` | interfering |
| `int_1` | intrusive |
| `int_3` | invasive |
| `int_5` | obtrusive |

**Page 2 — Irritation**
*(written for this study; 1 = Strongly disagree, 7 = Strongly agree)*

Five items written for this study. They are not from Edwards et al. (2002), which measured irritation with *irritating, phony, ridiculous, stupid, terrible* (from Wells, Leavitt & McConville 1971).

| Item ID | Statement |
|---------|-----------|
| `irr_1` | I found the ad irritating. |
| `irr_2` | I found the ad annoying. |
| `irr_3` | I found the ad frustrating. |
| `irr_4` | I found the ad unpleasant. |
| `irr_5` | I was bothered by the ad. |

**Page 3 — Secondary attitudes**

| Item ID | Type | Anchors / question |
|---------|------|--------------------|
| `sat_1` | Likert-7 | Overall, I was satisfied with the viewing experience. |
| `ad_att_1` | Semantic diff | Bad ← 1–7 → Good *(attitude toward the ad)* |
| `ad_att_2` | Semantic diff | Unfavourable ← 1–7 → Favourable |
| `ad_att_3` | Semantic diff | Negative ← 1–7 → Positive |
| `plat_att_1` | Semantic diff | Bad ← 1–7 → Good *(attitude toward the platform)* |
| `plat_att_2` | Semantic diff | Unfavourable ← 1–7 → Favourable |
| `plat_att_3` | Semantic diff | Untrustworthy ← 1–7 → Trustworthy |

**Page 4 — Perceived ad-content fit + skip intention**
*(1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement | Role |
|---------|-----------|------|
| `rel_1` | The advertised product was relevant to the video I watched. | H3b/H3c mediator; relevance manipulation check |
| `rel_2` | The ad fit well with the content I chose. | H3b/H3c mediator |
| `rel_3` | It made sense to show this particular ad with this video. | H3b/H3c mediator |
| `skip_1` | If I could have skipped this ad, I would have. | Skip intention |
| `attn_post` | **Attention check** — select "Somewhat agree" (5) | — |

Score `rel_1`–`rel_3` as a mean (perceived fit index); report Cronbach's α. The relevance manipulation check is a t-test of this index between the relevant and irrelevant arms (relevant arm should score higher).

**Page 5 — Manipulation checks**

| Item ID | Conditions | Type | Question |
|---------|------------|------|----------|
| `ctrl_1` | All | Likert-7 | I felt in control of when the ad played. |
| `ctrl_2` | All | Likert-7 | It was up to me how the ad fit into my viewing. |
| `ctrl_3` | All | Likert-7 | I had a say in how the advertising interrupted my video. |
| `manip_ad_seen` | All | Radio | Did an ad play at any point while you were watching? |
| `manip_prior_ad` | All | Radio | Had you seen this specific advertisement before today? |
| `manip_relevance` | All | Likert-7 | The ad appeared to be chosen based on the type of video I watched. |
| `track_1` | All | Likert-7 | This ad seemed to use personal information about me, beyond the video I chose. |
| `track_2` | All | Likert-7 | Seeing this ad made me feel watched by the service. |

`ctrl_1`–`ctrl_3` form a perceived-control index (mean; report Cronbach's α). They serve two roles: (1) **manipulation check** — A3 should score higher than A0–A2, confirming the viewer-chosen condition actually raised perceived control; (2) **mediator** — perceived control is the proposed mechanism linking timing condition to lower intrusion (H1a mediation path).

`manip_relevance` is the relevance manipulation check. It is distinct from `rel_1`–`rel_3` (which measure perceived ad-content fit as a mediator): this item asks whether the participant perceived the *matching mechanism* rather than product-level fit. The manipulation succeeds if `manip_relevance` scores significantly higher in the relevant arm than in the irrelevant arm (independent-samples *t*-test, one-tailed).

`track_1`–`track_2` measure **perceived tracking** and are **exploratory** — the proposed route behind H2b. They separate two things participants could infer from a relevant ad: that it was matched to the *content* they chose (`manip_relevance`, `rel_1`–`rel_3`) versus matched to *them personally* via data collection. Score as a 2-item mean and report the inter-item correlation rather than α. Because the relevance manipulation is content-based only — no participant data is used for targeting — elevated scores here reflect inferred rather than actual tracking, which is the point: it tests whether relevance alone triggers privacy concern. Expect moderation by the pre-exposure IUIPC score.

---

## Configuring conditions

`config/experiment.json` is read on every request — no restart needed.

```jsonc
// Switch between experiments:
"condition_assignment_mode": "balanced",   // balanced | random | fixed
"active_condition": "A0",                  // used only when mode = "fixed"
"random_pool": ["A0","A1","A2","A3"],      // Experiment 1
// "random_pool": ["B0","B1","B2","B3","B4","B5"],  // switch to Experiment 2
```

### Ad relevance per condition

Each ad slot in a condition carries an `ad_relevance` field:

| Value | Behaviour |
|---|---|
| `"balanced"` | Server assigns "relevant" or "irrelevant" using balanced minimisation within that condition (Exp 1) |
| `"relevant"` | Always show an ad matching the video's viewer profile (Exp 2 / B conditions) |
| `"irrelevant"` | Always show an ad that does not match the video's viewer profile |

To add or swap ad creatives: add an entry to `config/ad_library.json` with a `category` matching one of the four viewer profile IDs (see [Viewer profile ad categories](#viewer-profile-ad-categories)), then generate the MP4 into `static/ads/` with the matching generation script.

---

## Deployment

Assets are built on your own machine and shipped to the server as files. **The study server never downloads anything** — it needs no `yt-dlp`, no `ffmpeg`, and no internet access during participant sessions. Every video, ad, and poster is served from `static/`.

### Step 1 — build the assets locally

```bash
pip install -r requirements-build.txt

python scripts/generate_ads_v3.py   # → static/ads/
python scripts/download_all.py      # → static/content/ (full length)
python scripts/trim_content.py --trim-sec 480   # → static/content_short/ (8 min, what the player serves)
```

> **Don't skip `trim_content.py`.** `content_version` defaults to `"short"`, so the player serves from `static/content_short/` — which only that script creates. Skipping it leaves every title unplayable. (Set `content_version` to `"full"` to serve the untrimmed files from `static/content/` instead.)

All 19 thumbnails are committed to `static/posters/` and served from there, so a fresh clone has them and the server never fetches an image. Run `download_posters.py` only to rebuild them: six are downloaded artwork, and thirteen are a frame of the title's own clip (`FRAME_POSTERS` in the script, which needs the clips in `static/content_short/`), because their published artwork was wrong, unreachable or only a credits card.

### Step 2 — transfer to the server

Copy the repository including the populated `static/` tree. If `content_version` is `"short"` you only strictly need `static/content_short/`, not the much larger `static/content/`:

```bash
rsync -av --progress \
  --exclude 'static/content/' \
  --exclude 'data/events.sqlite' \
  ./ user@server:/srv/avod-lab/
```

Excluding `data/events.sqlite` avoids shipping your local test database — the server creates a fresh one on first run. (If you have not already cleared test data, see [Testing without polluting production data](#testing-without-polluting-production-data).)

### Step 3 — run it

```bash
pip install -r requirements.txt          # Flask + gunicorn only
export ADMIN_TOKEN="$(openssl rand -hex 24)"
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Mount `data/` on a persistent volume (SQLite). For high concurrency, swap to Postgres — the schema ports unchanged.

### Prolific completion redirect

Add `"prolific_completion_url": "https://app.prolific.com/submissions/complete?cc=XXXX"` to `experiment.json`. The debriefing screen will show a clickable return link.

---

## Project layout

```
avod-lab/
├── app.py                      Flask backend; balanced assignment; event log
├── README.md                   Setup, configuration, questionnaire reference
├── TESTING.md                  Manual QA checklist + event schema reference
├── requirements.txt            Server deps (Flask + gunicorn) — all the server needs
├── requirements-build.txt      Asset-building deps (Pillow + yt-dlp), local machine only
├── pilot/                      Survey-code maps for ad-relevance pilots (no response data)
├── config/
│   ├── experiment.json         Conditions A0–A3, B0–B5; catalogue; ad_relevance per slot
│   └── ad_library.json         Ad metadata; 4 viewer-profile categories; the 16 live synthetic_v3 ads
├── data/events.sqlite          Created on first run
├── static/
│   ├── app.js                  Session management; view routing; survey intercept
│   ├── survey.js               Pre- and post-exposure questionnaire (Exp 1)
│   ├── browse.js               Catalogue / hero rendering
│   ├── player.js               Video + ad scheduler + viewer-profile ad selection
│   ├── ads/                    Synthetic ad MP4s (gitignored — run generate_ads_v3.py)
│   ├── content/                Content MP4s, full length (gitignored — run download_all.py)
│   ├── content_short/          Content MP4s, 8 min (gitignored — run trim_content.py)
│   ├── posters/                Catalogue thumbnails, all local (committed; download_posters.py rebuilds)
│   └── style.css               Dark-theme UI + survey form styles
├── templates/
│   ├── index.html              Participant page (intro → surveys → browse → player)
│   ├── admin.html              Cell-balance panel; session list; condition URLs
│   └── session.html            Per-session event drill-down
└── scripts/
    ├── generate_ads_v3.py      The 16 synthetic ads (Pillow + ffmpeg, 4 per viewer profile)
    ├── ad_audio.py             Pure-Python audio synthesis (stdlib only); imported by the ad generator
    ├── download_all.py         Downloads the content videos (trimmed to 15 min)
    ├── trim_content.py         Creates the 8 min copies in static/content_short/ (originals untouched)
    ├── download_posters.py     Rebuilds the thumbnails in static/posters/
    ├── check_pilot.py          Checks an ad-relevance pilot export against the assignment mechanism
    └── purge_sessions.py       Clears test and/or all sessions from data/events.sqlite
```
