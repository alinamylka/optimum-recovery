"""
Small PNG charts for the Monday email. Mail apps don't run the page's Plotly
charts, so each athlete and model gets a picture of the last four weeks with
the reported week shaded.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

GREEN, AMBER, RED, ACCENT, GREY, MUTED = "#2e9e5b", "#e0a100", "#d64541", "#2f6fde", "#b5b5ae", "#6b6b66"
DAYS = 28

LABELS = {
    "pl": {"readiness": "Gotowość", "debt": "Dług zmęczeniowy", "decision": "Decyzja", "rhr": "Tętno spocz."},
    "en": {"readiness": "Readiness", "debt": "Fatigue debt", "decision": "Decision", "rhr": "Resting HR"},
}


def _by_size(v) -> str:
    if pd.isna(v):
        return GREY
    return RED if abs(v) >= 6 else AMBER if abs(v) >= 3 else GREEN


def _band(ax, part: pd.DataFrame, key: str, color: str, label: str) -> None:
    """The nightly readings, their 7-day line and the athlete's usual range — as on the page."""
    if f"{key}_low" in part:
        ax.fill_between(part.index, part[f"{key}_low"], part[f"{key}_high"], color=GREY, alpha=0.3, linewidth=0, step="mid")
    ax.plot(part.index, part[key], "o", color=color, alpha=0.45, markersize=3)
    if f"{key}_week" in part:
        ax.plot(part.index, part[f"{key}_week"], color=color, linewidth=2)
    ax.set_ylabel(label)


def week_png(model_key: str, result: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, lang: str = "pl") -> bytes | None:
    """The last four weeks up to `end` as a PNG, the week from `start` shaded; None without data."""
    if result.empty:
        return None
    part = result[(result.index > end - pd.Timedelta(days=DAYS)) & (result.index <= end)]
    if part["hrv"].notna().sum() == 0:
        return None
    words = LABELS.get(lang, LABELS["en"])
    debt = model_key == "debt"
    rows = [1.2, 1.2, 1.4, 1] if debt else [0.35, 1.6, 1]
    fig, axes = plt.subplots(len(rows), 1, sharex=True, figsize=(6.4, 1.15 * sum(rows) + 0.5), dpi=110,
                             gridspec_kw={"height_ratios": rows, "hspace": 0.12})
    if debt:
        ax = axes[0]
        ax.bar(part.index, part["readiness"], width=0.85, color=[_by_size(v) for v in part["readiness"]])
        ax.axhline(0, color=MUTED, linewidth=0.6)
        ax.set_ylim(-9.5, 9.5)
        ax.set_yticks([-6, 0, 6])
        ax.set_ylabel(words["readiness"])
        ax = axes[1]
        ax.fill_between(part.index, 0, part["debt"], color="#888888", alpha=0.25, linewidth=0)
        ax.plot(part.index, part["debt"], color="#888888", linewidth=2)
        for key, color in (("fo", "#8a63d2"), ("limit", AMBER), ("danger", RED)):
            ax.plot(part.index, part[key], color=color, linestyle="--", linewidth=1)
        ax.set_ylim(bottom=0)
        ax.set_ylabel(words["debt"])
        hrv_ax, rhr_ax = axes[2], axes[3]
    else:
        ax = axes[0]
        colors = {"green": GREEN, "amber": AMBER}
        ax.bar(part.index, part["signal"].notna().astype(int), width=0.85,
               color=[colors.get(s, GREY) for s in part["signal"]])
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_ylabel(words["decision"], rotation=0, ha="right", va="center")
        hrv_ax, rhr_ax = axes[1], axes[2]
    _band(hrv_ax, part, "hrv", ACCENT, "HRV (ms)")
    _band(rhr_ax, part, "rhr", RED, words["rhr"])
    for ax in axes:
        ax.axvspan(start - pd.Timedelta(hours=12), end + pd.Timedelta(hours=12), color=ACCENT, alpha=0.07, linewidth=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(GREY)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.yaxis.label.set_color(MUTED)
        ax.yaxis.label.set_fontsize(8)
        ax.grid(axis="y", color="#e3e3de", linewidth=0.6)
    axes[-1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    axes[-1].set_xlim(end - pd.Timedelta(days=DAYS - 0.5), end + pd.Timedelta(hours=12))
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buffer.getvalue()
