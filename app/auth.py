"""Logins: who may sign in, with which role. Passwords are stored as salted PBKDF2 hashes."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import db

log = logging.getLogger("uvicorn.error")

ROLES = ("admin", "coach", "athlete")
ITERATIONS = 200_000
# Apps reading the API send Basic auth; people sign in on /login and get a session cookie.
security = HTTPBasic(auto_error=False)
COOKIE = "session"
SESSION_DAYS = 30
RESET_HOURS = 2
INVITE_HOURS = 7 * 24
USERNAME = re.compile(r"^[a-z0-9._-]{2,40}$")
MIN_PASSWORD = 8


class NotSignedIn(Exception):
    """Raised for a request without a valid login; the app sends people to /login."""


@dataclass(frozen=True)
class Login:
    username: str
    role: str
    profile_id: int | None = None  # the athlete profile that is this person, if any
    language: str = "pl"
    name: str = ""  # from their own athlete profile, if they have one

    @property
    def display(self) -> str:
        return self.name or self.username

    @property
    def admin(self) -> bool:
        return self.role == "admin"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2${ITERATIONS}${salt}${digest}"


# Basic auth sends the password with every request; hashing it each time would
# cost a fifth of a second per page on the small server.
@lru_cache(maxsize=256)
def _matches(stored: str, password: str) -> bool:
    _, iterations, salt, digest = stored.split("$")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return secrets.compare_digest(candidate, digest)


def new_password() -> str:
    return secrets.token_urlsafe(12)


def check_password(username: str, password: str):
    """The login row when the password is right, else None. The name may also be the email address."""
    row = find(username) if "@" in username else db.login(username)
    if row is None or not _matches(row["password_hash"], password):
        return None
    return row


@lru_cache(maxsize=1)
def _key() -> bytes:
    """Signs session cookies; kept beside the database so sessions survive a restart."""
    path = os.path.join(os.path.dirname(db.DB_PATH) or ".", "session.key")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return bytes.fromhex(f.read().strip())


def _sign(purpose: str, username: str, expires: int, password_hash: str) -> str:
    # The password hash is part of the message, so changing a password ends its sessions
    # and makes a reset link work only once.
    message = f"{purpose}|{username}|{expires}|{password_hash}".encode()
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


def _token(purpose: str, row, seconds: int) -> str:
    expires = int(time.time()) + seconds
    return f"{row['username']}|{expires}|{_sign(purpose, row['username'], expires, row['password_hash'])}"


def _check(purpose: str, value: str | None):
    """The login a token was made for, if it is genuine, unexpired and its password unchanged."""
    try:
        username, expires, signature = (value or "").rsplit("|", 2)
        expires = int(expires)
    except ValueError:
        if value:
            log.warning("%s token unreadable: %r", purpose, value[:40])
        return None
    row = db.login(username)
    if row is None or expires < time.time():
        log.warning("%s token for %s: %s", purpose, username, "unknown login" if row is None else "expired")
        return None
    if not hmac.compare_digest(signature, _sign(purpose, username, expires, row["password_hash"])):
        log.warning("%s token for %s: signature differs (password or key changed)", purpose, username)
        return None
    return row


def session_cookie(row) -> tuple[str, int]:
    """The cookie value for a signed-in login and its lifetime in seconds."""
    max_age = SESSION_DAYS * 86400
    return _token("session", row, max_age), max_age


def reset_token(row, hours: int = RESET_HOURS) -> str:
    return _token("reset", row, hours * 3600)


def from_reset_token(token: str | None):
    return _check("reset", token)


def find(name_or_email: str):
    """A login by its name or, with an @, by its email address."""
    value = name_or_email.strip()
    return db.login_by_email(value) if "@" in value else db.login(value.lower())


def password_problem(password: str, again: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"The password needs at least {MIN_PASSWORD} characters."
    if password != again:
        return "The two passwords differ."
    return None


def username_problem(username: str) -> str | None:
    if not USERNAME.match(username):
        return "A login is 2–40 lowercase letters, digits, dots, dashes or underscores."
    if db.login(username):
        return f"The login {username} is taken."
    return None


def current(request: Request, credentials: HTTPBasicCredentials | None = Depends(security)) -> Login:
    if credentials:
        row = check_password(credentials.username, credentials.password)
        if row is None:
            raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    else:
        row = _check("session", request.cookies.get(COOKIE))
        if row is None:
            raise NotSignedIn()
    profile = db.own_profile(row["username"])
    return Login(
        row["username"], row["role"], profile["id"] if profile else None, row["language"] or "pl",
        profile["name"] if profile else "",
    )


def coach(me: Login = Depends(current)) -> Login:
    """Admins and coaches; athletes only look after their own profile."""
    if me.role == "athlete":
        raise HTTPException(404)
    return me


def admin(me: Login = Depends(current)) -> Login:
    if not me.admin:
        raise HTTPException(404)
    return me


def seed_from_env() -> None:
    """
    The first start takes its logins from USERS="alina:secret,arek:secret";
    names in ADMINS are admins, everyone else a coach. After that the logins
    live in the database and are managed on the Users page.
    """
    if db.logins():
        return
    admins = {a.strip() for a in os.environ.get("ADMINS", "").split(",") if a.strip()}
    pairs = [p.split(":", 1) for p in os.environ.get("USERS", "").split(",") if ":" in p]
    for username, password in pairs:
        role = "admin" if username.strip() in admins else "coach"
        db.add_login(username.strip(), hash_password(password.strip()), role)
