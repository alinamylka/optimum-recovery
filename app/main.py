"""Web app: athletes, data upload/sync, the recovery dashboard and user management."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth, db, models
from .auth import Login
from .model import Params, params_dict
from .sources import fetch_intervals, parse_trainingpeaks

app = FastAPI(title="Optimum Recovery")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# intervals.icu athletes are refreshed on view when their data is older than this.
STALE_AFTER = timedelta(hours=6)

NO_HRV = (
    "intervals.icu answers, but has no HRV for this athlete in the last 400 days. "
    "In intervals.icu → Settings → Connections, check that Garmin/Oura sync wellness data "
    "(HRV and resting HR), or upload a TrainingPeaks export below."
)


@app.on_event("startup")
def startup() -> None:
    db.init()
    auth.seed_from_env()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, me: Login = Depends(auth.current)):
    """Admins see every athlete grouped by coach; coaches their own and those shared with them."""
    athletes = db.all_athletes() if me.admin else [*db.athletes(me.username), *db.shared_with(me.username)]
    groups: dict[str, list[dict]] = {}
    for a in athletes:
        _refresh_if_stale(a)
        data = db.metrics(a["id"])
        signals = [(m, _latest(m, m.analyse(data))) for m in models.MODELS.values()]
        shared_by = a["owner"] if a["owner"] != me.username and not me.admin else None
        heading = a["owner"] if me.admin else ("Shared with you" if shared_by else "Your athletes")
        groups.setdefault(heading, []).append({"athlete": a, "signals": signals, "shared_by": shared_by})
    return templates.TemplateResponse(request, "index.html", {"me": me, "groups": groups})


@app.post("/athletes")
def create(
    me: Login = Depends(auth.current),
    name: str = Form(...),
    intervals_id: str = Form(""),
    api_key: str = Form(""),
):
    athlete_id = db.add_athlete(me.username, name.strip(), intervals_id.strip(), api_key.strip())
    if api_key.strip():
        _sync(db.athlete_by_id(athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/upload")
async def upload(athlete_id: int, me: Login = Depends(auth.current), file: UploadFile = File(...)):
    a = _manageable(me, athlete_id)
    try:
        frame = parse_trainingpeaks(await file.read())
    except Exception as e:  # a wrong file should say so, not return a 500
        raise HTTPException(400, f"Could not read this file as a TrainingPeaks metrics export: {e}")
    db.save_metrics(a["id"], frame)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/sync")
def sync(athlete_id: int, me: Login = Depends(auth.current)):
    _sync(_manageable(me, athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/delete")
def delete(athlete_id: int, me: Login = Depends(auth.current)):
    a = _manageable(me, athlete_id)
    db.delete_athlete(a["owner"], a["id"])
    return RedirectResponse("/", status_code=303)


@app.get("/athletes/{athlete_id}", response_class=HTMLResponse)
def dashboard(request: Request, athlete_id: int, model: str | None = None, me: Login = Depends(auth.current)):
    a = _visible(me, athlete_id)
    can_manage = me.admin or a["owner"] == me.username
    error = _refresh_if_stale(a)
    chosen = models.get(model)
    data = db.metrics(a["id"])
    if not error and a["api_key"] and data["hrv"].dropna().empty:
        error = NO_HRV
    result = chosen.analyse(data)
    shares = db.shares(a["id"]) if can_manage else []
    candidates = [u["username"] for u in db.logins() if u["username"] not in {a["owner"], *shares}]
    return templates.TemplateResponse(
        request,
        "athlete.html",
        {
            "me": me,
            "athlete": a,
            "model": chosen,
            "models": models.MODELS.values(),
            "today": _latest(chosen, result),
            "series": _series(result),
            "weeks": _weeks(result),
            "params": Params(),
            "error": error,
            "mine": can_manage,
            "shares": shares,
            "share_candidates": candidates if can_manage else [],
            "coaches": [u["username"] for u in db.logins()] if me.admin else [],
        },
    )


@app.get("/api/athletes/{athlete_id}/analysis")
def analysis(athlete_id: int, model: str | None = None, me: Login = Depends(auth.current)):
    """The whole analysis as JSON, for other apps (e.g. Fuel the Train)."""
    a = _visible(me, athlete_id)
    chosen = models.get(model)
    result = chosen.analyse(db.metrics(a["id"]))
    body = {"athlete": a["name"], "model": chosen.key, "days": _series(result)}
    if chosen.key == "debt":
        body["params"] = params_dict()
    return JSONResponse(body)


@app.post("/athletes/{athlete_id}/share")
def share(athlete_id: int, me: Login = Depends(auth.current), username: str = Form(...)):
    a = _manageable(me, athlete_id)
    if db.login(username) and username != a["owner"]:
        db.add_share(a["id"], username)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/unshare")
def unshare(athlete_id: int, me: Login = Depends(auth.current), username: str = Form(...)):
    db.remove_share(_manageable(me, athlete_id)["id"], username)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/owner")
def change_owner(athlete_id: int, me: Login = Depends(auth.admin), owner: str = Form(...)):
    a = _manageable(me, athlete_id)
    if db.login(owner):
        db.set_owner(a["id"], owner)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.get("/users", response_class=HTMLResponse)
def users(request: Request, me: Login = Depends(auth.admin)):
    return templates.TemplateResponse(
        request, "users.html", {"me": me, "users": db.logins(), "roles": auth.ROLES, "notice": None}
    )


@app.post("/users", response_class=HTMLResponse)
def add_user(
    request: Request,
    me: Login = Depends(auth.admin),
    username: str = Form(...),
    role: str = Form("coach"),
    password: str = Form(""),
):
    username = username.strip().lower()
    if not username or ":" in username or role not in auth.ROLES:
        raise HTTPException(400, "Invalid username or role")
    password = password.strip() or auth.new_password()
    try:
        db.add_login(username, auth.hash_password(password), role)
    except sqlite3.IntegrityError:
        raise HTTPException(400, f"User {username} already exists")
    return _users_page(request, me, f"Created {username} ({role}). Password: {password}")


@app.post("/users/{username}/reset", response_class=HTMLResponse)
def reset_password(request: Request, username: str, me: Login = Depends(auth.admin)):
    if not db.login(username):
        raise HTTPException(404)
    password = auth.new_password()
    db.update_login(username, password_hash=auth.hash_password(password))
    return _users_page(request, me, f"New password for {username}: {password}")


@app.post("/users/{username}/role")
def change_role(username: str, me: Login = Depends(auth.admin), role: str = Form(...)):
    # An admin can't demote themselves: there would be nobody left to undo it.
    if role in auth.ROLES and db.login(username) and username != me.username:
        db.update_login(username, role=role)
    return RedirectResponse("/users", status_code=303)


@app.post("/users/{username}/delete")
def delete_user(username: str, me: Login = Depends(auth.admin)):
    row = next((u for u in db.logins() if u["username"] == username), None)
    if row and username != me.username and row["athletes"] == 0:
        db.delete_login(username)
    return RedirectResponse("/users", status_code=303)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)


def _users_page(request: Request, me: Login, notice: str):
    return templates.TemplateResponse(
        request, "users.html", {"me": me, "users": db.logins(), "roles": auth.ROLES, "notice": notice}
    )


def _visible(me: Login, athlete_id: int):
    """Admins see everything; others the athletes they own or that were shared with them."""
    a = db.athlete_by_id(athlete_id) if me.admin else db.visible_athlete(me.username, athlete_id)
    if a is None:
        raise HTTPException(404)
    return a


def _manageable(me: Login, athlete_id: int):
    """Only the owner, or an admin, may change an athlete."""
    a = db.athlete_by_id(athlete_id) if me.admin else db.athlete(me.username, athlete_id)
    if a is None:
        raise HTTPException(404)
    return a


def _sync(a) -> str | None:
    if not a["api_key"]:
        return None
    try:
        frame = fetch_intervals(a["intervals_id"] or "0", a["api_key"])
    except httpx.HTTPError as e:
        return f"intervals.icu sync failed: {e}"
    db.save_metrics(a["id"], frame, synced=True)
    if frame["hrv"].dropna().empty:
        # A connection that works but brings no HRV looks exactly like an empty
        # athlete; say which it is, since the fix is in intervals.icu, not here.
        return NO_HRV
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
