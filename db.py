"""SQLite storage layer for PrivacyMirror.

A single-file local database. No ORM, no external deps — just sqlite3.
JSON-shaped fields (emails, phones, addresses) are stored as TEXT.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privacymirror.db")

# sqlite connections are not safe to share across threads by default; we use a
# lock + check_same_thread=False so the scheduler thread and HTTP threads share one.
_LOCK = threading.RLock()
_CONN = None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_conn():
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        # let the headless task and the web app share the DB without lock errors
        _CONN.execute("PRAGMA busy_timeout=5000")
    return _CONN


def execute(sql, params=()):
    with _LOCK:
        conn = get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def query(sql, params=()):
    with _LOCK:
        conn = get_conn()
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    full_name     TEXT DEFAULT '',
    aliases       TEXT DEFAULT '[]',   -- maiden names, nicknames
    emails        TEXT DEFAULT '[]',
    phones        TEXT DEFAULT '[]',
    addresses     TEXT DEFAULT '[]',   -- list of free-text addresses
    date_of_birth TEXT DEFAULT '',     -- YYYY-MM-DD or year only
    notes         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS brokers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE,
    name          TEXT NOT NULL,
    category      TEXT DEFAULT 'people-search',
    website       TEXT DEFAULT '',
    method        TEXT DEFAULT 'email',   -- email | form | phone | mail
    opt_out_url   TEXT DEFAULT '',
    privacy_email TEXT DEFAULT '',
    requires_id   INTEGER DEFAULT 0,      -- broker demands ID verification
    jurisdiction  TEXT DEFAULT 'US',      -- US | EU | both
    enabled       INTEGER DEFAULT 1,      -- include in removal runs
    notes         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id     INTEGER NOT NULL,
    status        TEXT DEFAULT 'pending', -- pending|queued|sent|acknowledged|completed|rejected|needs_action|overdue
    method        TEXT DEFAULT 'email',
    subject       TEXT DEFAULT '',
    body          TEXT DEFAULT '',
    created_at    TEXT,
    sent_at       TEXT,
    deadline_at   TEXT,                   -- legal response window
    last_update   TEXT,
    follow_up_count INTEGER DEFAULT 0,
    response_notes  TEXT DEFAULT '',
    FOREIGN KEY (broker_id) REFERENCES brokers(id)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER,
    ts          TEXT,
    kind        TEXT,    -- created|queued|sent|dry_run|status_change|follow_up|note|error
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS seen_messages (
    message_id TEXT PRIMARY KEY,   -- Gmail message id already ingested
    request_id INTEGER,
    ts         TEXT
);
"""

DEFAULT_SETTINGS = {
    "auto_send_enabled": "0",   # master switch for automated sending
    "dry_run": "1",             # when 1, "send" only logs, never hits SMTP
    "send_provider": "smtp",    # smtp | gmail
    "gmail_mode": "send",       # send | draft  (draft = create in Gmail for review)
    "gmail_client_id": "",
    "gmail_client_secret": "",
    "gmail_refresh_token": "",  # obtained after OAuth consent
    "gmail_email": "",          # the connected Gmail address (From)
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_use_tls": "1",
    "from_email": "",
    "from_name": "",
    "send_interval_minutes": "1440",   # how often the scheduler runs a pass
    "follow_up_after_days": "35",      # send a follow-up if no response by then
    "max_sends_per_pass": "5",         # rate-limit per scheduler pass
    "recheck_enabled": "0",            # auto-(re)generate requests on a cadence
    "recheck_interval_days": "90",     # re-request a broker this long after completion/rejection
    "ingest_replies_enabled": "1",     # read broker replies (needs Gmail readonly scope)
    "reply_classify_mode": "ack",      # ack | full | off  (how far to auto-advance status)
    "gmail_scopes": "",                # scopes actually granted at last consent
}


def init_db(seed_brokers=True):
    with _LOCK:
        conn = get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
    # ensure single profile row
    if not query_one("SELECT id FROM profile WHERE id = 1"):
        execute("INSERT INTO profile (id) VALUES (1)")
    # default settings
    for k, v in DEFAULT_SETTINGS.items():
        if get_setting(k) is None:
            set_setting(k, v)
    if seed_brokers and not query_one("SELECT id FROM brokers LIMIT 1"):
        from seed import seed_all
        seed_all()


# ---- settings helpers ----

def get_setting(key, default=None):
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def all_settings():
    return {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}


# ---- profile helpers ----

def get_profile():
    row = query_one("SELECT * FROM profile WHERE id = 1")
    if not row:
        return {}
    for f in ("aliases", "emails", "phones", "addresses"):
        try:
            row[f] = json.loads(row.get(f) or "[]")
        except (ValueError, TypeError):
            row[f] = []
    return row


def save_profile(data):
    execute(
        """UPDATE profile SET full_name=?, aliases=?, emails=?, phones=?,
           addresses=?, date_of_birth=?, notes=? WHERE id = 1""",
        (
            data.get("full_name", ""),
            json.dumps(data.get("aliases", [])),
            json.dumps(data.get("emails", [])),
            json.dumps(data.get("phones", [])),
            json.dumps(data.get("addresses", [])),
            data.get("date_of_birth", ""),
            data.get("notes", ""),
        ),
    )


def profile_is_complete():
    p = get_profile()
    return bool(p.get("full_name") and (p.get("emails") or p.get("addresses")))


# ---- event log ----

def log_event(request_id, kind, detail=""):
    execute(
        "INSERT INTO events (request_id, ts, kind, detail) VALUES (?, ?, ?, ?)",
        (request_id, now_iso(), kind, detail),
    )
