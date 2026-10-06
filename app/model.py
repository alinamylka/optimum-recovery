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
- Personal thresholds instead of one scale for everyone: a capacity that grows
  when the athlete comes back quickly from a block past the functional
  overreaching line, and shrinks when recovery drags or the debt lingers. The
  three lines (functional overreaching, adaptation limit, danger) are fixed
  shares of it. The idea of an adaptation limit follows allostatic load
  (McEwen 1998); the rules and numbers are our own.

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
    # Personal thresholds. Capacity (= the danger line) starts at `red`; functional
    # overreaching starts at amber/red of it and the adaptation limit at limit_share.
    limit_share: float = 0.77
    capacity_min: float = 12.5
    capacity_max: float = 62.5
    growth: float = 0.3  # capacity gained (or lost) per point a block went past the overreaching line
    # Recovery timed against the easy-day pace; a normal week mixes in hard days, so up to twice that is quick.
    fast_recovery: float = 2.0  # cleared within this many times the easy-day pace: adapted
    slow_recovery: float = 3.0  # slower than this: the block cost more than the body had
    linger_days: int = 21  # days in a row past the overreaching line before capacity starts to wear down
    linger_loss: float = 0.01  # share of capacity lost each further day
    unused_fade: float = 0.01  # share of capacity above the starting value lost per fresh day (detraining)


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
    capacity = Capacity(p)
    debts, recovered, states, signals, lines, changes, clears = [], [], [], [], [], [], []
    for day, row in out.iterrows():
        previous = debt
        s = row["score"]
        if pd.isna(s):
            debt *= p.decay
        else:
            strain = max(0.0, -s - p.dead_zone)
            relief = max(0.0, s)
            clearing = p.clear_gain * relief * (p.deep_clear_factor if debt >= capacity.danger else 1.0)
            debt = max(0.0, debt * p.decay + p.strain_gain * strain - clearing)
        peak = max(peak, debt)
        done = debt < 1.0 and peak >= p.recovered_peak
        if done:
            peak = 0.0
        lines.append(capacity.lines())  # judged against the lines as they stood that morning
        state, signal = _state(row, debt, previous, p, capacity)
        changes.append(capacity.update(debt))
        debts.append(debt)
        recovered.append(done)
        states.append(state)
        signals.append(signal)
        clears.append(days_to_clear(debt, p, danger=capacity.danger))

    out["debt"] = np.round(debts, 1)
    out["fo"], out["limit"], out["danger"] = (np.round(col, 1) for col in zip(*lines))
    out["capacity_change"] = np.round(changes, 1)
    out["recovered"] = recovered
    out["state"] = states
    out["signal"] = signals
    out["days_to_clear"] = clears
    return out


class Capacity:
    """
    How much fatigue debt this athlete can carry, learnt from how they came out
    of earlier blocks. A block is a stretch with the debt above 1; when it ends
    and it went past the functional overreaching line, the recovery is timed
    against the easy-day pace (`days_to_clear`): quick means the body adapted
    and capacity grows, slow means the block cost too much and it shrinks — by
    `growth` per point the peak went past the line. Staying past that line for
    weeks wears capacity down, and capacity gained but unused fades back.
    """

    def __init__(self, p: Params):
        self.p = p
        self.danger = p.red
        self.block_peak = 0.0
        self.peak_fo = 0.0
        self.peak_expected = 0
        self.days_since_peak = 0
        self.days_past_fo = 0

    @property
    def fo(self) -> float:
        return self.danger * self.p.amber / self.p.red

    @property
    def limit(self) -> float:
        return self.danger * self.p.limit_share

    def lines(self) -> tuple[float, float, float]:
        return self.fo, self.limit, self.danger

    def update(self, debt: float) -> float:
        """Takes the day's closing debt; returns how much capacity changed."""
        p, before = self.p, self.danger
        if debt >= 1.0:
            if debt > self.block_peak:
                self.block_peak, self.peak_fo, self.days_since_peak = debt, self.fo, 0
                self.peak_expected = days_to_clear(debt, p, danger=self.danger)
            else:
                self.days_since_peak += 1
            self.days_past_fo = self.days_past_fo + 1 if debt >= self.fo else 0
            if self.days_past_fo > p.linger_days:
                self.danger *= 1 - p.linger_loss
        else:
            if self.block_peak > self.peak_fo:
                pace = (self.days_since_peak + 1) / max(self.peak_expected, 1)
                stretch = p.growth * (self.block_peak - self.peak_fo)
                if pace <= p.fast_recovery:
                    self.danger += stretch
                elif pace >= p.slow_recovery:
                    self.danger -= stretch
            elif self.danger > p.red:
                self.danger -= (self.danger - p.red) * p.unused_fade
            self.block_peak = self.peak_fo = 0.0
            self.days_since_peak = self.days_past_fo = 0
        self.danger = min(max(self.danger, p.capacity_min), p.capacity_max)
        return self.danger - before


def _state(row: pd.Series, debt: float, previous: float, p: Params, c: Capacity) -> tuple[str, str | None]:
    if pd.isna(row["score"]):
        return "No data", None
    if debt >= c.danger:
        return "Danger: NFO risk", "red"
    if row["hrv_z"] >= 1.5 and previous >= p.recovered_peak:
        return "Rebound: HRV spike while in debt", "amber"
    if debt >= c.limit:
        return "Past the adaptation limit", "amber"
    if debt >= c.fo:
        return "Functional overreaching", "amber"
    if row["hrv_week_z"] < -p.swc and row.get("rhr_week_z", 0) > -p.swc:
        return "Chronic creep: HRV trending low", "amber"
    if debt < 1.0 and row["readiness"] >= 2:
        return "Fresh", "green"
    return "Absorbing load", "green"


def days_to_clear(debt: float, p: Params = Params(), easy_score: float = 0.5, danger: float | None = None) -> int:
    """Days until the debt drops below 1 if every day from now on is an ordinary good one."""
    danger = p.red if danger is None else danger
    days = 0
    while debt >= 1.0 and days < 90:
        factor = p.deep_clear_factor if debt >= danger else 1.0
        debt = max(0.0, debt * p.decay - p.clear_gain * easy_score * factor)
        days += 1
    return days


def params_dict(p: Params = Params()) -> dict:
    return asdict(p)
