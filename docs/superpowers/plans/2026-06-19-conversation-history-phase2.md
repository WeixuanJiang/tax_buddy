# ChatGPT-style Conversation History (Phase 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give logged-in users a sidebar of their past conversations — list, resume, "New chat", and delete — backed by a Postgres `conversations` table (list/titles) and Neo4j (message bodies). Guests unchanged.

**Architecture:** A new `conversations` table is the source of truth for the sidebar; message bodies load from Neo4j short-term by `session_id = thread_id`. The `/chat` boundary lazily upserts the conversation row on each answered logged-in turn. New auth-required, ownership-checked endpoints list/load/delete; delete purges both stores. Frontend adds a sidebar shown only when logged in.

**Tech Stack:** FastAPI, pydantic v2, Postgres (psycopg), `neo4j-agent-memory` v0.5.0, React/Vite, pytest.

## Global Constraints

- Builds on Phase 1 (branch `agent-memory-trial`): JWT identity via `current_username`, `agent/memory.py` is the only library boundary and is fail-soft, messages are persisted with `session_id = thread_id` and `metadata={"user_identifier": username}`.
- Conversation identity = `thread_id`. Lazy create: row created on the first *answered* turn; `title = first_user_message[:80]`. No explicit create endpoint; "New chat" is client-side only.
- Every per-conversation endpoint is **auth-required and ownership-checked**: guest → 401, unknown thread → 404, not-owner → 403.
- Delete is thorough: remove the Postgres row AND `clear_session(thread_id)` in Neo4j.
- Memory calls stay **fail-soft** (return `[]`/no-op, never raise). Conversation `touch` must never break the answer path (wrapped at the call site).
- `conversations` table created at startup AFTER `users` (FK), and is NOT in `ingestion/schema.sql`.
- Python 3.10+. Package imports as `knowledge_engine` from its PARENT dir; run pytest from the repo root. `git` from the repo root. Subagents cannot write into `.git/` — reports go to `<repo>/.sdd/`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- `api/conversations.py` (create) — Postgres conversations store.
- `agent/memory.py` (modify) — `load_conversation`, `delete_conversation_messages`.
- `api/models.py` (modify) — `Message`, `ConversationSummary`, `ConversationDetail`.
- `api/main.py` (modify) — table init; `touch` in `_memory_write`; 3 endpoints.
- `web/src/api.js` (modify) — `listConversations`/`getConversation`/`deleteConversation`.
- `web/src/components/ConversationList.jsx` (create) — sidebar.
- `web/src/App.jsx` (modify) — sidebar wiring (list/new/resume/delete/refresh).
- `eval/history_demo.py` (create) — manual end-to-end.
- Tests: `tests/test_conversations.py`, `tests/test_memory_history.py`, `tests/test_models_conversations.py`, `tests/test_api_conversations.py`.

---

### Task 1: Conversations store (`api/conversations.py`)

**Files:**
- Create: `api/conversations.py`
- Test: `tests/test_conversations.py`

**Interfaces:**
- Consumes: `knowledge_engine.db.get_conn`.
- Produces: `ensure_conversations_table() -> None`; `touch_conversation(thread_id, username, first_question) -> None`; `list_conversations(username) -> list[dict]` (`{thread_id, title, updated_at}`, `updated_at` ISO string, newest first); `get_owner(thread_id) -> str | None`; `delete_conversation(thread_id) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversations.py` (integration — skips if Postgres down):

```python
import uuid

import pytest

import knowledge_engine.api.conversations as convo
import knowledge_engine.api.users as users
from knowledge_engine.api.security import hash_password
from knowledge_engine.db import get_conn


def _db() -> bool:
    try:
        with get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db(), reason="Postgres not available")


def test_touch_list_owner_delete():
    users.ensure_users_table()
    convo.ensure_conversations_table()
    uname = f"u_{uuid.uuid4().hex[:8]}"
    users.create_user(uname, hash_password("hunter2pw"), "nurse", "3000")
    t1, t2 = f"t_{uuid.uuid4().hex[:6]}", f"t_{uuid.uuid4().hex[:6]}"
    try:
        convo.touch_conversation(t1, uname, "How do I claim car expenses for work?")
        convo.touch_conversation(t2, uname, "Medicare levy threshold?")
        # second touch on t1 keeps title, bumps updated_at -> t1 becomes newest
        convo.touch_conversation(t1, uname, "this should NOT change the title")

        items = convo.list_conversations(uname)
        assert [i["thread_id"] for i in items] == [t1, t2]  # newest-first
        assert items[0]["title"] == "How do I claim car expenses for work?"

        assert convo.get_owner(t1) == uname
        assert convo.get_owner("missing") is None

        convo.delete_conversation(t1)
        assert convo.get_owner(t1) is None
        assert [i["thread_id"] for i in convo.list_conversations(uname)] == [t2]
    finally:
        with get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE username = %s", (uname,))
            cur.execute("DELETE FROM users WHERE username = %s", (uname,))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_conversations.py -v`
Expected: FAIL (`ModuleNotFoundError: knowledge_engine.api.conversations`). If it SKIPs, start Postgres (`docker compose up -d db`).

- [ ] **Step 3: Write the module**

Create `api/conversations.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_conversations.py -v`
Expected: PASS (1 passed) with Postgres up.

- [ ] **Step 5: Commit**

```bash
git add api/conversations.py tests/test_conversations.py
git commit -m "feat: Postgres conversations store for chat-history sidebar"
```

---

### Task 2: Memory adapter — load + delete conversation messages

**Files:**
- Modify: `agent/memory.py`
- Test: `tests/test_memory_history.py`

**Interfaces:**
- Consumes: existing `_submit`, `_WRITE_TIMEOUT`, `_get_client`, `settings`, `logger`.
- Produces: `load_conversation(thread_id) -> list[dict]` (`[{role, content}]` chronological; `[]` on disabled/error); `delete_conversation_messages(thread_id) -> None` (no-op on disabled/error).

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_history.py`:

```python
import knowledge_engine.agent.memory as mem


def test_history_disabled(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.load_conversation("t1") == []
    assert mem.delete_conversation_messages("t1") is None


def test_history_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.load_conversation("t1") == []
    assert mem.delete_conversation_messages("t1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_memory_history.py -v`
Expected: FAIL (`AttributeError: load_conversation`).

- [ ] **Step 3: Append the functions**

At the END of `agent/memory.py`, add:

```python
def load_conversation(thread_id: str) -> list[dict]:
    """Return a thread's messages [{role, content}] in order; [] on any issue."""
    if not settings.memory_enabled or not thread_id:
        return []

    async def _run() -> list[dict]:
        client = await _get_client()
        conv = await client.short_term.get_conversation(session_id=thread_id)
        msgs = getattr(conv, "messages", conv) or []
        out: list[dict] = []
        for m in msgs:
            role = getattr(m, "role", "") or ""
            role = getattr(role, "value", role)  # MessageRole enum -> str
            content = getattr(m, "content", None) or ""
            out.append({"role": str(role), "content": str(content)})
        return out

    try:
        return _submit(_run()) or []
    except Exception:
        logger.warning("memory: load_conversation failed (returning [])", exc_info=True)
        return []


def delete_conversation_messages(thread_id: str) -> None:
    """Purge a thread's messages from Neo4j short-term. No-op on any issue."""
    if not settings.memory_enabled or not thread_id:
        return

    async def _run() -> None:
        client = await _get_client()
        await client.short_term.clear_session(thread_id)

    try:
        _submit(_run(), timeout=_WRITE_TIMEOUT)
    except Exception:
        logger.warning("memory: delete_conversation_messages failed", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_memory_history.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/memory.py tests/test_memory_history.py
git commit -m "feat: memory adapter — load and delete a conversation's messages"
```

---

### Task 3: Response models

**Files:**
- Modify: `api/models.py`
- Test: `tests/test_models_conversations.py`

**Interfaces:**
- Produces: `Message{role: str, content: str}`, `ConversationSummary{thread_id: str, title: str, updated_at: str}`, `ConversationDetail{thread_id: str, messages: list[Message]}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_conversations.py`:

```python
from knowledge_engine.api.models import ConversationSummary, ConversationDetail, Message


def test_summary_and_detail():
    s = ConversationSummary(thread_id="t1", title="Car expenses", updated_at="2026-06-19T00:00:00+00:00")
    assert s.thread_id == "t1"
    d = ConversationDetail(thread_id="t1", messages=[Message(role="user", content="hi")])
    assert d.messages[0].role == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_conversations.py -v`
Expected: FAIL (`ImportError: cannot import name 'ConversationSummary'`).

- [ ] **Step 3: Add the models**

In `api/models.py`, add (after `AuthResponse`):

```python
class Message(BaseModel):
    role: str
    content: str


class ConversationSummary(BaseModel):
    thread_id: str
    title: str
    updated_at: str


class ConversationDetail(BaseModel):
    thread_id: str
    messages: list[Message] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_conversations.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add api/models.py tests/test_models_conversations.py
git commit -m "feat: conversation summary/detail response models"
```

---

### Task 4: API — table init, touch on answer, list/load/delete endpoints

**Files:**
- Modify: `api/main.py`
- Test: `tests/test_api_conversations.py`; also update `tests/test_api_auth.py` (the `_memory_write` tests must stub `conversations.touch_conversation`).

**Interfaces:**
- Consumes: `api/conversations.py`, `agent/memory.load_conversation`/`delete_conversation_messages`, `current_username`, models from Task 3.
- Produces: `GET /conversations`, `GET /conversations/{thread_id}`, `DELETE /conversations/{thread_id}`; `_memory_write` now also touches the conversation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_conversations.py` (handlers as plain functions; no DB/lifespan — stores monkeypatched):

```python
import pytest
from fastapi import HTTPException

import knowledge_engine.api.main as main


def test_list_requires_login():
    with pytest.raises(HTTPException) as e:
        main.list_conversations_route(username=None)
    assert e.value.status_code == 401


def test_get_unknown_is_404(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: None)
    with pytest.raises(HTTPException) as e:
        main.get_conversation_route("t1", username="alice")
    assert e.value.status_code == 404


def test_get_not_owner_is_403(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "bob")
    with pytest.raises(HTTPException) as e:
        main.get_conversation_route("t1", username="alice")
    assert e.value.status_code == 403


def test_get_owner_loads(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "alice")
    monkeypatch.setattr("knowledge_engine.agent.memory.load_conversation",
                        lambda t: [{"role": "user", "content": "hi"}])
    out = main.get_conversation_route("t1", username="alice")
    assert out["thread_id"] == "t1"
    assert out["messages"] == [{"role": "user", "content": "hi"}]


def test_delete_owner_purges_both(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "alice")
    monkeypatch.setattr("knowledge_engine.api.conversations.delete_conversation",
                        lambda t: calls.append(("row", t)))
    monkeypatch.setattr("knowledge_engine.agent.memory.delete_conversation_messages",
                        lambda t: calls.append(("msgs", t)))
    out = main.delete_conversation_route("t1", username="alice")
    assert out == {"deleted": "t1"}
    assert ("row", "t1") in calls and ("msgs", "t1") in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_conversations.py -v`
Expected: FAIL (`AttributeError: list_conversations_route`).

- [ ] **Step 3: Wire imports + table init + touch**

In `api/main.py`, extend the API imports:

```python
from knowledge_engine.api import conversations, security, users
from knowledge_engine.api.models import (
    AnswerResponse, AskRequest, AuthResponse, ChatRequest, ConversationDetail,
    ConversationSummary, LoginRequest, RegisterRequest,
)
```

In the lifespan startup, after the users-table init, add the conversations table:

```python
    try:
        users.ensure_users_table()
        conversations.ensure_conversations_table()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] account tables init failed ({e}); auth/history error until DB is up")
```

(Replace the existing `users.ensure_users_table()` try-block with the above.)

In `_memory_write`, add the conversation touch after the memory writes, wrapped so it can never break the answer path:

```python
def _memory_write(username: str | None, thread_id: str, question: str, state: dict) -> None:
    if not username or state.get("route") != "answer":
        return
    from knowledge_engine.agent import memory
    memory.save_turn(username, thread_id, question, state.get("answer", ""))
    memory.remember(username, state.get("analysis"))
    try:
        conversations.touch_conversation(thread_id, username, question)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] conversation touch failed ({e})")
```

- [ ] **Step 4: Add the endpoints**

In `api/main.py`, after the `login` route, add:

```python
@app.get("/conversations", response_model=list[ConversationSummary])
def list_conversations_route(username: str | None = Depends(current_username)):
    if not username:
        raise HTTPException(401, "login required")
    return conversations.list_conversations(username)


@app.get("/conversations/{thread_id}", response_model=ConversationDetail)
def get_conversation_route(thread_id: str, username: str | None = Depends(current_username)):
    if not username:
        raise HTTPException(401, "login required")
    owner = conversations.get_owner(thread_id)
    if owner is None:
        raise HTTPException(404, "conversation not found")
    if owner != username:
        raise HTTPException(403, "not your conversation")
    from knowledge_engine.agent import memory
    return {"thread_id": thread_id, "messages": memory.load_conversation(thread_id)}


@app.delete("/conversations/{thread_id}")
def delete_conversation_route(thread_id: str, username: str | None = Depends(current_username)):
    if not username:
        raise HTTPException(401, "login required")
    owner = conversations.get_owner(thread_id)
    if owner is None:
        raise HTTPException(404, "conversation not found")
    if owner != username:
        raise HTTPException(403, "not your conversation")
    conversations.delete_conversation(thread_id)
    from knowledge_engine.agent import memory
    memory.delete_conversation_messages(thread_id)
    return {"deleted": thread_id}
```

- [ ] **Step 5: Keep the `_memory_write` unit tests green**

`_memory_write` now calls `conversations.touch_conversation`, which hits Postgres. In `tests/test_api_auth.py`, the two `_memory_write` tests must stub it so they stay DB-free. Add this stub (monkeypatch) to BOTH `test_memory_write_guest_and_nonanswer` and `test_memory_write_persists_on_answer`, before they call `main._memory_write`:

```python
    monkeypatch.setattr("knowledge_engine.api.conversations.touch_conversation",
                        lambda *a, **k: None)
```

(Both tests already take `monkeypatch`. The guest/non-answer test still asserts no save/remember calls; the touch stub is just so the answer-path test doesn't reach a real DB.)

- [ ] **Step 6: Run tests + import sanity**

Run: `python -m pytest tests/test_api_conversations.py tests/test_api_auth.py -v`
Expected: PASS (all).
Run (repo parent): `python -c "import knowledge_engine.api.main"`
Expected: imports cleanly.

- [ ] **Step 7: Commit**

```bash
git add api/main.py tests/test_api_conversations.py tests/test_api_auth.py
git commit -m "feat: conversation list/load/delete endpoints; touch conversation on answered turn"
```

---

### Task 5: Frontend — sidebar (list / new / resume / delete)

**Files:**
- Modify: `web/src/api.js`
- Create: `web/src/components/ConversationList.jsx`
- Modify: `web/src/App.jsx`

**Interfaces:**
- Consumes: `GET/DELETE /conversations`, `GET /conversations/{id}` (Task 4).
- Produces: `listConversations()`, `getConversation(threadId)`, `deleteConversation(threadId)` exports; a `ConversationList` sidebar; App state for the list + resume/new/delete.

- [ ] **Step 1: Add the conversation client to `web/src/api.js`**

After the `login` function, add:

```javascript
async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeader() } });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export function listConversations() {
  return get("/conversations");
}
export function getConversation(threadId) {
  return get(`/conversations/${encodeURIComponent(threadId)}`);
}
export async function deleteConversation(threadId) {
  const res = await fetch(`${BASE}/conversations/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
    headers: { ...authHeader() },
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}
```

- [ ] **Step 2: Create `web/src/components/ConversationList.jsx`**

```javascript
export default function ConversationList({ items, activeId, onSelect, onNew, onDelete, busy }) {
  return (
    <aside className="history">
      <button className="history__new" onClick={onNew} disabled={busy}>+ New chat</button>
      <ul className="history__list">
        {items.map((c) => (
          <li
            key={c.thread_id}
            className={"history__item" + (c.thread_id === activeId ? " is-active" : "")}
          >
            <button className="history__open" onClick={() => onSelect(c.thread_id)} title={c.title}>
              {c.title}
            </button>
            <button
              className="history__del"
              onClick={() => onDelete(c.thread_id)}
              aria-label="Delete conversation"
            >×</button>
          </li>
        ))}
        {items.length === 0 && <li className="history__empty">No conversations yet</li>}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 3: Wire the sidebar into `web/src/App.jsx`**

Add imports:

```javascript
import {
  chatStream, getAuth, logout,
  listConversations, getConversation, deleteConversation,
} from "./api.js";
import ConversationList from "./components/ConversationList.jsx";
```

Add state (near the others):

```javascript
  const [conversations, setConversations] = useState([]);
```

Add a loader + load-on-login effect:

```javascript
  async function refreshConversations() {
    if (!getAuth()) { setConversations([]); return; }
    try { setConversations(await listConversations()); } catch { /* ignore */ }
  }
  useEffect(() => { refreshConversations(); }, [auth]);
```

After a send finishes, refresh the list so a new conversation/title appears. In `send`, change the line after the `await chatStream(...)` block:

```javascript
    setBusy(false);
    refreshConversations();
```

Add new-chat / resume / delete handlers:

```javascript
  function newChat() {
    setExchanges([]);
    setThreadId(newThreadId());
  }

  async function openConversation(tid) {
    try {
      const data = await getConversation(tid);
      const ex = [];
      const msgs = data.messages || [];
      for (let i = 0; i < msgs.length; i++) {
        if (msgs[i].role === "user") {
          const ans = msgs[i + 1] && msgs[i + 1].role === "assistant" ? msgs[i + 1].content : "";
          ex.push({ id: `${tid}-${i}`, question: msgs[i].content, status: "done",
                    answer: ans, citations: [], related_links: [], suggestions: [] });
        }
      }
      setThreadId(tid);
      setExchanges(ex);
    } catch { /* ignore */ }
  }

  async function removeConversation(tid) {
    try { await deleteConversation(tid); } catch { /* ignore */ }
    setConversations((prev) => prev.filter((c) => c.thread_id !== tid));
    if (tid === threadRef.current) newChat();
  }
```

Replace the masthead `onReset={reset}` wiring to use `newChat` (delete the old `reset` function), and render the sidebar only when logged in. Wrap the main area:

```javascript
  return (
    <div className="app">
      <Masthead
        taxYear={taxYear}
        onReset={newChat}
        canReset={!empty && !busy}
        thinking={thinking}
        onToggleThinking={() => setThinking((v) => !v)}
      />
      <div className="authbar">
        {auth ? (
          <span>Signed in as <b>{auth.username}</b>{" "}
            <button onClick={() => { logout(); setAuth(null); }}>Log out</button>
          </span>
        ) : (
          <Auth onAuth={setAuth} />
        )}
      </div>
      <div className="layout">
        {auth && (
          <ConversationList
            items={conversations}
            activeId={threadId}
            onSelect={openConversation}
            onNew={newChat}
            onDelete={removeConversation}
            busy={busy}
          />
        )}
        <main className="thread" id="thread">
          {empty ? (
            <EmptyState onPick={send} />
          ) : (
            <div className="thread__list">
              {exchanges.map((e) => (
                <Exchange key={e.id} exchange={e} onAsk={send} busy={busy} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </main>
      </div>
      <div className="dock">
        <Composer onSend={send} busy={busy} />
      </div>
    </div>
  );
```

- [ ] **Step 4: Verify the build**

Run: `cd web && npm run build`
Expected: build succeeds (exit 0), no unresolved imports.

- [ ] **Step 5: Commit**

```bash
git add web/src/api.js web/src/components/ConversationList.jsx web/src/App.jsx
git commit -m "feat(web): conversation history sidebar — list, new, resume, delete"
```

---

### Task 6: Manual end-to-end history check

**Files:**
- Create: `eval/history_demo.py`

**Interfaces:**
- Consumes: `api/users`, `api/security`, `api/conversations`, `agent/memory`.

> Manual integration check. Requires `AUTH_SECRET`, `MEMORY_ENABLED=true`, Neo4j + Postgres up. Not a CI test.

- [ ] **Step 1: Write the script**

Create `eval/history_demo.py`:

```python
"""Manual end-to-end: a user with two conversations — list, resume, delete.

Prereqs: AUTH_SECRET set, MEMORY_ENABLED=true, Neo4j + Postgres up.
Run from the repo parent:  python -m knowledge_engine.eval.history_demo
"""
from __future__ import annotations

import uuid

from knowledge_engine.agent import memory
from knowledge_engine.api import conversations, security, users
from knowledge_engine.config import settings


def main() -> None:
    if not settings.memory_enabled or not settings.auth_secret:
        raise SystemExit("Set MEMORY_ENABLED=true and AUTH_SECRET, and start Neo4j/Postgres.")
    users.ensure_users_table()
    conversations.ensure_conversations_table()
    uname = f"hist_{uuid.uuid4().hex[:8]}"
    users.create_user(uname, security.hash_password("hunter2pw"), "teacher", "3000")

    t1, t2 = f"thr_{uuid.uuid4().hex[:6]}", f"thr_{uuid.uuid4().hex[:6]}"
    memory.save_turn(uname, t1, "Can I claim a home office?", "Home office expenses may be claimable...")
    conversations.touch_conversation(t1, uname, "Can I claim a home office?")
    memory.save_turn(uname, t2, "What is the Medicare levy?", "The Medicare levy is 2%...")
    conversations.touch_conversation(t2, uname, "What is the Medicare levy?")

    print("conversations (newest first):")
    for c in conversations.list_conversations(uname):
        print(f"  {c['thread_id']}  {c['title']!r}  {c['updated_at']}")

    print(f"\nresume {t1}:")
    for m in memory.load_conversation(t1):
        print(f"  {m['role']}: {m['content'][:60]}")

    print(f"\ndelete {t1} ...")
    conversations.delete_conversation(t1)
    memory.delete_conversation_messages(t1)
    print("remaining:", [c["thread_id"] for c in conversations.list_conversations(uname)])
    print("messages after delete:", memory.load_conversation(t1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Validate it imports**

Run (repo parent): `python -c "import knowledge_engine.eval.history_demo as d; print(hasattr(d,'main'))"`
Expected: prints `True`.

- [ ] **Step 3: Run the full unit suite**

Run (repo root): `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add eval/history_demo.py
git commit -m "test: manual end-to-end conversation history demo"
```

---

## Self-Review

**Spec coverage:**
- `conversations` table (FK to users, cascade, index), source of truth for list/titles → Task 1. ✓
- Lazy create + title from first message, bump on subsequent turns → Task 1 (`touch_conversation` ON CONFLICT), Task 4 (called in `_memory_write` on `route==answer`). ✓
- Message bodies from Neo4j; delete purges both stores → Task 2 (`load_conversation`/`delete_conversation_messages`), Task 4 (delete endpoint). ✓
- Auth + ownership (401/404/403) on every per-conversation endpoint → Task 4. ✓
- Memory fail-soft; touch can't break answer path → Tasks 2, 4 (wrapped). ✓
- Table created after users, not in schema.sql → Task 1 + Task 4 lifespan order. ✓
- Frontend sidebar list/new/resume/delete, logged-in only, guests unchanged → Task 5. ✓
- Live end-to-end → Task 6. ✓

**Placeholder scan:** No TBD/TODO; every step has concrete code/commands.

**Type consistency:** `touch_conversation(thread_id, username, first_question)`, `list_conversations(username) -> [{thread_id,title,updated_at}]`, `get_owner(thread_id)`, `delete_conversation(thread_id)` (Task 1) consumed unchanged in Task 4. `load_conversation(thread_id) -> [{role,content}]`, `delete_conversation_messages(thread_id)` (Task 2) consumed in Task 4. Route fns `list_conversations_route(username)`, `get_conversation_route(thread_id, username)`, `delete_conversation_route(thread_id, username)` defined and tested in Task 4. Models `Message/ConversationSummary/ConversationDetail` (Task 3) used in Task 4. Frontend `listConversations/getConversation/deleteConversation` (Task 5) match the endpoints. ✓
