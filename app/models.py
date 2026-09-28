"""The models a user can choose between, with where each one comes from."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import hrv_guided, model


@dataclass(frozen=True)
class Source:
    citation: str
    doi: str
    used_for: str

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}"


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    published: bool
    summary: str
    analyse: Callable[[pd.DataFrame], pd.DataFrame]
    advice: dict[str, str]
    sources: tuple[Source, ...]


JAVALOYES_2020 = Source(
    "Javaloyes A, Sarabia JM, Lamberts RP, Plews D, Moya-Ramon M. Training prescription guided by heart rate "
    "variability vs. block periodization in well-trained cyclists. J Strength Cond Res. 2020;34(6):1511-1518.",
    "10.1519/JSC.0000000000003337",
    "Decision rules: 7-day ln(RMSSD) average, SWC = mean ± 0.5 SD from a 2-week baseline, recalculated every 4 weeks; outside SWC → low intensity or rest.",
)
JAVALOYES_2019 = Source(
    "Javaloyes A, Sarabia JM, Lamberts RP, Moya-Ramon M. Training prescription guided by heart-rate variability "
    "in cycling. Int J Sports Physiol Perform. 2019;14(1):23-32.",
    "10.1123/ijspp.2018-0122",
    "The same approach in cyclists against a predefined plan.",
)
VESTERINEN_2016 = Source(
    "Vesterinen V, Nummela A, Heikura I, et al. Individual endurance training prescription with heart rate "
    "variability. Med Sci Sports Exerc. 2016;48(7):1347-1354.",
    "10.1249/MSS.0000000000000910",
    "Origin of the SWC-based daily decision.",
)
PLEWS_2012 = Source(
    "Plews DJ, Laursen PB, Kilding AE, Buchheit M. Heart rate variability in elite triathletes, is variation in "
    "variability the key to effective training? A case comparison. Eur J Appl Physiol. 2012;112(11):3729-3741.",
    "10.1007/s00421-012-2354-4",
    "Coefficient of variation of ln(RMSSD) as a warning sign.",
)
PLEWS_2013 = Source(
    "Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M. Training adaptation and heart rate variability in "
    "elite endurance athletes: opening the door to effective monitoring. Sports Med. 2013;43(9):773-781.",
    "10.1007/s40279-013-0071-8",
    "ln(RMSSD) against a rolling personal baseline and a ± 0.5 SD normal range.",
)
CALVERT_1976 = Source(
    "Calvert TW, Banister EW, Savage MV, Bach T. A systems model of the effects of training on physical "
    "performance. IEEE Trans Syst Man Cybern. 1976;SMC-6(2):94-102.",
    "10.1109/TSMC.1976.5409179",
    "Idea of fatigue that accumulates and decays exponentially.",
)
MEEUSEN_2013 = Source(
    "Meeusen R, Duclos M, Foster C, et al. Prevention, diagnosis, and treatment of the overtraining syndrome: "
    "joint consensus statement of the ECSS and the ACSM. Med Sci Sports Exerc. 2013;45(1):186-205.",
    "10.1249/MSS.0b013e318279a10a",
    "Definitions of functional and non-functional overreaching.",
)
LE_MEUR_2013 = Source(
    "Le Meur Y, Pichon A, Schaal K, et al. Evidence of parasympathetic hyperactivity in functionally overreached "
    "athletes. Med Sci Sports Exerc. 2013;45(11):2061-2071.",
    "10.1249/MSS.0b013e3182980125",
    "HRV can rise under overload: the 'rebound' warning.",
)

MODELS = {
    m.key: m
    for m in (
        Model(
            key="hrv-guided",
            name="HRV-guided training (Javaloyes 2020)",
            published=True,
            summary="Published method tested in cyclists: train hard when the 7-day HRV average is inside the "
            "athlete's normal range, easy or rest when it is outside — above or below.",
            analyse=hrv_guided.analyse,
            advice=hrv_guided.SIGNALS,
            sources=(JAVALOYES_2020, JAVALOYES_2019, VESTERINEN_2016, PLEWS_2012),
        ),
        Model(
            key="debt",
            name="Fatigue debt (experimental)",
            published=False,
            summary="Own model, not published or validated: readiness from HRV, resting HR and stress, and a "
            "fatigue debt that builds and clears. The ideas come from the papers below; the formula, weights "
            "and thresholds (12 / 25, taken from Arkadiusz's charts) do not.",
            analyse=model.analyse,
            advice=model.SIGNALS,
            sources=(PLEWS_2013, CALVERT_1976, MEEUSEN_2013, LE_MEUR_2013),
        ),
    )
}
DEFAULT = "hrv-guided"


def get(key: str | None) -> Model:
    return MODELS.get(key or DEFAULT, MODELS[DEFAULT])
