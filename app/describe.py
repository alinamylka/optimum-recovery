"""Plain-language summaries of a week, shown when a coach opens a row of the weekly table."""

from __future__ import annotations

import pandas as pd

from .model import Params


def week(week: pd.DataFrame, previous: pd.DataFrame | None) -> str:
    if "debt" in week:
        return _debt_week(week, previous, Params())
    return _hrv_week(week, previous)


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def _coverage(week: pd.DataFrame) -> str:
    n = len(week)
    return "" if n == 7 else f"Only {_days(n)} with data this week. "


def _hrv_week(w: pd.DataFrame, previous: pd.DataFrame | None) -> str:
    parts = [_coverage(w)]
    first, last = w["hrv_week"].iloc[0], w["hrv_week"].iloc[-1]
    lo, hi = w["hrv_low"].iloc[-1], w["hrv_high"].iloc[-1]
    move = "stayed around" if abs(last - first) < 1.5 else ("rose from" if last > first else "fell from")
    trend = f"{move} {last:.0f} ms" if move == "stayed around" else f"{move} {first:.0f} to {last:.0f} ms"
    parts.append(f"The 7-day HRV average {trend}; the normal range was {lo:.0f}–{hi:.0f} ms. ")

    states = w["state"].value_counts()
    inside = int(states.get("Inside the normal range", 0))
    below = int(states.get("Below the normal range", 0))
    above = int(states.get("Above the normal range", 0))
    if below == 0 and above == 0:
        parts.append(
            "Every day was inside the range: the load was being absorbed and hard sessions were fine. "
        )
    else:
        if below:
            parts.append(
                f"Below the range on {_days(below)} — a sign of accumulated fatigue (or illness, stress, travel); "
                "the method calls for easy training or rest until the average comes back. "
            )
        if above:
            parts.append(
                f"Above the range on {_days(above)}. The method treats this as an easy day too: a sudden rise, "
                "especially after hard training, is often a rebound rather than extra freshness. "
            )
        if inside:
            parts.append(f"Inside the range on {_days(inside)}. ")

    cv = w["cv"].mean()
    if previous is not None and not previous.empty and pd.notna(cv) and pd.notna(previous["cv"].mean()):
        before = previous["cv"].mean()
        prev_hrv = previous["hrv_week"].iloc[-1]
        if cv > before * 1.3:
            parts.append(f"Day-to-day variation rose (CV {before:.1f} → {cv:.1f} %). ")
            if last < prev_hrv:
                parts.append(
                    "Falling HRV with rising variation is the pattern Plews et al. (2012) saw before "
                    "non-functional overreaching — worth watching. "
                )
        elif cv < before / 1.3:
            parts.append(f"Day-to-day variation settled (CV {before:.1f} → {cv:.1f} %): a steadier system. ")
        else:
            parts.append(f"Day-to-day variation similar to the week before (CV {cv:.1f} %). ")
    return "".join(parts).strip()


def _debt_week(w: pd.DataFrame, previous: pd.DataFrame | None, p: Params) -> str:
    parts = [_coverage(w)]
    readiness = w["readiness"].mean()
    feel = "better than usual" if readiness >= 1 else ("worse than usual" if readiness <= -1 else "around usual")
    parts.append(f"Readiness averaged {readiness:+.1f}: HRV and resting HR were {feel}. ")

    start = previous["debt"].iloc[-1] if previous is not None and not previous.empty else w["debt"].iloc[0]
    end, peak = w["debt"].iloc[-1], w["debt"].max()
    if peak < 1:
        parts.append("No fatigue debt all week. ")
    else:
        direction = "built up" if end > start + 1 else ("came down" if end < start - 1 else "held steady")
        parts.append(f"Fatigue debt {direction}: {start:.0f} → {end:.0f} (peak {peak:.0f}). ")

    red = int((w["debt"] >= p.red).sum())
    amber = int(((w["debt"] >= p.amber) & (w["debt"] < p.red)).sum())
    if red:
        parts.append(
            f"{_days(red)} above {p.red:.0f} — deep enough to risk non-functional overreaching; "
            "only easy training until it drains. "
        )
    if amber:
        parts.append(f"{_days(amber)} between {p.amber:.0f} and {p.red:.0f}: overreaching, load no longer absorbed day to day. ")
    states = w["state"].value_counts()
    warned = False
    if states.get("Rebound: HRV spike while in debt"):
        parts.append("HRV spiked while still in debt — read as a reaction to overload, not freshness. ")
        warned = True
    if states.get("Chronic creep: HRV trending low"):
        parts.append("The weekly HRV sat below normal although no single day looked bad (chronic creep). ")
        warned = True
    if w["recovered"].any():
        day = w.index[w["recovered"]][-1]
        parts.append(f"Full recovery on {day:%a %d.%m}: the debt cleared — a good point to start the next block. ")
    elif peak < p.amber and not warned:
        parts.append("Load was absorbed within capacity. ")
    return "".join(parts).strip()
