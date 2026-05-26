# AVOD-Lab

Browser-based AVOD stimulus platform for Experiment 1 (ad placement × user control) and Experiment 2 (ad explanation × placement). Runs as a Flask app; logs every behavioural and survey event to SQLite.

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

## Triggering conditions

Append `?cond=<code>` to any participant URL to override the balanced assignment. Use this for testing and for sending condition-specific Prolific links.

### Experiment 1 — condition URLs

| Code | Label                    | URL                        | Design note                         |
|------|--------------------------|----------------------------|-------------------------------------|
| A0   | Post-roll (control)      | `/?cond=A0`                | Ad after clip; baseline             |
| A1   | Forced pre-roll          | `/?cond=A1`                | Ad before clip; shallow interruption|
| A2   | Forced mid-roll          | `/?cond=A2`                | Ad at midpoint; deep interruption   |
| A3   | Non-interruptive overlay | `/?cond=A3`                | Banner over lower-third; no pause   |
| A4   | User-initiated           | `/?cond=A4`                | Prompt at midpoint; click-to-watch  |

### Experiment 2 — condition URLs

| Code | Label                                       | URL           |
|------|---------------------------------------------|---------------|
| B0   | No explanation, Mid-roll                    | `/?cond=B0`   |
| B1   | Content-based explanation, Mid-roll         | `/?cond=B1`   |
| B2   | Data-based explanation, Mid-roll            | `/?cond=B2`   |
| B3   | No explanation, User-initiated              | `/?cond=B3`   |
| B4   | Content-based explanation, User-initiated   | `/?cond=B4`   |
| B5   | Data-based explanation, User-initiated      | `/?cond=B5`   |

> **Note.** Without `?cond=`, the server uses balanced minimisation to assign the least-filled arm from `random_pool` in `config/experiment.json`. For a live study, send each Prolific participant their condition-specific link; the override is logged in `condition_source = "override"`.

---

## Testing pipeline — Experiment 1

### 1. Pre-flight check (run once)

```bash
# Verify the server starts and the DB migrates cleanly
python app.py &
curl -s http://localhost:8000/healthz          # → {"ok": true, ...}
curl -s http://localhost:8000/admin?token=dev-admin-token | grep "AVOD-Lab"
kill %1
```

### 2. Per-condition smoke test

Run the following checklist for **each of A0–A4**. Open the URL in a fresh private/incognito window each time so you get a clean session.

```
http://localhost:8000/?cond=A0   (repeat for A1, A2, A3, A4)
```

**Step-by-step checklist**

| # | Step | What to verify |
|---|------|----------------|
| 1 | Intro screen loads | Study title and intro text visible; "Begin" button present |
| 2 | Click **Begin** | Pre-survey appears; page counter shows "1 / 3" |
| 3 | Complete **Demographics** page | Age, gender, VOD frequency — all required; "Next" blocked if any missing |
| 4 | Complete **Persuasion knowledge** page | 3 × 7-point Likert items |
| 5 | Complete **Privacy concern** page | 6 × IUIPC items + 1 attention check (select "Agree" = 6) |
| 6 | Browse screen appears | Hero tile and catalogue rows visible |
| 7 | Click a title | Player screen opens; "Now watching" label correct |
| 8 | *(A0)* Watch clip to end | 30-second post-roll ad plays; countdown visible; ad ends; post-survey appears |
| 8 | *(A1)* Click Play | 30-second pre-roll plays first; countdown visible; ad ends; content begins |
| 8 | *(A2)* Watch to midpoint | Content pauses; 30-second mid-roll plays; content resumes |
| 8 | *(A3)* Watch clip | Overlay image appears in lower-third; content continues uninterrupted; banner text visible |
| 8 | *(A4)* Start clip | "Watch an ad" button is visible immediately in the top-left of the player; click it at any point → ad plays; button disappears after click |
| 9 | Ad completes → post-survey appears | Page counter shows "1 / 6" |
| 10 | Complete **Intrusiveness** page | 7 × 7-point items |
| 11 | Complete **Irritation** page | 5 × 7-point items |
| 12 | Complete **Attitudes** page | Satisfaction + 3 ad-attitude + 3 platform-attitude semantic differentials |
| 13 | Complete **Purchase / skip** page | 3 PI items + skip item + attention check (select "Somewhat agree" = 5) |
| 14 | Complete **Manipulation checks** page | A3: overlay-noticing item; A4: control item; all: ad-seen + prior-exposure |
| 15 | Complete **Preferences** page | Rank 5 formats with ▲▼; each rank badge updates in real time |
| 16 | Click **Submit** | Debriefing screen appears |
| 17 | Admin panel | Session visible; condition code correct; `n_events` > 20 |

### 3. Decline path — A4 only

```
http://localhost:8000/?cond=A4
```

1. Complete pre-survey and start the video.
2. The "Watch an ad" button is visible immediately — **do not click it** — let the video finish.
3. Verify the admin panel shows an `ad_prompt_declined` event in the session drill-down.
4. Post-survey should still appear and be completable.

### 4. Attention check verification

After completing a survey with **wrong** answers on the attention-check items, open the admin and drill into the session. In the `survey_page` events, verify:

```json
{ "attn_pre_pass": false }   // if wrong answer given on pre-survey
{ "attn_post_pass": false }  // if wrong answer given on post-survey
```

Participants who fail both checks should be flagged for exclusion per the pre-registered criteria.

### 5. Cell balance check

After running each of A0–A4 at least once:

```
http://localhost:8000/admin?token=dev-admin-token
```

The **Experiment 1 — cell balance** panel should show one session per condition and balanced percentages. The "Source" badge on each session should read **balanced** (or **override** if you used `?cond=`).

### 6. CSV export and event schema

```
http://localhost:8000/admin/export.csv?token=dev-admin-token
```

Key columns: `session_id`, `condition` (e.g. `A2`), `condition_label`, `ts_server`, `ts_client`, `kind`, `payload` (JSON).

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
| `ad_start` / `ad_end` | Ad playback |
| `ad_prompt_shown` | A4 prompt appeared |
| `ad_prompt_clicked` | A4 prompt clicked |
| `ad_prompt_declined` | A4 prompt shown but never clicked |
| `ad_schedule_resolved` | Mid-roll/overlay timing computed |
| `banner_shown` / `banner_hidden` / `banner_click` | Explanation/sponsor banner |
| `page_unload` | Browser tab closed / navigated away |

---

## Questionnaire — Experiment 1

The full battery is implemented in [`static/survey.js`](static/survey.js). Items are rendered in-browser; responses are logged as `survey_page` events.

### Pre-exposure battery (3 pages)

**Page 1 — Demographics**

| Item ID | Question | Type |
|---------|----------|------|
| `age` | Your age (years) | Number |
| `gender` | Gender | Radio (4 options) |
| `vod_freq` | How often do you watch ad-supported streaming? | Radio (5 options) |

**Page 2 — Persuasion knowledge**
*(Friestad & Wright 1994; Jung et al. 2019; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Statement |
|---------|-----------|
| `pk_1` | Advertisers try to get people to buy things they don't really need. |
| `pk_2` | When I see an ad, I can tell it is designed to persuade me. |
| `pk_3` | I understand the techniques that advertisers use to influence people. |

**Page 3 — Privacy concern / IUIPC short form**
*(Malhotra et al. 2004; 1 = Strongly disagree, 7 = Strongly agree)*

| Item ID | Subscale | Statement |
|---------|----------|-----------|
| `iuipc_col_1` | Collection | It bothers me to give personal information to so many online companies. |
| `iuipc_col_2` | Collection | I am concerned that online companies are collecting too much personal information about me. |
| `iuipc_ctl_1` | Control | Online companies should be required to get my permission before using my personal information for any purpose. |
| `iuipc_ctl_2` | Control | I want to have complete control over what online companies do with my personal information. |
| `iuipc_awa_1` | Awareness | Online companies should clearly disclose how they use the personal information they collect from me. |
| `iuipc_awa_2` | Awareness | I am usually aware of whether or not an online company is collecting information about me. |
| `attn_pre` | — | **Attention check** — select "Agree" (6) |

---

### Post-exposure battery (6 pages)

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

**Page 4 — Purchase & skip intention**

| Item ID | Statement |
|---------|-----------|
| `pi_1` | I would consider purchasing the product advertised. |
| `pi_2` | I am interested in the product advertised. |
| `pi_3` | It is likely that I would buy the product advertised. |
| `skip_1` | If I could have skipped this ad, I would have. |
| `attn_post` | **Attention check** — select "Somewhat agree" (5) |

**Page 5 — Manipulation checks** *(condition-dependent)*

| Item ID | Conditions | Type | Question |
|---------|------------|------|----------|
| `manip_overlay_noticed` | A3 only | Radio | During the video, did you notice any image or banner displayed on top of the video? |
| `manip_control` | A4 only | Likert-5 | To what extent did you feel in control of when you watched the ad? |
| `manip_ad_seen` | All | Radio | Did you see an advertisement during or after the video clip? |
| `manip_prior_ad` | All | Radio | Had you seen this specific advertisement before today? |

**Page 6 — Stated preference ranking**

Five ad format descriptions presented in randomised order. Participants rank from most (1) to least (5) preferred using ▲▼ buttons. Stored as `pref_rank` = array of IDs in ranked order.

| Option ID | Description |
|-----------|-------------|
| `pref_postroll`  | An ad plays automatically after the video ends (no interruption to viewing) |
| `pref_preroll`   | An ad plays before the video starts (no skip option) |
| `pref_midroll`   | An ad interrupts the video at the midpoint (no skip option) |
| `pref_overlay`   | A banner ad appears over the video while it continues playing |
| `pref_initiated` | You choose to watch an ad in exchange for bonus content |

---

## Configuring conditions

`config/experiment.json` is read on every request — no restart needed.

```jsonc
// Switch between experiments:
"condition_assignment_mode": "balanced",   // balanced | random | fixed
"active_condition": "A0",                  // used only when mode = "fixed"
"random_pool": ["A0","A1","A2","A3","A4"], // Experiment 1
// "random_pool": ["B0","B1","B2","B3","B4","B5"],  // switch to Experiment 2
```

To swap the ad creative, add an entry to `config/ad_library.json` and update `library_ref` in the relevant condition's ad slot.

---

## Deployment

```bash
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
├── config/
│   ├── experiment.json         Conditions A0–A4, B0–B5; catalogue; assignment mode
│   └── ad_library.json         Ad creative metadata; 4 categories
├── data/events.sqlite          Created on first run
├── static/
│   ├── app.js                  Session management; view routing; survey intercept
│   ├── survey.js               Pre- and post-exposure questionnaire (Exp 1)
│   ├── browse.js               Catalogue / hero rendering
│   ├── player.js               Video + ad scheduler + event logging
│   └── style.css               Dark-theme UI + survey form styles
├── templates/
│   ├── index.html              Participant page (intro → surveys → browse → player)
│   ├── admin.html              Cell-balance panel; session list; condition URLs
│   └── session.html            Per-session event drill-down
└── scripts/
    └── generate_ads.py         Renders synthetic ad MP4s via ffmpeg
```
