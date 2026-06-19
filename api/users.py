"""Postgres-backed user account store (separate from the corpus tables, so the
ingestion pipeline never drops it)."""
from __future__ import annotations

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


def ensure_users_table() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)


def create_user(username: str, password_hash: str, occupation: str, postcode: str) -> bool:
    """Insert a new user. Returns False if the username already exists."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return False
        cur.execute(
            "INSERT INTO users (username, password_hash, occupation, postcode) "
            "VALUES (%s, %s, %s, %s)",
            (username, password_hash, occupation, postcode),
        )
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
