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
    """The coach's own athletes and those shared with them; an athlete's own profile if that is all they have."""
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


def report(username: str, role: str, today: datetime | None = None) -> tuple[str, str, str] | None:
    """Subject, HTML and plain text of the report, or None when there is nobody to report on."""
    from .main import _latest, _refresh_if_stale  # the web module holds the shared helpers

    today = today or datetime.now(TIMEZONE)
    start, end = last_week(today)
    athletes = athletes_for(username, role)
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
                    "today": _latest(m, result),
                    "summary": describe.week(week, before) if not week.empty else "No data last week.",
                    "counts": week["signal"].value_counts().to_dict() if not week.empty else {},
                }
            )
        entries.append({"athlete": a, "models": per_model, "url": f"{public_url()}/athletes/{a['id']}"})

    subject = f"Recovery — week of {start:%d.%m} to {end:%d.%m}"
    context = {"entries": entries, "start": start, "end": end, "username": username, "base": public_url()}
    html = templates.get_template("mail.html").render(context)
    text = templates.get_template("mail.txt").render(context)
    return subject, html, text


def send(to: str, subject: str, html: str, text: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    message["To"] = to
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
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
        built = report(row["username"], row["role"], now)
        if built is None:
            continue
        try:
            send(row["email"], *built)
        except Exception:  # one bad address must not stop the others
            log.exception("weekly mail to %s failed", row["username"])
            continue
        db.log_mail(row["username"], week)
        sent.append(row["username"])
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
