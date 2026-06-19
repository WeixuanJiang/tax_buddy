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
