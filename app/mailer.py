"""
The Monday email: for every coach with an address, their athletes' signal for
today and a written summary of the week that just ended.

Sending goes through SMTP (e.g. a Gmail account with an app password), set in
the environment. Without it the report can still be previewed in the app.
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db, describe, models

log = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("MAIL_TIMEZONE", "Europe/Zurich"))
SEND_HOUR = int(os.environ.get("MAIL_HOUR", "6"))
CHECK_EVERY = 600  # seconds

templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"])
)


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"))


def public_url() -> str:
    return os.environ.get("PUBLIC_URL", "").rstrip("/")


def athletes_for(username: str, role: str) -> list:
    """
    Admins get every athlete; coaches their own and those shared with them;
    an athlete their own profile.
    """
    if role == "admin":
        return db.all_athletes()
    own = db.own_profile(username)
    seen, result = set(), []
    for a in [*db.athletes(username), *db.shared_with(username), *([own] if own else [])]:
        if a["id"] not in seen:
            seen.add(a["id"])
            result.append(a)
    return result


def last_week(today: datetime) -> tuple[pd.Timestamp, pd.Timestamp]:
    monday = pd.Timestamp(today.date()) - pd.Timedelta(days=today.weekday())
    return monday - pd.Timedelta(days=7), monday - pd.Timedelta(days=1)


def report(
    username: str, role: str, today: datetime | None = None, language: str = "pl"
) -> tuple[str, str, str] | None:
    """Subject, HTML and plain text of the report, or None when there is nobody to report on."""
    from .main import _latest, _refresh_if_stale  # the web module holds the shared helpers

    return report_on(athletes_for(username, role), username, today, language)


def report_on(athletes: list, recipient: str, today: datetime | None = None, language: str = "pl"):
    """The report for a given list of athletes — a coach's roster, or one athlete for themselves."""
    from .main import _latest, _refresh_if_stale

    username = recipient
    today = today or datetime.now(TIMEZONE)
    start, end = last_week(today)
    if not athletes:
        return None
    entries = []
    for a in athletes:
        _refresh_if_stale(a)
        data = db.metrics(a["id"])
        per_model = []
        for m in models.MODELS.values():
            result = m.analyse(data)
            known = result[result["signal"].notna()] if not result.empty else result
            week = known[(known.index >= start) & (known.index <= end)] if not known.empty else known
            before = known[(known.index >= start - pd.Timedelta(days=7)) & (known.index < start)] if not known.empty else None
            per_model.append(
                {
                    "model": m,
                    "today": _latest(m, result, language),
                    "summary": describe.week(week, before, language) if not week.empty else describe.no_data(language),
                    "counts": week["signal"].value_counts().to_dict() if not week.empty else {},
                }
            )
        entries.append({"athlete": a, "models": per_model, "url": f"{public_url()}/athletes/{a['id']}"})

    pl = language == "pl"
    subject = (
        f"Regeneracja — tydzień {start:%d.%m}–{end:%d.%m}" if pl else f"Recovery — week of {start:%d.%m} to {end:%d.%m}"
    )
    context = {
        "entries": entries, "start": start, "end": end, "username": username, "base": public_url(), "pl": pl,
    }
    html = templates.get_template("mail.html").render(context)
    text = templates.get_template("mail.txt").render(context)
    return subject, html, text


ACCOUNT_MAIL = {
    "invite": {
        "pl": ("Twoje konto w Optimum Recovery",
               "{inviter} założył(a) Ci konto w Optimum Recovery: codzienny sygnał regeneracji z Twoich danych HRV i tętna spoczynkowego.",
               "Twój login: {username}. Ustaw hasło tutaj (link działa {hours} h):", "Ustaw hasło"),
        "en": ("Your Optimum Recovery account",
               "{inviter} set up an Optimum Recovery account for you: a daily recovery signal from your HRV and resting heart rate.",
               "Your login: {username}. Set your password here (the link works for {hours} h):", "Set password"),
    },
    "reset": {
        "pl": ("Nowe hasło do Optimum Recovery",
               "Ktoś (pewnie Ty) poprosił o nowe hasło do konta {username}. Jeśli to nie Ty, zignoruj tę wiadomość.",
               "Ustaw nowe hasło tutaj (link działa {hours} h):", "Ustaw nowe hasło"),
        "en": ("New password for Optimum Recovery",
               "Someone (probably you) asked for a new password for {username}. If it wasn't you, ignore this email.",
               "Set a new password here (the link works for {hours} h):", "Set new password"),
    },
}


def account_mail(kind: str, username: str, link: str, hours: int, language: str = "pl", inviter: str = "") -> tuple[str, str, str]:
    """Subject, HTML and text of an invitation or a password reset, each with a link to set the password."""
    subject, intro, ask, button = (
        line.format(username=username, hours=hours, inviter=inviter)
        for line in ACCOUNT_MAIL[kind].get(language, ACCOUNT_MAIL[kind]["pl"])
    )
    text = f"{intro}\n\n{ask}\n{link}\n"
    html = templates.get_template("account_mail.html").render(intro=intro, ask=ask, button=button, link=link)
    return subject, html, text


def send(to: str, subject: str, html: str, text: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    message["To"] = to
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "465"))
    # 465 is TLS from the first byte (Gmail); 587 starts plain and upgrades (Oracle Email Delivery).
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
        smtp.starttls()
    with smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


def send_weekly(now: datetime | None = None) -> list[str]:
    """Sends this week's report to everyone who wants it and hasn't had it yet. Returns who got one."""
    now = now or datetime.now(TIMEZONE)
    week = now.strftime("%G-W%V")
    sent = []
    for row in db.logins():
        if not row["email"] or not row["weekly_mail"] or db.mail_sent(row["username"], week):
            continue
        built = report(row["username"], row["role"], now, row["language"] or "pl")
        if built is None:
            continue
        try:
            send(row["email"], *built)
        except Exception:  # one bad address must not stop the others
            log.exception("weekly mail to %s failed", row["username"])
            continue
        db.log_mail(row["username"], week)
        sent.append(row["username"])
    # Athletes without an account get their own report at the address their coach entered.
    for a in db.all_athletes():
        key = f"athlete:{a['id']}"
        if a["login"] or not a["email"] or not a["weekly_mail"] or db.mail_sent(key, week):
            continue
        built = report_on([a], a["name"], now, a["language"] or "pl")
        if built is None:
            continue
        try:
            send(a["email"], *built)
        except Exception:
            log.exception("weekly mail to athlete %s failed", a["id"])
            continue
        db.log_mail(key, week)
        sent.append(key)
    return sent


def _loop() -> None:
    while True:
        now = datetime.now(TIMEZONE)
        # Monday from SEND_HOUR on; the log makes a restart later that day harmless.
        if now.weekday() == 0 and now.hour >= SEND_HOUR:
            try:
                who = send_weekly(now)
                if who:
                    log.info("weekly mail sent to %s", ", ".join(who))
            except Exception:
                log.exception("weekly mail run failed")
        time.sleep(CHECK_EVERY)


def start() -> None:
    if configured():
        threading.Thread(target=_loop, name="weekly-mail", daemon=True).start()
