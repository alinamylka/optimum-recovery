"""
Plain-language summaries of a week (shown when a coach opens a row of the
weekly table, and in the Monday email), plus translations of the models'
state names and advice. Languages: "pl" and "en".
"""

from __future__ import annotations

import pandas as pd

from .model import Params

LANGUAGES = {"pl": "Polski", "en": "English"}
DEFAULT = "pl"

STATES = {
    "Inside the normal range": "W normie",
    "Below the normal range": "Poniżej normy",
    "Above the normal range": "Powyżej normy",
    "Danger: NFO risk": "Niebezpiecznie: ryzyko NFO",
    "Rebound: HRV spike while in debt": "Odbicie: skok HRV mimo długu",
    "Overreaching": "Przeciążenie",
    "Chronic creep: HRV trending low": "Pełzające zmęczenie: HRV nisko",
    "Fresh": "Świeżość",
    "Absorbing load": "Obciążenie przyswajane",
    "No data": "Brak danych",
}

ADVICE = {
    "hrv-guided": {
        "green": "Trening intensywny zgodnie z planem (maks. 2 mocne dni z rzędu).",
        "amber": "Lekko albo odpoczynek, aż 7-dniowe HRV wróci do normy (maks. 2 dni wolne z rzędu).",
    },
    "debt": {
        "red": "Odpoczynek albo luźna jazda — bez intensywności, dopóki dług nie spadnie.",
        "amber": "Trenuj, ale spokojnie: wytrzymałość, bez dokładania obciążenia.",
        "green": "Śmiało: kluczowe jednostki są OK.",
    },
}


def state(text: str, lang: str) -> str:
    return STATES.get(text, text) if lang == "pl" else text


def advice(model_key: str, signal: str, english: str, lang: str) -> str:
    return ADVICE.get(model_key, {}).get(signal, english) if lang == "pl" else english


def week(week: pd.DataFrame, previous: pd.DataFrame | None, lang: str = DEFAULT) -> str:
    t = _PL if lang == "pl" else _EN
    if "debt" in week:
        return _debt_week(week, previous, Params(), t)
    return _hrv_week(week, previous, t)


def _pl_days(n: int) -> str:
    if n == 1:
        return "1 dzień"
    return f"{n} dni"


_EN = {
    "days": lambda n: f"{n} day" if n == 1 else f"{n} days",
    "coverage": "Only {days} with data this week. ",
    "stayed": "The 7-day HRV average stayed around {last:.0f} ms; the normal range was {lo:.0f}–{hi:.0f} ms. ",
    "rose": "The 7-day HRV average rose from {first:.0f} to {last:.0f} ms; the normal range was {lo:.0f}–{hi:.0f} ms. ",
    "fell": "The 7-day HRV average fell from {first:.0f} to {last:.0f} ms; the normal range was {lo:.0f}–{hi:.0f} ms. ",
    "all_inside": "Every day was inside the range: the load was being absorbed and hard sessions were fine. ",
    "below": "Below the range on {days} — a sign of accumulated fatigue (or illness, stress, travel); "
    "the method calls for easy training or rest until the average comes back. ",
    "above": "Above the range on {days}. The method treats this as an easy day too: a sudden rise, "
    "especially after hard training, is often a rebound rather than extra freshness. ",
    "inside": "Inside the range on {days}. ",
    "cv_up": "Day-to-day variation rose (CV {before:.1f} → {now:.1f} %). ",
    "cv_warning": "Falling HRV with rising variation is the pattern Plews et al. (2012) saw before "
    "non-functional overreaching — worth watching. ",
    "cv_down": "Day-to-day variation settled (CV {before:.1f} → {now:.1f} %): a steadier system. ",
    "cv_same": "Day-to-day variation similar to the week before (CV {now:.1f} %). ",
    "readiness": "Readiness averaged {r:+.1f}: HRV and resting HR were {feel}. ",
    "better": "better than usual",
    "worse": "worse than usual",
    "usual": "around usual",
    "no_debt": "No fatigue debt all week. ",
    "debt": "Fatigue debt {direction}: {start:.0f} → {end:.0f} (peak {peak:.0f}). ",
    "built": "built up",
    "down": "came down",
    "steady": "held steady",
    "red": "{days} above {red:.0f} — deep enough to risk non-functional overreaching; only easy training until it drains. ",
    "amber": "{days} between {amber:.0f} and {red:.0f}: overreaching, load no longer absorbed day to day. ",
    "rebound": "HRV spiked while still in debt — read as a reaction to overload, not freshness. ",
    "creep": "The weekly HRV sat below normal although no single day looked bad (chronic creep). ",
    "recovered": "Full recovery on {day}: the debt cleared — a good point to start the next block. ",
    "absorbed": "Load was absorbed within capacity. ",
    "no_week": "No data last week.",
}

_PL = {
    "days": _pl_days,
    "coverage": "W tym tygodniu dane tylko za {days}. ",
    "stayed": "7-dniowa średnia HRV utrzymywała się około {last:.0f} ms; norma wynosiła {lo:.0f}–{hi:.0f} ms. ",
    "rose": "7-dniowa średnia HRV wzrosła z {first:.0f} do {last:.0f} ms; norma wynosiła {lo:.0f}–{hi:.0f} ms. ",
    "fell": "7-dniowa średnia HRV spadła z {first:.0f} do {last:.0f} ms; norma wynosiła {lo:.0f}–{hi:.0f} ms. ",
    "all_inside": "Każdy dzień w normie: obciążenie było przyswajane, mocne jednostki były OK. ",
    "below": "Poniżej normy przez {days} — oznaka nagromadzonego zmęczenia (albo choroby, stresu, podróży); "
    "metoda zaleca lekki trening lub odpoczynek, aż średnia wróci. ",
    "above": "Powyżej normy przez {days}. Metoda traktuje to też jako dzień lekki: nagły wzrost, "
    "zwłaszcza po ciężkim treningu, to często odbicie, a nie dodatkowa świeżość. ",
    "inside": "W normie przez {days}. ",
    "cv_up": "Zmienność z dnia na dzień wzrosła (CV {before:.1f} → {now:.1f} %). ",
    "cv_warning": "Spadające HRV przy rosnącej zmienności to wzorzec, który Plews i in. (2012) widzieli "
    "przed przeciążeniem niefunkcjonalnym — warto obserwować. ",
    "cv_down": "Zmienność z dnia na dzień się uspokoiła (CV {before:.1f} → {now:.1f} %): stabilniejszy organizm. ",
    "cv_same": "Zmienność z dnia na dzień podobna jak tydzień wcześniej (CV {now:.1f} %). ",
    "readiness": "Średnia gotowość {r:+.1f}: HRV i tętno spoczynkowe {feel}. ",
    "better": "lepsze niż zwykle",
    "worse": "gorsze niż zwykle",
    "usual": "na zwykłym poziomie",
    "no_debt": "Przez cały tydzień bez długu zmęczeniowego. ",
    "debt": "Dług zmęczeniowy {direction}: {start:.0f} → {end:.0f} (szczyt {peak:.0f}). ",
    "built": "narósł",
    "down": "zmalał",
    "steady": "bez większych zmian",
    "red": "{days} powyżej {red:.0f} — na tyle głęboko, że grozi przeciążeniem niefunkcjonalnym; "
    "tylko lekki trening, aż dług spadnie. ",
    "amber": "{days} między {amber:.0f} a {red:.0f}: przeciążenie, organizm nie nadąża z bieżącym obciążeniem. ",
    "rebound": "HRV skoczyło mimo długu — to raczej reakcja na przeciążenie niż świeżość. ",
    "creep": "Tygodniowe HRV było poniżej normy, choć żaden pojedynczy dzień nie wyglądał źle (pełzające zmęczenie). ",
    "recovered": "Pełna regeneracja {day}: dług się wyzerował — dobry moment na start kolejnego bloku. ",
    "absorbed": "Obciążenie mieściło się w możliwościach organizmu. ",
    "no_week": "Brak danych z zeszłego tygodnia.",
}


def no_data(lang: str) -> str:
    return (_PL if lang == "pl" else _EN)["no_week"]


def _coverage(week: pd.DataFrame, t: dict) -> str:
    n = len(week)
    return "" if n == 7 else t["coverage"].format(days=t["days"](n))


def _hrv_week(w: pd.DataFrame, previous: pd.DataFrame | None, t: dict) -> str:
    parts = [_coverage(w, t)]
    first, last = w["hrv_week"].iloc[0], w["hrv_week"].iloc[-1]
    lo, hi = w["hrv_low"].iloc[-1], w["hrv_high"].iloc[-1]
    key = "stayed" if abs(last - first) < 1.5 else ("rose" if last > first else "fell")
    parts.append(t[key].format(first=first, last=last, lo=lo, hi=hi))

    states = w["state"].value_counts()
    inside = int(states.get("Inside the normal range", 0))
    below = int(states.get("Below the normal range", 0))
    above = int(states.get("Above the normal range", 0))
    if below == 0 and above == 0:
        parts.append(t["all_inside"])
    else:
        if below:
            parts.append(t["below"].format(days=t["days"](below)))
        if above:
            parts.append(t["above"].format(days=t["days"](above)))
        if inside:
            parts.append(t["inside"].format(days=t["days"](inside)))

    cv = w["cv"].mean()
    if previous is not None and not previous.empty and pd.notna(cv) and pd.notna(previous["cv"].mean()):
        before = previous["cv"].mean()
        prev_hrv = previous["hrv_week"].iloc[-1]
        if cv > before * 1.3:
            parts.append(t["cv_up"].format(before=before, now=cv))
            if last < prev_hrv:
                parts.append(t["cv_warning"])
        elif cv < before / 1.3:
            parts.append(t["cv_down"].format(before=before, now=cv))
        else:
            parts.append(t["cv_same"].format(now=cv))
    return "".join(parts).strip()


def _debt_week(w: pd.DataFrame, previous: pd.DataFrame | None, p: Params, t: dict) -> str:
    parts = [_coverage(w, t)]
    readiness = w["readiness"].mean()
    feel = t["better"] if readiness >= 1 else (t["worse"] if readiness <= -1 else t["usual"])
    parts.append(t["readiness"].format(r=readiness, feel=feel))

    start = previous["debt"].iloc[-1] if previous is not None and not previous.empty else w["debt"].iloc[0]
    end, peak = w["debt"].iloc[-1], w["debt"].max()
    if peak < 1:
        parts.append(t["no_debt"])
    else:
        direction = t["built"] if end > start + 1 else (t["down"] if end < start - 1 else t["steady"])
        parts.append(t["debt"].format(direction=direction, start=start, end=end, peak=peak))

    red = int((w["debt"] >= p.red).sum())
    amber = int(((w["debt"] >= p.amber) & (w["debt"] < p.red)).sum())
    if red:
        parts.append(t["red"].format(days=t["days"](red).capitalize(), red=p.red))
    if amber:
        parts.append(t["amber"].format(days=t["days"](amber).capitalize(), amber=p.amber, red=p.red))
    states = w["state"].value_counts()
    warned = False
    if states.get("Rebound: HRV spike while in debt"):
        parts.append(t["rebound"])
        warned = True
    if states.get("Chronic creep: HRV trending low"):
        parts.append(t["creep"])
        warned = True
    if w["recovered"].any():
        day = w.index[w["recovered"]][-1]
        parts.append(t["recovered"].format(day=f"{day:%d.%m}"))
    elif peak < p.amber and not warned:
        parts.append(t["absorbed"])
    return "".join(parts).strip()
