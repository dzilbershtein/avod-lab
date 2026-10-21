"""
AVOD-Lab backend.

Serves the streaming-catalogue stimulus, assigns each session a condition
and an ad-relevance arm by balanced minimisation, and logs every behavioural
and survey event the client emits to a SQLite database.

Run locally:
    pip install -r requirements.txt
    python app.py

Hosting:
    gunicorn -w 4 -b 0.0.0.0:8000 app:app
    (behind nginx or a managed PaaS — see README)
"""

from __future__ import annotations

import csv
import io
import json
import os
import random
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    render_template,
    request,
)

# --------------------------------------------------------------------------- #
#  Paths and config
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "experiment.json"
AD_LIBRARY_PATH = BASE_DIR / "config" / "ad_library.json"
DB_PATH = BASE_DIR / "data" / "events.sqlite"

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB per event POST is plenty

# Very simple admin token — replace in production.
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token")

# A session counts toward balanced assignment once it has completed the
# post-survey, or while it may still be in progress: for this many minutes
# after the participant opened a video, or, before they have opened one, after
# the session started. Past that it is treated as abandoned and stops counting,
# so drop-outs do not leave their cell over-filled. From opening a video, the
# 8-minute clip, the ad and the post-survey take about 12 minutes.
ABANDON_AFTER_MIN = 30


def _counted_sql(alias: str = "") -> tuple[str, list]:
    """SQL condition (and its parameter) selecting sessions that count toward balance."""
    p = f"{alias}." if alias else ""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ABANDON_AFTER_MIN)).isoformat(
        timespec="seconds")
    return (f"({p}completed_at IS NOT NULL OR "
            f"COALESCE({p}video_opened_at, {p}created_at) >= ?)", [cutoff])


def load_config(
    condition_override: str | None = None,
    db: sqlite3.Connection | None = None,
    is_test: int = 0,
) -> dict:
    """Load experiment.json and resolve the session's condition.

    The active condition's ad slots are copied into cfg["ads"] (the shape
    the client expects); the player picks the creative for each slot from
    the ad library. Resolution order:

        1. `condition_override` (the `?cond=A2` query param) wins if it
           names a known condition, and the choice is flagged in cfg.
        2. ``condition_assignment_mode == "balanced"`` picks the arm with
           the fewest counted sessions (minimisation; see ABANDON_AFTER_MIN);
           requires *db*. Real
           sessions are balanced against real ones and test sessions against
           test ones, so testing neither skews the study nor gets stuck in
           whichever cell the real data leaves emptiest.
        3. ``condition_assignment_mode == "random"`` picks uniformly from
           ``random_pool`` (or all condition keys).
        4. Otherwise the static ``active_condition`` is used.
    """
    with CONFIG_PATH.open() as f:
        cfg = json.load(f)
    cfg["_ad_library"] = _load_ad_library()  # the player draws creatives from it

    conditions = cfg["conditions"]
    chosen, source = _pick_condition(cfg, conditions, condition_override, db=db, is_test=is_test)
    cond_def = conditions.get(chosen, {})
    cfg["active_condition_resolved"] = chosen
    cfg["active_condition_source"] = source  # "override"|"balanced"|"random"|"fixed"
    cfg["active_condition_label"] = cond_def.get("label", chosen)
    cfg["active_condition_description"] = cond_def.get("description", "")
    base_label = cfg.get("condition_label", "phase2b")
    # Stamp the resolved code into the persisted condition_label so the
    # CSV export and admin views show which arm a session was on.
    if not base_label.endswith(f"-{chosen}"):
        cfg["condition_label"] = f"{base_label}-{chosen}"
    cfg["ads"] = [dict(slot) for slot in cond_def.get("ads", [])]

    # Resolve ad_relevance arm if any ad slot uses "balanced" or "random".
    # Stored in cfg so the client player can use it without re-rolling.
    uses_dynamic_relevance = any(
        slot.get("ad_relevance") in ("balanced", "random")
        for slot in cond_def.get("ads", [])
    )
    if uses_dynamic_relevance:
        arm, arm_source = _pick_ad_relevance(chosen, db=db, is_test=is_test)
        cfg["resolved_ad_relevance"] = arm
        cfg["resolved_ad_relevance_source"] = arm_source
    return cfg


def _pick_condition(
    cfg: dict,
    conditions: dict,
    override: str | None,
    db: sqlite3.Connection | None = None,
    is_test: int = 0,
) -> tuple[str, str]:
    """Return (condition_id, source).

    source is one of: "override" | "balanced" | "random" | "fixed"
    """
    if override and isinstance(conditions.get(override), dict):
        return override, "override"

    mode = (cfg.get("condition_assignment_mode") or "fixed").lower()

    if mode == "balanced":
        pool = cfg.get("random_pool") or list(conditions.keys())
        pool = [c for c in pool if c in conditions]
        if pool and db is not None:
            counts = _count_condition_assignments(pool, db, is_test=is_test)
            min_n = min(counts.values())
            candidates = [c for c in pool if counts[c] == min_n]
            return random.choice(candidates), "balanced"
        # Fall back to simple random if DB is unavailable (e.g. GET / preview).
        if pool:
            return random.choice(pool), "random"

    if mode == "random":
        pool = cfg.get("random_pool") or list(conditions.keys())
        pool = [c for c in pool if c in conditions]
        if pool:
            return random.choice(pool), "random"

    fixed = cfg.get("active_condition")
    if fixed and fixed in conditions:
        return fixed, "fixed"
    # Last-resort fallback — first declared condition.
    return next(iter(conditions)), "fixed"


def _pick_ad_relevance(
    condition: str,
    db: sqlite3.Connection | None,
    is_test: int = 0,
) -> tuple[str, str]:
    """Return (arm, source) where arm is 'relevant' or 'irrelevant'.

    Uses balanced minimisation within each placement condition so that
    the (condition × relevance) cell counts stay as equal as possible
    across the study.  Falls back to simple random when the DB is not
    available (e.g. the preview GET / request before session start).
    """
    if db is None:
        return random.choice(["relevant", "irrelevant"]), "random"
    counts: dict[str, int] = {"relevant": 0, "irrelevant": 0}
    counted, params = _counted_sql()
    rows = db.execute(
        "SELECT ad_relevance_arm, COUNT(*) AS n FROM sessions "
        "WHERE condition = ? AND ad_relevance_arm IN ('relevant', 'irrelevant') "
        f"AND COALESCE(is_test, 0) = ? AND {counted} "
        "GROUP BY ad_relevance_arm",
        (condition, is_test, *params),
    ).fetchall()
    for row in rows:
        if row["ad_relevance_arm"] in counts:
            counts[row["ad_relevance_arm"]] = row["n"]
    min_n = min(counts.values())
    candidates = [k for k, v in counts.items() if v == min_n]
    return random.choice(candidates), "balanced"


def _count_condition_assignments(
    pool: list, db: sqlite3.Connection, is_test: int = 0
) -> dict:
    """Return {condition_code: n_sessions} for every code in pool.

    Counts real sessions by default, or test sessions when is_test=1, and
    skips abandoned ones (see ABANDON_AFTER_MIN).
    """
    counts = {c: 0 for c in pool}
    if not pool:
        return counts
    placeholders = ",".join("?" * len(pool))
    counted, params = _counted_sql()
    rows = db.execute(
        f"SELECT condition, COUNT(*) AS n FROM sessions "
        f"WHERE condition IN ({placeholders}) AND COALESCE(is_test, 0) = ? AND {counted} "
        f"GROUP BY condition",
        [*pool, is_test, *params],
    ).fetchall()
    for row in rows:
        if row["condition"] in counts:
            counts[row["condition"]] = row["n"]
    return counts


def _load_ad_library() -> dict:
    if AD_LIBRARY_PATH.exists():
        with AD_LIBRARY_PATH.open() as f:
            return json.load(f)
    return {"categories": [], "ads": []}


# --------------------------------------------------------------------------- #
#  Database
# --------------------------------------------------------------------------- #


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id                   TEXT PRIMARY KEY,
            created_at           TEXT NOT NULL,
            user_agent           TEXT,
            condition_label      TEXT,
            condition            TEXT,
            condition_source     TEXT,
            ad_relevance_arm     TEXT,
            config_snapshot      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            ts_server   TEXT NOT NULL,
            ts_client   REAL NOT NULL,
            kind        TEXT NOT NULL,
            payload     TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_kind    ON events(kind);
        """
    )
    # Migrations: add new columns and indexes to pre-existing databases.
    # Each statement is attempted independently; OperationalError means it
    # already exists, which is fine.
    for migration in [
        "ALTER TABLE sessions ADD COLUMN condition TEXT",
        "ALTER TABLE sessions ADD COLUMN condition_source TEXT",
        "ALTER TABLE sessions ADD COLUMN ad_relevance_arm TEXT",
        "ALTER TABLE sessions ADD COLUMN is_test INTEGER DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN completed_at TEXT",
        "ALTER TABLE sessions ADD COLUMN video_opened_at TEXT",
        "CREATE INDEX IF NOT EXISTS idx_sessions_cond ON sessions(condition)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_rel  ON sessions(condition, ad_relevance_arm)",
    ]:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column / index already exists
    # Backfill completion for sessions logged before completed_at existed.
    conn.execute(
        "UPDATE sessions SET completed_at = ("
        "  SELECT MIN(e.ts_server) FROM events e WHERE e.session_id = sessions.id "
        "  AND e.kind = 'survey_complete' AND json_extract(e.payload, '$.survey') = 'post'"
        ") WHERE completed_at IS NULL"
    )
    # Same for the time the first video was opened.
    conn.execute(
        "UPDATE sessions SET video_opened_at = ("
        "  SELECT substr(MIN(e.ts_server), 1, 19) || '+00:00' FROM events e "
        "  WHERE e.session_id = sessions.id AND e.kind = 'watch_start'"
        ") WHERE video_opened_at IS NULL"
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
#  Routes — participant facing
# --------------------------------------------------------------------------- #


@app.route("/")
def index() -> str:
    """Render the player page.

    The condition resolved here is provisional — the random arm is finalised
    on /api/session/start so the experimenter sees the same condition the
    participant was actually assigned. The client refreshes cfg from the
    session_start response, so any difference is silently corrected.
    """
    cfg = load_config(condition_override=request.args.get("cond"))
    return render_template("index.html", config_json=json.dumps(cfg))


@app.post("/api/session/start")
def start_session():
    # URL param wins; JSON body is supported for parity with future fetch calls.
    body = request.get_json(silent=True) or {}
    override = request.args.get("cond") or body.get("cond")
    is_test = 1 if (request.args.get("test") or body.get("test")) in ("1", "true", True) else 0
    # Pass the DB so balanced assignment can query current cell counts.
    db = get_db()
    cfg = load_config(condition_override=override, db=db, is_test=is_test)
    sid = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO sessions "
        "(id, created_at, user_agent, condition_label, condition, condition_source, "
        " ad_relevance_arm, is_test, config_snapshot) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            request.headers.get("User-Agent", "")[:512],
            cfg.get("condition_label", "phase1-default"),
            cfg.get("active_condition_resolved"),       # clean code, e.g. "A2"
            cfg.get("active_condition_source"),         # "balanced"|"random"|"fixed"|"override"
            cfg.get("resolved_ad_relevance"),           # "relevant"|"irrelevant"|None
            is_test,
            json.dumps(cfg, separators=(",", ":")),
        ),
    )
    db.commit()
    return jsonify({"session_id": sid, "config": cfg, "is_test": bool(is_test)})


@app.post("/api/event")
def log_event():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    kind = data.get("kind")
    payload = data.get("payload", {})
    ts_client = float(data.get("ts_client", time.time() * 1000))
    if not sid or not kind:
        abort(400, "session_id and kind required")

    db = get_db()
    row = db.execute("SELECT 1 FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None:
        abort(404, "unknown session")

    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO events (session_id, ts_server, ts_client, kind, payload) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            sid,
            now.isoformat(timespec="milliseconds"),
            ts_client,
            kind,
            json.dumps(payload, separators=(",", ":")),
        ),
    )
    if kind == "watch_start":
        db.execute(
            "UPDATE sessions SET video_opened_at = ? WHERE id = ? AND video_opened_at IS NULL",
            (now.isoformat(timespec="seconds"), sid),
        )
    if kind == "survey_complete" and isinstance(payload, dict) and payload.get("survey") == "post":
        db.execute(
            "UPDATE sessions SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
            (now.isoformat(timespec="seconds"), sid),
        )
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
#  Routes — admin / data export
# --------------------------------------------------------------------------- #


def _require_admin() -> None:
    token = request.args.get("token") or request.headers.get("X-Admin-Token")
    if token != ADMIN_TOKEN:
        abort(401, "admin token required")


@app.get("/admin")
def admin():
    _require_admin()
    db = get_db()
    sessions = db.execute(
        "SELECT id, created_at, condition_label, condition, condition_source, "
        "ad_relevance_arm, is_test, user_agent, "
        "(SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS n_events "
        "FROM sessions s ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    # Cell-balance summary for the admin overview.
    cfg = load_config()
    conditions_meta = cfg.get("conditions", {})
    exp1_pool = [c for c in cfg.get("random_pool", []) if c in conditions_meta]
    cell_counts = _count_condition_assignments(exp1_pool, db) if exp1_pool else {}

    # 8-cell breakdown: condition × ad_relevance_arm.
    cell8_counts: dict[tuple, int] = {}
    if exp1_pool:
        placeholders = ",".join("?" * len(exp1_pool))
        counted, params = _counted_sql()
        for row in db.execute(
            f"SELECT condition, ad_relevance_arm, COUNT(*) AS n FROM sessions "
            f"WHERE condition IN ({placeholders}) AND ad_relevance_arm IS NOT NULL "
            f"AND COALESCE(is_test, 0) = 0 AND {counted} "
            f"GROUP BY condition, ad_relevance_arm",
            [*exp1_pool, *params],
        ).fetchall():
            cell8_counts[(row["condition"], row["ad_relevance_arm"])] = row["n"]

    n_test_sessions = db.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE is_test = 1"
    ).fetchone()["n"]

    return render_template(
        "admin.html",
        sessions=sessions,
        token=ADMIN_TOKEN,
        conditions_meta=conditions_meta,
        exp1_pool=exp1_pool,
        cell_counts=cell_counts,
        cell8_counts=cell8_counts,
        n_test_sessions=n_test_sessions,
        abandon_after_min=ABANDON_AFTER_MIN,
    )


@app.get("/admin/session/<sid>")
def admin_session(sid: str):
    _require_admin()
    db = get_db()
    session_row = db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if session_row is None:
        abort(404)
    events = db.execute(
        "SELECT id, ts_server, ts_client, kind, payload FROM events "
        "WHERE session_id = ? ORDER BY id ASC",
        (sid,),
    ).fetchall()
    return render_template(
        "session.html", session=session_row, events=events, token=ADMIN_TOKEN
    )


@app.get("/admin/export_participants.csv")
def admin_export_participants_csv():
    """All data in one file, one row per session: session metadata, behaviour
    derived from the event log, every survey answer, and the session's full
    event log as JSON in `events_json`.

    Test sessions (started with ?test=1) are excluded by default.
    Pass ?include_test=1 to include them (e.g. to inspect your own test runs).
    """
    _require_admin()
    db = get_db()
    include_test = request.args.get("include_test") == "1"
    query = ("SELECT id, condition, condition_source, ad_relevance_arm, condition_label, "
             "created_at, video_opened_at, completed_at, is_test FROM sessions")
    if not include_test:
        query += " WHERE (is_test IS NULL OR is_test = 0)"
    query += " ORDER BY created_at ASC"
    sessions = db.execute(query).fetchall()

    meta_cols = [
        "session_id", "condition", "condition_source", "ad_relevance_arm", "is_test",
        "condition_label", "created_at", "video_opened_at", "post_survey_complete", "completed_at",
        # behaviour, derived from the event log
        "title_watched", "watch_duration_sec", "ad_id_shown", "ad_category",
        "ad_effective_relevance", "ad_placement", "ad_start_t_content",
        "ad_view_duration_sec", "ad_end_reason", "ad_timing_chosen", "ad_skipped",
        "attn_pre_pass", "attn_post_pass", "n_back_blocked", "n_load_errors",
        "debrief_comment",
    ]
    rows: dict[str, dict] = {}
    logs: dict[str, list] = {}
    for s in sessions:
        sid = s["id"]
        rows[sid] = dict.fromkeys(meta_cols, "")
        rows[sid].update({
            "session_id": sid,
            "condition": s["condition"],
            "condition_source": s["condition_source"],
            "ad_relevance_arm": s["ad_relevance_arm"],
            "is_test": s["is_test"] or 0,
            "condition_label": s["condition_label"],
            "created_at": s["created_at"],
            "video_opened_at": s["video_opened_at"] or "",
            "post_survey_complete": 1 if s["completed_at"] else 0,
            "completed_at": s["completed_at"] or "",
            "n_back_blocked": 0,
            "n_load_errors": 0,
        })
        logs[sid] = []

    events = db.execute(
        "SELECT session_id, ts_server, ts_client, kind, payload FROM events ORDER BY id ASC"
    ).fetchall()

    for ev in events:
        sid = ev["session_id"]
        if sid not in rows:
            continue
        row = rows[sid]
        kind = ev["kind"]
        try:
            data = json.loads(ev["payload"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        logs[sid].append({"ts_server": ev["ts_server"], "ts_client": ev["ts_client"],
                          "kind": kind, "payload": data})

        if kind == "watch_start":
            row["title_watched"] = data.get("title_id", "")
        elif kind == "watch_end":
            row["watch_duration_sec"] = data.get("t_content", "")
        elif kind == "ad_start":
            row["ad_id_shown"] = data.get("ad_id", "")
            row["ad_category"] = data.get("category", "")
            row["ad_effective_relevance"] = data.get("effective_relevance", "")
            row["ad_placement"] = data.get("placement", "")
            row["ad_start_t_content"] = data.get("t_content", "")
            row["ad_skipped"] = False
        elif kind == "ad_end":
            row["ad_view_duration_sec"] = data.get("t_ad", "")
            row["ad_end_reason"] = data.get("reason", "")
        elif kind == "debrief_comment":
            row["debrief_comment"] = data.get("text", "")
        elif kind == "ad_timing_chosen":
            row["ad_timing_chosen"] = data.get("choice", "")
        elif kind == "ad_prompt_declined":
            row["ad_skipped"] = True
        elif kind == "back_blocked":
            row["n_back_blocked"] += 1
        elif kind in ("video_source_error", "ad_source_error"):
            row["n_load_errors"] += 1
        elif kind == "survey_page":
            for k, v in (data.get("responses") or {}).items():
                if k in ("attn_pre_pass", "attn_post_pass"):
                    row[k] = v
        elif kind == "survey_complete":
            responses = data.get("all_responses", data.get("responses", {}))
            if isinstance(responses, dict):
                for k, v in responses.items():
                    row[k] = v

    survey_keys = sorted({k for row in rows.values() for k in row if k not in meta_cols})
    all_cols = meta_cols + survey_keys + ["events_json"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(all_cols)
    for sid, row in rows.items():
        row["events_json"] = json.dumps(logs[sid], separators=(",", ":"))
        writer.writerow([row.get(c, "") for c in all_cols])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=avod_lab_data.csv"},
    )


# --------------------------------------------------------------------------- #
#  Boilerplate
# --------------------------------------------------------------------------- #


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=True)
