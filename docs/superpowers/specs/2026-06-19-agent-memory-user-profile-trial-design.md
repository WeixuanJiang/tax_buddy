# Design: `agent-memory` user-profile trial

**Date:** 2026-06-19
**Status:** Approved (design); pending spec review
**Scope:** Trial integration of `neo4j-labs/agent-memory` to give the ATO
knowledge-engine agent a persistent, cross-session **user profile**.

## Goal

The agent currently extracts a user profile in `triage` (intent, income year,
occupation/entities) and then discards it when the LangGraph thread ends. The
trial adds a long-term, user-scoped memory so confirmed facts persist **across
sessions/threads**, letting the agent skip clarifying questions it has already
asked and personalize answers.

This is an evaluation, not a production commitment. It must be fully reversible
and **off by default**.

## Non-goals (explicitly out of scope)

- Short-term/conversation memory — already handled by the LangGraph Postgres
  checkpointer keyed by `thread_id`.
- Reasoning memory and tool-usage traces.
- Building a knowledge graph over the ATO corpus (corpus stays in pgvector).
- Real authentication / user accounts. The trial uses a caller-supplied
  `user_id`.
- The hosted NAMS backend. The trial runs **self-hosted Neo4j** so no user tax
  data leaves the machine.

## Library facts (to confirm at implementation)

- Package: `neo4j-agent-memory`; **async-only**; needs **Neo4j 5.20+** plus an
  embedding (and likely an LLM) provider.
- Provider strings are LiteLLM-style (`openrouter/<slug>`,
  `sentence-transformers/<model>`).
- Public surface used (per README; **exact signatures verified against the
  installed package as implementation step 1**): `MemoryClient`,
  `MemorySettings`, `long_term.add_preference(...)`, `long_term.add_fact(...)`,
  `long_term.add_entity(...)`, `get_context(query, ...)`.

Because the exact API is unverified, **all library calls are confined to a
single adapter module** (`agent/memory.py`). If a signature differs, only that
file changes.

## Architecture

**Approach A — memory I/O at the API boundary, graph nodes stay pure/sync.**

Rationale: nodes are sync (`graph.invoke`/`.stream`), the library is async-only,
and `/chat/stream` is a sync generator. Doing memory I/O at the API boundary
keeps async + library specifics in one place, keeps `/ask` stateless, and avoids
bridging async into every node. (Approaches B "calls inside nodes" and C
"dedicated memory node" were rejected — both spread async bridging into the
graph and pollute the stateless `/ask` path.)

### Data flow (`/chat` and `/chat/stream` only)

```
request (question, thread_id, user_id?)
  -> profile_text = memory.get_user_profile(user_id)        # sync, fail-soft
  -> graph.invoke({..., "user_profile": profile_text})
        triage      : uses user_profile -> skip known clarifications
        synthesize  : uses user_profile -> personalize
  -> memory.remember(user_id, final_state["analysis"])      # sync, fail-soft
  -> response
```

`/ask` is unchanged: stateless, no `user_id`, no memory.

## Components

### 1. `agent/memory.py` (new — only file that imports the library)

- Owns **one** background `asyncio` event loop in a daemon thread.
- Opens **one** long-lived `MemoryClient` on that loop at first use (or app
  startup) and keeps it open for the process lifetime.
- Exposes two **synchronous** functions that submit coroutines to the background
  loop via `run_coroutine_threadsafe(...).result(timeout=...)`:
  - `get_user_profile(user_id: str) -> str` — returns known facts as a short
    text block; returns `""` on any error, when disabled, or on timeout.
  - `remember(user_id: str, analysis: dict) -> None` — persists confirmed facts;
    no-op on any error or when disabled.
- **Fail-soft contract:** no memory error may ever propagate to the answer path.
  Every public function wraps its body in try/except and degrades to the
  "memory off" behavior. Matches the existing defensive node style.
- Gated by `settings.memory_enabled` (default **False**). When false, both
  functions short-circuit immediately and the client is never created.

### 2. Identity

- Add optional `user_id: str | None` to `ChatRequest`. When omitted, default to
  `thread_id` (so each conversation is its own "user" unless the caller opts
  into a stable identity).
- `AskRequest` unchanged.

### 3. Read -> inject

- Add `user_profile: str` to `AgentState` (TypedDict, `total=False`).
- Chat routes compute `profile_text` and pass it in the initial state.
- `triage` prompt: include the profile block; instruct the model to **not** ask
  for facts already present (e.g. occupation, residency, income year) and to
  fill `income_year` from the profile when not in the question.
- `synthesize` prompt: include the profile block to personalize wording. Grounding
  rules unchanged — answers still come only from retrieved ATO sources;
  the profile only affects framing and which year/occupation context applies.

### 4. Write -> persist (deterministic)

- After the graph returns, call `remember(user_id, state["analysis"])`.
- Map deterministically from what `triage` already extracted — **no extra LLM
  call, no feeding raw messages**:
  - `analysis.income_year` -> `add_preference(category="tax",
    preference="income year <yr>")` (or equivalent fact).
  - `analysis.entities` (occupation/asset types) -> `add_fact(...)` per entity.
- Only persist non-empty, confirmed values. Skip when `analysis` is empty (e.g.
  triage fell back to defaults).

### 5. Infrastructure & configuration

- `docker-compose.yml`: add a `neo4j:5.20` service with a named volume and a
  healthcheck; expose Bolt locally. The API service depends on it only when
  `MEMORY_ENABLED=true`.
- `requirements.txt`: add `neo4j-agent-memory[sentence-transformers]`.
  Embeddings run **locally** (no tax-data egress). If the client constructor
  requires an LLM, reuse the OpenRouter key via `openrouter/<slug>`.
- `config.py` new settings (all with safe defaults):
  - `memory_enabled: bool = False` (`MEMORY_ENABLED`)
  - `neo4j_uri: str = "bolt://localhost:7687"` (`NEO4J_URI`)
  - `neo4j_user: str = "neo4j"` (`NEO4J_USER`)
  - `neo4j_password: str = ""` (`NEO4J_PASSWORD`)
  - `memory_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"`
    (`MEMORY_EMBEDDING_MODEL`)
- `.env.example`: document the new vars.

## Error handling & failure modes

- Memory **off by default**; existing behavior is byte-for-byte unchanged until
  `MEMORY_ENABLED=true`.
- Neo4j unreachable / client init fails / call times out -> functions degrade to
  `""` / no-op; the agent answers exactly as it does today.
- Bounded timeout on every cross-thread memory call so a slow Neo4j can't stall
  a response.

## Testing / demonstration

The trial's whole point is cross-session recall, so the demonstration proves it:

- A script / eval case issuing two `/chat` calls with **different `thread_id`
  but the same `user_id`**:
  1. Turn 1 (thread A): user states "I'm a sole trader, 2025-26."
  2. Turn 2 (thread B, fresh): a question that would normally trigger a
     clarification — assert it is **not** asked and/or the income year is applied
     from memory.
- Adapter-level unit checks with memory disabled (functions are no-ops) and with
  a forced error (functions stay silent, return defaults).
- Existing `eval/run_eval.py` continues to pass with `MEMORY_ENABLED=false`.

## Reversibility

Removing the trial = set `MEMORY_ENABLED=false` (runtime) or drop `agent/memory.py`,
the Neo4j compose service, the requirement line, and the `user_profile` plumbing.
No schema or data in the existing Postgres store is touched.
