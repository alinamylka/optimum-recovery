"""
Recovery model: turns daily HRV, resting heart rate and (optionally) stress into
a readiness score, a fatigue debt, personal thresholds and an autonomic state.

The structure follows the charts Arkadiusz shared from the method's author,
reverse-engineered on Alina's data (same days, same export); the author's code
is not public, so every number here is our approximation of it:

- Each metric scores -3..+3: its 7-day average against the athlete's own
  90-day baseline, one point per half standard deviation (beyond a small dead
  zone). HRV up is good, resting HR and stress up are bad. Readiness is the sum
  of the three, -9..+9 (lnRMSSD against a rolling baseline: Plews et al. 2013).
- Fatigue debt is the "fatigue area": the negative readiness of the last 8
  days added up. It is zero once a whole 8 days pass without a negative day —
  a full recovery. On Alina's data this matches the author's curve closely.
- HRV variation 0..9: the 7-day coefficient of variation of lnRMSSD against
  its own baseline, 4.5 = usual, 3-6 = normal (Plews et al. 2012).
- Personal thresholds: functional overreaching, adaptation limit and danger
  are fixed shares (0.44 / 0.77 / 1) of a capacity that starts at the author's
  57 and moves with how the athlete comes out of each block: quick recovery
  raises it, slow recovery or a debt that lingers for weeks lowers it. The
  adaptation limit follows allostatic load (McEwen 1998); these rules are ours.
- A state for every day, from the author's legend: standard loading
  (parasympathetic or sympathetic), peak freshness, chronic creep, functional
  overreaching, autonomic rebound (an HRV spike in the middle of a block — Le
  Meur et al. 2013), borderline exhaustion and NFO / danger (Meeusen 2013).

All thresholds are parameters: starting points to calibrate, not validated values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Params:
    baseline_days: int = 90
    min_baseline_days: int = 14
    acute_days: int = 7
    step: float = 0.5  # standard deviations per readiness point
    dead_zone: float = 0.1  # closer to the baseline than this is zero
    area_days: int = 8  # how many days of negative readiness add up to the debt
    recovered_peak: float = 5.0  # a debt this big has to clear to count as a recovery
    # Personal thresholds: the danger line is the capacity, the other two are shares of it.
    capacity: float = 57.0
    fo_share: float = 0.44
    limit_share: float = 0.77
    capacity_min: float = 15.0
    capacity_max: float = 120.0
    growth: float = 0.3  # capacity gained (or lost) per point a block went past the overreaching line
    fast_recovery: int = 12  # days from a block's peak back to zero: this quick means the body adapted
    slow_recovery: int = 21  # this slow means the block cost more than the body had
    linger_days: int = 21  # days in a row past the overreaching line before capacity starts to wear down
    linger_loss: float = 0.01  # share of capacity lost each further day
    unused_fade: float = 0.01  # share of capacity above the starting value lost per fresh day (detraining)

    # The starting lines, for texts shown before there is any data.
    @property
    def amber(self) -> float:
        return self.capacity * self.fo_share

    @property
    def red(self) -> float:
        return self.capacity


# Which way is good for each metric.
DIRECTION = {"hrv": 1.0, "rhr": -1.0, "stress": -1.0}
# Below these a standard deviation is too small to divide by: a flat baseline
# would turn a one-beat change into an alarm.
SD_FLOOR = {"hrv": 0.03, "rhr": 1.0, "stress": 2.0}

SIGNALS = {
    "red": "Rest or easy spin only — no intensity until the debt comes down.",
    "amber": "Train, but keep it controlled: endurance, no new load.",
    "green": "Go: key sessions are fine.",
}

# State → signal. The order in `_state` decides which one wins.
STATE_SIGNALS = {
    "NFO / danger": "red",
    "Borderline exhaustion": "amber",
    "Autonomic rebound (fake-out)": "amber",
    "Functional overreaching": "amber",
    "Chronic creep": "amber",
    "Peak freshness": "green",
    "Standard loading (parasympathetic)": "green",
    "Standard loading (sympathetic)": "green",
}


def analyse(daily: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    """
    `daily` is indexed by date with columns hrv (ms), rhr (bpm) and optionally
    stress (0-100). Missing days are fine. Returns one row per calendar day.
    """
    if daily.empty:
        return pd.DataFrame()
    d = daily.sort_index().asfreq("D")
    for col in DIRECTION:
        if col not in d:
            d[col] = np.nan
    series = {"hrv": np.log(d["hrv"].where(d["hrv"] > 0)), "rhr": d["rhr"], "stress": d["stress"]}

    out = pd.DataFrame(index=d.index)
    out["hrv"], out["rhr"], out["stress"] = d["hrv"], d["rhr"], d["stress"]
    total = pd.Series(0.0, index=d.index)
    known = pd.Series(False, index=d.index)
    for name, s in series.items():
        rolling = s.rolling(p.baseline_days, min_periods=p.min_baseline_days)
        base = rolling.mean().shift(1)
        sd = rolling.std().shift(1).clip(lower=SD_FLOOR[name])
        week = s.rolling(p.acute_days, min_periods=3).mean()
        z = DIRECTION[name] * (week - base) / sd
        points = np.sign(z) * np.minimum(3, np.floor((z.abs() - p.dead_zone) / p.step) + 1).clip(lower=0)
        has = points.notna()
        total += points.where(has, 0.0)
        known |= has
        out[f"{name}_points"] = points
        out[f"{name}_week_z"] = z * DIRECTION[name]
        # The range is shown in the metric's own unit, so HRV goes back from logs to ms.
        lo, hi, wk = base - 0.5 * sd, base + 0.5 * sd, week
        if name == "hrv":
            lo, hi, wk = np.exp(lo), np.exp(hi), np.exp(wk)
        out[f"{name}_low"], out[f"{name}_high"], out[f"{name}_week"] = lo, hi, wk
    out["readiness"] = total.where(known)

    cv = series["hrv"].rolling(7, min_periods=4).std() / series["hrv"].rolling(7, min_periods=4).mean()
    base_cv = cv.rolling(p.baseline_days, min_periods=p.min_baseline_days).median().shift(1)
    out["hrv_variation"] = (4.5 * cv / base_cv).clip(0, 9).round(1)

    negative = (-out["readiness"]).clip(lower=0).fillna(0)
    debts = negative.rolling(p.area_days, min_periods=1).sum()
    capacity = Capacity(p)
    peak, since_negative = 0.0, p.area_days
    recovered, states, signals, lines, changes, clears = [], [], [], [], [], []
    for (day, row), debt, neg in zip(out.iterrows(), debts, negative):
        since_negative = 0 if neg > 0 else since_negative + 1
        peak = max(peak, debt)
        done = debt == 0 and peak >= p.recovered_peak
        if done:
            peak = 0.0
        lines.append(capacity.lines())  # judged against the lines as they stood that morning
        state = _state(row, debt, capacity)
        changes.append(capacity.update(debt))
        recovered.append(done)
        states.append(state)
        signals.append(STATE_SIGNALS.get(state))
        # With no further negative day the debt is gone once the last one drops out of the window.
        clears.append(max(0, p.area_days - since_negative) if debt > 0 else 0)

    out["debt"] = debts.round(1) + 0.0  # rolling sums can leave a -0.0
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
    of earlier blocks. A block is a stretch with any debt; when it ends and it
    went past the functional overreaching line, the days from its peak back to
    zero decide: quick means the body adapted and capacity grows, slow means the
    block cost too much and it shrinks — by `growth` per point the peak went past
    the line. Staying past that line for weeks wears capacity down, and capacity
    gained but unused fades back.
    """

    def __init__(self, p: Params):
        self.p = p
        self.danger = p.capacity
        self.block_peak = 0.0
        self.peak_fo = 0.0
        self.days_since_peak = 0
        self.days_past_fo = 0

    @property
    def fo(self) -> float:
        return self.danger * self.p.fo_share

    @property
    def limit(self) -> float:
        return self.danger * self.p.limit_share

    def lines(self) -> tuple[float, float, float]:
        return self.fo, self.limit, self.danger

    def update(self, debt: float) -> float:
        """Takes the day's closing debt; returns how much capacity changed."""
        p, before = self.p, self.danger
        if debt > 0:
            if debt > self.block_peak:
                self.block_peak, self.peak_fo, self.days_since_peak = debt, self.fo, 0
            else:
                self.days_since_peak += 1
            self.days_past_fo = self.days_past_fo + 1 if debt >= self.fo else 0
            if self.days_past_fo > p.linger_days:
                self.danger *= 1 - p.linger_loss
        else:
            if self.block_peak > self.peak_fo:
                days = self.days_since_peak + 1
                stretch = p.growth * (self.block_peak - self.peak_fo)
                if days <= p.fast_recovery:
                    self.danger += stretch
                elif days >= p.slow_recovery:
                    self.danger -= stretch
            elif self.danger > p.capacity:
                self.danger -= (self.danger - p.capacity) * p.unused_fade
            self.block_peak = self.peak_fo = 0.0
            self.days_since_peak = self.days_past_fo = 0
        self.danger = min(max(self.danger, p.capacity_min), p.capacity_max)
        return self.danger - before


def _state(row: pd.Series, debt: float, c: Capacity) -> str:
    if pd.isna(row["readiness"]):
        return "No data"
    if debt >= c.danger:
        return "NFO / danger"
    if debt >= c.limit:
        return "Borderline exhaustion"
    if debt >= c.fo and row["hrv_points"] == 3:
        return "Autonomic rebound (fake-out)"
    if debt >= c.fo:
        return "Functional overreaching"
    if row["hrv_points"] <= -2 and not row["rhr_points"] <= -2:
        # HRV sliding while resting HR looks fine: the slow kind of fatigue no single day shows.
        return "Chronic creep"
    if debt == 0 and row["readiness"] >= 3:
        return "Peak freshness"
    if row["hrv_points"] >= 0:
        return "Standard loading (parasympathetic)"
    return "Standard loading (sympathetic)"


def params_dict(p: Params = Params()) -> dict:
    return asdict(p)
