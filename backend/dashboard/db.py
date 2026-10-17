"""Accounts, sign-in sessions (laptop and phone), QR pairings and check results. No audio.

DATABASE_URL (in .env) picks the database: PostgreSQL for postgresql://... (the Docker database, see
docker-compose.yml), otherwise a local SQLite file for sqlite:///path. Queries are written once with ? placeholders
and run on both.
"""
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from backend import settings

URL = settings.DATABASE_URL
POSTGRES = URL.startswith(("postgresql://", "postgres://"))

if POSTGRES:
    import psycopg
    from psycopg.rows import dict_row

    IntegrityError = psycopg.IntegrityError
else:
    IntegrityError = sqlite3.IntegrityError
    _path = Path(URL.removeprefix("sqlite:///"))
    SQLITE_PATH = _path if _path.is_absolute() else settings.ROOT / _path

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password TEXT NOT NULL,
    created REAL NOT NULL
);
-- kind 'laptop': a dashboard sign-in; kind 'phone': a linked phone. Only token hashes are stored.
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    device TEXT,
    created REAL NOT NULL,
    last_seen REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pairings (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
-- status: queued -> checking -> done | rejected (unusable recording) | error
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    device TEXT,
    created REAL NOT NULL,
    mode TEXT NOT NULL,
    text_id TEXT,
    status TEXT NOT NULL,
    result TEXT,
    message TEXT,
    email TEXT
);
-- Track your voice: one row per reading of a text; session is the voice_checker.analyze dict as JSON
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text_id TEXT NOT NULL,
    created REAL NOT NULL,
    session TEXT NOT NULL
);
"""

# Same tables in PostgreSQL. Times are Unix seconds (DOUBLE PRECISION; REAL would round them to minutes).
# Emails are stored lower-case by the server, so a plain UNIQUE is enough.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    created DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    device TEXT,
    created DOUBLE PRECISION NOT NULL,
    last_seen DOUBLE PRECISION NOT NULL,
    expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS pairings (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires DOUBLE PRECISION NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    device TEXT,
    created DOUBLE PRECISION NOT NULL,
    mode TEXT NOT NULL,
    text_id TEXT,
    status TEXT NOT NULL,
    result TEXT,
    message TEXT,
    email TEXT
);
CREATE INDEX IF NOT EXISTS checks_user_created ON checks (user_id, created DESC);
CREATE TABLE IF NOT EXISTS readings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text_id TEXT NOT NULL,
    created DOUBLE PRECISION NOT NULL,
    session TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_user_text ON readings (user_id, text_id, created);
"""


def safe_url():
    """DATABASE_URL with the password hidden, for messages."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", URL)


class _Postgres:
    """Lets the queries below keep SQLite's ? placeholders on a psycopg connection."""

    def __init__(self, con):
        self.con = con

    def execute(self, sql, params=()):
        # psycopg uses %s placeholders, so a literal % (as in LIKE 'a%') must be doubled first
        return self.con.execute(sql.replace("%", "%%").replace("?", "%s"), params)


@contextmanager
def connect():
    """A connection that commits on success, rolls back on error and always closes."""
    if POSTGRES:
        with psycopg.connect(URL, row_factory=dict_row, connect_timeout=10) as con:
            yield _Postgres(con)
        return
    con = sqlite3.connect(SQLITE_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def init():
    """Create the tables, and fail the checks a previous run never finished (their audio is gone)."""
    try:
        if not POSTGRES:
            SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with connect() as con:
            if POSTGRES:
                for statement in filter(str.strip, POSTGRES_SCHEMA.split(";")):
                    con.execute(statement)
            else:
                con.execute("PRAGMA journal_mode = WAL")  # the check worker writes while the servers read
                con.executescript(SQLITE_SCHEMA)
            con.execute("UPDATE checks SET status = 'error', message = ? WHERE status IN ('queued', 'checking')",
                        ("The laptop app stopped before this recording was checked. Please send it again.",))
            con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            con.execute("DELETE FROM pairings WHERE expires < ? OR used = 1", (time.time(),))
    except (sqlite3.Error, *((psycopg.Error,) if POSTGRES else ())) as e:
        hint = " Is the database running? Start it with: docker compose up -d db" if POSTGRES else ""
        raise SystemExit(f"Couldn't open the database {safe_url()}: {e}.{hint}") from e


# --- Accounts ---------------------------------------------------------------
def create_user(name, email, password_hash):
    """The new user's id, or None if the email is taken."""
    try:
        with connect() as con:
            return con.execute("INSERT INTO users (name, email, password, created) VALUES (?, ?, ?, ?) RETURNING id",
                               (name, email, password_hash, time.time())).fetchone()["id"]
    except IntegrityError:
        return None


def user_by_email(email):
    with connect() as con:
        return con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def has_users():
    with connect() as con:
        return con.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


# --- Sessions ---------------------------------------------------------------
def create_session(user_id, kind, token_hash, days, device=None):
    now = time.time()
    with connect() as con:
        return con.execute("INSERT INTO sessions (token_hash, user_id, kind, device, created, last_seen, expires) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                           (token_hash, user_id, kind, device, now, now, now + days * 86400)).fetchone()["id"]


def session_user(token_hash, kind):
    """The signed-in user (with session_id and device) for a token, or None; refreshes last_seen."""
    now = time.time()
    with connect() as con:
        row = con.execute("SELECT u.id, u.name, u.email, s.id AS session_id, s.device FROM sessions s "
                          "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.kind = ? AND s.expires > ?",
                          (token_hash, kind, now)).fetchone()
        if row:
            con.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (now, row["session_id"]))
        return row


def delete_session(token_hash):
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def phones(user_id):
    """The user's linked phones, most recently used first."""
    with connect() as con:
        return con.execute("SELECT id, device, created, last_seen FROM sessions WHERE user_id = ? AND kind = 'phone' "
                           "AND expires > ? ORDER BY last_seen DESC", (user_id, time.time())).fetchall()


def unlink_phone(user_id, session_id):
    """Disconnect one of the user's phones; False if it wasn't theirs."""
    with connect() as con:
        return con.execute("DELETE FROM sessions WHERE id = ? AND user_id = ? AND kind = 'phone'",
                           (session_id, user_id)).rowcount > 0


# --- QR pairings ------------------------------------------------------------
def create_pairing(user_id, token_hash, ttl_s):
    """Store a new pairing. Older codes stay valid until used or expired, so two dashboard tabs both work."""
    with connect() as con:
        con.execute("DELETE FROM pairings WHERE expires < ? OR used = 1", (time.time(),))
        con.execute("INSERT INTO pairings (token_hash, user_id, expires) VALUES (?, ?, ?)",
                    (token_hash, user_id, time.time() + ttl_s))


def pairing_owner(token_hash):
    """The name of the user a still-valid pairing belongs to, or None."""
    with connect() as con:
        row = con.execute("SELECT u.name FROM pairings p JOIN users u ON u.id = p.user_id "
                          "WHERE p.token_hash = ? AND p.used = 0 AND p.expires > ?", (token_hash, time.time())).fetchone()
        return row["name"] if row else None


def use_pairing(token_hash):
    """Mark a pairing used and return its user id; None if it is unknown, used or expired."""
    with connect() as con:
        row = con.execute("UPDATE pairings SET used = 1 WHERE token_hash = ? AND used = 0 AND expires > ? "
                          "RETURNING user_id", (token_hash, time.time())).fetchone()
        return row["user_id"] if row else None


# --- Checks -----------------------------------------------------------------
def add_check(user, mode, text_id):
    """A queued check from a phone session row (see session_user); returns its id."""
    with connect() as con:
        return con.execute("INSERT INTO checks (user_id, session_id, device, created, mode, text_id, status) "
                           "VALUES (?, ?, ?, ?, ?, ?, 'queued') RETURNING id",
                           (user["id"], user["session_id"], user["device"], time.time(), mode, text_id)).fetchone()["id"]


def update_check(check_id, **fields):
    """Set some of: status, result (a dict), message, email."""
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"])
    with connect() as con:
        con.execute(f"UPDATE checks SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                    (*fields.values(), check_id))


def checks(user_id, limit=50):
    """The user's latest checks, newest first, as dicts."""
    with connect() as con:
        rows = con.execute("SELECT * FROM checks WHERE user_id = ? ORDER BY created DESC LIMIT ?",
                           (user_id, limit)).fetchall()
    return [check_dict(r) for r in rows]


def check(check_id, user_id):
    """One of the user's checks as a dict, or None."""
    with connect() as con:
        row = con.execute("SELECT * FROM checks WHERE id = ? AND user_id = ?", (check_id, user_id)).fetchone()
    return check_dict(row) if row else None


def check_dict(row):
    out = {k: row[k] for k in ("id", "device", "created", "mode", "text_id", "status", "message", "email")}
    out["result"] = json.loads(row["result"]) if row["result"] else None
    return out


# --- Track your voice -------------------------------------------------------
def add_reading(user_id, text_id, session):
    """Store one analyzed reading (a voice_checker.analyze session dict)."""
    with connect() as con:
        con.execute("INSERT INTO readings (user_id, text_id, created, session) VALUES (?, ?, ?, ?)",
                    (user_id, text_id, time.time(), json.dumps(session)))


def readings(user_id, text_id):
    """The user's readings of one text as session dicts, oldest first (the order drift scoring expects)."""
    with connect() as con:
        rows = con.execute("SELECT session FROM readings WHERE user_id = ? AND text_id = ? ORDER BY created, id",
                           (user_id, text_id)).fetchall()
    return [json.loads(r["session"]) for r in rows]


def reading_counts(user_id):
    """{text_id: number of readings} for the user."""
    with connect() as con:
        rows = con.execute("SELECT text_id, COUNT(*) AS n FROM readings WHERE user_id = ? GROUP BY text_id",
                           (user_id,)).fetchall()
    return {r["text_id"]: r["n"] for r in rows}


def delete_readings(user_id, text_id):
    with connect() as con:
        con.execute("DELETE FROM readings WHERE user_id = ? AND text_id = ?", (user_id, text_id))
