# Design: ChatGPT-style Conversation History (Phase 2)

**Date:** 2026-06-19
**Status:** Drafted; pending user review
**Builds on:** Phase 1 (accounts + per-user memory) on branch `agent-memory-trial`.
Phase 1 already persists each logged-in turn to Neo4j short-term with
`session_id = thread_id` and `user_identifier = username` (in message metadata),
and derives identity from the JWT.

## Goal

Give logged-in users a ChatGPT-style **conversation history**: a sidebar
listing their past conversations, click to **resume** one, a **New chat**
button, and **delete**. Guests are unchanged (single ephemeral chat, no sidebar).

## Decisions (confirmed with the user)

- **Lazy create + title:** a conversation row is created on the *first answered
  turn* of a thread; `title` = the first user message, truncated. No empty rows;
  "New chat" just opens a blank thread client-side. No explicit create endpoint.
- **Delete is thorough:** removes the Postgres row AND purges the thread's
  messages from Neo4j (`short_term.clear_session(thread_id)`).
- Conversation identity = `thread_id` (already the Neo4j `session_id` and the
  LangGraph checkpointer key from Phase 1). One id ties Postgres row, Neo4j
  messages, and checkpointer state together.

## Non-goals (Phase 2)

- Renaming conversations; search across conversations; pinning/folders.
- Pagination of the sidebar (a flat newest-first list is fine for the trial).
- Guest history (guests keep the ephemeral single chat).
- LLM-generated titles (first-message truncation only).

## Verified library facts (v0.5.0)

- `short_term.get_conversation(session_id, *, limit=None, ...) -> Conversation`
  with a `.messages` list — loads a thread's messages (scoped by session_id;
  confirmed during Phase 1 diagnostics).
- `short_term.clear_session(session_id) -> None` — deletes a session's messages.

## Architecture

A new Postgres `conversations` table is the source of truth for the sidebar
**list + titles**; message **bodies** come from Neo4j. All endpoints are
auth-required and ownership-checked. The `/chat` boundary upserts the
conversation row on each answered logged-in turn (lazy create + `updated_at`
bump). Frontend gains a sidebar; guests never see it.

```
logged-in answered turn (route==answer):
   save_turn + remember (Phase 1)  AND  conversations.touch(thread_id, username, question)
GET    /conversations            -> list (Postgres), newest first
GET    /conversations/{thread}   -> messages (Neo4j), after owner check
DELETE /conversations/{thread}   -> delete row (Postgres) + clear_session (Neo4j)
```

## Components

### 1. `api/conversations.py` (new — Postgres store)
- `ensure_conversations_table()` — `CREATE TABLE IF NOT EXISTS conversations
  (thread_id TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username)
  ON DELETE CASCADE, title TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
  DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())` plus an index
  on `(username, updated_at DESC)`. Created at startup **after**
  `ensure_users_table()` (FK dependency).
- `touch_conversation(thread_id, username, first_question)` — upsert: insert with
  `title = first_question[:80]` if absent (race-safe via `ON CONFLICT
  (thread_id) DO UPDATE SET updated_at = now()`), so the first turn sets the
  title and every turn bumps `updated_at`.
- `list_conversations(username) -> list[dict]` — `{thread_id, title, updated_at}`
  ordered by `updated_at DESC`.
- `get_owner(thread_id) -> str | None` — for ownership checks.
- `delete_conversation(thread_id) -> None` — delete the row.

### 2. `agent/memory.py` (extend — fail-soft, library-boundary)
- `load_conversation(thread_id) -> list[dict]` — `get_conversation(session_id=
  thread_id)` → `[{role, content}]` in chronological order; `[]` on
  disabled/error.
- `delete_conversation_messages(thread_id) -> None` — `clear_session(thread_id)`;
  no-op on disabled/error.

### 3. `api/models.py` (extend)
- `ConversationSummary { thread_id, title, updated_at }`.
- `ConversationDetail { thread_id, messages: list[Message] }` where
  `Message { role, content }`.

### 4. `api/main.py` (extend)
- Lifespan: `conversations.ensure_conversations_table()` after users table.
- `_memory_write` (logged-in, `route == "answer"`) also calls
  `conversations.touch_conversation(thread_id, username, question)`.
- `GET /conversations` (Depends `current_username`; 401 if guest) →
  `list_conversations`.
- `GET /conversations/{thread_id}` → 401 guest; 404 if `get_owner` is None;
  403 if owner != caller; else `load_conversation`.
- `DELETE /conversations/{thread_id}` → same ownership checks; then
  `delete_conversation` + `memory.delete_conversation_messages`.

### 5. Frontend (`web/`)
- `api.js`: `listConversations()`, `getConversation(threadId)`,
  `deleteConversation(threadId)` (all send the auth header).
- `components/ConversationList.jsx` — sidebar: "New chat" button + newest-first
  list; active item highlighted; per-item delete. Rendered only when logged in.
- `App.jsx`: hold `conversations` state; on login, load the list. "New chat" →
  new `thread_id` + clear the view. Clicking an item → set `threadId` and load
  its messages into the exchange view (map consecutive user→assistant messages
  into `{question, answer, status:"done"}` exchanges). After a send completes for
  a logged-in user, refresh the list (new conversation/title appears). Delete →
  drop from list; if it was active, start a New chat.

## Error handling & failure modes

- Memory calls (`load_conversation`, `delete_conversation_messages`) stay
  **fail-soft** (return `[]` / no-op; never raise). A delete still removes the
  Postgres row even if the Neo4j purge fails (logged).
- Ownership is enforced on every per-conversation endpoint (404 unknown, 403 not
  yours) so users can't read/delete each other's threads.
- `touch_conversation` failure must not break the answer path — it runs in the
  same post-answer `_memory_write` which the chat routes already treat as
  best-effort; wrap so it can't raise into the response.

## Testing

- **Conversations store (integration, skip if no DB):** `touch` creates + titles
  on first call, bumps `updated_at` (not title) on second; `list` ordering;
  `get_owner`; `delete` removes the row.
- **Memory:** `load_conversation`/`delete_conversation_messages` are `[]`/no-op
  when disabled and swallow errors.
- **API:** guest → 401 on `/conversations`; non-owner → 403; unknown → 404
  (handlers tested as functions with monkeypatched store + `current_username`).
- **Frontend:** `npm run build` succeeds.
- **Live (manual):** log in, hold two conversations, list shows both newest-first
  with first-message titles, resume one (messages render), delete one (gone from
  list and from Neo4j).

## Security / privacy

- Inherits Phase 1: token identity, ownership checks, bcrypt, fail-soft memory.
- Delete is a genuine purge (Postgres row + Neo4j messages) — important for a
  store of personal tax conversations.

## Reversibility

Drop the `conversations` table, the new module/endpoints, and the sidebar to
remove Phase 2; Phase 1 and guest behavior are untouched.
