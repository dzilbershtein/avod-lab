# AVOD-Lab

Browser-based AVOD stimulus platform for Experiment 1 (ad placement × ad relevance) and Experiment 2 (ad explanation × placement). Runs as a Flask app; logs every behavioural and survey event to SQLite.

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

---

## Content and ad videos

All video files are excluded from git. Before running the server, generate synthetic ads and download content:

```bash
# 1. Generate synthetic ad MP4s (requires Pillow + ffmpeg)
python scripts/generate_ads.py       # v1 — 12 ads, original set
python scripts/generate_ads_v2.py    # v2 — 12 ads, richer visuals
python scripts/generate_ads_v3.py    # v3 — 12 ads, content-library targeted (recommended)

# Generate a single ad (any script supports --only)
python scripts/generate_ads_v3.py --only ad_intel_horizon ad_thrill_torque

# 2. Download all content and non-synthetic ad videos
#    (requires yt-dlp + ffmpeg on PATH)
python scripts/download_all.py

# Download selectively
python scripts/download_all.py --content-only
python scripts/download_all.py --ads-only
python scripts/download_all.py --ids big_buck_bunny sintel decay_cern
python scripts/download_all.py --force    # re-download even if file exists
```

`download_all.py` reads `source_url` from `config/experiment.json` and `config/ad_library.json`. YouTube URLs are fetched via yt-dlp; HTTP URLs are stream-copied via ffmpeg. Content is trimmed to **15 minutes (900 s)**; ads are trimmed to **15 seconds**.

To create shorter (≤11 min) copies without touching the originals:

```bash
python scripts/trim_content.py            # trim all active titles → static/content_short/
python scripts/trim_content.py --force    # re-trim even if output exists
python scripts/trim_content.py --trim-sec 600  # custom cap
```

Then switch `"content_version"` in `config/experiment.json` from `"full"` to `"short"`. The player will serve from `static/content_short/`; the full 15-min files in `static/content/` are preserved.

### Content catalogue

All clips are 10–15 minutes. Titles under 10 min have been retired.

| ID | Title | Genre | Duration | Viewer profile | Source |
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

**Inactive titles** (in catalog but not shown in any row): `plan_9`, `night_of_living_dead`, `decay_cern`, `teenagers_outer_space`, `little_shop_horrors` — horror/B-movie content de-prioritised to balance the library.

To add CC YouTube content: add an entry to `scripts/cc_video_manifest.json`, run `python scripts/fetch_cc_videos.py --verify-only` to confirm the license, then paste the catalogue snippet into `config/experiment.json` and add the ID to the relevant `rows`.

### Viewer profile ad categories

Every title carries a `relevant_ad_category` field using one of four **viewer-profile labels**. The player uses this field to pick synthetic ads from `config/ad_library.json`: the *relevant* arm selects an ad whose `category` matches the title's profile; the *irrelevant* arm selects one that does not.

**Single taxonomy:** all active titles and all synthetic ads use the same four labels. Never tag a title with a product label (`electronics_tech`, `automotive`, `food_beverage`) — those labels exist only on archived/retired ad assets and have no matching synthetic ads, so the relevance manipulation would silently fall back to a random ad.

| Profile | Content genres | v1 ads | v3 ads (content-targeted) |
|---|---|---|---|
| `thrill_seeker` | Action, adventure, sports, horror | ENERGYBLAST, BATTLECAST, RUSHZONE | GRAVECREST (horror), TORQUE (cars/outdoors), VANGUARD (adventure) |
| `intellectual_explorer` | Sci-Fi, fantasy, science, travel | MINDSPAN, WANDERSCOUT, STARATLAS | CURIOSITY (science/nature), HORIZON (sci-fi/fantasy), TERRA (nature/travel) |
| `content_chameleon` | Comedy, family, nature, lifestyle | COMFYHOME, FUNSTREAM, PETPALS | TOONBOX (animation), STAGECRAFT (classic film), PANTRY (food/grocery) |
| `investigative_viewer` | Drama, thriller, crime, news | TRUEVIEW, NEWSDESK, CASEFILE | NOCTURNE (noir), DEADLINES (journalism), CASEROOM (true crime) |

The active ad set is controlled by `synthetic_ad_version` in `config/experiment.json` (`"v1"`, `"v2"`, or `"v3"`). v3 ads are designed to maximise tag-Jaccard overlap with the specific content in the library.

---

## Triggering conditions

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

**4 — Post-survey.** Identical to A0–A2 plus one additional item on page 5: `manip_control` — *"To what extent did you feel in control of when the ad played?"* (5-point scale, A3 only).

### Condition and relevance assignment

Assignment happens in two phases separated by an HTTP round-trip:

**Phase 1 — page load (`GET /`).** `load_config()` runs without a database connection. It cannot query cell counts, so it falls back to a random draw from `random_pool`. This provisional config is embedded in the page HTML and used only for initial rendering. It is **not** the locked assignment.

**Phase 2 — session start (`POST /api/session/start`).** The client calls this immediately on page load (before the participant interacts). `load_config()` now runs with the database and performs two sequential minimisation steps:

**Step A — timing condition.** Counts completed sessions per code in `random_pool`, finds the minimum, and randomly picks among all tied minimums (standard minimisation).

**Step B — relevance arm.** Within the just-chosen condition, counts `relevant` vs `irrelevant` sessions, picks the minimum. This keeps all eight (condition × relevance) cells near-equal.

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

> **Note.** Without `?cond=`, the server uses balanced minimisation to assign the least-filled arm from `random_pool` in `config/experiment.json`. For a live study, send each Prolific participant their condition-specific link; the override is logged in `condition_source = "override"`.

---

## Testing pipeline — Experiment 1

### 1. Pre-flight check (run once)

```bash
python app.py &
curl -s http://localhost:8000/healthz          # → {"ok": true, ...}
curl -s http://localhost:8000/admin?token=dev-admin-token | grep "AVOD-Lab"
kill %1
```

### 2. Per-condition smoke test

Run the following checklist for **each of A0–A3**. Open the URL in a fresh private/incognito window each time so you get a clean session.

```
http://localhost:8000/?cond=A0   (repeat for A1, A2, A3)
```

**Step-by-step checklist**

| # | Step | What to verify |
|---|------|----------------|
| 1 | Intro screen loads | Study title and intro text visible; "Begin" button present |
| 2 | Click **Begin** | Pre-survey appears; consent form shown first; page counter shows "1 / 4" |
| 3 | Complete **Demographics** page | Age, gender, VOD frequency — all required; "Next" blocked if any missing |
| 4 | Complete **Persuasion knowledge** page | 3 × 7-point Likert items |
| 5 | Complete **Privacy concern** page | 9 × IUIPC items (3 per subscale) + 1 attention check (select "Agree" = 6) |
| 6 | Browse screen appears | Hero tile and catalogue rows visible |
| 7 | Click a title | Player screen opens; "Now watching" label correct |
| 8 | *(A0)* Watch clip to end | 15-second post-roll ad plays; countdown visible; ad ends; post-survey appears |
| 8 | *(A1)* Click Play | 15-second pre-roll plays first; countdown visible; ad ends; content begins |
| 8 | *(A2)* Watch to midpoint | Content pauses; 15-second mid-roll plays; content resumes |
| 8 | *(A3)* Open title | Timing-choice gate appears over the player (before playback starts); click one of the three buttons → gate hides, ad plays at chosen moment, content plays around it |
| 9 | Ad completes → post-survey appears | Page counter shows "1 / 5"; A3 verify the chosen timing fired correctly |
| 10 | Complete **Intrusiveness** page | 7 × 7-point items |
| 11 | Complete **Irritation** page | 5 × 7-point items |
| 12 | Complete **Attitudes** page | Satisfaction + 3 ad-attitude + 3 platform-attitude semantic differentials |
| 13 | Complete **Skip intention** page | Skip item + attention check (select "Somewhat agree" = 5) |
| 14 | Complete **Manipulation checks** page | A3: control item; all: ad-seen + prior-exposure |
| 15 | Click **Submit** | Debriefing screen appears |
| 16 | Admin panel | Session visible; condition code correct; `n_events` > 20 |

### 3. Timing-choice gate — A3

```
http://localhost:8000/?cond=A3
```

1. Complete the pre-survey and click a title.
2. Verify the timing-choice gate appears over the player (before any content starts).
3. Click each option in separate runs and confirm:
   - **Before the video** → 15s ad plays first, then content starts
   - **In the middle** → content plays to ~50%, pauses, ad plays, content resumes
   - **After the video** → content plays to end, then ad plays
4. Confirm `ad_timing_chosen` event appears in the admin drill-down with the correct `choice` value.
5. Confirm the post-survey appears after the ad completes in all three paths.

### 4. Attention check verification

After completing a survey with **wrong** answers on the attention-check items, open the admin and drill into the session. In the `survey_page` events, verify:

```json
{ "attn_pre_pass": false }   // if wrong answer given on pre-survey
{ "attn_post_pass": false }  // if wrong answer given on post-survey
```

Participants who fail both checks should be flagged for exclusion per the pre-registered criteria.

### 5. Cell balance check

After running each of A0–A3 at least once:

```
http://localhost:8000/admin?token=dev-admin-token
```

The **Experiment 1 — cell balance** panel should show one session per condition and balanced percentages. The "Source" badge on each session should read **balanced** (or **override** if you used `?cond=`).

To verify ad relevance assignment, check the CSV export: the `ad_start` event for each session should have `"effective_relevance": "relevant"` or `"effective_relevance": "irrelevant"` in the `payload` column. Across sessions in the same condition the counts should be roughly equal.

### 6. CSV export and event schema

```
http://localhost:8000/admin/export.csv?token=dev-admin-token
```

Key columns: `session_id`, `condition` (e.g. `A2`), `condition_label`, `ts_server`, `ts_client`, `kind`, `payload` (JSON).

The `sessions` table also has an `ad_relevance_arm` column (`"relevant"` or `"irrelevant"`) that records the balanced assignment for Experiment 1.

Events logged per session:

| kind | when fired |
|------|-----------|
| `session_start` | Session created |
| `survey_page` | Each survey page submitted |
| `survey_complete` | Pre- or post-survey finished |
| `browse_open` | Participant reaches catalogue |
| `tile_click` | Title selected |
| `watch_start` / `watch_end` | Player opens / closes |
| `content_play` / `content_pause` / `content_seek` | Playback events |
| `content_ended` | Main clip finished |
| `ad_start` / `ad_end` | Ad playback — payload includes `ad_id`, `category`, `effective_relevance` |
| `timing_gate_shown` | A3: timing-choice gate displayed (start of deliberation window) |
| `ad_timing_chosen` | A3: participant picked a timing (payload: `choice` = preroll / midroll / postroll); latency = this ts − `timing_gate_shown` ts |
| `ad_prompt_shown` / `ad_prompt_clicked` / `ad_prompt_declined` | Exp-2 B-series user-initiated CTA events |
| `ad_schedule_resolved` | Mid-roll/overlay timing computed |
| `banner_shown` / `banner_hidden` / `banner_click` | Explanation/sponsor banner |
| `page_unload` | Browser tab closed / navigated away |

---

## Questionnaire — Experiment 1

The full battery is implemented in [`static/survey.js`](static/survey.js). Items are rendered in-browser; responses are logged as `survey_page` events.

### Pre-exposure battery (4 pages)

**Page 1 — Informed consent**

Six required checkboxes and one optional checkbox. All required items must be ticked before the participant can advance. Responses are logged as `true`/`false`.

| Item ID | Required | Statement |
|---------|----------|-----------|
| `consent_read` | Yes | I confirm that I have read and understood the information letter for this study (Version 1.0) … |
| `consent_age` | Yes | I am at least 18 years of age. |
| `consent_voluntary` | Yes | I understand that my participation is voluntary … |
| `consent_data` | Yes | I consent to the collection and processing of the data … |
| `consent_deletion` | Yes | I understand that I may request deletion of my data within 14 days … |
| `consent_publication` | Yes | I consent to the anonymous publication of the research results … |
| `consent_summary` | No | I would like to receive a plain-language summary of the research results … |

**Page 2 — Demographics**

| Item ID | Question | Type |
|---------|----------|------|
| `age` | Your age group | Radio (18–24 / 25–34 / 35–44 / 45–54 / 55 or older) |
| `gender` | Gender | Radio (4 options) |
| `vod_freq` | How often do you watch ad-supported streaming? | Radio (5 options) |

**Page 3 — Persuasion knowledge**
*(Friestad & Wright 1994; Jung et al. 2019; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement |
|---------|-----------|
| `pk_1` | Advertisers try to get people to buy things they don't really need. |
| `pk_2` | When I see an ad, I can tell it is designed to persuade me. |
| `pk_3` | I understand the techniques that advertisers use to influence people. |

**Page 4 — Privacy concern / IUIPC**
*(Malhotra et al. 2004; 3 items per subscale; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Subscale | Statement |
|---------|----------|-----------|
| `iuipc_col_1` | Collection | It bothers me to give personal information to so many online companies. |
| `iuipc_col_2` | Collection | I am concerned that online companies are collecting too much personal information about me. |
| `iuipc_col_3` | Collection | When online companies ask me for personal information, I sometimes think twice before providing it. |
| `iuipc_ctl_1` | Control | Online companies should be required to get my permission before using my personal information for any purpose. |
| `iuipc_ctl_2` | Control | I want to have complete control over what online companies do with my personal information. |
| `iuipc_ctl_3` | Control | Consumer online privacy is really a matter of consumers' right to exercise control over how their information is collected, used, and shared. |
| `iuipc_awa_1` | Awareness | Online companies should clearly disclose how they use the personal information they collect from me. |
| `iuipc_awa_2` | Awareness | I am usually aware of whether or not an online company is collecting information about me. |
| `iuipc_awa_3` | Awareness | It is very important to me to be aware of what online companies do with my personal information. |
| `attn_pre` | — | **Attention check** — select "Agree" (6) |

---

### Post-exposure battery (5 pages)

**Page 1 — Intrusiveness**
*(Li et al. 2002; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement |
|---------|-----------|
| `int_1` | The ad was intrusive. |
| `int_2` | The ad was forced on me. |
| `int_3` | The ad was invasive. |
| `int_4` | The ad disturbed me. |
| `int_5` | The ad was obtrusive. |
| `int_6` | The ad intruded on what I was doing. |
| `int_7` | The ad interrupted my activity. |

**Page 2 — Irritation**
*(Edwards et al. 2002; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement |
|---------|-----------|
| `irr_1` | I found the ad irritating. |
| `irr_2` | I found the ad annoying. |
| `irr_3` | I found the ad aggravating. |
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

**Page 5 — Manipulation checks** *(condition-dependent)*

| Item ID | Conditions | Type | Question |
|---------|------------|------|----------|
| `manip_control` | A3 only | Likert-5 | To what extent did you feel in control of when the ad played? |
| `manip_ad_seen` | All | Radio | Did you see an advertisement during or after the video clip? |
| `manip_prior_ad` | All | Radio | Had you seen this specific advertisement before today? |
| `manip_relevance` | All | Likert-7 | The ad appeared to be chosen based on the type of video I watched. |

`manip_relevance` is the relevance manipulation check. It is distinct from `rel_1`–`rel_3` (which measure perceived ad-content fit as a mediator): this item asks whether the participant perceived the *matching mechanism* rather than product-level fit. The manipulation succeeds if `manip_relevance` scores significantly higher in the relevant arm than in the irrelevant arm (independent-samples *t*-test, one-tailed).

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

The video → ad category mapping is set by `relevant_ad_category` on each title in the catalogue. To add or swap ad creatives, add an entry to `config/ad_library.json` and make sure its `category` matches one of the four viewer profile IDs (`thrill_seeker`, `intellectual_explorer`, `content_chameleon`, `investigative_viewer`). Synthetic ads must also exist as MP4 files in `static/ads/` (run the matching generation script to regenerate). The active set is selected by `"synthetic_ad_version"` in `experiment.json`.

---

## Deployment

```bash
export ADMIN_TOKEN="$(openssl rand -hex 24)"
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Mount `data/` on a persistent volume (SQLite). For high concurrency, swap to Postgres — the schema ports unchanged.

### Offline / air-gapped server

The server does not need internet access at runtime. All `video_url` fields point to `/static/content/<id>.mp4` or `/static/ads/<id>.mp4`. Populate these before deployment:

```bash
python scripts/generate_ads_v3.py  # recommended synthetic ads (content-targeted)
python scripts/download_all.py     # content + non-synthetic ads
```

Then copy the `static/` tree to the server. No outbound requests are made during participant sessions.

### Prolific completion redirect

Add `"prolific_completion_url": "https://app.prolific.com/submissions/complete?cc=XXXX"` to `experiment.json`. The debriefing screen will show a clickable return link.

---

## Project layout

```
avod-lab/
├── app.py                      Flask backend; balanced assignment; event log
├── config/
│   ├── experiment.json         Conditions A0–A3, B0–B5; catalogue; ad_relevance per slot
│   └── ad_library.json         Ad metadata; 4 viewer-profile categories; 12 synthetic ads (3 per category)
├── data/events.sqlite          Created on first run
├── static/
│   ├── app.js                  Session management; view routing; survey intercept
│   ├── survey.js               Pre- and post-exposure questionnaire (Exp 1)
│   ├── browse.js               Catalogue / hero rendering
│   ├── player.js               Video + ad scheduler + viewer-profile ad selection
│   ├── ads/                    Synthetic ad MP4s (gitignored — run generate_ads.py)
│   ├── content/                Content MP4s (gitignored — run download_all.py)
│   └── style.css               Dark-theme UI + survey form styles
├── templates/
│   ├── index.html              Participant page (intro → surveys → browse → player)
│   ├── admin.html              Cell-balance panel; session list; condition URLs
│   └── session.html            Per-session event drill-down
└── scripts/
    ├── generate_ads.py         v1 — 12 synthetic ads (Pillow + ffmpeg, 3 per viewer profile)
    ├── generate_ads_v2.py      v2 — 12 synthetic ads with richer visuals and glow text
    ├── generate_ads_v3.py      v3 — 12 synthetic ads designed for this content library (recommended)
    ├── ad_audio.py             Pure-Python audio synthesis (stdlib only); imported by all ad generators
    ├── download_all.py         Downloads all content + ad videos; trims to 900 s / 15 s
    ├── trim_content.py         Creates ≤11 min copies in static/content_short/ (originals untouched)
    ├── fetch_cc_videos.py      Verifies CC licenses and downloads YouTube content
    └── cc_video_manifest.json  Source URLs and metadata for CC YouTube titles
```
