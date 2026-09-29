"""
SQLite storage: logins, athletes and their daily numbers.

An athlete has a coach (`owner`, the login that manages them) and optionally
an account of their own (`login`). Athletes without an account are managed
entirely by their coach.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd

DB_PATH = os.environ.get("DB_PATH", "data/recovery.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS athlete (
    id INTEGER PRIMARY KEY,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    intervals_id TEXT,
    api_key TEXT,
    synced_at TEXT,
    login TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS metric (
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    hrv REAL,
    rhr REAL,
    stress REAL,
    PRIMARY KEY (athlete_id, date)
);
CREATE TABLE IF NOT EXISTS login (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'coach', 'athlete')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email TEXT,
    weekly_mail INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS mail_log (
    username TEXT NOT NULL,
    week TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, week)
);
CREATE TABLE IF NOT EXISTS share (
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    PRIMARY KEY (athlete_id, username)
);
"""


@contextmanager
def connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Brings a database created by an earlier version up to the current schema."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(athlete)")}
    if "login" not in columns:
        conn.execute("ALTER TABLE athlete ADD COLUMN login TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS athlete_login ON athlete(login)")
    login_columns = {r["name"] for r in conn.execute("PRAGMA table_info(login)")}
    if "email" not in login_columns:
        conn.execute("ALTER TABLE login ADD COLUMN email TEXT")
        conn.execute("ALTER TABLE login ADD COLUMN weekly_mail INTEGER NOT NULL DEFAULT 1")
    # SQLite can't change a CHECK constraint, so the table is rebuilt to allow the athlete role.
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'login'").fetchone()["sql"]
    if "'athlete'" not in sql:
        conn.executescript(
            """
            ALTER TABLE login RENAME TO login_old;
            CREATE TABLE login (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'coach', 'athlete')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                email TEXT,
                weekly_mail INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO login (username, password_hash, role, created_at)
                SELECT username, password_hash, role, created_at FROM login_old;
            DROP TABLE login_old;
            """
        )


def login(username: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM login WHERE username = ?", (username,)).fetchone()


def logins() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT l.username, l.role, l.created_at, l.email, l.weekly_mail,
                   (SELECT COUNT(*) FROM athlete a WHERE a.owner = l.username) AS athletes,
                   (SELECT COUNT(*) FROM share s WHERE s.username = l.username) AS shared,
                   (SELECT a.id FROM athlete a WHERE a.login = l.username) AS profile_id,
                   (SELECT a.name FROM athlete a WHERE a.login = l.username) AS profile
            FROM login l ORDER BY l.role, l.username
            """
        ).fetchall()


def add_login(username: str, password_hash: str, role: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO login (username, password_hash, role) VALUES (?, ?, ?)", (username, password_hash, role)
        )


def update_login(username: str, password_hash: str | None = None, role: str | None = None) -> None:
    with connect() as conn:
        if password_hash:
            conn.execute("UPDATE login SET password_hash = ? WHERE username = ?", (password_hash, username))
        if role:
            conn.execute("UPDATE login SET role = ? WHERE username = ?", (role, username))


def set_mail(username: str, email: str | None, weekly: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE login SET email = ?, weekly_mail = ? WHERE username = ?", (email or None, int(weekly), username)
        )


def mail_sent(username: str, week: str) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM mail_log WHERE username = ? AND week = ?", (username, week)
        ).fetchone() is not None


def log_mail(username: str, week: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO mail_log (username, week) VALUES (?, ?)", (username, week))


def delete_login(username: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM share WHERE username = ?", (username,))
        conn.execute("UPDATE athlete SET login = NULL WHERE login = ?", (username,))
        conn.execute("DELETE FROM login WHERE username = ?", (username,))


def all_athletes() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM athlete ORDER BY owner, name").fetchall()


def athlete_by_id(athlete_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM athlete WHERE id = ?", (athlete_id,)).fetchone()


def athletes(owner: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM athlete WHERE owner = ? ORDER BY name", (owner,)).fetchall()


def athlete(owner: str, athlete_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM athlete WHERE id = ? AND owner = ?", (athlete_id, owner)
        ).fetchone()


def own_profile(username: str) -> sqlite3.Row | None:
    """The athlete profile that belongs to this login, if any."""
    with connect() as conn:
        return conn.execute("SELECT * FROM athlete WHERE login = ?", (username,)).fetchone()


def update_athlete(athlete_id: int, name: str, intervals_id: str | None, api_key: str | None, keep_key: bool) -> None:
    """A changed data source syncs again from scratch, so synced_at is cleared."""
    with connect() as conn:
        if keep_key:
            conn.execute(
                "UPDATE athlete SET name = ?, intervals_id = ?, synced_at = NULL WHERE id = ?",
                (name, intervals_id or None, athlete_id),
            )
        else:
            conn.execute(
                "UPDATE athlete SET name = ?, intervals_id = ?, api_key = ?, synced_at = NULL WHERE id = ?",
                (name, intervals_id or None, api_key or None, athlete_id),
            )


def link_login(athlete_id: int, username: str | None) -> None:
    with connect() as conn:
        if username:
            conn.execute("UPDATE athlete SET login = NULL WHERE login = ?", (username,))
        conn.execute("UPDATE athlete SET login = ? WHERE id = ?", (username or None, athlete_id))


def shared_with(username: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT a.* FROM athlete a JOIN share s ON s.athlete_id = a.id WHERE s.username = ? ORDER BY a.name",
            (username,),
        ).fetchall()


def visible_athlete(username: str, athlete_id: int) -> sqlite3.Row | None:
    """The athlete if this user owns it or it was shared with them."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT a.* FROM athlete a
            WHERE a.id = ? AND (a.owner = ? OR a.login = ? OR EXISTS (
                SELECT 1 FROM share s WHERE s.athlete_id = a.id AND s.username = ?))
            """,
            (athlete_id, username, username, username),
        ).fetchone()


def shares(athlete_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT username FROM share WHERE athlete_id = ? ORDER BY username", (athlete_id,))
        return [r["username"] for r in rows]


def add_share(athlete_id: int, username: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO share (athlete_id, username) VALUES (?, ?)", (athlete_id, username))


def remove_share(athlete_id: int, username: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM share WHERE athlete_id = ? AND username = ?", (athlete_id, username))


def add_athlete(owner: str, name: str, intervals_id: str | None, api_key: str | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO athlete (owner, name, intervals_id, api_key) VALUES (?, ?, ?, ?)",
            (owner, name, intervals_id or None, api_key or None),
        )
        return cur.lastrowid


def set_owner(athlete_id: int, owner: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE athlete SET owner = ? WHERE id = ?", (owner, athlete_id))
        # The new owner sees it anyway; a share with them would just be a duplicate.
        conn.execute("DELETE FROM share WHERE athlete_id = ? AND username = ?", (athlete_id, owner))


def delete_athlete(owner: str, athlete_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM athlete WHERE id = ? AND owner = ?", (athlete_id, owner))


def save_metrics(athlete_id: int, frame: pd.DataFrame, synced: bool = False) -> int:
    """Upserts the days in `frame`; a metric missing from it keeps its stored value."""
    rows = [
        (athlete_id, day.date().isoformat(), _val(r.get("hrv")), _val(r.get("rhr")), _val(r.get("stress")))
        for day, r in frame.iterrows()
    ]
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO metric (athlete_id, date, hrv, rhr, stress) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (athlete_id, date) DO UPDATE SET
                hrv = COALESCE(excluded.hrv, hrv),
                rhr = COALESCE(excluded.rhr, rhr),
                stress = COALESCE(excluded.stress, stress)
            """,
            rows,
        )
        if synced:
            conn.execute(
                "UPDATE athlete SET synced_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), athlete_id),
            )
    return len(rows)


def metrics(athlete_id: int) -> pd.DataFrame:
    with connect() as conn:
        frame = pd.read_sql_query(
            "SELECT date, hrv, rhr, stress FROM metric WHERE athlete_id = ? ORDER BY date",
            conn,
            params=(athlete_id,),
            parse_dates=["date"],
        )
    return frame.set_index("date").astype(float)


def _val(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)
