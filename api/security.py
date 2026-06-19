"""Password hashing (bcrypt) and JWT tokens for account auth.

Pure functions — no DB, no FastAPI. Tokens require settings.auth_secret to be set.
"""
from __future__ import annotations

import datetime as dt

import bcrypt
import jwt

from knowledge_engine.config import settings

_ALG = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(username: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + dt.timedelta(hours=settings.auth_token_ttl_hours),
    }
    return jwt.encode(payload, settings.auth_secret, algorithm=_ALG)


def decode_token(token: str) -> str | None:
    """Return the username from a valid token, else None (invalid/expired/no secret)."""
    if not settings.auth_secret or not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[_ALG])
    except Exception:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None
