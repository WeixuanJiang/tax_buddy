# Design: Accounts + Per-User Memory (Phase 1)

**Date:** 2026-06-19
**Status:** Drafted; pending user review
**Builds on:** the agent-memory user-profile trial (branch `agent-memory-trial`) —
the fail-soft `agent/memory.py` adapter, qwen custom embedder, and `/chat`
memory wiring already exist.

## Goal

Let a user **register** (username, password, occupation, postcode) and **log
in**. While logged in, the user's conversations are persisted to Neo4j and the
agent recalls that user's history and preferences across sessions. Login is
**optional** — guests keep today's behavior (no cross-session memory).

This is **Phase 1** of a larger feature. Phase 2 (a ChatGPT-style conversation
history sidebar: list / resume / new / delete / auto-titles) is **out of scope
here** and will get its own spec. Phase 1's persistence is built to be
forward-compatible with it.

## Non-goals (Phase 1)

- Conversation history sidebar / listing / resume UI (Phase 2).
- A `conversations` metadata table and its endpoints (Phase 2).
- Password reset, email verification, roles, OAuth/social login.
- Replacing the Postgres LangGraph checkpointer (it still handles live
  in-thread state).

## Decisions (confirmed with the user)

- **Credentials in Postgres**, memory in Neo4j (clean separation).
- **Full transcript + facts** persisted for logged-in users; checkpointer kept.
- **Logical per-user scoping** (one shared Neo4j index; filter by identifier).
- **Login optional**; guests still chat.
- **Identity from the token**, never from a request body field (no spoofing).
- **Conversation scoping:** Neo4j short-term `session_id = thread_id`, messages
  tagged `user_identifier = username`. (Phase 2 lists conversations by user; the
  per-thread session_id makes that possible without rework.)

## Verified library facts (v0.5.0)

- `short_term.add_message(session_id, role, content, *, user_identifier=None,
  generate_embedding=True, extract_entities=True, extract_relations=True, ...)`.
  We call it with **`extract_entities=False, extract_relations=False`** (the lib
  has no LLM adapter for our DeepSeek model, and we want deterministic, cheap
  writes) and **`generate_embedding=True`** (qwen, via the existing custom
  embedder).
- `short_term.search_messages(query, *, session_id=None, limit, threshold,
  metadata_filters=None)` — used for user-wide recall via
  `metadata_filters={"user_identifier": username}` (**verify this filter key at
  implementation**; fall back to preferences-only recall if unsupported).
- `long_term.get_preferences_for(user_identifier=...)` — user-scoped prefs
  (already used). `long_term.add_preference(category, preference, *,
  user_identifier=, generate_embedding=)` — already used.

## Architecture

Memory I/O stays at the FastAPI boundary; all Neo4j/library specifics stay in
`agent/memory.py`. New auth code is API-layer. Identity flows from a JWT in the
`Authorization` header to a `username`, which becomes the memory scope.

```
register -> bcrypt hash -> users table (Postgres) + seed prefs (Neo4j)
login    -> verify hash -> JWT { sub: username, exp }
/chat (Bearer token present & valid):
   uid = username
   read:  get_user_context(uid, query)      # prefs + past-message recall
   graph.invoke({..., user_profile: <that>})
   write: save_turn(uid, thread_id, q, answer) + remember(uid, analysis)   # on route==answer
/chat (no/invalid token): guest — no memory (today's behavior)
```

## Components

### 1. `api/security.py` (new — pure, unit-testable)
- `hash_password(pw) -> str` / `verify_password(pw, hash) -> bool` (bcrypt).
- `create_token(username) -> str` / `decode_token(token) -> str | None`
  (PyJWT, HS256, signed with `settings.auth_secret`, `exp` = now + TTL;
  returns the username or `None` on invalid/expired).

### 2. `api/users.py` (new — Postgres user store)
- `ensure_users_table()` — `CREATE TABLE IF NOT EXISTS users (username TEXT
  PRIMARY KEY, password_hash TEXT NOT NULL, occupation TEXT NOT NULL, postcode
  TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())`. Called from the
  API lifespan startup. **Not** in `ingestion/schema.sql`, so `ingest` never
  drops it.
- `create_user(username, password_hash, occupation, postcode) -> bool`
  (False if the username already exists).
- `get_user(username) -> dict | None`.

### 3. `agent/memory.py` (extend the existing adapter)
- `register_user_profile(uid, occupation, postcode)` — write two user-scoped
  prefs (`profile: occupation: <x>`, `profile: postcode: <x>`). Fail-soft.
- `save_turn(uid, thread_id, question, answer)` — two `add_message` calls
  (`session_id=thread_id`, `user_identifier=uid`, extraction off, embedding on).
  Fail-soft, write timeout.
- `recall_conversation(uid, query) -> str` — `search_messages(query,
  metadata_filters={"user_identifier": uid}, limit=5)`, formatted as a short
  block; `""` on disabled/error/empty. Read timeout.
- `get_user_context(uid, query) -> str` — concatenates `get_user_profile(uid)`
  (existing) + `recall_conversation(uid, query)`; the single entry point the API
  injects. Fail-soft.

### 4. `api/models.py` (extend)
- `RegisterRequest { username, password, occupation, postcode }` with validation:
  username 3–32 chars `[A-Za-z0-9_]`; password ≥ 8; occupation non-empty;
  postcode = 4 digits (AU).
- `LoginRequest { username, password }`. `AuthResponse { token, username }`.
- `ChatRequest`: **remove `user_id`** (superseded by token identity); keep
  `question`, `thread_id`, `reasoning`.

### 5. `api/main.py` (extend)
- Lifespan startup also calls `ensure_users_table()`.
- `POST /auth/register` → validate, hash, `create_user`; on success
  `register_user_profile(...)` and return a token. 409 if username taken.
- `POST /auth/login` → verify; 401 on bad creds; return `{token, username}`.
- `current_username(authorization: str | None = Header(None)) -> str | None` —
  decode bearer token; `None` for guests.
- `/chat` and `/chat/stream`: `uid = current_username(...)`. If `uid`:
  read `get_user_context(uid, query)` into `user_profile`; after a completed
  answer (`route == "answer"`) call `save_turn(uid, thread_id, q, answer)` +
  `remember(uid, analysis)`. If guest: unchanged, no memory. `/ask` untouched.

### 6. `config.py` / deps / env
- `auth_secret: str` (`AUTH_SECRET`), `auth_token_ttl_hours: int = 24`
  (`AUTH_TOKEN_TTL_HOURS`). The API **refuses to start auth** (register/login
  return 503) if `AUTH_SECRET` is empty, so there is no insecure default.
- `requirements.txt`: add `bcrypt`, `PyJWT`.
- `.env.example`: document `AUTH_SECRET` (generate a random value; never commit).

### 7. Frontend (`web/`)
- `api.js`: `register(...)`, `login(...)` → store `{token, username}` in
  `localStorage`; `authHeader()` helper; send `Authorization: Bearer <token>`
  on `chat`/`chatStream` when present.
- A small `Auth` component (toggle register/login form) and logged-in state in
  `App.jsx` (show username + Logout; Logout clears localStorage). Guests see the
  app exactly as today.

## Error handling & failure modes

- All memory calls remain **fail-soft** (reads `""`, writes no-op; never raise).
  A logged-in user whose Neo4j is down still gets answers, just no memory.
- Auth failures are explicit HTTP codes (400 validation, 401 bad creds, 409
  duplicate, 503 if `AUTH_SECRET` unset) — auth is a real gate, not fail-soft.
- Invalid/expired token on `/chat` ⇒ treated as guest (no error), so an expired
  session degrades to anonymous chat rather than breaking.

## Security & privacy

- Passwords **bcrypt-hashed**; only the hash is stored. `AUTH_SECRET` lives in
  `.env` only (gitignored); no secret committed (public repo).
- JWT is signed (HS256) with `exp`; tokens carry only the username.
- **Privacy escalation (named):** full tax-conversation transcripts are now
  stored in Neo4j and **qwen-embedded via OpenRouter** for logged-in users —
  more sensitive than the profile-facts trial. This is the user's explicit
  intent. Guests persist nothing.

## Testing

- **Unit (no DB):** `security` (hash round-trips and rejects wrong password;
  token encode→decode returns username; tampered/expired token → `None`);
  request-model validation (bad username/password/postcode rejected).
- **Memory adapter:** `save_turn`/`recall_conversation`/`get_user_context` are
  no-ops/`""` when disabled and swallow errors (monkeypatch `_submit`, as the
  existing tests do).
- **Live integration check** (like the trial, run manually): register a user →
  login → two chats in different threads → confirm occupation/postcode + prior
  context are recalled and a normally-clarifying question is answered directly;
  confirm a guest persists nothing.

## Reversibility

Auth/memory gated by `AUTH_SECRET` + `MEMORY_ENABLED`. Dropping the `users`
table and the new modules removes the feature; corpus and existing chat
behavior are untouched.
