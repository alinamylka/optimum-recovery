"""
Recovery model: turns daily HRV, resting heart rate and (optionally) stress into
a readiness score, an accumulated fatigue debt and a green/amber/red signal.

The building blocks come from the HRV-guided training literature:

- lnRMSSD against a rolling personal baseline, with a "normal range" of
  baseline +/- 0.5 SD (Plews et al. 2013; Vesterinen et al. 2016).
- Resting heart rate and stress read the same way, in the opposite direction.
- Debt that builds on bad days and drains on good ones, decaying like the
  fatigue term of Banister's impulse-response model — but driven by the body's
  response rather than by training load.
- Clearing is slower once the debt is deep: an exhausted system recovers less
  per good day (Meeusen et al. 2013 on NFO).
- A sharp HRV rise while still in debt is treated as a warning, not as
  freshness (parasympathetic rebound; Le Meur et al. 2013).

All thresholds are parameters: they are starting points to calibrate, not
validated values.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Params:
    baseline_days: int = 60
    min_baseline_days: int = 14
    swc: float = 0.5  # half a standard deviation: the smallest change that matters
    amber: float = 12.0  # debt at which load stops being absorbed day to day
    red: float = 25.0  # debt deep enough to risk non-functional overreaching
    decay: float = 0.92  # share of the debt still there the next day on a neutral day
    strain_gain: float = 3.0
    clear_gain: float = 1.5
    deep_clear_factor: float = 0.5  # clearing speed once the debt is past red
    dead_zone: float = 0.2  # small negative scores are noise, not strain
    recovered_peak: float = 5.0  # a debt this big has to clear to count as a recovery


# How much each metric counts towards readiness, and which way is good.
WEIGHTS = {"hrv": (0.5, 1.0), "rhr": (0.3, -1.0), "stress": (0.2, -1.0)}
# Below these a standard deviation is too small to divide by: a flat baseline
# would turn a one-beat change into an alarm.
SD_FLOOR = {"hrv": 0.03, "rhr": 1.0, "stress": 2.0}

SIGNALS = {
    "red": "Rest or easy spin only — no intensity until the debt comes down.",
    "amber": "Train, but keep it controlled: endurance, no new load.",
    "green": "Go: key sessions are fine.",
}


def analyse(daily: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    """
    `daily` is indexed by date with columns hrv (ms), rhr (bpm) and optionally
    stress (0-100). Missing days are fine. Returns one row per calendar day.
    """
    if daily.empty:
        return pd.DataFrame()
    d = daily.sort_index().asfreq("D")
    for col in WEIGHTS:
        if col not in d:
            d[col] = np.nan
    series = {"hrv": np.log(d["hrv"].where(d["hrv"] > 0)), "rhr": d["rhr"], "stress": d["stress"]}

    out = pd.DataFrame(index=d.index)
    out["hrv"], out["rhr"], out["stress"] = d["hrv"], d["rhr"], d["stress"]
    weighted = pd.Series(0.0, index=d.index)
    weight_sum = pd.Series(0.0, index=d.index)
    for name, s in series.items():
        rolling = s.rolling(p.baseline_days, min_periods=p.min_baseline_days)
        base = rolling.mean().shift(1)
        sd = rolling.std().shift(1).clip(lower=SD_FLOOR[name])
        short = s.rolling(3, min_periods=1).mean()
        week = s.rolling(7, min_periods=3).mean()
        z = (short - base) / sd
        weight, direction = WEIGHTS[name]
        has = z.notna() & s.notna()
        weighted += (direction * z * weight).where(has, 0.0)
        weight_sum += pd.Series(weight, index=d.index).where(has, 0.0)
        out[f"{name}_z"] = z
        out[f"{name}_week_z"] = (week - base) / sd
        # The range is shown in the metric's own unit, so HRV goes back from logs to ms.
        lo, hi, wk = base - p.swc * sd, base + p.swc * sd, week
        if name == "hrv":
            lo, hi, wk = np.exp(lo), np.exp(hi), np.exp(wk)
        out[f"{name}_low"], out[f"{name}_high"], out[f"{name}_week"] = lo, hi, wk

    score = (weighted / weight_sum).where(weight_sum > 0)
    out["score"] = score
    out["readiness"] = (score * 3).round().clip(-9, 9)

    cv = series["hrv"].rolling(7, min_periods=4).std() / series["hrv"].rolling(7, min_periods=4).mean()
    base_cv = cv.rolling(p.baseline_days, min_periods=p.min_baseline_days).median().shift(1)
    out["hrv_variation"] = cv / base_cv

    debt, peak = 0.0, 0.0
    debts, recovered, states, signals = [], [], [], []
    for day, row in out.iterrows():
        previous = debt
        s = row["score"]
        if pd.isna(s):
            debt *= p.decay
        else:
            strain = max(0.0, -s - p.dead_zone)
            relief = max(0.0, s)
            clearing = p.clear_gain * relief * (p.deep_clear_factor if debt >= p.red else 1.0)
            debt = max(0.0, debt * p.decay + p.strain_gain * strain - clearing)
        peak = max(peak, debt)
        done = debt < 1.0 and peak >= p.recovered_peak
        if done:
            peak = 0.0
        debts.append(debt)
        recovered.append(done)
        state, signal = _state(row, debt, previous, p)
        states.append(state)
        signals.append(signal)

    out["debt"] = np.round(debts, 1)
    out["recovered"] = recovered
    out["state"] = states
    out["signal"] = signals
    out["days_to_clear"] = [days_to_clear(x, p) for x in debts]
    return out


def _state(row: pd.Series, debt: float, previous: float, p: Params) -> tuple[str, str | None]:
    if pd.isna(row["score"]):
        return "No data", None
    if debt >= p.red:
        return "Danger: NFO risk", "red"
    if row["hrv_z"] >= 1.5 and previous >= p.recovered_peak:
        return "Rebound: HRV spike while in debt", "amber"
    if debt >= p.amber:
        return "Overreaching", "amber"
    if row["hrv_week_z"] < -p.swc and row.get("rhr_week_z", 0) > -p.swc:
        return "Chronic creep: HRV trending low", "amber"
    if debt < 1.0 and row["readiness"] >= 2:
        return "Fresh", "green"
    return "Absorbing load", "green"


def days_to_clear(debt: float, p: Params = Params(), easy_score: float = 0.5) -> int:
    """Days until the debt drops below 1 if every day from now on is an ordinary good one."""
    days = 0
    while debt >= 1.0 and days < 90:
        factor = p.deep_clear_factor if debt >= p.red else 1.0
        debt = max(0.0, debt * p.decay - p.clear_gain * easy_score * factor)
        days += 1
    return days


def params_dict(p: Params = Params()) -> dict:
    return asdict(p)
