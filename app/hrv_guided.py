"""
HRV-guided training as published by Javaloyes et al. (2019, 2020), following
Vesterinen et al. (2016). Implemented from the methods of the 2020 paper:

- Morning HRV as ln(RMSSD); decisions use its 7-day rolling average.
- Smallest worthwhile change (SWC) = mean +/- 0.5 SD of ln(RMSSD), first from a
  2-week baseline, then recalculated every 4 weeks from the previous 4 weeks.
- 7-day average inside the SWC: high-intensity training as planned.
  Outside it, in either direction: low-intensity training or rest.

The paper also capped high intensity at 2 consecutive days and rest at 2
consecutive days; that depends on what was actually trained, so it is shown
as advice and not computed.

The coefficient of variation of ln(RMSSD) over 7 days (Plews et al. 2012) is
added as a second, informational line: a falling average with a rising CV
preceded non-functional overreaching in their case study. The papers set no
threshold for it, so it does not change the signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BASELINE_DAYS = 14
UPDATE_DAYS = 28
SWC = 0.5
MIN_VALUES = 7  # fewer readings than this in a window and the previous range stays

SIGNALS = {
    "green": "High intensity as planned (max 2 hard days in a row).",
    "amber": "Low intensity or rest until the 7-day HRV is back in the range (max 2 rest days in a row).",
}


def analyse(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty or daily["hrv"].dropna().empty:
        return pd.DataFrame()
    d = daily.sort_index().asfreq("D")
    ln = np.log(d["hrv"].where(d["hrv"] > 0))
    week = ln.rolling(7, min_periods=3).mean()

    start = ln.first_valid_index()
    low = pd.Series(np.nan, index=d.index)
    high = pd.Series(np.nan, index=d.index)
    # The first range comes from the 2-week baseline; each later one from the
    # 4 weeks just before it, and holds for the next 4 weeks.
    bounds = None
    window_start, change = start, start + pd.Timedelta(days=BASELINE_DAYS)
    while change <= d.index[-1]:
        values = ln[window_start : change - pd.Timedelta(days=1)].dropna()
        if len(values) >= MIN_VALUES:
            mean, sd = values.mean(), values.std()
            bounds = (mean - SWC * sd, mean + SWC * sd)
        if bounds:
            applies = (d.index >= change) & (d.index < change + pd.Timedelta(days=UPDATE_DAYS))
            low[applies], high[applies] = bounds
        window_start, change = change, change + pd.Timedelta(days=UPDATE_DAYS)

    out = pd.DataFrame(index=d.index)
    out["hrv"], out["rhr"], out["stress"] = d["hrv"], d.get("rhr"), d.get("stress")
    out["hrv_week"] = np.exp(week)
    out["hrv_low"], out["hrv_high"] = np.exp(low), np.exp(high)
    out["cv"] = (ln.rolling(7, min_periods=4).std() / ln.rolling(7, min_periods=4).mean() * 100).round(2)

    known = week.notna() & low.notna()
    inside = known & (week >= low) & (week <= high)
    out["signal"] = np.where(inside, "green", np.where(known, "amber", None))
    out["state"] = np.select(
        [inside, known & (week < low), known & (week > high)],
        ["Inside the normal range", "Below the normal range", "Above the normal range"],
        default="No data",
    )
    return out
