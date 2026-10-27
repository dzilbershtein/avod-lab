# Testing pipeline

Manual QA checklist for verifying a build before running real participants. See [README.md](README.md) for setup and configuration.

> **Always append `&test=1`** to the participant URLs below. It tags the session as test data so it stays out of real participants' balancing, the cell-balance panel and the default CSV export — see [Test sessions and launch checklist](README.md#test-sessions-and-launch-checklist). Finish with [step 7](#7-clear-test-data-before-going-live).

---

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
http://localhost:8000/?cond=A0&test=1   (repeat for A1, A2, A3)
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
| 13 | Complete **Perceived fit + skip intention** page | `rel_1`–`rel_3` (ad-content fit) + skip item + attention check (select "Somewhat agree" = 5) |
| 14 | Complete **Manipulation checks** page | All: `ctrl_1`–`ctrl_3` (perceived control) + ad-seen + prior-exposure + relevance |
| 15 | Click **Submit** | Debriefing screen appears |
| 16 | Admin panel | Session visible with a red **TEST** badge; condition code correct; `n_events` > 20 |

### 3. Timing-choice gate — A3

```
http://localhost:8000/?cond=A3&test=1
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

```
http://localhost:8000/admin?token=dev-admin-token
```

**5a — confirm test sessions are excluded.** After the runs above, the admin page should show a red **TEST** badge on each of those sessions and a count in the header ("N test sessions excluded"). The **timing balance** panel should still read **0** for every condition — test sessions are filtered out of it on purpose, so that QA runs never skew assignment for real participants.

**5b — confirm balance itself works.** Test sessions are balanced among themselves, so this works with tagged sessions. Open the URL without `?cond=` eight times in fresh private windows and click through to the browse screen:

```
http://localhost:8000/?test=1
```

In the admin session list the eight should spread over A0–A3, two each, with both a relevant and an irrelevant session in every condition and the "Source" badge reading **balanced**. They should never all land in one cell.

For per-session detail, the data file's `ad_effective_relevance` column records the arm each ad was actually drawn for (use the *including test* link):

```
http://localhost:8000/admin/export_participants.csv?token=dev-admin-token&include_test=1
```

### 6. CSV export and event schema

The admin page's **Downloads** card has one file, *All data*, as *real sessions* or *including test*. It is one row per session, ready for analysis without joins:

- **Assignment:** `condition`, `condition_source` (`override` marks a `?cond=` link), `ad_relevance_arm`, `is_test`, `created_at`, `video_opened_at`, `post_survey_complete` (1/0) and `completed_at`.
- **Behaviour, derived from the event log:** `hero_title` (the randomly featured title at the top of the catalogue), `title_watched`, `watch_duration_sec`, `ad_id_shown`, `ad_category`, `ad_effective_relevance`, `ad_placement`, `ad_start_t_content` (where in the clip the ad began), `ad_view_duration_sec`, `ad_end_reason`, `ad_timing_chosen` (A3), `ad_skipped`, `attn_pre_pass`, `attn_post_pass`, `n_back_blocked`, `n_load_errors` and `debrief_comment` (the optional comment on the final screen).
- **Every survey answer** as its own column.
- **`events_json`:** the session's complete event log (timestamps, kind and payload of every event), for any check not covered above.

Test sessions (`?test=1`) are excluded; the *including test* link keeps them — see [Test sessions and launch checklist](README.md#test-sessions-and-launch-checklist) in the README.

```
http://localhost:8000/admin/export_participants.csv?token=dev-admin-token
http://localhost:8000/admin/export_participants.csv?token=dev-admin-token&include_test=1
```

`events_json` can exceed Excel's 32,767-character cell limit for long sessions; read the file with R or pandas rather than Excel if you need it.

The `sessions` table also has an `ad_relevance_arm` column (`"relevant"` or `"irrelevant"`) that records the balanced relevance assignment.

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
| `ad_schedule_resolved` | Mid-roll timing computed |
| `banner_shown` / `banner_hidden` / `banner_click` | Explanation/sponsor banner |
| `page_unload` | Browser tab closed / navigated away |

### 7. Clear test data before going live

QA leaves two kinds of rows behind: the tagged ones from steps 2–4 and the untagged ones from step 5b. Wipe both so the study starts from an empty database:

```bash
python scripts/purge_sessions.py --all
```

Confirm it worked — the balance panel should read 0 across the board and the header should report no test sessions:

```
http://localhost:8000/admin?token=dev-admin-token
```

If you only want to drop the tagged QA runs and keep real data (i.e. you are testing *during* a live study), use `--test-only` instead.
