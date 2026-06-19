# agent-memory User-Profile Trial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the ATO knowledge-engine agent a persistent, cross-session user profile via `neo4j-labs/agent-memory`, so it stops re-asking facts (occupation, income year) it already learned.

**Architecture:** Memory I/O happens at the FastAPI boundary (Approach A from the spec): the `/chat` routes read a profile string before invoking the (sync) LangGraph graph and write confirmed facts after. All async + library specifics are confined to one fail-soft adapter module (`agent/memory.py`). The graph nodes stay synchronous and only consume an injected `user_profile` string. `/ask` stays stateless.

**Tech Stack:** Python 3.10+, FastAPI, LangGraph, `neo4j-agent-memory` (async, self-hosted Neo4j 5.20+), embeddings via qwen/qwen3-embedding-8b on OpenRouter (custom embedder reusing the corpus pipeline), pytest.

## Global Constraints

- Python 3.10+; Neo4j 5.20+ (self-hosted, local Docker).
- Memory is **off by default** (`MEMORY_ENABLED=false`). With it off, all existing behavior is byte-for-byte unchanged.
- **Fail-soft:** no memory error may ever propagate to the answer path. Reads return `""`, writes are no-ops, on any error/timeout/disabled.
- **All `neo4j-agent-memory` imports and calls live only in `agent/memory.py`.** No other file imports the library.
- Embeddings use **qwen/qwen3-embedding-8b via OpenRouter** (user instruction — the same model the corpus uses), through a custom embedder reusing `ingestion.embed.embed_passages`. Short profile strings are therefore sent to OpenRouter for embedding (privacy trade-off accepted by the user, overriding the spec's local-embedding default). No extraction LLM is exercised on our deterministic path.
- Fact persistence is **deterministic** from the agent's own `Triage` output — no extra LLM call, no feeding raw messages to the library.
- `/ask` remains stateless (no `user_id`, no memory).
- Package imports as `knowledge_engine` from its parent directory; run commands from the repo's parent (`...\Desktop`) or rely on the `conftest.py` added in Task 1.
- All `git` commands run from the repo root (`...\Desktop\knowledge_engine`).

## File Structure

- `requirements.txt` (modify) — add library + pytest.
- `conftest.py` (create) — put the package's parent on `sys.path` for tests.
- `config.py` (modify) — new memory settings.
- `agent/memory.py` (create) — the only file importing the library; sync, fail-soft adapter.
- `agent/state.py` (modify) — add `entities` to `Triage`; add `user_profile` to `AgentState`.
- `agent/prompts.py` (modify) — memory-aware instruction text.
- `agent/nodes.py` (modify) — `_profile_block` helper; inject into `triage` and `synthesize`.
- `api/models.py` (modify) — `user_id` on `ChatRequest`.
- `api/main.py` (modify) — `_memory_read`/`_memory_write` helpers; wire `/chat` and `/chat/stream`.
- `docker-compose.yml` (modify) — add `neo4j` service.
- `.env.example` (modify) — document new vars.
- `eval/memory_demo.py` (create) — manual cross-session recall demonstration.
- `tests/` (create) — `test_config_memory.py`, `test_memory_adapter.py`, `test_nodes_profile.py`, `test_api_memory_helpers.py`.

> **Spec deviation (intentional, flagged for review):** The active flow uses the `Triage` model, which today surfaces only `income_year` — not occupation/entities. To make persistence and the "skip the clarifying question" demo meaningful (the spec's example is "I'm a sole trader, 2025-26"), Task 4 adds an `entities` field to `Triage`. This is the minimal change that lets the trial demonstrate value.

---

### Task 1: Dependencies, test harness, and library API verification

**Files:**
- Modify: `requirements.txt`
- Create: `conftest.py`
- Create: `docs/superpowers/notes/agent-memory-api.md` (record of the real API)

**Interfaces:**
- Produces: the confirmed real names for `MemoryClient`, `MemorySettings`, the long-term add methods, `get_context`, and the user-scoping kwarg. Task 3 consumes these.

- [ ] **Step 1: Add dependencies**

In `requirements.txt`, under the LLM section add the library, and add a test section at the end:

```
# --- Long-term memory (trial: neo4j-labs/agent-memory) ---
neo4j-agent-memory[sentence-transformers]>=0.1.0

# --- Tests ---
pytest>=8.0
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: installs `neo4j-agent-memory`, `sentence-transformers`, `pytest` (first install pulls model/runtime deps; a few minutes).

- [ ] **Step 3: Create `conftest.py` at the repo root**

```python
"""Put the package's parent dir on sys.path so `import knowledge_engine` works
when pytest is invoked from inside the knowledge_engine/ directory."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: Verify the real library API and record it**

Run (from the repo parent, `...\Desktop`):

```bash
python -c "import neo4j_agent_memory as m, inspect; print('top:', [n for n in dir(m) if not n.startswith('_')]); from neo4j_agent_memory import MemoryClient, MemorySettings; print('client:', [n for n in dir(MemoryClient) if not n.startswith('_')]); print('settings fields:', list(getattr(MemorySettings,'model_fields',{}).keys()))"
```

Then inspect the long-term surface and `get_context`:

```bash
python -c "from neo4j_agent_memory import MemoryClient; import inspect; print(inspect.signature(MemoryClient.get_context))"
```

Write the findings to `docs/superpowers/notes/agent-memory-api.md` with the **actual** names/signatures for: client construction, `MemorySettings` fields (neo4j/embedding/llm), the long-term `add_preference`/`add_fact`/`add_entity` (or their real equivalents), `get_context`, and the user-scoping parameter name (the spec assumes `user_identifier`). If a name differs from this plan's assumption, note the mapping — Task 3 adjusts only its three call sites accordingly.

- [ ] **Step 5: Confirm pytest discovers the (empty) suite**

Run (from the repo root): `python -m pytest -q`
Expected: `no tests ran` (exit 5) or collection succeeds — confirms `conftest.py` loads without import errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt conftest.py docs/superpowers/notes/agent-memory-api.md
git commit -m "chore: add agent-memory + pytest deps, test bootstrap, verified API notes"
```

---

### Task 2: Memory configuration settings

**Files:**
- Modify: `config.py`
- Test: `tests/test_config_memory.py`

**Interfaces:**
- Produces: `settings.memory_enabled: bool`, `settings.neo4j_uri/neo4j_user/neo4j_password: str`. Task 3 consumes these (and reuses the existing `embed_model`/`embed_dim` for embeddings).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_memory.py`:

```python
from knowledge_engine.config import Settings


def test_memory_defaults_off_and_local():
    s = Settings(_env_file=None)
    assert s.memory_enabled is False
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.memory_embedding_model == "all-MiniLM-L6-v2"


def test_memory_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    s = Settings(_env_file=None)
    assert s.memory_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_memory.py -v`
Expected: FAIL (`AttributeError`/`ValidationError`: no `memory_enabled`).

- [ ] **Step 3: Add settings**

In `config.py`, inside `class Settings`, after the `# Retrieval knobs` block, add:

```python
    # --- Long-term memory (trial: neo4j-labs/agent-memory) ---
    memory_enabled: bool = Field(default=False, alias="MEMORY_ENABLED")
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")
    # Bare model name; the provider (sentence_transformers) is set separately
    # when the adapter builds EmbeddingConfig.
    memory_embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        alias="MEMORY_EMBEDDING_MODEL",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_memory.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config_memory.py
git commit -m "feat: add memory configuration settings (off by default)"
```

---

### Task 3: Fail-soft memory adapter

**Files:**
- Create: `agent/memory.py`
- Test: `tests/test_memory_adapter.py`

**Interfaces:**
- Consumes: `settings.memory_enabled`, `settings.neo4j_uri/neo4j_user/neo4j_password` (Task 2); `settings.embed_model`, `settings.embed_dim`, `settings.openrouter_model` (existing). Reuses `knowledge_engine.ingestion.embed.embed_passages` (qwen via OpenRouter) for the custom embedder.
- Produces:
  - `get_user_profile(user_id: str) -> str` — known facts as text; `""` on disabled/error/timeout.
  - `remember(user_id: str, analysis: dict | None) -> None` — persists `income_year` + `entities` from a `Triage` dump; no-op on disabled/error.

> **API confirmed by Task 1** — see `docs/superpowers/notes/agent-memory-api.md` (package v0.5.0). Key facts the adapter below already reflects:
> - `MemoryClient.get_context` does **NOT** accept `user_identifier`. User-scoped reads use `client.long_term.get_preferences_for(user_identifier=...)`.
> - `add_fact(subject, predicate, obj, ...)` has **no** `user_identifier` kwarg, so it cannot be user-scoped. We therefore persist **everything as user-scoped preferences** (`add_preference(..., user_identifier=...)`) and do not use `add_fact`.
> - `MemorySettings` takes config **objects** (`Neo4jConfig`, `EmbeddingConfig`, `LLMConfig`), not provider strings. `Neo4jConfig` uses `username` (not `user`).
> - **Embeddings use qwen via OpenRouter** (per user instruction — the same model the corpus uses). `EmbeddingConfig` has no base-URL field, so we pass a **custom embedder** to `MemoryClient(embedder=...)` that reuses the project's `embed_passages`. The custom embedder must implement async `embed(text) -> list[float]` and `embed_batch(texts) -> list[list[float]]` (the library's `Embedder` protocol). `EmbeddingConfig(provider="custom", dimensions=settings.embed_dim)` sets the Neo4j vector-index dimension (4096) to match qwen.
> - Reads use a direct `get_preferences_for` lookup (no embedding). Writes embed via qwen (`generate_embedding=True`, the default).
> - **Privacy note:** short profile strings (e.g. "income year 2026", "sole trader") are sent to OpenRouter for embedding — same provider as the corpus. This is the user's explicit choice, overriding the spec's local-embedding default.
>
> **Implementer:** before relying on construction, do a no-DB instantiation check:
> `python -c "from neo4j_agent_memory import MemorySettings, Neo4jConfig, EmbeddingConfig; MemorySettings(neo4j=Neo4jConfig(uri='bolt://x',username='neo4j',password='x'), embedding=EmbeddingConfig(provider='custom', model='qwen/qwen3-embedding-8b', dimensions=4096))"`.
> If a field name or a required-but-missing config differs from the notes, adjust the construction in `_get_client` (and only there). The fail-soft tests do not exercise construction or the embedder.

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_adapter.py`:

```python
import knowledge_engine.agent.memory as mem


def test_get_profile_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.get_user_profile("u1") == ""


def test_get_profile_empty_user_returns_empty(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    assert mem.get_user_profile("") == ""


def test_remember_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.remember("u1", {"income_year": 2026}) is None


def test_get_profile_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro):
        coro.close()  # avoid "coroutine never awaited" warning
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.get_user_profile("u1") == ""


def test_remember_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.remember("u1", {"income_year": 2026, "entities": ["sole trader"]}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_memory_adapter.py -v`
Expected: FAIL (`ModuleNotFoundError: knowledge_engine.agent.memory`).

- [ ] **Step 3: Write the adapter**

Create `agent/memory.py`:

```python
"""Thin, synchronous, fail-soft adapter over neo4j-agent-memory.

This is the ONLY module that imports the library. Public functions never raise:
when settings.memory_enabled is False, or on any error/timeout, reads return ""
and writes are no-ops, so the agent's answer path is never affected.

The async library runs on a single background event loop (daemon thread); the
client is created lazily and kept open for the process lifetime.
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Optional

from knowledge_engine.config import settings

_CALL_TIMEOUT = 8.0  # seconds; a slow/unreachable Neo4j must not stall a response

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()
_client: Any = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, name="memory-loop", daemon=True
            ).start()
            _loop = loop
        return _loop


def _submit(coro) -> Any:
    """Run a coroutine on the background loop and block (bounded) for its result."""
    fut: Future = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    return fut.result(timeout=_CALL_TIMEOUT)


class _QwenEmbedder:
    """Custom embedder implementing the library's `Embedder` protocol by reusing
    the project's qwen/OpenRouter embedding. `embed_passages` is sync (httpx), so
    we run it off the event loop with asyncio.to_thread."""

    async def embed(self, text: str) -> list[float]:
        from knowledge_engine.ingestion.embed import embed_passages
        vectors = await asyncio.to_thread(embed_passages, [text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        from knowledge_engine.ingestion.embed import embed_passages
        return await asyncio.to_thread(embed_passages, list(texts))


async def _get_client() -> Any:
    """Lazily create one long-lived MemoryClient on the background loop.

    Library import is deferred to here so this module imports even when the
    package is absent (keeps `import ...memory` safe in any environment).

    Construction uses config OBJECTS (verified against v0.5.0). Embeddings use
    qwen via a custom embedder (reusing the corpus pipeline); the LLM config is
    never exercised but is supplied so construction succeeds if required.
    """
    global _client
    if _client is not None:
        return _client
    from neo4j_agent_memory import (
        EmbeddingConfig,
        LLMConfig,
        MemoryClient,
        MemorySettings,
        Neo4jConfig,
    )

    ms = MemorySettings(
        neo4j=Neo4jConfig(
            uri=settings.neo4j_uri,
            username=settings.neo4j_user,
            password=settings.neo4j_password,
        ),
        # provider="custom" + the embedder= kwarg below routes embedding through
        # qwen/OpenRouter; dimensions must match qwen (settings.embed_dim, 4096)
        # so the Neo4j vector index is sized correctly.
        embedding=EmbeddingConfig(
            provider="custom",
            model=settings.embed_model,
            dimensions=settings.embed_dim,
        ),
        # Never exercised on our deterministic path; present so construction
        # succeeds if MemorySettings requires an llm config.
        llm=LLMConfig(
            provider="openai",
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key or "unused",
        ),
    )
    client = MemoryClient(ms, embedder=_QwenEmbedder())
    await client.connect()
    _client = client
    return _client


def _format_prefs(prefs: Any) -> str:
    """Render a list of Preference objects as a short text block."""
    lines = []
    for p in prefs or []:
        text = getattr(p, "preference", None) or str(p)
        category = getattr(p, "category", "") or ""
        prefix = f"{category}: " if category else ""
        line = f"- {prefix}{text}".strip()
        if line and line != "-":
            lines.append(line)
    return "\n".join(lines).strip()


def get_user_profile(user_id: str) -> str:
    """Return the user's known profile as a short text block, or '' on any issue."""
    if not settings.memory_enabled or not user_id:
        return ""

    async def _run() -> str:
        client = await _get_client()
        prefs = await client.long_term.get_preferences_for(user_identifier=user_id)
        return _format_prefs(prefs)

    try:
        return _submit(_run()) or ""
    except Exception:
        return ""


def remember(user_id: str, analysis: Optional[dict]) -> None:
    """Persist confirmed facts from a Triage dump as user-scoped preferences.

    Deterministic (no LLM/extraction). Each preference is embedded via qwen
    (generate_embedding defaults True). Everything is stored as a preference
    because add_fact is NOT user-scoped.
    """
    if not settings.memory_enabled or not user_id or not analysis:
        return

    async def _run() -> None:
        client = await _get_client()
        yr = analysis.get("income_year")
        if yr:
            await client.long_term.add_preference(
                category="tax",
                preference=f"income year {yr}",
                user_identifier=user_id,
            )
        for ent in analysis.get("entities") or []:
            if ent and ent.strip():
                await client.long_term.add_preference(
                    category="profile",
                    preference=ent.strip(),
                    user_identifier=user_id,
                )

    try:
        _submit(_run())
    except Exception:
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_memory_adapter.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/memory.py tests/test_memory_adapter.py
git commit -m "feat: add fail-soft sync memory adapter over neo4j-agent-memory"
```

---

### Task 4: Surface user facts in Triage; add state + request fields

**Files:**
- Modify: `agent/state.py`
- Modify: `api/models.py`
- Test: `tests/test_nodes_profile.py` (extended in Task 5; create the schema asserts here)

**Interfaces:**
- Produces: `Triage.entities: list[str]`; `AgentState["user_profile"]: str`; `ChatRequest.user_id: str | None`. Tasks 5 and 6 consume these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_nodes_profile.py`:

```python
from knowledge_engine.agent.state import Triage
from knowledge_engine.api.models import ChatRequest


def test_triage_has_entities_field():
    t = Triage(in_scope=True, entities=["sole trader"])
    assert t.entities == ["sole trader"]


def test_triage_entities_defaults_empty():
    t = Triage(in_scope=True)
    assert t.entities == []


def test_chat_request_accepts_user_id():
    r = ChatRequest(question="hello there", thread_id="t1", user_id="u1")
    assert r.user_id == "u1"


def test_chat_request_user_id_optional():
    r = ChatRequest(question="hello there", thread_id="t1")
    assert r.user_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nodes_profile.py -v`
Expected: FAIL (`Triage` has no `entities`; `ChatRequest` has no `user_id`).

- [ ] **Step 3: Add `entities` to `Triage`**

In `agent/state.py`, in `class Triage`, add this field after `income_year`:

```python
    entities: list[str] = Field(
        default_factory=list,
        description="Durable facts about the user worth remembering across "
                    "sessions: occupation, residency status, asset types "
                    "(e.g. 'sole trader', 'foreign resident', 'rental property'). "
                    "Only include facts the user actually stated.")
```

- [ ] **Step 4: Add `user_profile` to `AgentState`**

In `agent/state.py`, in `class AgentState`, add after `query: str`:

```python
    user_profile: str               # facts recalled from long-term memory
```

- [ ] **Step 5: Add `user_id` to `ChatRequest`**

In `api/models.py`, in `class ChatRequest`, add after `thread_id`:

```python
    user_id: str | None = Field(
        default=None,
        description="Stable user id for cross-session memory. Defaults to "
                    "thread_id when omitted.")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_nodes_profile.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add agent/state.py api/models.py tests/test_nodes_profile.py
git commit -m "feat: surface user entities in Triage; add user_profile state + user_id request"
```

---

### Task 5: Inject the profile into triage and synthesize

**Files:**
- Modify: `agent/prompts.py`
- Modify: `agent/nodes.py`
- Test: `tests/test_nodes_profile.py` (extend)

**Interfaces:**
- Consumes: `AgentState["user_profile"]` (Task 4).
- Produces: `nodes._profile_block(state) -> str` (pure helper). `triage` and `synthesize` append it to their system prompt.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nodes_profile.py`:

```python
from knowledge_engine.agent import nodes


def test_profile_block_empty_when_no_profile():
    assert nodes._profile_block({}) == ""
    assert nodes._profile_block({"user_profile": "   "}) == ""


def test_profile_block_includes_facts_and_guardrail():
    block = nodes._profile_block({"user_profile": "income year 2026; sole trader"})
    assert "income year 2026" in block
    assert "sole trader" in block
    assert "personalised advice" in block.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nodes_profile.py -v`
Expected: FAIL (`nodes._profile_block` does not exist).

- [ ] **Step 3: Add memory instruction text to prompts**

In `agent/prompts.py`, add at the end:

```python
PROFILE_PREFIX = (
    "\n\nKnown about this user from past sessions. Use it to avoid re-asking "
    "facts already known (e.g. occupation, residency) and to apply the right "
    "income year when the user did not state one. This is context only — still "
    "give general information, NOT personalised advice:\n"
)
```

- [ ] **Step 4: Add the helper and inject it**

In `agent/nodes.py`, add the helper near `_user_query` (after it):

```python
def _profile_block(state: AgentState) -> str:
    """Format recalled user facts for prompt injection; '' when none."""
    profile = (state.get("user_profile") or "").strip()
    return prompts.PROFILE_PREFIX + profile if profile else ""
```

In the `triage` function, change the structured call's system message to append the block. Replace:

```python
        t: Triage = structured(Triage, reasoning=reasoning).invoke(
            [SystemMessage(prompts.TRIAGE_SYS), *history, HumanMessage(q)]
        )
```

with:

```python
        t: Triage = structured(Triage, reasoning=reasoning).invoke(
            [SystemMessage(prompts.TRIAGE_SYS + _profile_block(state)),
             *history, HumanMessage(q)]
        )
```

In the `synthesize` function, replace:

```python
    sys = prompts.SYNTH_SYS.format(year_label=state.get("income_year_label",
                                                        settings.tax_year_label))
```

with:

```python
    sys = prompts.SYNTH_SYS.format(year_label=state.get("income_year_label",
                                                        settings.tax_year_label))
    sys = sys + _profile_block(state)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_nodes_profile.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add agent/prompts.py agent/nodes.py tests/test_nodes_profile.py
git commit -m "feat: inject recalled user profile into triage and synthesize prompts"
```

---

### Task 6: Wire memory into the API boundary

**Files:**
- Modify: `api/main.py`
- Test: `tests/test_api_memory_helpers.py`

**Interfaces:**
- Consumes: `memory.get_user_profile`, `memory.remember` (Task 3); `ChatRequest.user_id` (Task 4).
- Produces: `main._memory_read(user_id) -> str`, `main._memory_write(user_id, state) -> None`, used by `/chat` and `/chat/stream`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_memory_helpers.py`:

```python
from knowledge_engine.api import main


def test_memory_read_delegates(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_profile",
        lambda uid: f"profile:{uid}",
    )
    assert main._memory_read("u1") == "profile:u1"


def test_memory_read_blank_user_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_profile",
        lambda uid: "should-not-be-called",
    )
    assert main._memory_read("") == ""


def test_memory_write_delegates(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.remember",
        lambda uid, analysis: captured.update(uid=uid, analysis=analysis),
    )
    main._memory_write("u1", {"analysis": {"income_year": 2026}})
    assert captured == {"uid": "u1", "analysis": {"income_year": 2026}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_memory_helpers.py -v`
Expected: FAIL (`main._memory_read` does not exist).

- [ ] **Step 3: Add the helpers**

In `api/main.py`, after `_to_response`, add:

```python
def _memory_read(user_id: str) -> str:
    """Recall the user's profile (deferred import keeps the library optional)."""
    if not user_id:
        return ""
    from knowledge_engine.agent import memory
    return memory.get_user_profile(user_id)


def _memory_write(user_id: str, state: dict) -> None:
    if not user_id:
        return
    from knowledge_engine.agent import memory
    memory.remember(user_id, state.get("analysis"))
```

- [ ] **Step 4: Wire `/chat`**

In `api/main.py`, replace the body of `def chat(req: ChatRequest):` with:

```python
    uid = req.user_id or req.thread_id
    cfg = {"configurable": {"thread_id": req.thread_id}}
    try:
        s = _state["chat_graph"].invoke({
            "messages": [HumanMessage(req.question)], "query": req.question,
            "reasoning": req.reasoning, "user_profile": _memory_read(uid),
        }, cfg)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"agent error: {e}")
    _memory_write(uid, s)
    return _to_response(s)
```

- [ ] **Step 5: Wire `/chat/stream`**

In `chat_stream`, set the effective id and seed the input with the recalled profile. Replace:

```python
    cfg = {"configurable": {"thread_id": req.thread_id}}
    inp = {"messages": [HumanMessage(req.question)], "query": req.question,
           "reasoning": req.reasoning}
```

with:

```python
    uid = req.user_id or req.thread_id
    cfg = {"configurable": {"thread_id": req.thread_id}}
    inp = {"messages": [HumanMessage(req.question)], "query": req.question,
           "reasoning": req.reasoning, "user_profile": _memory_read(uid)}
```

Then, inside `gen()`, persist after the stream completes. Replace:

```python
                elif mode == "values":
                    final = data
            yield _sse("done", _to_response(final or {}).model_dump())
```

with:

```python
                elif mode == "values":
                    final = data
            _memory_write(uid, final or {})
            yield _sse("done", _to_response(final or {}).model_dump())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_memory_helpers.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Run the full suite + import-sanity the API**

Run: `python -m pytest -q`
Expected: all tests pass.
Run: `python -c "import knowledge_engine.api.main"` (from repo parent)
Expected: no error (module imports cleanly).

- [ ] **Step 8: Commit**

```bash
git add api/main.py tests/test_api_memory_helpers.py
git commit -m "feat: read/write long-term memory at the /chat API boundary"
```

---

### Task 7: Neo4j infrastructure and env documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Produces: a local `neo4j` service on `bolt://localhost:7687`; documented env vars.

- [ ] **Step 1: Add the neo4j service**

In `docker-compose.yml`, add under `services:` (sibling of `db`):

```yaml
  neo4j:
    image: neo4j:5.20
    container_name: ato_kb_neo4j
    environment:
      NEO4J_AUTH: neo4j/please-change-me
    ports:
      - "7474:7474"          # browser UI
      - "7687:7687"          # bolt
    volumes:
      - ato_kb_neo4jdata:/data
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7474 >/dev/null 2>&1 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
```

And add the volume under the `volumes:` block:

```yaml
  ato_kb_neo4jdata:
```

- [ ] **Step 2: Document env vars**

In `.env.example`, add at the end:

```
# --- Long-term memory (trial: neo4j-labs/agent-memory) ---
# Off by default; set true to enable cross-session user-profile memory.
MEMORY_ENABLED=false
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=please-change-me
# Memory embeds via qwen/OpenRouter, reusing EMBED_MODEL / EMBED_DIM and the
# existing OPENROUTER_API_KEY — no separate memory embedding env var.
```

- [ ] **Step 3: Validate compose parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML/schema errors).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add local neo4j service and document memory env vars"
```

---

### Task 8: Cross-session recall demonstration (manual integration)

**Files:**
- Create: `eval/memory_demo.py`

**Interfaces:**
- Consumes: `build_graph`, `memory.get_user_profile`/`remember` — exercises the same read/write the API boundary does, without HTTP.

> This is a manual integration demo, not a CI test: it requires `MEMORY_ENABLED=true`, a running Neo4j (`docker compose up -d neo4j`), the Postgres checkpointer, and a populated corpus. It proves the trial's whole point — recall across two different threads for the same user.

- [ ] **Step 1: Write the demo script**

Create `eval/memory_demo.py`:

```python
"""Manual demo: long-term user memory recalled across two separate threads.

Prerequisites:
  - MEMORY_ENABLED=true in .env
  - Neo4j running:  docker compose up -d neo4j
  - Postgres + corpus ingested (see README)

Run from the repo parent:  python -m knowledge_engine.eval.memory_demo
"""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage

from knowledge_engine.agent import memory
from knowledge_engine.agent.graph import build_graph
from knowledge_engine.config import settings


def _turn(graph, cfg, question: str, uid: str) -> dict:
    profile = memory.get_user_profile(uid)
    print(f"\n[recalled profile for {uid!r}]: {profile!r}")
    state = graph.invoke(
        {"messages": [HumanMessage(question)], "query": question,
         "user_profile": profile},
        cfg,
    )
    memory.remember(uid, state)
    return state


def main() -> None:
    if not settings.memory_enabled:
        raise SystemExit("Set MEMORY_ENABLED=true and start Neo4j first.")
    graph = build_graph()  # stateless graph is fine; memory is the cross-session store
    uid = f"demo-{uuid.uuid4().hex[:8]}"

    print("=== Turn 1 (thread A): user states their situation ===")
    s1 = _turn(graph, {"configurable": {"thread_id": "A"}},
               "I'm a sole trader and I want to know about the 2025-26 income year.",
               uid)
    print("route:", s1.get("route"), "| analysis:", s1.get("analysis"))

    print("\n=== Turn 2 (thread B, fresh): a question that usually needs occupation ===")
    s2 = _turn(graph, {"configurable": {"thread_id": "B"}},
               "What work-related expenses can I claim?", uid)
    print("route:", s2.get("route"))
    print("(Expected: NOT 'clarify' — occupation was recalled from memory.)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (manual)**

Run (with Neo4j up and `MEMORY_ENABLED=true`, from the repo parent):
`python -m knowledge_engine.eval.memory_demo`
Expected: Turn 2 prints a non-empty recalled profile and a route that is **not** `clarify` (the occupation/year was remembered across threads).

- [ ] **Step 3: Commit**

```bash
git add eval/memory_demo.py
git commit -m "test: add manual cross-session memory recall demo"
```

---

## Self-Review

**Spec coverage:**
- Self-hosted local Neo4j → Task 7. ✓
- User-profile layer only (no short-term/reasoning/corpus-graph) → scope held; only `add_preference`/`add_fact` used. ✓
- Wired into the live agent → Tasks 5–6 (triage/synth inject; API read/write). ✓
- `agent/memory.py` sole library boundary, sync, fail-soft, flag-gated default-off → Task 3 + Global Constraints. ✓
- Identity `user_id` defaulting to `thread_id`; `/ask` untouched → Tasks 4, 6. ✓
- Deterministic persistence from `analysis` (no extra LLM call) → Task 3. ✓
- Local embeddings (no egress) → Tasks 1, 2, 7. ✓
- Demonstration of cross-session recall → Task 8. ✓
- Reversibility (flag off / drop module) → guaranteed by default-off + isolated module. ✓
- Spec gap surfaced: `Triage` lacked occupation/entities → resolved in Task 4 (flagged deviation). ✓

**Placeholder scan:** No TBD/TODO; the one genuinely unverifiable item (exact library signatures) is pinned by Task 1 before any dependent code, and confined to three call sites. ✓

**Type consistency:** `get_user_profile(user_id: str) -> str` and `remember(user_id, analysis)` are defined in Task 3 and consumed unchanged in Task 6; `_profile_block(state) -> str` defined and consumed in Task 5; `Triage.entities`, `AgentState["user_profile"]`, `ChatRequest.user_id` defined in Task 4 and consumed in Tasks 5–6. ✓
