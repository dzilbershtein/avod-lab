# AVOD-Lab

Browser-based AVOD stimulus platform for a 4 × 2 experiment (ad placement × ad relevance). Runs as a Flask app and logs every behavioural and survey event to SQLite.

**Contents**

- [Quick start](#quick-start)
- [Content and ad videos](#content-and-ad-videos) — [catalogue](#content-catalogue) · [content categories](#content-categories) · [how a creative is chosen](#how-a-creative-is-chosen)
- [Conditions and assignment](#conditions-and-assignment)
- [Test sessions and launch checklist](#test-sessions-and-launch-checklist)
- [Questionnaire](#questionnaire)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Project layout](#project-layout)

The manual QA checklist and the data-export columns are in **[TESTING.md](TESTING.md)**.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py          # http://localhost:8000
```

Admin panel (session list, cell balance, data download): `http://localhost:8000/admin?token=dev-admin-token`

`requirements.txt` (Flask, gunicorn) is all the study server needs. Building the video assets happens on your own machine and needs `pip install -r requirements-build.txt` (Pillow, yt-dlp) plus `ffmpeg`/`ffprobe` on PATH.

---

## Content and ad videos

Video files are not in git. Build them before running:

```bash
python scripts/generate_ads_v3.py                 # the 16 ads → static/ads/
python scripts/download_all.py                    # content, up to 15 min → static/content/
python scripts/trim_content.py --trim-sec 480     # 8-min copies → static/content_short/
```

Each script takes `--only` / `--ids` to rebuild selected items and `--force` to overwrite. The player serves `static/content_short/` (`"content_version": "short"`), so every clip is exactly 8:00 and the forced mid-roll falls at 240 s for everyone.

### Content catalogue

| ID | Title | Genre | Content category | Source |
|---|---|---|---|---|
| `big_buck_bunny` | Big Buck Bunny | Animated Comedy | content_chameleon | Internet Archive (CC BY 3.0) |
| `elephant_dream` | Elephant's Dream | Sci-Fi Animation | intellectual_explorer | Internet Archive (CC BY 2.5) |
| `sintel` | Sintel | Fantasy Drama | intellectual_explorer | Internet Archive (CC BY 3.0) |
| `tears_of_steel` | Tears of Steel | Sci-Fi Thriller | intellectual_explorer | Internet Archive (CC BY 3.0) |
| `pioneer_one` | Pioneer One (Ep. 1) | Sci-Fi Drama | intellectual_explorer | Internet Archive (CC BY-NC-SA 3.0) |
| `sprite_fright` | Sprite Fright | Horror · Comedy | thrill_seeker | YouTube (CC BY 4.0) |
| `doa_1950` | D.O.A. | Crime · Noir | investigative_viewer | Internet Archive (PD) |
| `captain_kidd` | Captain Kidd | Action · Adventure | thrill_seeker | Internet Archive (PD) |
| `jackie_robinson` | The Jackie Robinson Story | Drama · Sports | thrill_seeker | Internet Archive (PD) |
| `blood_on_sun` | Blood on the Sun | Action · Thriller | thrill_seeker | Internet Archive (PD) |
| `hemo_magnificent` | Hemo the Magnificent | Science · Documentary | intellectual_explorer | YouTube (PD) |
| `unchained_goddess` | The Unchained Goddess | Science · Documentary | intellectual_explorer | YouTube (PD) |
| `his_girl_friday` | His Girl Friday | Screwball Comedy | content_chameleon | Internet Archive (PD) |
| `jack_beanstalk` | Jack and the Beanstalk | Family · Comedy | content_chameleon | Internet Archive (PD) |
| `inspector_general` | The Inspector General | Musical Comedy | content_chameleon | Internet Archive (PD) |
| `pied_piper` | The Pied Piper of Hamelin | Family · Fantasy | content_chameleon | Internet Archive (PD) |
| `detour_1945` | Detour | Crime · Noir | investigative_viewer | Internet Archive (PD) |
| `suddenly_1954` | Suddenly | Crime · Thriller | investigative_viewer | Internet Archive (PD) |
| `jigsaw_1949` | Jigsaw | Crime · Drama | investigative_viewer | Internet Archive (PD) |

The title featured at the top of the catalogue is chosen at random per participant (`catalog.hero: "random"`) and exported as `hero_title`.

To add a title: add it under `catalog.titles` in `config/experiment.json` with a `source_url`, `relevant_ad_category` and `context_tags`, add its ID to a row, then run `download_all.py --ids <id>` and `trim_content.py --ids <id>`.

### Content categories

Every title and every ad belongs to one of four content categories. The relevant arm shows an ad from the clip's category; the irrelevant arm, one from another category. Nothing about the participant is used. The IDs are legacy names kept in the config; they label content, not viewers.

| Category (ID) | Content genres | Ads (product) |
|---|---|---|
| Action and thrills (`thrill_seeker`) | Action, adventure, sports, horror | THUNDERDROP (rollercoaster-park tickets), ADRENALINE (energy drink), APEX (running shoes), RANGER (climbing gear) |
| Science and discovery (`intellectual_explorer`) | Sci-Fi, fantasy, science, technology | SYNAPSE (smartphone), RENDERLAB (3D animation software), CURIOSITY (home telescope), HORIZON (VR headset) |
| Comedy and lifestyle (`content_chameleon`) | Comedy, family, musicals, animation | CHUCKLE (popcorn), TOONBOX (breakfast cereal), SINGALONG (karaoke machine), STAGECRAFT (theatre tickets) |
| Drama and crime (`investigative_viewer`) | Crime, noir, thrillers, courtroom | NIGHTWATCH (doorbell camera), TRIBUNAL (legal-advice app), WHODUNIT (detective audiobooks), CASEROOM (crime-fiction magazine) |

All 16 ads are synthetic (`source: "synthetic_v3"`), generated by `scripts/generate_ads_v3.py`. Each sells a fictitious product; its category is conveyed by the product and the ad's setting, imagery and music, never named in the copy. Ad IDs are stable across redesigns; three on-screen brands differ from their IDs: `ad_thrill_gravecrest` is THUNDERDROP, `ad_invest_deadlines` is NIGHTWATCH, `ad_invest_caseroom` is CASEROOM.

### How a creative is chosen

Within the arm's pool, `player.js` scores each ad against the clip's `context_tags` with the overlap coefficient (shared tags ÷ size of the smaller tag set). The relevant arm keeps ads within `RELEVANT_FIT_MARGIN = 0.20` of the best score; the irrelevant arm keeps the lowest-scoring ads. A session-level random offset rotates creatives across participants.

Across all 19 clips, every relevant draw scores at least 0.50, every irrelevant draw scores 0, and all 16 creatives appear in both arms.

---

## Conditions and assignment

| Code | Condition | Ad placement |
|---|---|---|
| A0 | Post-roll (control) | After the clip |
| A1 | Forced pre-roll | Before the clip |
| A2 | Forced mid-roll | At 240 s |
| A3 | Viewer-chosen | A gate before playback asks: before, in the middle or after; the choice is locked |

Each condition is crossed with relevance (relevant / irrelevant): eight cells. Every participant sees exactly one 15-second non-skippable ad. In A3, `timing_gate_shown` and `ad_timing_chosen` are logged, so deliberation latency is their time difference.

**Assignment.** When a session starts (`POST /api/session/start`), the server picks the condition with the fewest counted sessions, then the relevance arm with fewer counted sessions in that condition, breaking ties at random. The assignment is stored in `sessions` and sent to the browser.

**Which sessions count.** Completed sessions (post-survey finished), plus unfinished ones for 30 minutes (`ABANDON_AFTER_MIN` in `app.py`) after the participant opened a video or, before that, after the session started. Older unfinished sessions are treated as abandoned. Test sessions are balanced only against other test sessions.

**Overrides.** `?cond=<code>` forces a condition, e.g. to test or to top up an under-filled cell; such sessions are marked `condition_source = override` and still count toward balance.

---

## Test sessions and launch checklist

Add `&test=1` to any URL (e.g. `http://localhost:8000/?cond=A0&test=1`) to mark the session as test data. Test sessions are excluded from real balancing, from the admin balance panels and from the default data download, and are shown with a **TEST** badge in the admin session list.

**Before recruiting:**

1. Set `prolific_completion_url` in `config/experiment.json` to the completion URL from Prolific. While it is empty, the final screen tells participants to close the tab.
2. Clear the database: `python scripts/purge_sessions.py --all` (or `--test-only` to remove only test sessions). Both ask for confirmation; `--yes` skips it.

---

## Questionnaire

Implemented in [`static/survey.js`](static/survey.js); every item requires an answer.

### Before the video (4 pages)

**Consent** — six required checkboxes: `consent_read`, `consent_age`, `consent_voluntary`, `consent_data`, `consent_deletion` (within 14 days), `consent_publication`.

**Demographics** — `age` (5 bands), `gender` (4 options), `vod_freq` (5 options).

**Persuasion knowledge** — written for this study, informed by Friestad & Wright (1994); 1–7 agreement.

| Item | Statement |
|---|---|
| `pk_1` | Advertisers try to get people to buy things they don't really need. |
| `pk_2` | When I see an ad, I can tell it is designed to persuade me. |
| `pk_3` | I understand the techniques that advertisers use to influence people. |

**Privacy concern** — adapted from IUIPC (Malhotra et al. 2004), 3 items per subscale; 1–7 agreement. Collection items are verbatim; awareness items keep Malhotra's normative wording, simplified; `iuipc_ctl_3` follows Malhotra, `iuipc_ctl_1`–`2` are newly written.

| Item | Subscale | Statement |
|---|---|---|
| `iuipc_col_1` | Collection | It bothers me to give personal information to so many online companies. |
| `iuipc_col_2` | Collection | I am concerned that online companies are collecting too much personal information about me. |
| `iuipc_col_3` | Collection | When online companies ask me for personal information, I sometimes think twice before providing it. |
| `iuipc_ctl_1` | Control | Online companies should be required to get my permission before using my personal information for any purpose. |
| `iuipc_ctl_2` | Control | I want to have complete control over what online companies do with my personal information. |
| `iuipc_ctl_3` | Control | Consumer online privacy is really a matter of consumers' right to exercise control over how their information is collected, used, and shared. |
| `iuipc_awa_1` | Awareness | Online companies should clearly disclose how they use the personal information they collect from me. |
| `iuipc_awa_2` | Awareness | Online companies' privacy policies should be clear and easy to find. |
| `iuipc_awa_3` | Awareness | It is very important to me to be aware of what online companies do with my personal information. |
| `attn_pre` | — | Attention check: select "Agree" (6) |

### After the video (5 pages)

**Intrusiveness** — Li, Edwards & Lee (2002), verbatim: one stem, *"When the ad played, I thought it was…"* (the original says "popped-up"), then the seven adjectives as a grid; 1–7 agreement.

| `int_7` | `int_4` | `int_2` | `int_6` | `int_1` | `int_3` | `int_5` |
|---|---|---|---|---|---|---|
| distracting | disturbing | forced | interfering | intrusive | invasive | obtrusive |

**Irritation** — written for this study; 1–7 agreement.

| Item | Statement |
|---|---|
| `irr_1` | I found the ad irritating. |
| `irr_2` | I found the ad annoying. |
| `irr_3` | I found the ad frustrating. |
| `irr_4` | I found the ad unpleasant. |
| `irr_5` | I was bothered by the ad. |

**Attitudes** — `sat_1` (Likert: *Overall, I was satisfied with the viewing experience*); attitude toward the ad `ad_att_1`–`3` and toward the platform `plat_att_1`–`3` (semantic differentials: bad–good, unfavourable–favourable, negative–positive / untrustworthy–trustworthy).

**Perceived ad-content fit and skip intention** — 1–7 agreement.

| Item | Statement |
|---|---|
| `rel_1` | The advertised product was relevant to the video I watched. |
| `rel_2` | The ad fit well with the content I chose. |
| `rel_3` | It made sense to show this particular ad with this video. |
| `skip_1` | If I could have skipped this ad, I would have. |
| `attn_post` | Attention check: select "Somewhat agree" (5) |

**Perceived control and checks** — all conditions.

| Item | Type | Question |
|---|---|---|
| `ctrl_1` | 1–7 | I felt in control of when the ad played. |
| `ctrl_2` | 1–7 | It was up to me how the ad fit into my viewing. |
| `ctrl_3` | 1–7 | I had a say in how the advertising interrupted my video. |
| `manip_ad_seen` | Radio | Did an ad play at any point while you were watching? |
| `manip_prior_ad` | Radio | Had you seen this specific advertisement before today? |
| `manip_relevance` | 1–7 | The ad appeared to be chosen based on the type of video I watched. |
| `track_1` | 1–7 | This ad seemed to use personal information about me, beyond the video I chose. |
| `track_2` | 1–7 | Seeing this ad made me feel watched by the service. |

`ctrl_1`–`3` are the control manipulation check and mediator; `manip_relevance` is the relevance manipulation check; `rel_1`–`3` measure perceived fit (the relevance mediator); `track_1`–`2` are exploratory. See the pre-registration for how each is analysed.

---

## Configuration

`config/experiment.json` is read on every request; no restart needed.

| Setting | Value | Effect |
|---|---|---|
| `condition_assignment_mode` | `balanced` | Balanced assignment (also `random`, `fixed`) |
| `random_pool` | `["A0","A1","A2","A3"]` | Conditions that balancing assigns |
| `content_version` | `short` | Serve the 8-min clips from `static/content_short/` |
| `allow_return_to_catalogue` | `false` | Opening a video is final; `true` restores the *← Browse* button (usable until the ad starts) |
| `catalog.hero` | `random` | Featured title chosen per participant; a title ID fixes it |
| `prolific_completion_url` | `""` | Prolific completion link shown on the final screen |

Each condition's ad slot has `ad_relevance`: `balanced` (the server assigns the arm; used by A0–A3), `relevant` or `irrelevant`. To add a creative, add it to `config/ad_library.json` with one of the four category IDs and generate its MP4 into `static/ads/`.

---

## Deployment

Assets are built locally and copied to the server; the server never downloads anything.

1. **Build** on your machine: the three commands under [Content and ad videos](#content-and-ad-videos). Don't skip `trim_content.py`: the player serves only `static/content_short/`. Thumbnails are already committed in `static/posters/` (`download_posters.py` rebuilds them).
2. **Transfer** the repository with the populated `static/` folder; the full-length `static/content/` and your local database are not needed:
   ```bash
   rsync -av --exclude 'static/content/' --exclude 'data/events.sqlite' ./ user@server:/srv/avod-lab/
   ```
3. **Run**:
   ```bash
   pip install -r requirements.txt
   export ADMIN_TOKEN="$(openssl rand -hex 24)"
   gunicorn -w 4 -b 0.0.0.0:8000 app:app
   ```
   Keep `data/` on a persistent volume. Turn off IP logging in the web server's access logs: participants are told no IP address is collected.

Then work through the [launch checklist](#test-sessions-and-launch-checklist).

---

## Project layout

```
avod-lab/
├── app.py                      Flask backend: assignment, event log, admin, data export
├── TESTING.md                  Manual QA checklist and export columns
├── requirements.txt            Server dependencies
├── requirements-build.txt      Asset-building dependencies (local only)
├── pilot/                      Survey-code maps for the ad-relevance pilots
├── config/
│   ├── experiment.json         Conditions, catalogue, study settings
│   └── ad_library.json         The 16 ads and their categories
├── static/
│   ├── app.js                  Session, view routing, surveys around the video
│   ├── survey.js               Questionnaires
│   ├── browse.js               Catalogue
│   ├── player.js               Video, ad scheduling, ad selection
│   ├── ads/ content/ content_short/   Video files (not in git)
│   ├── posters/                Catalogue thumbnails
│   └── style.css
├── templates/                  index.html (participant), admin.html, session.html
└── scripts/
    ├── generate_ads_v3.py      Builds the 16 ads (with ad_audio.py)
    ├── download_all.py         Downloads content videos
    ├── trim_content.py         Makes the 8-min copies
    ├── download_posters.py     Rebuilds thumbnails
    ├── check_pilot.py          Checks an ad-relevance pilot export against the selection logic
    └── purge_sessions.py       Deletes test or all sessions
```
