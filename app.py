"""
Experiment 1 VOD-simulator backend.

Phase 1: serves a single content clip with configurable ad insertions
(pre-roll, mid-roll skippable, overlay) and an explanation banner.
Logs every behavioural event the client emits to a SQLite database.

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
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
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


def load_config(
    condition_override: str | None = None,
    db: sqlite3.Connection | None = None,
) -> dict:
    """Load experiment.json and expand ad slots.

    If a `conditions` block is present, the active condition is resolved
    into cfg["ads"] (the shape the client expects). Resolution order:

        1. `condition_override` (the `?cond=A2` query param) wins if it
           names a known condition, and the choice is flagged in cfg.
        2. ``condition_assignment_mode == "balanced"`` picks the arm with
           the fewest completed sessions (minimisation); requires *db*.
        3. ``condition_assignment_mode == "random"`` picks uniformly from
           ``random_pool`` (or all condition keys).
        4. Otherwise the static ``active_condition`` is used.

    Legacy configs with a top-level `ads` array still work — they fall
    through the legacy branch unchanged.
    """
    with CONFIG_PATH.open() as f:
        cfg = json.load(f)
    library = _load_ad_library()
    cfg["_ad_library"] = library  # exposed so the client can see categories

    conditions = cfg.get("conditions")
    if conditions:
        chosen, source = _pick_condition(cfg, conditions, condition_override, db=db)
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
        cfg["ads"] = [_resolve_ad(slot, library) for slot in cond_def.get("ads", [])]

        # Resolve ad_relevance arm if any ad slot uses "balanced" or "random".
        # Stored in cfg so the client player can use it without re-rolling.
        uses_dynamic_relevance = any(
            slot.get("ad_relevance") in ("balanced", "random")
            for slot in cond_def.get("ads", [])
        )
        if uses_dynamic_relevance:
            arm, arm_source = _pick_ad_relevance(chosen, db=db)
            cfg["resolved_ad_relevance"] = arm
            cfg["resolved_ad_relevance_source"] = arm_source
    else:
        cfg["ads"] = [_resolve_ad(slot, library) for slot in cfg.get("ads", [])]
    return cfg


def _pick_condition(
    cfg: dict,
    conditions: dict,
    override: str | None,
    db: sqlite3.Connection | None = None,
) -> tuple[str, str]:
    """Return (condition_id, source).

    source is one of: "override" | "balanced" | "random" | "fixed"
    """
    if override and override in conditions:
        return override, "override"

    mode = (cfg.get("condition_assignment_mode") or "fixed").lower()

    if mode == "balanced":
        pool = cfg.get("random_pool") or list(conditions.keys())
        pool = [c for c in pool if c in conditions]
        if pool and db is not None:
            counts = _count_condition_assignments(pool, db)
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
    rows = db.execute(
        "SELECT ad_relevance_arm, COUNT(*) AS n FROM sessions "
        "WHERE condition = ? AND ad_relevance_arm IN ('relevant', 'irrelevant') "
        "GROUP BY ad_relevance_arm",
        (condition,),
    ).fetchall()
    for row in rows:
        if row["ad_relevance_arm"] in counts:
            counts[row["ad_relevance_arm"]] = row["n"]
    min_n = min(counts.values())
    candidates = [k for k, v in counts.items() if v == min_n]
    return random.choice(candidates), "balanced"


def _count_condition_assignments(pool: list, db: sqlite3.Connection) -> dict:
    """Return {condition_code: n_sessions} for every code in pool.

    Queries the ``condition`` column added by the schema migration;
    only counts sessions where the column is non-NULL (i.e. assigned
    through this mechanism, not legacy rows).
    """
    counts = {c: 0 for c in pool}
    if not pool:
        return counts
    placeholders = ",".join("?" * len(pool))
    rows = db.execute(
        f"SELECT condition, COUNT(*) AS n FROM sessions "
        f"WHERE condition IN ({placeholders}) GROUP BY condition",
        pool,
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


def _merge_lib_entry(lib_entry: dict, slot: dict) -> dict:
    """Merge a single ad-library entry with slot-level overrides."""
    merged = {
        "id": lib_entry["id"],
        "url": lib_entry.get("video_url"),
        "fallback_urls": lib_entry.get("fallback_urls", []),
        "duration_sec": lib_entry.get("duration_sec"),
        "click_url": lib_entry.get("click_url"),
        "category": lib_entry.get("category"),
        "source": lib_entry.get("source"),
    }
    if "default_banner" in lib_entry and "banner" not in slot:
        merged["banner"] = {
            "show": True,
            "text": lib_entry["default_banner"],
            "show_at_ad_sec": 0,
            "hide_at_ad_sec": lib_entry.get("duration_sec", 12),
        }
    merged.update(
        {k: v for k, v in slot.items() if k not in ("library_ref", "library_refs")}
    )
    return merged


def _resolve_ad(slot: dict, library: dict) -> dict:
    """If `slot` carries library_ref or library_refs, merge library entries.

    library_refs (list): resolves the full pool, shuffles it randomly so
        different participants see a different ordering, and stores it as
        `ad_pool`. The client player cycles through the pool across
        successive title plays so each video gets a fresh ad from the
        correct relevance category. The primary `url` / `id` is taken from
        the first entry after shuffling (backwards-compatible fallback).

    library_ref (str): original single-entry path — behaviour unchanged.

    Slot-level fields (placement, start_at_sec, banner, …) override every
    library entry so per-placement tweaks still work.
    """
    ads_index = {a["id"]: a for a in library.get("ads", [])}

    refs = slot.get("library_refs")
    if refs and isinstance(refs, list):
        pool = [_merge_lib_entry(ads_index[r], slot) for r in refs if r in ads_index]
        if not pool:
            return slot
        random.shuffle(pool)
        primary = pool[0].copy()
        primary["ad_pool"] = pool
        return primary

    ref = slot.get("library_ref")
    if not ref:
        return slot
    lib_entry = ads_index.get(ref)
    if lib_entry is None:
        return slot  # silently ignore — admin will see the missing event in logs
    return _merge_lib_entry(lib_entry, slot)


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
        "CREATE INDEX IF NOT EXISTS idx_sessions_cond ON sessions(condition)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_rel  ON sessions(condition, ad_relevance_arm)",
    ]:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column / index already exists
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
    # Pass the DB so balanced assignment can query current cell counts.
    db = get_db()
    cfg = load_config(condition_override=override, db=db)
    sid = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO sessions "
        "(id, created_at, user_agent, condition_label, condition, condition_source, "
        " ad_relevance_arm, config_snapshot) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            request.headers.get("User-Agent", "")[:512],
            cfg.get("condition_label", "phase1-default"),
            cfg.get("active_condition_resolved"),       # clean code, e.g. "A2"
            cfg.get("active_condition_source"),         # "balanced"|"random"|"fixed"|"override"
            cfg.get("resolved_ad_relevance"),           # "relevant"|"irrelevant"|None
            json.dumps(cfg, separators=(",", ":")),
        ),
    )
    db.commit()
    return jsonify({"session_id": sid, "config": cfg})


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

    db.execute(
        "INSERT INTO events (session_id, ts_server, ts_client, kind, payload) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            sid,
            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            ts_client,
            kind,
            json.dumps(payload, separators=(",", ":")),
        ),
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
        "ad_relevance_arm, user_agent, "
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
        for row in db.execute(
            f"SELECT condition, ad_relevance_arm, COUNT(*) AS n FROM sessions "
            f"WHERE condition IN ({placeholders}) AND ad_relevance_arm IS NOT NULL "
            f"GROUP BY condition, ad_relevance_arm",
            exp1_pool,
        ).fetchall():
            cell8_counts[(row["condition"], row["ad_relevance_arm"])] = row["n"]

    return render_template(
        "admin.html",
        sessions=sessions,
        token=ADMIN_TOKEN,
        conditions_meta=conditions_meta,
        exp1_pool=exp1_pool,
        cell_counts=cell_counts,
        cell8_counts=cell8_counts,
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
    """One row per session: metadata + key behavioural columns + all survey answers."""
    _require_admin()
    db = get_db()
    sessions = db.execute(
        "SELECT id, condition, ad_relevance_arm, condition_label, ts_created "
        "FROM sessions ORDER BY ts_created ASC"
    ).fetchall()

    rows: dict[str, dict] = {}
    for s in sessions:
        sid = s["id"]
        rows[sid] = {
            "session_id": sid,
            "condition": s["condition"],
            "ad_relevance_arm": s["ad_relevance_arm"],
            "condition_label": s["condition_label"],
            "ts_created": s["ts_created"],
            # behavioural columns filled below
            "title_watched": "",
            "ad_id_shown": "",
            "ad_skipped": "",
            "watch_duration_sec": "",
            "ad_view_duration_sec": "",
        }

    events = db.execute(
        "SELECT session_id, kind, payload FROM events ORDER BY id ASC"
    ).fetchall()

    for ev in events:
        sid = ev["session_id"]
        if sid not in rows:
            continue
        kind = ev["kind"]
        try:
            data = json.loads(ev["payload"])
        except (json.JSONDecodeError, TypeError):
            data = {}

        if kind == "watch_start":
            rows[sid]["title_watched"] = data.get("title_id", "")
        elif kind == "watch_end":
            rows[sid]["watch_duration_sec"] = data.get("elapsed_sec", "")
        elif kind == "ad_start":
            rows[sid]["ad_id_shown"] = data.get("ad_id", "")
            rows[sid]["ad_skipped"] = False
        elif kind == "ad_end":
            rows[sid]["ad_view_duration_sec"] = data.get("elapsed_sec", "")
        elif kind == "ad_prompt_declined":
            rows[sid]["ad_skipped"] = True
        elif kind == "survey_complete":
            responses = data.get("all_responses", data.get("responses", {}))
            if isinstance(responses, dict):
                for k, v in responses.items():
                    rows[sid][k] = v

    if not rows:
        return Response("session_id\n", mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=participants.csv"})

    meta_cols = ["session_id", "condition", "ad_relevance_arm", "condition_label",
                 "ts_created", "title_watched", "ad_id_shown", "ad_skipped",
                 "watch_duration_sec", "ad_view_duration_sec"]
    survey_keys = sorted({k for row in rows.values() for k in row if k not in meta_cols})
    all_cols = meta_cols + survey_keys

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(all_cols)
    for row in rows.values():
        writer.writerow([row.get(c, "") for c in all_cols])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=participants.csv"},
    )


@app.get("/admin/export.csv")
def admin_export_csv():
    _require_admin()
    db = get_db()
    rows = db.execute(
        "SELECT e.session_id, s.condition, s.ad_relevance_arm, s.condition_label, "
        "       e.ts_server, e.ts_client, e.kind, e.payload "
        "FROM events e JOIN sessions s ON s.id = e.session_id "
        "ORDER BY e.session_id, e.id ASC"
    ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["session_id", "condition", "ad_relevance_arm", "condition_label",
         "ts_server", "ts_client", "kind", "payload"]
    )
    for r in rows:
        writer.writerow(
            [r["session_id"], r["condition"], r["ad_relevance_arm"],
             r["condition_label"], r["ts_server"], r["ts_client"],
             r["kind"], r["payload"]]
        )
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=events.csv"},
    )


# --------------------------------------------------------------------------- #
#  Boilerplate
# --------------------------------------------------------------------------- #


@app.get("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(app.static_folder, filename)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=True)
