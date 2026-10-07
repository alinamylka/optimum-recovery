import numpy as np
import pandas as pd

from app.model import Params, analyse
from app.sources import parse_trainingpeaks


def steady(days=90, hrv=60.0, rhr=50.0, stress=30.0, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {"hrv": hrv + rng.normal(0, 3, days), "rhr": rhr + rng.normal(0, 1, days), "stress": stress + rng.normal(0, 3, days)},
        index=idx,
    )


def overload(data, block, hrv=15, rhr=6, stress=12):
    data.iloc[block, 0] -= hrv
    data.iloc[block, 1] += rhr
    data.iloc[block, 2] += stress
    return data


def test_steady_athlete_stays_mostly_green():
    result = analyse(steady())
    signals = result["signal"].dropna()
    assert (signals == "green").mean() > 0.8
    assert (signals == "red").sum() == 0


def test_readiness_is_three_metric_scores_added_up():
    result = analyse(overload(steady(120), slice(60, 75)))
    points = result[["hrv_points", "rhr_points", "stress_points"]]
    assert points.abs().max().max() <= 3
    assert result["readiness"].dropna().eq(points.loc[result["readiness"].notna()].fillna(0).sum(axis=1)).all()
    assert result["readiness"].iloc[70] == -9


def test_debt_is_the_negative_readiness_of_the_last_8_days():
    result = analyse(overload(steady(120), slice(60, 75)))
    area = (-result["readiness"]).clip(lower=0).fillna(0).rolling(Params().area_days, min_periods=1).sum()
    assert np.allclose(result["debt"], area.round(1))
    assert result["debt"].iloc[74] >= result["danger"].iloc[74]
    assert result["signal"].iloc[74] == "red"
    # Eight days without a negative day and the debt is gone: a full recovery.
    assert result["recovered"].iloc[75:].any()
    assert result["debt"].iloc[-1] == 0


def test_days_to_clear_counts_down_to_the_end_of_the_window():
    result = analyse(overload(steady(120), slice(60, 75)))
    after = result.iloc[75:110]
    clear = after.loc[after["debt"] > 0, "days_to_clear"]
    assert clear.max() <= Params().area_days
    assert (result.loc[result["debt"] == 0, "days_to_clear"] == 0).all()


def test_quick_recovery_raises_the_personal_thresholds():
    result = analyse(overload(steady(160), slice(60, 64), hrv=12, rhr=4, stress=10))
    assert result["debt"].iloc[60:80].max() > Params().capacity * Params().fo_share  # it went past FO
    assert result["danger"].iloc[-1] > Params().capacity
    assert (result["fo"] / result["danger"]).round(2).eq(Params().fo_share).all()


def test_drawn_out_overload_lowers_the_personal_thresholds():
    result = analyse(overload(steady(200), slice(60, 130), hrv=10, rhr=4, stress=8))
    assert result["danger"].iloc[129] < Params().capacity
    assert result["danger"].min() >= Params().capacity_min
    assert {"Borderline exhaustion", "NFO / danger"} & set(result["state"])


def test_week_summary_names_the_personal_lines():
    from app import describe

    result = analyse(overload(steady(120), slice(60, 75)))
    text = describe.week(result.iloc[70:77], result.iloc[63:70], "en")
    assert "danger threshold" in text


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


def test_hrv_guided_follows_the_swc_rule():
    from app import hrv_guided

    data = steady(90)
    data.iloc[50:60, 0] -= 20  # a clear HRV drop pushes the 7-day average below the range
    result = hrv_guided.analyse(data)
    assert result["signal"].iloc[:14].isna().all()  # still collecting the 2-week baseline
    assert result["state"].iloc[58] == "Below the normal range"
    assert result["signal"].iloc[58] == "amber"
    # the range only changes at the 4-week boundaries after the baseline
    low = result["hrv_low"].dropna()
    changed = low.index[low.diff().fillna(0).ne(0)]
    assert all((day - low.index[0]).days % 28 == 0 for day in changed)


def test_password_hash_roundtrip():
    from app import auth

    stored = auth.hash_password("s3cret")
    assert auth._matches(stored, "s3cret")
    assert not auth._matches(stored, "wrong")


def test_oura_trends_export():
    from app.sources import parse_export

    csv = (
        "date,Sleep Score,Average HRV,Lowest Resting Heart Rate,Average Resting Heart Rate\n"
        "2026-01-01,80,78,42,47.1\n"
        "2026-01-02,82,,,\n"
        "2026-01-03,85,90,40,45.0\n"
    ).encode()
    frame = parse_export(csv)
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-03"]
    assert frame.loc["2026-01-03", "hrv"] == 90
    assert frame.loc["2026-01-03", "rhr"] == 40


def test_last_week_is_the_monday_to_sunday_before():
    from datetime import datetime

    from app.mailer import last_week

    start, end = last_week(datetime(2026, 9, 28, 6, 0))  # a Monday
    assert (start.date().isoformat(), end.date().isoformat()) == ("2026-09-21", "2026-09-27")
