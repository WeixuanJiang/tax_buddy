# Accounts + Per-User Memory (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users register/log in (username, password, occupation, postcode); while logged in, persist their conversations to Neo4j and recall their history + preferences across sessions. Guests are unchanged.

**Architecture:** Credentials live in a Postgres `users` table (bcrypt); a JWT carries the username. Memory I/O stays at the FastAPI `/chat` boundary and all Neo4j/library calls stay in `agent/memory.py`. Identity comes from the token; logged-in turns read combined recall (prefs + past messages) and write the transcript + facts to Neo4j (scoped by `user_identifier=username`, `session_id=thread_id`).

**Tech Stack:** FastAPI, pydantic v2, bcrypt, PyJWT, Postgres (psycopg), `neo4j-agent-memory` v0.5.0 (qwen custom embedder), React/Vite, pytest.

## Global Constraints

- Builds on branch `agent-memory-trial` (the fail-soft `agent/memory.py`, qwen embedder, and `/chat` memory wiring already exist).
- Login is **optional**; guests keep today's behavior. `/ask` stays stateless/untouched.
- Identity is derived **only from the JWT** (`Authorization: Bearer <token>`), never from a request-body field. `ChatRequest` must NOT carry `user_id`.
- Memory remains **fail-soft**: reads return `""`, writes are no-ops, on disabled/error/timeout; never raises. All `neo4j-agent-memory` imports/calls live ONLY in `agent/memory.py`.
- Conversation scoping: short-term `session_id = thread_id`, every message tagged `user_identifier = username`; `generate_embedding=True` (qwen), `extract_entities=False`, `extract_relations=False`.
- **No insecure default:** `/auth/register` and `/auth/login` return HTTP 503 when `settings.auth_secret` is empty. Passwords are bcrypt-hashed; `AUTH_SECRET` lives in `.env` only (gitignored).
- The `users` table is created idempotently at API startup and is **separate** from the corpus tables (`ingest` must never drop it). It is NOT added to `ingestion/schema.sql`.
- Python 3.10+. Package imports as `knowledge_engine` from its PARENT dir; run pytest from the repo root (a root `conftest.py` already fixes `sys.path`). All `git` commands run from the repo root. Subagents cannot write into `.git/`.
- Commit message trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- `config.py` (modify) — `auth_secret`, `auth_token_ttl_hours`.
- `requirements.txt` (modify) — `bcrypt`, `PyJWT`.
- `.env.example` (modify) — document `AUTH_SECRET`, `AUTH_TOKEN_TTL_HOURS`.
- `api/security.py` (create) — bcrypt hashing + JWT (pure, no DB/FastAPI).
- `api/users.py` (create) — Postgres user store (`ensure_users_table`, `create_user`, `get_user`).
- `api/models.py` (modify) — `RegisterRequest`/`LoginRequest`/`AuthResponse`; remove `user_id` from `ChatRequest`.
- `agent/memory.py` (modify) — `register_user_profile`, `save_turn`, `recall_conversation`, `get_user_context`.
- `api/main.py` (modify) — `ensure_users_table` on startup; `/auth/register`, `/auth/login`; `current_username` dependency; rewire `/chat` + `/chat/stream` helpers.
- `web/src/api.js` (modify) — `register`/`login`/`logout`/`getAuth`; send `Authorization` header.
- `web/src/components/Auth.jsx` (create) — login/register form.
- `web/src/App.jsx` (modify) — auth state, sign-in/out UI.
- `eval/auth_demo.py` (create) — manual end-to-end check.
- Tests: `tests/test_security.py`, `tests/test_users.py`, `tests/test_models_auth.py`, `tests/test_memory_user.py`, `tests/test_api_auth.py`.

---

### Task 1: Auth config + dependencies

**Files:**
- Modify: `config.py`, `requirements.txt`, `.env.example`
- Test: `tests/test_security.py` (config asserts; extended in Task 2)

**Interfaces:**
- Produces: `settings.auth_secret: str` (default `""`), `settings.auth_token_ttl_hours: int` (default `24`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_security.py`:

```python
from knowledge_engine.config import Settings


def test_auth_defaults():
    s = Settings(_env_file=None)
    assert s.auth_secret == ""
    assert s.auth_token_ttl_hours == 24
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_security.py -v`
Expected: FAIL (`AttributeError`: no `auth_secret`).

- [ ] **Step 3: Add settings**

In `config.py`, inside `class Settings`, after the memory settings block (the `neo4j_password` field), add:

```python
    # --- Auth (Phase 1: accounts) ---
    auth_secret: str = Field(default="", alias="AUTH_SECRET")
    auth_token_ttl_hours: int = Field(default=24, alias="AUTH_TOKEN_TTL_HOURS")
```

- [ ] **Step 4: Add dependencies**

In `requirements.txt`, under the memory section, add:

```
bcrypt>=4.1
PyJWT>=2.8
```

Run: `pip install -r requirements.txt`
Expected: bcrypt installs (PyJWT already present).

- [ ] **Step 5: Document env vars**

In `.env.example`, append after the memory block:

```
# --- Auth (Phase 1: accounts) ---
# REQUIRED for register/login. Generate a random value, e.g.:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
AUTH_SECRET=
AUTH_TOKEN_TTL_HOURS=24
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_security.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add config.py requirements.txt .env.example tests/test_security.py
git commit -m "feat: add auth config (AUTH_SECRET) and bcrypt/PyJWT deps"
```

---

### Task 2: Password hashing + JWT (`api/security.py`)

**Files:**
- Create: `api/security.py`
- Test: `tests/test_security.py` (extend)

**Interfaces:**
- Consumes: `settings.auth_secret`, `settings.auth_token_ttl_hours` (Task 1).
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `create_token(username: str) -> str`, `decode_token(token: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_security.py`:

```python
import knowledge_engine.api.security as sec


def test_password_hash_roundtrip():
    h = sec.hash_password("hunter2pw")
    assert h != "hunter2pw"
    assert sec.verify_password("hunter2pw", h) is True
    assert sec.verify_password("wrong", h) is False


def test_token_roundtrip(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert sec.decode_token(tok) == "alice"


def test_token_rejects_tampered(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert sec.decode_token(tok + "x") is None


def test_decode_without_secret_returns_none(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "")
    assert sec.decode_token("anything") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_security.py -v`
Expected: FAIL (`ModuleNotFoundError: knowledge_engine.api.security`).

- [ ] **Step 3: Write the module**

Create `api/security.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_security.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add api/security.py tests/test_security.py
git commit -m "feat: bcrypt password hashing + JWT token helpers"
```

---

### Task 3: Postgres user store (`api/users.py`)

**Files:**
- Create: `api/users.py`
- Test: `tests/test_users.py`

**Interfaces:**
- Consumes: `knowledge_engine.db.get_conn` (existing; autocommit psycopg connection).
- Produces: `ensure_users_table() -> None`, `create_user(username, password_hash, occupation, postcode) -> bool` (False if username exists), `get_user(username) -> dict | None` (keys: username, password_hash, occupation, postcode).

- [ ] **Step 1: Write the failing test**

Create `tests/test_users.py` (integration — skips cleanly if Postgres is unavailable):

```python
import uuid

import pytest

import knowledge_engine.api.users as users
from knowledge_engine.db import get_conn


def _db_available() -> bool:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not available")


def test_create_get_and_duplicate():
    users.ensure_users_table()
    uname = f"u_{uuid.uuid4().hex[:10]}"
    try:
        assert users.create_user(uname, "hash1", "nurse", "3000") is True
        got = users.get_user(uname)
        assert got["username"] == uname
        assert got["occupation"] == "nurse"
        assert got["postcode"] == "3000"
        # duplicate username rejected
        assert users.create_user(uname, "hash2", "x", "2000") is False
        assert users.get_user("missing_" + uname) is None
    finally:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (uname,))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_users.py -v`
Expected: FAIL (`ModuleNotFoundError: knowledge_engine.api.users`) — or SKIP if no DB. If skipped, start Postgres (`docker compose up -d db`) so the task is actually verified.

- [ ] **Step 3: Write the module**

Create `api/users.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_users.py -v`
Expected: PASS (1 passed) with Postgres up.

- [ ] **Step 5: Commit**

```bash
git add api/users.py tests/test_users.py
git commit -m "feat: Postgres user account store (users table)"
```

---

### Task 4: Auth request/response models + drop ChatRequest.user_id

**Files:**
- Modify: `api/models.py`
- Modify: `tests/test_nodes_profile.py` (remove the two `user_id` assertions from the trial)
- Test: `tests/test_models_auth.py`

**Interfaces:**
- Produces: `RegisterRequest{username,password,occupation,postcode}`, `LoginRequest{username,password}`, `AuthResponse{token,username}`. `ChatRequest` no longer has `user_id`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_auth.py`:

```python
import pytest
from pydantic import ValidationError

from knowledge_engine.api.models import RegisterRequest, ChatRequest


def test_register_valid():
    r = RegisterRequest(username="alice_1", password="hunter2pw",
                         occupation="nurse", postcode="3000")
    assert r.username == "alice_1"


@pytest.mark.parametrize("bad", [
    {"username": "al", "password": "hunter2pw", "occupation": "n", "postcode": "3000"},      # too short
    {"username": "has space", "password": "hunter2pw", "occupation": "n", "postcode": "3000"},
    {"username": "alice", "password": "short", "occupation": "n", "postcode": "3000"},        # pw < 8
    {"username": "alice", "password": "hunter2pw", "occupation": "", "postcode": "3000"},      # empty occ
    {"username": "alice", "password": "hunter2pw", "occupation": "n", "postcode": "30a0"},     # bad postcode
    {"username": "alice", "password": "hunter2pw", "occupation": "n", "postcode": "30000"},    # 5 digits
])
def test_register_invalid(bad):
    with pytest.raises(ValidationError):
        RegisterRequest(**bad)


def test_chatrequest_has_no_user_id():
    assert "user_id" not in ChatRequest.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_auth.py -v`
Expected: FAIL (`ImportError`: cannot import `RegisterRequest`).

- [ ] **Step 3: Add the models and remove user_id**

In `api/models.py`, add at the top with the other imports:

```python
import re
from pydantic import field_validator
```

Add these classes (after `AskRequest`):

```python
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    occupation: str = Field(..., min_length=1)
    postcode: str = Field(...)

    @field_validator("username")
    @classmethod
    def _username_chars(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError("username may contain only letters, digits, underscore")
        return v

    @field_validator("postcode")
    @classmethod
    def _postcode_au(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("postcode must be exactly 4 digits")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    username: str
```

In the existing `ChatRequest`, DELETE the `user_id` field added by the trial (the three lines):

```python
    user_id: str | None = Field(
        default=None,
        description="Stable user id for cross-session memory. Defaults to "
                    "thread_id when omitted.")
```

- [ ] **Step 4: Remove the stale user_id tests**

In `tests/test_nodes_profile.py`, DELETE these two test functions (they assert the now-removed field):

```python
def test_chat_request_accepts_user_id():
    r = ChatRequest(question="hello there", thread_id="t1", user_id="u1")
    assert r.user_id == "u1"


def test_chat_request_user_id_optional():
    r = ChatRequest(question="hello there", thread_id="t1")
    assert r.user_id is None
```

(The `ChatRequest` import in that file may now be unused; if so, remove it from the import line to keep the suite warning-free. Leave the `Triage` tests intact.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_models_auth.py tests/test_nodes_profile.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add api/models.py tests/test_models_auth.py tests/test_nodes_profile.py
git commit -m "feat: auth request/response models; drop ChatRequest.user_id (token identity)"
```

---

### Task 5: Memory adapter — profile seed, transcript save, recall

**Files:**
- Modify: `agent/memory.py`
- Test: `tests/test_memory_user.py`

**Interfaces:**
- Consumes: existing `_submit`, `_WRITE_TIMEOUT`, `_get_client`, `get_user_profile`, `_format_prefs`, `settings`, `logger`.
- Produces: `register_user_profile(user_id, occupation, postcode) -> None`, `save_turn(user_id, thread_id, question, answer) -> None`, `recall_conversation(user_id, query) -> str`, `get_user_context(user_id, query) -> str`.

> **API note (verify at implementation):** `short_term.search_messages` is called with `metadata_filters={"user_identifier": user_id}`. If v0.5.0 rejects that filter key, `recall_conversation` will swallow the error and return `""` (fail-soft), so `get_user_context` degrades to preferences-only recall — acceptable. Confirm the key against `docs/superpowers/notes/agent-memory-api.md` / a quick `inspect`, and adjust only this call if needed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_user.py`:

```python
import knowledge_engine.agent.memory as mem


def test_user_writes_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.register_user_profile("u1", "nurse", "3000") is None
    assert mem.save_turn("u1", "t1", "q", "a") is None
    assert mem.recall_conversation("u1", "q") == ""
    assert mem.get_user_context("u1", "q") == ""


def test_user_calls_swallow_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.register_user_profile("u1", "nurse", "3000") is None
    assert mem.save_turn("u1", "t1", "q", "a") is None
    assert mem.recall_conversation("u1", "q") == ""
    assert mem.get_user_context("u1", "q") == ""


def test_get_user_context_combines(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    monkeypatch.setattr(mem, "get_user_profile", lambda uid: "- profile: nurse")
    monkeypatch.setattr(mem, "recall_conversation", lambda uid, q: "- user: hi")
    out = mem.get_user_context("u1", "q")
    assert "- profile: nurse" in out and "- user: hi" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_memory_user.py -v`
Expected: FAIL (`AttributeError`: `register_user_profile` not found).

- [ ] **Step 3: Append the functions**

At the END of `agent/memory.py`, add:

```python
def register_user_profile(user_id: str, occupation: str, postcode: str) -> None:
    """Seed durable profile preferences at registration (occupation, postcode)."""
    if not settings.memory_enabled or not user_id:
        return

    async def _run() -> None:
        client = await _get_client()
        for label, value in (("occupation", occupation), ("postcode", postcode)):
            if value and value.strip():
                await client.long_term.add_preference(
                    category="profile",
                    preference=f"{label}: {value.strip()}",
                    user_identifier=user_id,
                )

    try:
        _submit(_run(), timeout=_WRITE_TIMEOUT)
    except Exception:
        logger.warning("memory: register_user_profile failed", exc_info=True)


def save_turn(user_id: str, thread_id: str, question: str, answer: str) -> None:
    """Persist one Q/A turn to the user's conversation (Neo4j short-term)."""
    if not settings.memory_enabled or not user_id or not thread_id:
        return

    async def _run() -> None:
        client = await _get_client()
        for role, content in (("user", question), ("assistant", answer)):
            if content and content.strip():
                await client.short_term.add_message(
                    session_id=thread_id,
                    role=role,
                    content=content,
                    user_identifier=user_id,
                    extract_entities=False,
                    extract_relations=False,
                    generate_embedding=True,
                )

    try:
        _submit(_run(), timeout=_WRITE_TIMEOUT)
    except Exception:
        logger.warning("memory: save_turn failed (skipping persist)", exc_info=True)


def _format_messages(msgs: Any) -> str:
    lines = []
    for m in msgs or []:
        role = getattr(m, "role", "") or ""
        role = getattr(role, "value", role)  # MessageRole enum -> str
        content = getattr(m, "content", None) or str(m)
        text = str(content).strip().replace("\n", " ")[:200]
        if text:
            lines.append(f"- {role}: {text}")
    return "\n".join(lines).strip()


def recall_conversation(user_id: str, query: str) -> str:
    """Recall the user's relevant past messages across their conversations."""
    if not settings.memory_enabled or not user_id:
        return ""

    async def _run() -> str:
        client = await _get_client()
        msgs = await client.short_term.search_messages(
            query, metadata_filters={"user_identifier": user_id}, limit=5
        )
        return _format_messages(msgs)

    try:
        return _submit(_run()) or ""
    except Exception:
        logger.warning("memory: recall_conversation failed (returning empty)", exc_info=True)
        return ""


def get_user_context(user_id: str, query: str) -> str:
    """Combined recall injected by the API: durable preferences + relevant past messages."""
    parts = [p for p in (get_user_profile(user_id), recall_conversation(user_id, query)) if p]
    return "\n".join(parts).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_memory_user.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/memory.py tests/test_memory_user.py
git commit -m "feat: memory adapter — profile seed, transcript save, conversation recall"
```

---

### Task 6: Auth endpoints + token identity wiring (`api/main.py`)

**Files:**
- Modify: `api/main.py`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Consumes: `api/security.py`, `api/users.py`, `RegisterRequest`/`LoginRequest`/`AuthResponse`, `agent/memory` (`get_user_context`, `save_turn`, `remember`, `register_user_profile`).
- Produces: `current_username(authorization) -> str | None`; `_memory_read(username, query) -> str`; `_memory_write(username, thread_id, question, state) -> None`; routes `/auth/register`, `/auth/login`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_auth.py` (no DB / no lifespan — calls functions directly):

```python
import knowledge_engine.api.main as main
import knowledge_engine.api.security as sec


def test_current_username_guest():
    assert main.current_username(None) is None
    assert main.current_username("Bearer ") is None
    assert main.current_username("garbage") is None


def test_current_username_from_token(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert main.current_username(f"Bearer {tok}") == "alice"


def test_memory_read_guest_short_circuits(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("knowledge_engine.agent.memory.get_user_context",
                        lambda u, q: called.__setitem__("n", called["n"] + 1) or "x")
    assert main._memory_read(None, "q") == ""
    assert called["n"] == 0


def test_memory_write_guest_and_nonanswer(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.agent.memory.save_turn",
                        lambda *a, **k: calls.append("save"))
    monkeypatch.setattr("knowledge_engine.agent.memory.remember",
                        lambda *a, **k: calls.append("remember"))
    main._memory_write(None, "t1", "q", {"route": "answer", "answer": "a"})   # guest
    main._memory_write("alice", "t1", "q", {"route": "clarify"})              # not an answer
    assert calls == []


def test_memory_write_persists_on_answer(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.agent.memory.save_turn",
                        lambda u, t, q, a: calls.append(("save", u, t, q, a)))
    monkeypatch.setattr("knowledge_engine.agent.memory.remember",
                        lambda u, an: calls.append(("remember", u, an)))
    state = {"route": "answer", "answer": "hello", "analysis": {"income_year": 2026}}
    main._memory_write("alice", "t1", "q", state)
    assert ("save", "alice", "t1", "q", "hello") in calls
    assert ("remember", "alice", {"income_year": 2026}) in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: FAIL (`AttributeError`: `current_username` not found).

- [ ] **Step 3: Add imports and the auth/identity code**

In `api/main.py`, update imports:

```python
from fastapi import Depends, FastAPI, Header, HTTPException
```

and add:

```python
from knowledge_engine.api import security, users
from knowledge_engine.api.models import (
    AnswerResponse, AskRequest, AuthResponse, ChatRequest, LoginRequest, RegisterRequest,
)
```

(Replace the existing `from knowledge_engine.api.models import AnswerResponse, AskRequest, ChatRequest` line.)

In the `lifespan` startup (inside the `try` that sets up the chat graph, or its own try), ensure the users table exists:

```python
    try:
        users.ensure_users_table()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] users table init failed ({e}); auth will error until DB is up")
```

Replace the existing `_memory_read` / `_memory_write` helpers with:

```python
def current_username(authorization: str | None = Header(default=None)) -> str | None:
    """Resolve the logged-in username from a Bearer token; None for guests."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return security.decode_token(authorization.split(" ", 1)[1].strip())


def _memory_read(username: str | None, query: str) -> str:
    if not username:
        return ""
    from knowledge_engine.agent import memory
    return memory.get_user_context(username, query)


def _memory_write(username: str | None, thread_id: str, question: str, state: dict) -> None:
    if not username or state.get("route") != "answer":
        return
    from knowledge_engine.agent import memory
    memory.save_turn(username, thread_id, question, state.get("answer", ""))
    memory.remember(username, state.get("analysis"))
```

Add the auth routes (after `health`):

```python
@app.post("/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    if not settings.auth_secret:
        raise HTTPException(503, "auth not configured (AUTH_SECRET unset)")
    ok = users.create_user(req.username, security.hash_password(req.password),
                           req.occupation, req.postcode)
    if not ok:
        raise HTTPException(409, "username already taken")
    from knowledge_engine.agent import memory
    memory.register_user_profile(req.username, req.occupation, req.postcode)
    return AuthResponse(token=security.create_token(req.username), username=req.username)


@app.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    if not settings.auth_secret:
        raise HTTPException(503, "auth not configured (AUTH_SECRET unset)")
    u = users.get_user(req.username)
    if not u or not security.verify_password(req.password, u["password_hash"]):
        raise HTTPException(401, "invalid username or password")
    return AuthResponse(token=security.create_token(req.username), username=req.username)
```

- [ ] **Step 4: Rewire `/chat`**

Replace the `chat` function body with:

```python
@app.post("/chat", response_model=AnswerResponse)
def chat(req: ChatRequest, username: str | None = Depends(current_username)):
    cfg = {"configurable": {"thread_id": req.thread_id}}
    try:
        s = _state["chat_graph"].invoke({
            "messages": [HumanMessage(req.question)], "query": req.question,
            "reasoning": req.reasoning, "user_profile": _memory_read(username, req.question),
        }, cfg)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"agent error: {e}")
    _memory_write(username, req.thread_id, req.question, s)
    return _to_response(s)
```

- [ ] **Step 5: Rewire `/chat/stream`**

Change the `chat_stream` signature and the read/write lines:

```python
@app.post("/chat/stream")
def chat_stream(req: ChatRequest, username: str | None = Depends(current_username)):
```

Replace the input seed:

```python
    cfg = {"configurable": {"thread_id": req.thread_id}}
    inp = {"messages": [HumanMessage(req.question)], "query": req.question,
           "reasoning": req.reasoning, "user_profile": _memory_read(username, req.question)}
```

Replace the post-stream write (inside `gen()`):

```python
                elif mode == "values":
                    final = data
            _memory_write(username, req.thread_id, req.question, final or {})
            yield _sse("done", _to_response(final or {}).model_dump())
```

- [ ] **Step 6: Run tests + import sanity**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: PASS (5 passed).
Run (from the repo parent): `python -c "import knowledge_engine.api.main"`
Expected: imports cleanly.

- [ ] **Step 7: Commit**

```bash
git add api/main.py tests/test_api_auth.py
git commit -m "feat: /auth/register + /auth/login; derive chat identity from token"
```

---

### Task 7: Frontend — auth UI + send token

**Files:**
- Modify: `web/src/api.js`
- Create: `web/src/components/Auth.jsx`
- Modify: `web/src/App.jsx`

**Interfaces:**
- Consumes: `/auth/register`, `/auth/login` (Task 6).
- Produces: `register`, `login`, `logout`, `getAuth` exports; `Authorization` header on chat calls; an `Auth` form component.

- [ ] **Step 1: Add auth client + header in `web/src/api.js`**

After the `BASE` constant, add:

```javascript
const AUTH_KEY = "ke_auth";

export function getAuth() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)); } catch { return null; }
}
function setAuth(a) { localStorage.setItem(AUTH_KEY, JSON.stringify(a)); }
export function logout() { localStorage.removeItem(AUTH_KEY); }
function authHeader() {
  const a = getAuth();
  return a?.token ? { Authorization: `Bearer ${a.token}` } : {};
}

export async function register(username, password, occupation, postcode) {
  const a = await post("/auth/register", { username, password, occupation, postcode });
  setAuth(a);
  return a;
}
export async function login(username, password) {
  const a = await post("/auth/login", { username, password });
  setAuth(a);
  return a;
}
```

In `chatStream`, merge the auth header into the request headers:

```javascript
      headers: { "Content-Type": "application/json", ...authHeader() },
```

(Apply the same `...authHeader()` to the `post` helper's headers so `/chat` is authenticated too.)

- [ ] **Step 2: Create `web/src/components/Auth.jsx`**

```javascript
import { useState } from "react";
import { login, register } from "../api.js";

export default function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", occupation: "", postcode: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const a = mode === "login"
        ? await login(form.username, form.password)
        : await register(form.username, form.password, form.occupation, form.postcode);
      onAuth?.(a);
    } catch (e2) {
      setErr(e2.message || "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth" onSubmit={submit}>
      <div className="auth__tabs">
        <button type="button" disabled={mode === "login"} onClick={() => setMode("login")}>Log in</button>
        <button type="button" disabled={mode === "register"} onClick={() => setMode("register")}>Register</button>
      </div>
      <input placeholder="username" value={form.username} onChange={set("username")} autoComplete="username" />
      <input placeholder="password" type="password" value={form.password} onChange={set("password")} autoComplete="current-password" />
      {mode === "register" && (
        <>
          <input placeholder="occupation" value={form.occupation} onChange={set("occupation")} />
          <input placeholder="postcode (4 digits)" value={form.postcode} onChange={set("postcode")} />
        </>
      )}
      {err && <p className="auth__err">{err}</p>}
      <button type="submit" disabled={busy}>{busy ? "…" : mode === "login" ? "Log in" : "Create account"}</button>
    </form>
  );
}
```

- [ ] **Step 3: Wire auth state into `web/src/App.jsx`**

Add imports:

```javascript
import { chatStream, getAuth, logout } from "./api.js";
import Auth from "./components/Auth.jsx";
```

Add state near the other `useState` calls:

```javascript
  const [auth, setAuth] = useState(getAuth);
```

Add a sign-in/out control to the masthead area (render above `<main>`), so guests can chat but logging in is one click away:

```javascript
      <div className="authbar">
        {auth ? (
          <span>Signed in as <b>{auth.username}</b>{" "}
            <button onClick={() => { logout(); setAuth(null); }}>Log out</button>
          </span>
        ) : (
          <Auth onAuth={setAuth} />
        )}
      </div>
```

(Guests still see the full chat UI; the `Auth` form is just an inline panel. Keep it minimal — styling polish is not required for Phase 1.)

- [ ] **Step 4: Verify the frontend builds**

Run: `cd web && npm run build`
Expected: build succeeds (exit 0), no unresolved imports.

- [ ] **Step 5: Commit**

```bash
git add web/src/api.js web/src/components/Auth.jsx web/src/App.jsx
git commit -m "feat(web): login/register UI; send Authorization header on chat"
```

---

### Task 8: Manual end-to-end auth + memory check

**Files:**
- Create: `eval/auth_demo.py`

**Interfaces:**
- Consumes: `api/security`, `api/users`, `agent/memory`, `agent/graph.build_graph` — exercises register → seed → recall without HTTP.

> Manual integration check. Requires `AUTH_SECRET` set, `MEMORY_ENABLED=true`, Neo4j up, Postgres up + corpus ingested. Not a CI test.

- [ ] **Step 1: Write the script**

Create `eval/auth_demo.py`:

```python
"""Manual end-to-end: register a user, then show the agent recalls their
occupation in a fresh thread (no clarifying question).

Prereqs: AUTH_SECRET set, MEMORY_ENABLED=true, Neo4j + Postgres up, corpus ingested.
Run from the repo parent:  python -m knowledge_engine.eval.auth_demo
"""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage

from knowledge_engine.agent import memory
from knowledge_engine.agent.graph import build_graph
from knowledge_engine.api import security, users
from knowledge_engine.config import settings


def main() -> None:
    if not settings.memory_enabled or not settings.auth_secret:
        raise SystemExit("Set MEMORY_ENABLED=true and AUTH_SECRET, and start Neo4j/Postgres.")
    users.ensure_users_table()
    uname = f"demo_{uuid.uuid4().hex[:8]}"

    # Register (seeds occupation/postcode preferences in Neo4j)
    users.create_user(uname, security.hash_password("hunter2pw"), "electrician", "3000")
    memory.register_user_profile(uname, "electrician", "3000")
    print(f"registered {uname} (electrician, 3000)")

    graph = build_graph()
    q = "What work-related expenses can I claim?"
    profile = memory.get_user_context(uname, q)
    print(f"\nrecalled context:\n{profile or '(empty)'}")
    s = graph.invoke({"messages": [HumanMessage(q)], "query": q, "user_profile": profile})
    print("\nroute:", s.get("route"))
    print("(Expected: NOT 'clarify' — occupation recalled from the user's profile.)")
    memory.save_turn(uname, "thread-A", q, s.get("answer", ""))
    print("saved turn to conversation.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Validate it imports**

Run (from the repo parent): `python -c "import knowledge_engine.eval.auth_demo as d; print(hasattr(d,'main'))"`
Expected: prints `True`.

- [ ] **Step 3: Run the full unit suite**

Run (repo root): `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add eval/auth_demo.py
git commit -m "test: manual end-to-end auth + per-user memory recall demo"
```

---

## Self-Review

**Spec coverage:**
- Postgres users table (bcrypt), separate from corpus → Tasks 1–3. ✓
- Register/login endpoints + validation (username/password/occupation/4-digit postcode) → Tasks 4, 6. ✓
- Token identity, no body `user_id`, optional guest → Tasks 4, 6 (`current_username`, `Depends`). ✓
- Seed occupation/postcode prefs at registration → Tasks 5, 6. ✓
- Persist transcript (`session_id=thread_id`, `user_identifier=username`, embed on, extract off) → Task 5 (`save_turn`), Task 6 (wiring on `route==answer`). ✓
- Per-user recall (prefs + past messages) injected each turn → Task 5 (`get_user_context`), Task 6. ✓
- No insecure default (503 when `AUTH_SECRET` unset) → Task 6. ✓
- Fail-soft, library only in `agent/memory.py` → Task 5 + Global Constraints. ✓
- Frontend login/register + token header, guests unchanged → Task 7. ✓
- Live end-to-end check → Task 8. ✓

**Placeholder scan:** No TBD/TODO. The one verification (`search_messages` filter key) is pinned with a stated fail-soft fallback in Task 5.

**Type consistency:** `register_user_profile(user_id, occupation, postcode)`, `save_turn(user_id, thread_id, question, answer)`, `recall_conversation(user_id, query)`, `get_user_context(user_id, query)` defined in Task 5 and consumed unchanged in Task 6. `current_username(authorization)`, `_memory_read(username, query)`, `_memory_write(username, thread_id, question, state)` defined and consumed within Task 6. `RegisterRequest/LoginRequest/AuthResponse` defined in Task 4, used in Task 6. ✓
