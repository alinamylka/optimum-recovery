"""Where the daily numbers come from: intervals.icu, or a TrainingPeaks metrics export."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, timedelta

import httpx
import pandas as pd

INTERVALS = "https://intervals.icu/api/v1"


def fetch_intervals(athlete_id: str, api_key: str, days: int = 400) -> pd.DataFrame:
    """
    Daily wellness from intervals.icu. A coach's key works for athletes who
    share their account with the coach; "0" means the key's own athlete.
    """
    newest = date.today()
    oldest = newest - timedelta(days=days)
    response = httpx.get(
        f"{INTERVALS}/athlete/{athlete_id or '0'}/wellness",
        params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        auth=("API_KEY", api_key),
        timeout=30,
    )
    response.raise_for_status()
    rows = [
        {"date": r["id"], "hrv": r.get("hrv"), "rhr": r.get("restingHR"), "stress": None}
        for r in response.json()
    ]
    return _frame(rows)


def parse_trainingpeaks(data: bytes) -> pd.DataFrame:
    """
    TrainingPeaks: Account Settings -> Export Data -> Custom Metrics gives a zip
    with metrics.csv (Timestamp, Type, Value). Either the zip or the CSV works.

    Several devices can write the same metric on the same day. Readings taken
    in the morning come from a device measuring the night (WHOOP, Oura, a
    morning HRV app); entries at exactly midnight are daily summaries synced
    by another device, whose "resting" pulse can be a whole-day average. So a
    morning reading wins, and the first one of the day if there are several.
    """
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            csvs = [n for n in names if n.lower().endswith(".csv")]
            if not csvs:
                if any(".fit" in n.lower() for n in names):
                    raise ValueError(
                        f"this is a Workout Files export ({len(names)} .FIT workouts). Recovery needs the "
                        "morning HRV and resting HR: in TrainingPeaks export Custom Metrics instead."
                    )
                raise ValueError(f"the zip has no CSV file (it contains {', '.join(names[:3])}...)")
            data = z.read(csvs[0])
    text = data.decode("utf-8-sig")
    picked: dict[tuple[str, str], tuple[bool, str, float]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        column = {"HRV": "hrv", "Pulse": "rhr", "Stress Level": "stress"}.get(row.get("Type", ""))
        if not column:
            continue
        value = _number(row["Value"], column)
        if value is None:
            continue
        stamp = row["Timestamp"]
        day, time = stamp[:10], stamp[11:]
        midnight = time.startswith("00:00")
        key = (day, column)
        candidate = (midnight, time, value)
        if key not in picked or candidate[:2] < picked[key][:2]:
            picked[key] = candidate
    if not picked:
        raise ValueError("no HRV, Pulse or Stress Level rows found — is this the Custom Metrics export?")
    rows: dict[str, dict] = {}
    for (day, column), (_, _, value) in picked.items():
        rows.setdefault(day, {"date": day})[column] = value
    return _frame(list(rows.values()))


def _number(raw: str, column: str) -> float | None:
    if column == "stress":
        # Garmin writes "Max : 52 / Avg : 14"; the average is the day's level.
        match = re.search(r"Avg\s*:\s*([\d.]+)", raw)
        raw = match.group(1) if match else raw
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "hrv", "rhr", "stress"])
    if frame.empty:
        return frame.set_index("date")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index().astype(float)
    return frame.dropna(how="all")
