"""
Plain-language summaries of a week (shown when a coach opens a row of the
weekly table, and in the Monday email), plus translations of the models'
state names and advice. Languages: "pl" and "en".
"""

from __future__ import annotations

import pandas as pd

LANGUAGES = {"pl": "Polski", "en": "English"}
DEFAULT = "pl"

STATES = {
    "Inside the normal range": "W normie",
    "Below the normal range": "Poniżej normy",
    "Above the normal range": "Powyżej normy",
    "Danger: NFO risk": "Niebezpiecznie: ryzyko NFO",
    "Rebound: HRV spike while in debt": "Odbicie: skok HRV mimo długu",
    "Functional overreaching": "Przeciążenie funkcjonalne",
    "Past the adaptation limit": "Ponad granicą adaptacji",
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
        return _debt_week(week, previous, t)
    return _hrv_week(week, previous, t)


def _pl_days(n: int) -> str:
    if n == 1:
        return "1 dzień"
    return f"{n} dni"


_EN = {
    "days": lambda n: f"{n} day" if n == 1 else f"{n} days",
    "coverage": "Only {days} with data this week. ",
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
    "red": "{days} above the danger threshold ({red:.0f}) — deep enough to risk non-functional overreaching, injury or "
    "illness; only easy training until it drains. ",
    "limit": "{days} past the adaptation limit ({limit:.0f}): the body was no longer adapting but paying for the load "
    "— ease off before it reaches {red:.0f}. ",
    "amber": "{days} of functional overreaching ({amber:.0f}–{limit:.0f}): a productive stimulus, as long as a full "
    "recovery follows. ",
    "capacity_up": "The personal thresholds went up (danger {before:.0f} → {after:.0f}): the athlete came back quickly "
    "from the last block — the body adapted and can take a little more. ",
    "capacity_down": "The personal thresholds went down (danger {before:.0f} → {after:.0f}): the debt stayed high too "
    "long or recovery dragged, so the load cost more than the body had — a lighter next block is advised. ",
    "rebound": "HRV spiked while still in debt — read as a reaction to overload, not freshness. ",
    "creep": "The weekly HRV sat below normal although no single day looked bad (chronic creep). ",
    "recovered": "Full recovery on {day}: the debt cleared — a good point to start the next block. ",
    "absorbed": "Load was absorbed within capacity. ",
    "no_week": "No data last week.",
    "v_calm": "A steady week: HRV inside the normal range every day — the load was being absorbed and hard sessions were fine. ",
    "v_tired": "A week of fatigue: HRV below the normal range on {days} ({when}). ",
    "v_high": "A week above the normal range: {days} ({when}). ",
    "v_dip": "Mostly inside the normal range, with a short dip below it ({when}). ",
    "v_spike": "Mostly inside the normal range, with a short rise above it ({when}). ",
    "v_mixed": "An unsettled week: HRV below the range on {below} and above it on {above}. ",
    "trend_stayed": "The 7-day average held around {last:.0f} ms (normal {lo:.0f}–{hi:.0f}). ",
    "trend_rose": "The 7-day average rose from {first:.0f} to {last:.0f} ms (normal {lo:.0f}–{hi:.0f}). ",
    "trend_fell": "The 7-day average fell from {first:.0f} to {last:.0f} ms (normal {lo:.0f}–{hi:.0f}). ",
    "above_small": "Only {over:.0f} ms over the top of the range: formally an easy day, in practice the edge of normal. ",
    "above_after_low": "HRV jumped {over:.0f} ms above the range right after a low spell — that is the typical "
    "rebound after overload (Le Meur 2013), not freshness: keep the intensity down until it settles. ",
    "above_big": "HRV went clearly above the range (up to {over:.0f} ms over). A sudden rise can be the body reacting "
    "to load; easy training is advised until the average is back inside. ",
    "below_small": "Only {under:.0f} ms under the range — easy days were enough. ",
    "below_big": "It fell well below (up to {under:.0f} ms under): accumulated fatigue, or illness, stress or travel. "
    "Easy training or rest until the average comes back. ",
    "below_still": "The week ends {under:.0f} ms below the range — start the next one easy. ",
    "weekdays": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

_PL = {
    "days": _pl_days,
    "coverage": "W tym tygodniu dane tylko za {days}. ",
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
    "red": "{days} powyżej progu niebezpiecznego ({red:.0f}) — na tyle głęboko, że grozi przeciążeniem "
    "niefunkcjonalnym, kontuzją albo chorobą; tylko lekki trening, aż dług spadnie. ",
    "limit": "{days} ponad granicą adaptacji ({limit:.0f}): organizm już się nie przystosowywał, tylko płacił za "
    "obciążenie — zaleca się odpuścić, zanim dojdzie do {red:.0f}. ",
    "amber": "{days} przeciążenia funkcjonalnego ({amber:.0f}–{limit:.0f}): to dobry bodziec, o ile po nim przyjdzie "
    "pełna regeneracja. ",
    "capacity_up": "Osobiste progi wzrosły (próg niebezpieczny {before:.0f} → {after:.0f}): zawodnik szybko wrócił "
    "po ostatnim bloku — organizm się zaadaptował i zniesie trochę więcej. ",
    "capacity_down": "Osobiste progi spadły (próg niebezpieczny {before:.0f} → {after:.0f}): dług za długo trzymał "
    "się wysoko albo regeneracja się ciągnęła, więc obciążenie kosztowało więcej, niż organizm miał — kolejny blok "
    "zaleca się lżejszy. ",
    "rebound": "HRV skoczyło mimo długu — to raczej reakcja na przeciążenie niż świeżość. ",
    "creep": "Tygodniowe HRV było poniżej normy, choć żaden pojedynczy dzień nie wyglądał źle (pełzające zmęczenie). ",
    "recovered": "Pełna regeneracja {day}: dług się wyzerował — dobry moment na start kolejnego bloku. ",
    "absorbed": "Obciążenie mieściło się w możliwościach organizmu. ",
    "no_week": "Brak danych z zeszłego tygodnia.",
    "v_calm": "Spokojny tydzień: HRV każdego dnia w normie — organizm przyswajał obciążenie, mocne jednostki były OK. ",
    "v_tired": "Tydzień zmęczenia: HRV poniżej normy przez {days} ({when}). ",
    "v_high": "Tydzień powyżej normy: {days} ({when}). ",
    "v_dip": "Przeważnie w normie, z krótkim spadkiem poniżej ({when}). ",
    "v_spike": "Przeważnie w normie, z krótkim wyjściem ponad normę ({when}). ",
    "v_mixed": "Niespokojny tydzień: HRV poniżej normy przez {below} i powyżej przez {above}. ",
    "trend_stayed": "7-dniowa średnia trzymała się około {last:.0f} ms (norma {lo:.0f}–{hi:.0f}). ",
    "trend_rose": "7-dniowa średnia wzrosła z {first:.0f} do {last:.0f} ms (norma {lo:.0f}–{hi:.0f}). ",
    "trend_fell": "7-dniowa średnia spadła z {first:.0f} do {last:.0f} ms (norma {lo:.0f}–{hi:.0f}). ",
    "above_small": "Tylko {over:.0f} ms ponad górną granicę: formalnie dzień lekki, w praktyce skraj normy. ",
    "above_after_low": "HRV skoczyło o {over:.0f} ms ponad normę zaraz po okresie spadku — to typowe odbicie po "
    "przeciążeniu (Le Meur 2013), a nie świeżość: trzymaj niską intensywność, aż się uspokoi. ",
    "above_big": "HRV wyraźnie powyżej normy (nawet o {over:.0f} ms). Nagły wzrost bywa reakcją organizmu na obciążenie; "
    "zaleca się lekki trening, aż średnia wróci do normy. ",
    "below_small": "Tylko {under:.0f} ms poniżej normy — lżejsze dni wystarczyły. ",
    "below_big": "Spadek był wyraźny (nawet o {under:.0f} ms): nagromadzone zmęczenie albo choroba, stres, podróż. "
    "Lekki trening lub odpoczynek, aż średnia wróci. ",
    "below_still": "Tydzień kończy się {under:.0f} ms poniżej normy — zacznij kolejny spokojnie. ",
    "weekdays": ("pon", "wt", "śr", "czw", "pt", "sob", "niedz"),
}


def no_data(lang: str) -> str:
    return (_PL if lang == "pl" else _EN)["no_week"]


def _coverage(week: pd.DataFrame, t: dict) -> str:
    n = len(week)
    return "" if n == 7 else t["coverage"].format(days=t["days"](n))


def _when(days: pd.DatetimeIndex, t: dict) -> str:
    """Weekdays as short names, runs joined with a dash: "Thu–Sat", "Mon, Wed"."""
    numbers = sorted({d.weekday() for d in days})
    runs, run = [], [numbers[0]]
    for n in numbers[1:]:
        if n == run[-1] + 1:
            run.append(n)
        else:
            runs.append(run)
            run = [n]
    runs.append(run)
    names = t["weekdays"]
    return ", ".join(names[r[0]] if len(r) == 1 else f"{names[r[0]]}–{names[r[-1]]}" for r in runs)


def _hrv_week(w: pd.DataFrame, previous: pd.DataFrame | None, t: dict) -> str:
    """The verdict first, then the trend, then what the days outside the range mean."""
    parts = [_coverage(w, t)]
    first, last = w["hrv_week"].iloc[0], w["hrv_week"].iloc[-1]
    lo, hi = w["hrv_low"].iloc[-1], w["hrv_high"].iloc[-1]
    above_days = w[w["state"] == "Above the normal range"]
    below_days = w[w["state"] == "Below the normal range"]
    above, below = len(above_days), len(below_days)

    if len(w) < 3:
        pass  # too few days to judge the week
    elif not above and not below:
        parts.append(t["v_calm"])
    elif below and above:
        parts.append(t["v_mixed"].format(below=t["days"](below), above=t["days"](above)))
    elif below >= 3:
        parts.append(t["v_tired"].format(days=t["days"](below), when=_when(below_days.index, t)))
    elif below:
        parts.append(t["v_dip"].format(when=_when(below_days.index, t)))
    elif above >= 3:
        parts.append(t["v_high"].format(days=t["days"](above), when=_when(above_days.index, t)))
    else:
        parts.append(t["v_spike"].format(when=_when(above_days.index, t)))

    trend = "trend_stayed" if abs(last - first) < 1.5 else ("trend_rose" if last > first else "trend_fell")
    parts.append(t[trend].format(first=first, last=last, lo=lo, hi=hi))

    if below:
        under = float((below_days["hrv_low"] - below_days["hrv_week"]).max())
        if w["state"].iloc[-1] == "Below the normal range":
            parts.append(t["below_still"].format(under=max(w["hrv_low"].iloc[-1] - last, 1)))
        else:
            parts.append(t["below_small" if under < 0.05 * lo else "below_big"].format(under=max(under, 1)))
    if above:
        over = float((above_days["hrv_week"] - above_days["hrv_high"]).max())
        # A jump right after days below the range is the classic rebound.
        before = w[w.index < above_days.index[0]]
        if previous is not None and not previous.empty:
            before = pd.concat([previous, before])
        low_before = (before.tail(5)["state"] == "Below the normal range").any()
        key = "above_after_low" if low_before else ("above_small" if over < 0.05 * hi else "above_big")
        parts.append(t[key].format(over=max(over, 1)))

    cv = w["cv"].mean()
    if previous is not None and not previous.empty and pd.notna(cv) and pd.notna(previous["cv"].mean()):
        before_cv = previous["cv"].mean()
        if cv > before_cv * 1.3:
            parts.append(t["cv_up"].format(before=before_cv, now=cv))
            if last < previous["hrv_week"].iloc[-1]:
                parts.append(t["cv_warning"])
        elif cv < before_cv / 1.3:
            parts.append(t["cv_down"].format(before=before_cv, now=cv))
    return "".join(parts).strip()


def _debt_week(w: pd.DataFrame, previous: pd.DataFrame | None, t: dict) -> str:
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

    # Each day against the personal lines as they stood that day; the text quotes the week's last ones.
    lines = {"amber": w["fo"].iloc[-1], "limit": w["limit"].iloc[-1], "red": w["danger"].iloc[-1]}
    zones = {
        "red": w["debt"] >= w["danger"],
        "limit": (w["debt"] >= w["limit"]) & (w["debt"] < w["danger"]),
        "amber": (w["debt"] >= w["fo"]) & (w["debt"] < w["limit"]),
    }
    for zone, days in zones.items():
        if days.any():
            parts.append(t[zone].format(days=t["days"](int(days.sum())).capitalize(), **lines))
    before = w["danger"].iloc[0]
    after = before + w["capacity_change"].sum()
    if abs(after - before) >= 0.5:
        parts.append(t["capacity_up" if after > before else "capacity_down"].format(before=before, after=after))
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
    elif not (w["debt"] >= w["fo"]).any() and not warned:
        parts.append(t["absorbed"])
    return "".join(parts).strip()
