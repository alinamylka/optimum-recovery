# Optimum Recovery

Proof of concept: daily HRV, resting heart rate and stress turned into a
readiness score, an accumulated fatigue debt and a green / amber / red signal,
so a coach can see when an athlete has fully recovered and when load stops
being absorbed.

Data comes from **intervals.icu** (API key, syncs by itself) or from a
**TrainingPeaks metrics export** (Account Settings → Export Data → Custom Metrics, upload the zip).

## The model

`app/model.py`, built from the HRV-guided training literature:

| Piece | What it does | Source |
|---|---|---|
| Baseline | lnRMSSD, RHR and stress against the athlete's own rolling 60 days; normal range = baseline ± 0.5 SD | Plews et al. 2013, Vesterinen et al. 2016 |
| Readiness | −9…+9 from the 3-day average vs baseline (HRV 50 %, RHR 30 %, stress 20 %) | |
| Fatigue debt | grows on negative days, decays and drains on positive ones, drains slower when deep | Banister impulse-response; Meeusen et al. 2013 |
| Full recovery | debt back to zero after a real build-up | |
| Rebound | HRV spike while in debt counts as a warning, not freshness | Le Meur et al. 2013 |
| Chronic creep | weekly HRV below the normal range | Plews et al. 2012 |

Thresholds (`Params`) are starting points to calibrate on real athletes, not validated values.
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
