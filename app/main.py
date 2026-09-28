"""Web app: athletes, data upload/sync, and the recovery dashboard."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from . import db
from . import models
from .model import Params, params_dict
from .sources import fetch_intervals, parse_trainingpeaks

app = FastAPI(title="Optimum Recovery")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
security = HTTPBasic()

# intervals.icu athletes are refreshed on view when their data is older than this.
STALE_AFTER = timedelta(hours=6)


def _users() -> dict[str, str]:
    """USERS="alina:secret,arek:secret" — each user sees only their own athletes."""
    pairs = (p.split(":", 1) for p in os.environ.get("USERS", "").split(",") if ":" in p)
    return {u.strip(): pw.strip() for u, pw in pairs}


def user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected = _users().get(credentials.username)
    if expected is None or not secrets.compare_digest(credentials.password, expected):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.on_event("startup")
def startup() -> None:
    db.init()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, owner: str = Depends(user)):
    cards = []
    for a in db.athletes(owner):
        _refresh_if_stale(a)
        data = db.metrics(a["id"])
        signals = [(m, _latest(m, m.analyse(data))) for m in models.MODELS.values()]
        cards.append({"athlete": a, "signals": signals})
    return templates.TemplateResponse(request, "index.html", {"owner": owner, "cards": cards})


@app.post("/athletes")
def create(
    owner: str = Depends(user),
    name: str = Form(...),
    intervals_id: str = Form(""),
    api_key: str = Form(""),
):
    athlete_id = db.add_athlete(owner, name.strip(), intervals_id.strip(), api_key.strip())
    if api_key.strip():
        _sync(db.athlete(owner, athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/upload")
async def upload(athlete_id: int, owner: str = Depends(user), file: UploadFile = File(...)):
    a = _owned(owner, athlete_id)
    try:
        frame = parse_trainingpeaks(await file.read())
    except Exception as e:  # a wrong file should say so, not return a 500
        raise HTTPException(400, f"Could not read this file as a TrainingPeaks metrics export: {e}")
    db.save_metrics(a["id"], frame)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/sync")
def sync(athlete_id: int, owner: str = Depends(user)):
    _sync(_owned(owner, athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/delete")
def delete(athlete_id: int, owner: str = Depends(user)):
    db.delete_athlete(owner, _owned(owner, athlete_id)["id"])
    return RedirectResponse("/", status_code=303)


@app.get("/athletes/{athlete_id}", response_class=HTMLResponse)
def dashboard(request: Request, athlete_id: int, model: str | None = None, owner: str = Depends(user)):
    a = _owned(owner, athlete_id)
    error = _refresh_if_stale(a)
    chosen = models.get(model)
    result = chosen.analyse(db.metrics(a["id"]))
    return templates.TemplateResponse(
        request,
        "athlete.html",
        {
            "athlete": a,
            "model": chosen,
            "models": models.MODELS.values(),
            "today": _latest(chosen, result),
            "series": _series(result),
            "weeks": _weeks(result),
            "params": Params(),
            "error": error,
        },
    )


@app.get("/api/athletes/{athlete_id}/analysis")
def analysis(athlete_id: int, model: str | None = None, owner: str = Depends(user)):
    """The whole analysis as JSON, for other apps (e.g. Fuel the Train)."""
    a = _owned(owner, athlete_id)
    chosen = models.get(model)
    result = chosen.analyse(db.metrics(a["id"]))
    body = {"athlete": a["name"], "model": chosen.key, "days": _series(result)}
    if chosen.key == "debt":
        body["params"] = params_dict()
    return JSONResponse(body)


def _owned(owner: str, athlete_id: int):
    a = db.athlete(owner, athlete_id)
    if a is None:
        raise HTTPException(404)
    return a


def _sync(a) -> str | None:
    if not a["api_key"]:
        return None
    try:
        db.save_metrics(a["id"], fetch_intervals(a["intervals_id"] or "0", a["api_key"]), synced=True)
    except httpx.HTTPError as e:
        return f"intervals.icu sync failed: {e}"
    return None


def _refresh_if_stale(a) -> str | None:
    if not a["api_key"]:
        return None
    synced = a["synced_at"] and datetime.fromisoformat(a["synced_at"])
    if synced and datetime.now(timezone.utc) - synced < STALE_AFTER:
        return None
    return _sync(a)


def _latest(m: models.Model, result: pd.DataFrame) -> dict | None:
    if result.empty:
        return None
    known = result[result["signal"].notna()]
    if known.empty:
        return None
    row = known.iloc[-1]
    if m.key == "debt":
        stats = [
            ("Readiness", f"{int(row['readiness'])} / 9"),
            ("Fatigue debt", row["debt"]),
            ("Days to clear (easy days)", f"≈ {int(row['days_to_clear'])}" if row["days_to_clear"] else "—"),
            ("Last full recovery", _last_recovery(result) or "—"),
        ]
    else:
        stats = [
            ("HRV 7-day", f"{row['hrv_week']:.0f} ms"),
            ("Normal range", f"{row['hrv_low']:.0f}–{row['hrv_high']:.0f} ms"),
            ("CV 7-day", f"{row['cv']:.1f} %" if pd.notna(row["cv"]) else "—"),
        ]
    return {
        "date": known.index[-1].date().isoformat(),
        "signal": row["signal"],
        "advice": m.advice[row["signal"]],
        "state": row["state"],
        "stats": stats,
    }


def _last_recovery(result: pd.DataFrame) -> str | None:
    days = result.index[result["recovered"]]
    return days[-1].date().isoformat() if len(days) else None


def _series(result: pd.DataFrame) -> list[dict]:
    if result.empty:
        return []
    frame = result.copy()
    frame.insert(0, "date", frame.index.strftime("%Y-%m-%d"))
    frame = frame.astype(object).where(frame.notna(), None)
    return frame.to_dict(orient="records")


def _weeks(result: pd.DataFrame) -> list[dict]:
    """A Monday-to-Sunday summary, newest first — what a coach reads when planning the week."""
    if result.empty:
        return []
    known = result[result["signal"].notna()]
    rows = []
    for start, week in known.groupby(pd.Grouper(freq="W-MON", label="left", closed="left")):
        if week.empty:
            continue
        counts = week["signal"].value_counts()
        row = {
            "start": start.date().isoformat(),
            "green": int(counts.get("green", 0)),
            "amber": int(counts.get("amber", 0)),
            "red": int(counts.get("red", 0)),
        }
        if "debt" in week:
            row |= {
                "readiness": round(week["readiness"].mean(), 1),
                "debt_end": week["debt"].iloc[-1],
                "debt_max": week["debt"].max(),
                "recovered": bool(week["recovered"].any()),
            }
        else:
            row |= {"hrv_week": round(week["hrv_week"].iloc[-1]), "cv": round(week["cv"].mean(), 1)}
        rows.append(row)
    return rows[::-1]
