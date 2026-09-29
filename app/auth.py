"""Logins: who may sign in, with which role. Passwords are stored as salted PBKDF2 hashes."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import db

ROLES = ("admin", "coach", "athlete")
ITERATIONS = 200_000
security = HTTPBasic()


@dataclass(frozen=True)
class Login:
    username: str
    role: str
    profile_id: int | None = None  # the athlete profile that is this person, if any

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


def current(credentials: HTTPBasicCredentials = Depends(security)) -> Login:
    row = db.login(credentials.username)
    if row is None or not _matches(row["password_hash"], credentials.password):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    profile = db.own_profile(row["username"])
    return Login(row["username"], row["role"], profile["id"] if profile else None)


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
