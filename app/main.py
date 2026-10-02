"""Web app: athletes, data upload/sync, the recovery dashboard and user management."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from jinja2 import pass_context
from markupsafe import Markup
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, db, describe, i18n, mailer, models
from .auth import Login
from .model import Params, params_dict
from .sources import fetch_intervals, fetch_intervals_name, fetch_intervals_profile, parse_export

app = FastAPI(title="Optimum Recovery")
templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates",
    context_processors=[lambda request: {"lang": i18n.language(request)}],
)


@pass_context
def _t(context, text: str, **values):
    return i18n.t(text, context.get("lang", i18n.DEFAULT), **values)


templates.env.globals["t"] = _t

AVATAR_COLOURS = ("#2f6fde", "#2e9e5b", "#8a63d2", "#d07a2b", "#c2477a", "#2a8f9a")


def _avatar(a, size: int = 36) -> Markup:
    """The athlete's intervals.icu photo, or their initials on a colour of their own."""
    style = f"width:{size}px;height:{size}px"
    if a["photo"]:
        return Markup('<img class="avatar" src="{}" alt="" style="{}" loading="lazy" referrerpolicy="no-referrer">').format(
            a["photo"], style
        )
    initials = "".join(part[0] for part in a["name"].split()[:2]).upper() or "?"
    colour = AVATAR_COLOURS[sum(map(ord, a["name"])) % len(AVATAR_COLOURS)]
    return Markup('<span class="avatar" style="{};background:{};font-size:{}px">{}</span>').format(
        style, colour, round(size * 0.4), initials
    )


templates.env.globals["avatar"] = _avatar
STATIC = Path(__file__).parent / "static"
# Icons are public: browsers fetch them before anyone signs in.
app.mount("/static", StaticFiles(directory=STATIC), name="static")

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
    mailer.start()


@app.exception_handler(auth.NotSignedIn)
async def not_signed_in(request: Request, exc):
    # Apps reading the API get the Basic auth challenge; people go to the sign-in page.
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401, headers={"WWW-Authenticate": "Basic"})
    target = request.url.path if request.method == "GET" else "/"
    return RedirectResponse(f"/login?next={target}" if target != "/" else "/login", status_code=303)


def _safe_next(target: str | None) -> str:
    """Only paths on this site, so the sign-in page can't send anyone elsewhere."""
    return target if target and target.startswith("/") and not target.startswith("//") else "/"


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None):
    return templates.TemplateResponse(request, "login.html", {"me": None, "next": _safe_next(next)})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    row = auth.check_password(username.strip().lower(), password)
    if row is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"me": None, "next": _safe_next(next), "username": username, "error": "Wrong login or password."},
            status_code=401,
        )
    return _signed_in(RedirectResponse(_safe_next(next), status_code=303), row)


def _signed_in(response, row):
    """Gives the browser a fresh session cookie for this login."""
    value, max_age = auth.session_cookie(row)
    response.set_cookie(
        auth.COOKIE, value, max_age=max_age, httponly=True, samesite="lax",
        secure=os.environ.get("PUBLIC_URL", "").startswith("https://"),
    )
    return response


@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "forgot.html", {"me": None, "configured": mailer.configured()})


@app.post("/forgot", response_class=HTMLResponse)
def forgot(request: Request, who: str = Form(...)):
    """
    Mails a link for setting a new password. The answer is the same whether or not
    the login exists, so the page can't be used to find out who has an account.
    """
    row = auth.find(who)
    email = row and db.email_of(row["username"])
    if email and mailer.configured():
        try:
            _mail_link("reset", row, email, request)
        except Exception as e:
            print(f"Password reset mail to {row['username']} failed: {e}", flush=True)
    return templates.TemplateResponse(
        request, "forgot.html", {"me": None, "configured": mailer.configured(), "sent": True}
    )


def _mail_link(kind: str, row, email: str, request: Request, inviter: str = "") -> None:
    """Mails a link for setting the password: a reset, or an invitation to a new account."""
    hours = auth.INVITE_HOURS if kind == "invite" else auth.RESET_HOURS
    base = mailer.public_url() or str(request.base_url).rstrip("/")
    link = f"{base}/reset?token={auth.reset_token(row, hours)}"
    mailer.send(email, *mailer.account_mail(kind, row["username"], link, hours, row["language"] or "pl", inviter))


@app.get("/reset", response_class=HTMLResponse)
def reset_page(request: Request, token: str = ""):
    row = auth.from_reset_token(token)
    return templates.TemplateResponse(
        request, "reset.html", {"me": None, "token": token, "row": row}, status_code=200 if row else 400
    )


@app.post("/reset", response_class=HTMLResponse)
def reset(
    request: Request, token: str = Form(""), password: str = Form(...), again: str = Form(...), email: str = Form("")
):
    row = auth.from_reset_token(token)
    lang = i18n.language(request)
    problem = None if row else i18n.t("This link has expired or was already used.", lang)
    problem = problem or auth.password_problem(password, again, lang)
    if problem:
        return templates.TemplateResponse(
            request, "reset.html", {"me": None, "token": token, "row": row, "error": problem}, status_code=400
        )
    db.update_login(row["username"], password_hash=auth.hash_password(password))
    if email.strip() and not row["email"]:
        db.set_mail(row["username"], email.strip(), True)
    return _signed_in(RedirectResponse("/", status_code=303), db.login(row["username"]))


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE)
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC / "favicon-32.png", media_type="image/png")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, tab: str | None = None, me: Login = Depends(auth.current)):
    """
    One group of athletes at a time, picked in the Athletes menu: admins see every
    coach's athletes, coaches their own and those shared with them. Your own
    profile is under My data; athletes go straight there.
    """
    if me.role == "athlete":
        own = db.own_profile(me.username)
        return RedirectResponse(f"/athletes/{own['id']}" if own else "/account", status_code=303)
    groups = _athlete_groups(me)
    current = tab if tab in groups else next(iter(groups), None)
    label, athletes = groups[current] if current else ("Athletes", [])
    return templates.TemplateResponse(
        request, "index.html", {"me": me, "label": label, "cards": [_card(me, a) for a in athletes]}
    )


def _athlete_groups(me: Login) -> dict[str, tuple[str, list]]:
    """The groups the Athletes menu offers, keyed by the ?tab= that shows them."""
    own = db.own_profile(me.username)
    groups: dict[str, tuple[str, list]] = {}
    if me.admin:
        names = _names()
        for a in db.all_athletes():
            # Your own profile is under My data, unless another coach looks after it.
            if not own or a["id"] != own["id"] or a["owner"] != me.username:
                groups.setdefault(a["owner"], (names.get(a["owner"], a["owner"]), []))[1].append(a)
        return dict(sorted(groups.items(), key=lambda g: g[1][0].lower()))
    groups["mine"] = ("Your athletes", [a for a in db.athletes(me.username) if not own or a["id"] != own["id"]])
    shared = db.shared_with(me.username)
    if shared:
        groups["shared"] = ("Shared with you", shared)
    return groups


def _athlete_menu(me: Login | None) -> list[tuple[str, str, int]]:
    if me is None or me.role == "athlete":
        return []
    return [(key, label, len(athletes)) for key, (label, athletes) in _athlete_groups(me).items()]


templates.env.globals["athlete_menu"] = _athlete_menu
# Pages name people by their full name, not their login.
templates.env.globals["person"] = lambda username: _names().get(username, username)


def _names() -> dict[str, str]:
    """Each login's full name from its own athlete profile, else the login itself."""
    return {u["username"]: u["profile"] or u["username"] for u in db.logins()}


def _card(me: Login, a) -> dict:
    _refresh_if_stale(a)
    data = db.metrics(a["id"])
    signals = [(m, _latest(m, m.analyse(data), me.language)) for m in models.MODELS.values()]
    shared_by = _names().get(a["owner"], a["owner"]) if a["owner"] != me.username and a["login"] != me.username and not me.admin else None
    return {"athlete": a, "signals": signals, "shared_by": shared_by}


@app.get("/athletes/new", response_class=HTMLResponse)
def new_athlete(request: Request, me: Login = Depends(auth.coach)):
    names = _names()
    coaches = [(u["username"], names[u["username"]]) for u in db.logins() if u["role"] == "coach"] if me.admin else []
    return templates.TemplateResponse(request, "add_athlete.html", {"me": me, "coaches": coaches})


@app.post("/athletes")
def create(
    me: Login = Depends(auth.coach),
    name: str = Form(""),
    intervals_id: str = Form(""),
    api_key: str = Form(""),
    coach: str = Form(""),
):
    # Admins add athletes straight to a coach; everyone else to themselves.
    owner = coach if me.admin and coach and db.login(coach) else me.username
    # Left empty, the name comes from the athlete's intervals.icu profile.
    name = name.strip() or (api_key.strip() and fetch_intervals_name(intervals_id.strip(), api_key.strip()))
    if not name:
        raise HTTPException(400, "Give the athlete a name, or an intervals.icu key whose profile has one")
    athlete_id = db.add_athlete(owner, name, intervals_id.strip(), api_key.strip())
    if api_key.strip():
        _sync(db.athlete_by_id(athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/upload")
async def upload(request: Request, athlete_id: int, me: Login = Depends(auth.current), file: UploadFile = File(...)):
    a = _manageable(me, athlete_id)
    try:
        frame = parse_export(await file.read())
    except Exception as e:  # a wrong file should say what is wrong with it, on the page
        problem = i18n.t("{file} could not be imported: {error}", me.language, file=file.filename, error=str(e) or type(e).__name__)
        return _athlete_page(request, me, a, None, error=problem, status=400, view="settings")
    db.save_metrics(a["id"], frame)
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/sync")
def sync(athlete_id: int, me: Login = Depends(auth.current)):
    _sync(_manageable(me, athlete_id))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/delete")
def delete(athlete_id: int, me: Login = Depends(auth.current)):
    a = _manageable(me, athlete_id, coach_only=True)
    db.delete_athlete(a["owner"], a["id"])
    return RedirectResponse("/", status_code=303)


@app.get("/athletes/{athlete_id}", response_class=HTMLResponse)
def dashboard(request: Request, athlete_id: int, model: str | None = None, me: Login = Depends(auth.current)):
    return _athlete_page(request, me, _visible(me, athlete_id), model)


@app.get("/athletes/{athlete_id}/settings", response_class=HTMLResponse)
def settings_page(request: Request, athlete_id: int, me: Login = Depends(auth.current)):
    """Data source, data, account, email and sharing, apart from the dashboard."""
    return _athlete_page(request, me, _manageable(me, athlete_id), None, view="settings")


@app.post("/athletes/{athlete_id}/settings")
def settings(
    athlete_id: int,
    me: Login = Depends(auth.current),
    name: str = Form(...),
    intervals_id: str = Form(""),
    api_key: str = Form(""),
    remove_key: str = Form(""),
):
    """The data source. The athlete may set it up themselves, or their coach does it for them."""
    a = _manageable(me, athlete_id)
    keep = not api_key.strip() and not remove_key
    db.update_athlete(a["id"], name.strip() or a["name"], intervals_id.strip(), api_key.strip(), keep_key=keep)
    _sync(db.athlete_by_id(a["id"]))
    return RedirectResponse(f"/athletes/{athlete_id}", status_code=303)


@app.post("/athletes/{athlete_id}/mail")
def athlete_mail(
    athlete_id: int,
    me: Login = Depends(auth.current),
    email: str = Form(""),
    language: str = Form("pl"),
    weekly: str = Form(""),
):
    """Monday email for an athlete without an account, set up by their coach."""
    a = _manageable(me, athlete_id, coach_only=True)
    db.set_athlete_mail(a["id"], email.strip(), language if language in describe.LANGUAGES else "pl", bool(weekly))
    return RedirectResponse(f"/athletes/{athlete_id}/settings", status_code=303)


@app.post("/athletes/{athlete_id}/mail/preview", response_class=HTMLResponse)
def athlete_mail_preview(athlete_id: int, me: Login = Depends(auth.current)):
    a = _manageable(me, athlete_id, coach_only=True)
    built = mailer.report_on([a], a["name"], language=a["language"] or "pl")
    return HTMLResponse(built[1] if built else "<p>No data.</p>")


@app.post("/athletes/{athlete_id}/account", response_class=HTMLResponse)
def account(
    request: Request,
    athlete_id: int,
    me: Login = Depends(auth.current),
    existing: str = Form(""),
    new_username: str = Form(""),
    email: str = Form(""),
):
    """
    Links the profile to a login, or creates one so the athlete can sign in and see
    their own data. With an email address the athlete gets an invitation to set
    their own password; without, the coach gets a generated one to pass on.
    """
    a = _manageable(me, athlete_id, coach_only=True)
    notice = None
    username = new_username.strip().lower()
    email = email.strip() or (a["email"] or "")
    if username:
        problem = auth.username_problem(username, me.language)
        if problem:
            return _athlete_page(request, me, a, None, error=problem, status=400, view="settings")
        # Nobody knows this password: the athlete sets their own through the sign-up link.
        db.add_login(username, auth.hash_password(auth.new_password()), "athlete")
        db.link_login(a["id"], username)
        db.set_language(username, a["language"] or "pl")
        if email:
            # The athlete's Monday email now goes to their login, in the profile's language.
            db.set_mail(username, email, bool(a["weekly_mail"]))
        notice = i18n.t("Created login {username} for {name}.", me.language, username=username, name=a["name"])
        if email and mailer.configured():
            try:
                _mail_link("invite", db.login(username), email, request, inviter=_names()[me.username])
                notice += " " + i18n.t("The sign-up link also went to {email}.", me.language, email=email)
            except Exception as e:
                notice += " " + i18n.t("Mailing the sign-up link to {email} failed: {error}", me.language, email=email, error=str(e))
        return _athlete_page(
            request, me, db.athlete_by_id(a["id"]), None, notice, link=_signup_link(username, request), view="settings"
        )
    elif existing == "-":
        db.link_login(a["id"], None)
    elif existing and db.login(existing):
        db.link_login(a["id"], existing)
    if notice is None:
        return RedirectResponse(f"/athletes/{athlete_id}/settings", status_code=303)
    return _athlete_page(request, me, db.athlete_by_id(a["id"]), None, notice, view="settings")


@app.post("/athletes/{athlete_id}/account/link", response_class=HTMLResponse)
def new_signup_link(request: Request, athlete_id: int, me: Login = Depends(auth.current)):
    """A fresh link for an athlete who lost theirs or forgot the password."""
    a = _manageable(me, athlete_id, coach_only=True)
    if not a["login"]:
        raise HTTPException(404)
    return _athlete_page(request, me, a, None, link=_signup_link(a["login"], request), view="settings")


def _signup_link(username: str, request: Request) -> str:
    base = mailer.public_url() or str(request.base_url).rstrip("/")
    return f"{base}/reset?token={auth.reset_token(db.login(username), auth.INVITE_HOURS)}"


def _athlete_page(
    request: Request, me: Login, a, model: str | None, notice: str | None = None, error: str | None = None,
    status: int = 200, link: str | None = None, view: str = "dashboard",
):
    is_coach = me.admin or a["owner"] == me.username
    is_self = a["login"] == me.username
    error = error or _refresh_if_stale(a)
    a = db.athlete_by_id(a["id"])
    chosen = models.get(model)
    data = db.metrics(a["id"])
    if not error and a["api_key"] and data["hrv"].dropna().empty:
        error = NO_HRV
    result = chosen.analyse(data)
    shares = db.shares(a["id"]) if is_coach else []
    logins = db.logins()
    return templates.TemplateResponse(
        request,
        "athlete_settings.html" if view == "settings" else "athlete.html",
        {
            "me": me,
            "athlete": a,
            "model": chosen,
            "models": models.MODELS.values(),
            "today": _latest(chosen, result, me.language),
            "series": _series(result),
            "weeks": _weeks(result, me.language),
            "params": Params(),
            "error": error,
            "notice": notice,
            "mine": is_coach,
            "configurable": is_coach or is_self,
            "is_self": is_self,
            "shares": shares,
            "coach_name": next((u["profile"] or u["username"] for u in logins if u["username"] == a["owner"]), a["owner"]),
            "share_candidates": [u["username"] for u in logins if u["username"] not in {a["owner"], *shares}],
            "coaches": [u["username"] for u in logins if u["role"] != "athlete"] if me.admin else [],
            "free_logins": [u["username"] for u in logins if u["profile_id"] is None],
            "languages": describe.LANGUAGES,
            "link": link,
            "view": view,
        },
        status_code=status,
    )


@app.get("/api/athletes/{athlete_id}/analysis")
def analysis(athlete_id: int, model: str | None = None, me: Login = Depends(auth.current)):
    """The whole analysis as JSON, for other apps (e.g. Fuel the Train)."""
    a = _visible(me, athlete_id)
    # Other apps read this without opening the page, so it has to bring the data up to date itself.
    if _refresh_if_stale(a) is None:
        a = db.athlete_by_id(athlete_id)
    chosen = models.get(model)
    result = chosen.analyse(db.metrics(a["id"]))
    body = {"athlete": a["name"], "model": chosen.key, "days": _series(result)}
    if chosen.key == "debt":
        body["params"] = params_dict()
    return JSONResponse(body)


@app.post("/athletes/{athlete_id}/share")
def share(athlete_id: int, me: Login = Depends(auth.current), username: str = Form(...)):
    a = _manageable(me, athlete_id, coach_only=True)
    if db.login(username) and username != a["owner"]:
        db.add_share(a["id"], username)
    return RedirectResponse(f"/athletes/{athlete_id}/settings", status_code=303)


@app.post("/athletes/{athlete_id}/unshare")
def unshare(athlete_id: int, me: Login = Depends(auth.current), username: str = Form(...)):
    db.remove_share(_manageable(me, athlete_id, coach_only=True)["id"], username)
    return RedirectResponse(f"/athletes/{athlete_id}/settings", status_code=303)


@app.post("/athletes/{athlete_id}/owner")
def change_owner(athlete_id: int, me: Login = Depends(auth.admin), owner: str = Form(...)):
    a = _manageable(me, athlete_id)
    row = db.login(owner)
    if row and row["role"] != "athlete":
        db.set_owner(a["id"], owner)
    return RedirectResponse(f"/athletes/{athlete_id}/settings", status_code=303)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, me: Login = Depends(auth.current), notice: str | None = None, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "account.html",
        {
            "me": me,
            "row": db.login(me.username),
            "configured": mailer.configured(),
            "languages": describe.LANGUAGES,
            "notice": notice,
            "error": error,
        },
    )


@app.post("/account", response_class=HTMLResponse)
def save_account(
    request: Request,
    me: Login = Depends(auth.current),
    email: str = Form(""),
    weekly: str = Form(""),
    language: str = Form("pl"),
):
    db.set_mail(me.username, email.strip(), bool(weekly))
    if language in describe.LANGUAGES:
        db.set_language(me.username, language)
    return RedirectResponse("/account", status_code=303)


@app.post("/account/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    me: Login = Depends(auth.current),
    current: str = Form(...),
    password: str = Form(...),
    again: str = Form(...),
):
    if auth.check_password(me.username, current) is None:
        return account_page(request, me, error=i18n.t("The current password is wrong.", me.language))
    problem = auth.password_problem(password, again, me.language)
    if problem:
        return account_page(request, me, error=problem)
    db.update_login(me.username, password_hash=auth.hash_password(password))
    # The new hash ends every other session; this browser gets a new cookie.
    return _signed_in(account_page(request, me, notice=i18n.t("Password changed.", me.language)), db.login(me.username))


@app.post("/account/username", response_class=HTMLResponse)
def change_username(request: Request, me: Login = Depends(auth.current), username: str = Form(...)):
    username = username.strip().lower()
    if username == me.username:
        return RedirectResponse("/account", status_code=303)
    problem = auth.username_problem(username, me.language)
    if problem:
        return account_page(request, me, error=problem)
    db.rename_login(me.username, username)
    return _signed_in(RedirectResponse("/account", status_code=303), db.login(username))


@app.get("/account/preview", response_class=HTMLResponse)
def preview_mail(me: Login = Depends(auth.current)):
    built = mailer.report(me.username, me.role, language=me.language)
    if built is None:
        return HTMLResponse("<p>No athletes to report on yet.</p>")
    return HTMLResponse(built[1])


@app.post("/account/test", response_class=HTMLResponse)
def test_mail(request: Request, me: Login = Depends(auth.current)):
    row = db.login(me.username)
    built = mailer.report(me.username, me.role, language=me.language)
    if not row["email"] or built is None or not mailer.configured():
        return account_page(request, me, error=i18n.t("Nothing to send: add an email address and athletes first.", me.language))
    try:
        mailer.send(row["email"], *built)
    except Exception as e:
        return account_page(request, me, error=i18n.t("Sending failed: {error}", me.language, error=str(e)))
    return account_page(request, me, notice=i18n.t("Sent to {email}.", me.language, email=row["email"]))


@app.post("/users/{username}/email")
def set_user_email(
    username: str, me: Login = Depends(auth.admin), email: str = Form(""), language: str = Form("")
):
    row = db.login(username)
    if row:
        db.set_mail(username, email.strip(), bool(row["weekly_mail"]))
        if language in describe.LANGUAGES:
            db.set_language(username, language)
    return RedirectResponse("/users", status_code=303)


@app.get("/users", response_class=HTMLResponse)
def users(request: Request, me: Login = Depends(auth.admin)):
    return _users_page(request, me, None)


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
    notice = i18n.t("Created {username} ({role}). Password: {password}", me.language,
                    username=username, role=i18n.t(role, me.language), password=password)
    return _users_page(request, me, notice)


@app.post("/users/{username}/reset", response_class=HTMLResponse)
def reset_password(request: Request, username: str, me: Login = Depends(auth.admin)):
    if not db.login(username):
        raise HTTPException(404)
    password = auth.new_password()
    db.update_login(username, password_hash=auth.hash_password(password))
    return _users_page(request, me, i18n.t("New password for {username}: {password}", me.language, username=username, password=password))


@app.post("/users/{username}/rename", response_class=HTMLResponse)
def rename_user(request: Request, username: str, me: Login = Depends(auth.admin), new: str = Form(...)):
    new = new.strip().lower()
    if not db.login(username):
        raise HTTPException(404)
    if new == username:
        return RedirectResponse("/users", status_code=303)
    problem = auth.username_problem(new, me.language)
    if problem:
        return _users_page(request, me, None, error=problem)
    db.rename_login(username, new)
    response = RedirectResponse("/users", status_code=303)
    return _signed_in(response, db.login(new)) if username == me.username else response


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


def _users_page(request: Request, me: Login, notice: str | None, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "me": me, "users": db.logins(), "roles": auth.ROLES, "notice": notice, "error": error,
            "languages": describe.LANGUAGES,
        },
    )


def _visible(me: Login, athlete_id: int):
    """Admins see everything; others the athletes they own or that were shared with them."""
    a = db.athlete_by_id(athlete_id) if me.admin else db.visible_athlete(me.username, athlete_id)
    if a is None:
        raise HTTPException(404)
    return a


def _manageable(me: Login, athlete_id: int, coach_only: bool = False):
    """
    The coach (owner) and admins may change everything. The athlete may look
    after their own data source, but not delete, share or move themselves.
    """
    a = db.athlete_by_id(athlete_id)
    allowed = a is not None and (
        me.admin or a["owner"] == me.username or (not coach_only and a["login"] == me.username)
    )
    if not allowed:
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
    profile = fetch_intervals_profile(a["intervals_id"] or "0", a["api_key"])
    if profile is not None:
        db.set_photo(a["id"], profile["photo"])
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


def _latest(m: models.Model, result: pd.DataFrame, lang: str = "en") -> dict | None:
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
        "advice": describe.advice(m.key, row["signal"], m.advice[row["signal"]], lang),
        "state": describe.state(row["state"], lang),
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


def _weeks(result: pd.DataFrame, lang: str = "en") -> list[dict]:
    """A Monday-to-Sunday summary, newest first — what a coach reads when planning the week."""
    if result.empty:
        return []
    known = result[result["signal"].notna()]
    rows = []
    previous = None
    for start, week in known.groupby(pd.Grouper(freq="W-MON", label="left", closed="left")):
        if week.empty:
            continue
        counts = week["signal"].value_counts()
        row = {
            "start": start.date().isoformat(),
            "description": describe.week(week, previous, lang),
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
        previous = week
    return rows[::-1]
