"""Postgres-backed conversation index for the chat-history sidebar.

The row is the source of truth for the sidebar list + title; message bodies live
in Neo4j. Created after the users table (FK). Separate from corpus tables.
"""
from __future__ import annotations

from knowledge_engine.db import get_conn

_TITLE_MAX = 80

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    thread_id  TEXT PRIMARY KEY,
    username   TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversations_user_updated
    ON conversations (username, updated_at DESC);
"""


def ensure_conversations_table() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)


def touch_conversation(thread_id: str, username: str, first_question: str) -> None:
    """Lazily create the conversation (title from the first question) or bump it."""
    title = (first_question or "").strip()[:_TITLE_MAX] or "New conversation"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (thread_id, username, title) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()",
            (thread_id, username, title),
        )


def list_conversations(username: str) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT thread_id, title, updated_at FROM conversations "
            "WHERE username = %s ORDER BY updated_at DESC",
            (username,),
        )
        rows = cur.fetchall()
    return [{"thread_id": r[0], "title": r[1], "updated_at": r[2].isoformat()} for r in rows]


def get_owner(thread_id: str) -> str | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT username FROM conversations WHERE thread_id = %s", (thread_id,))
        row = cur.fetchone()
    return row[0] if row else None


def delete_conversation(thread_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE thread_id = %s", (thread_id,))
