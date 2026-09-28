import numpy as np
import pandas as pd

from app.model import Params, analyse, days_to_clear
from app.sources import parse_trainingpeaks


def steady(days=90, hrv=60.0, rhr=50.0, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=days, freq="D")
    return pd.DataFrame({"hrv": hrv + rng.normal(0, 3, days), "rhr": rhr + rng.normal(0, 1, days)}, index=idx)


def test_steady_athlete_stays_mostly_green():
    result = analyse(steady())
    signals = result["signal"].dropna()
    assert (signals == "green").mean() > 0.8
    assert (signals == "red").sum() == 0


def test_overload_builds_debt_and_then_clears():
    data = steady(120)
    block = slice(60, 75)
    data.iloc[block, 0] -= 15  # HRV drops
    data.iloc[block, 1] += 6  # RHR rises
    result = analyse(data)
    assert result["debt"].iloc[74] >= Params().red
    assert result["signal"].iloc[74] == "red"
    assert result["recovered"].iloc[75:].any()
    assert result["debt"].iloc[-1] < 1


def test_days_to_clear():
    assert days_to_clear(0.5) == 0
    assert days_to_clear(25) > days_to_clear(12) > 0


def test_trainingpeaks_prefers_morning_reading():
    csv = (
        '"Timestamp","Type","Value"\n'
        '"2026-01-01 00:00:00","Pulse","98"\n'
        '"2026-01-01 07:10:00","Pulse","48"\n'
        '"2026-01-01 07:10:00","HRV","61.5"\n'
        '"2026-01-01 00:00:00","Stress Level","Max : 52 / Avg : 14"\n'
        '"2026-01-02 00:00:00","Pulse","50"\n'
    ).encode()
    frame = parse_trainingpeaks(csv)
    assert frame.loc["2026-01-01", "rhr"] == 48
    assert frame.loc["2026-01-01", "hrv"] == 61.5
    assert frame.loc["2026-01-01", "stress"] == 14
    assert frame.loc["2026-01-02", "rhr"] == 50
