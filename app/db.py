"""SQLite storage: athletes, who owns them, and their daily numbers."""

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
    synced_at TEXT
);
CREATE TABLE IF NOT EXISTS metric (
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    hrv REAL,
    rhr REAL,
    stress REAL,
    PRIMARY KEY (athlete_id, date)
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


def athletes(owner: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM athlete WHERE owner = ? ORDER BY name", (owner,)).fetchall()


def athlete(owner: str, athlete_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM athlete WHERE id = ? AND owner = ?", (athlete_id, owner)
        ).fetchone()


def add_athlete(owner: str, name: str, intervals_id: str | None, api_key: str | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO athlete (owner, name, intervals_id, api_key) VALUES (?, ?, ?, ?)",
            (owner, name, intervals_id or None, api_key or None),
        )
        return cur.lastrowid


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
