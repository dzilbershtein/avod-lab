# Testing pipeline — Experiment 1

Manual QA checklist for verifying a build before running real participants. See [README.md](README.md) for setup, configuration, and the `?test=1` workflow for keeping test sessions out of production data.

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
| 13 | Complete **Perceived fit + skip intention** page | `rel_1`–`rel_3` (ad-content fit) + skip item + attention check (select "Somewhat agree" = 5) |
| 14 | Complete **Manipulation checks** page | All: `ctrl_1`–`ctrl_3` (perceived control) + ad-seen + prior-exposure + relevance |
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

The admin panel links to a single export — **Download data (CSV)** — one row per session with condition, arm, behavioural columns (`title_watched`, `ad_id_shown`, `ad_skipped`, `watch_duration_sec`, `ad_view_duration_sec`) and all survey answers as flat columns. Ready for analysis without joins. Test sessions (`?test=1`) are excluded by default — see [Testing without polluting production data](README.md#testing-without-polluting-production-data) in the README.

```
http://localhost:8000/admin/export_participants.csv?token=dev-admin-token
```

A second, unlinked route dumps the full raw event log (one row per event — `session_id`, `condition`, `kind`, `payload` JSON) for debugging or auditing:

```
http://localhost:8000/admin/export.csv?token=dev-admin-token
```

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
