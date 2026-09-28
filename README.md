# Optimum Recovery

Proof of concept: daily HRV, resting heart rate and stress turned into a
readiness score, an accumulated fatigue debt and a green / amber / red signal,
so a coach can see when an athlete has fully recovered and when load stops
being absorbed.

Data comes from **intervals.icu** (API key, syncs by itself) or from a
**TrainingPeaks metrics export** (Account Settings → Export Data → Custom Metrics, upload the zip).

## Models

The athlete page has a model switch; each model lists its sources with DOI links.

**HRV-guided training — published** (`app/hrv_guided.py`), default. Implemented
from the methods of Javaloyes et al. 2020 (J Strength Cond Res 34(6):1511–1518,
[doi:10.1519/JSC.0000000000003337](https://doi.org/10.1519/JSC.0000000000003337)),
following Vesterinen et al. 2016 and Javaloyes et al. 2019:
7-day average of ln(RMSSD); normal range (SWC) = mean ± 0.5 SD, from a 2-week
baseline and then recalculated every 4 weeks from the previous 4 weeks; inside →
high intensity, outside (either way) → low intensity or rest. Plus the 7-day
coefficient of variation (Plews et al. 2012) as an informational line.

**Fatigue debt — experimental** (`app/model.py`). Own model: readiness from HRV,
RHR and stress against a 60-day baseline, and a debt that builds and clears.
Ideas from Plews 2013, Banister/Calvert 1976, Meeusen 2013, Le Meur 2013; the
formula, weights and thresholds are not from any paper and are not validated.

Not medical advice.

## Run locally

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
USERS=alina:secret DB_PATH=data/recovery.db .venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m pytest
```

## Deploy

On any Linux box with Docker (here an Oracle Cloud free E2.1.Micro):

```bash
git clone https://github.com/alinamylka/optimum-recovery.git && cd optimum-recovery
cp .env.example .env   # set DOMAIN and real passwords
docker compose up -d --build
```

Ports 80 and 443 must be open in the cloud security list and in the machine's
own firewall. Update: `git pull && docker compose up -d --build`.
The database lives in the `app-data` volume.
