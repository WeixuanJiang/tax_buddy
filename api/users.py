"""Postgres-backed user account store (separate from the corpus tables, so the
ingestion pipeline never drops it)."""
from __future__ import annotations

import json

import psycopg

from knowledge_engine.db import get_conn

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    occupation    TEXT NOT NULL,
    postcode      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# AI-recommended starter questions, generated once per user and cached here so we
# don't pay an LLM call on every empty-state render. Added via migration so
# existing user rows pick up the column without a drop.
_MIGRATIONS = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suggestions JSONB",
)


def ensure_users_table() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)
        for stmt in _MIGRATIONS:
            cur.execute(stmt)


def create_user(username: str, password_hash: str, occupation: str, postcode: str) -> bool:
    """Insert a new user. Returns False if the username already exists.

    Let the PRIMARY KEY be the single source of truth: attempt the insert and
    treat a UniqueViolation as "already exists". This is race-safe (no
    check-then-insert window) and yields a clean 409 in the route.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, occupation, postcode) "
                "VALUES (%s, %s, %s, %s)",
                (username, password_hash, occupation, postcode),
            )
    except psycopg.errors.UniqueViolation:
        return False
    return True


def get_user(username: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT username, password_hash, occupation, postcode "
            "FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"username": row[0], "password_hash": row[1],
            "occupation": row[2], "postcode": row[3]}


def get_suggestions(username: str) -> list[str] | None:
    """Return the user's cached starter questions, or None if not generated yet."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT suggestions FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    # psycopg returns JSONB already decoded; be defensive about shape.
    value = row[0]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return list(value) if isinstance(value, list) else None


def set_suggestions(username: str, suggestions: list[str]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET suggestions = %s WHERE username = %s",
            (json.dumps(suggestions), username),
        )
