"""Thin, synchronous, fail-soft adapter over neo4j-agent-memory.

This is the ONLY module that imports the library. Public functions never raise:
when settings.memory_enabled is False, or on any error/timeout, reads return ""
and writes are no-ops, so the agent's answer path is never affected.

The async library runs on a single background event loop (daemon thread); the
client is created lazily and kept open for the process lifetime.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from concurrent.futures import Future
from typing import Any, Optional

from knowledge_engine.config import settings

logger = logging.getLogger(__name__)

_CALL_TIMEOUT = 8.0     # read budget (on the answer's critical path): a slow/unreachable Neo4j must not stall a response
_RECALL_TIMEOUT = 15.0  # conversation recall embeds the query via qwen; allow a cold first call (warms after)
_WRITE_TIMEOUT = 30.0   # write budget (post-answer): allow cold connect + qwen embedding over the network

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


def _submit(coro, timeout: float = _CALL_TIMEOUT) -> Any:
    """Run a coroutine on the background loop and block (bounded) for its result."""
    fut: Future = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    return fut.result(timeout=timeout)


class _QwenEmbedder:
    """Custom embedder implementing the library's `Embedder` protocol by reusing
    the project's qwen/OpenRouter embedding. `embed_passages` is sync (httpx), so
    we run it off the event loop with asyncio.to_thread.

    Must expose `dimensions` + `embed` + `embed_batch` to satisfy the library's
    runtime-checkable `Embedder` protocol (checked in connect())."""

    @property
    def dimensions(self) -> int:
        return settings.embed_dim

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
    # No async lock needed: _get_client only ever runs on the single background
    # event loop (every call is funnelled through _submit), so creation is
    # serialized and _client is set before any concurrent caller can observe it.
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


def extract_durable_facts(text: str) -> list[str]:
    """Extract deterministic user facts that should survive across chats."""
    if not text:
        return []

    facts: list[str] = []
    normalized = " ".join(text.lower().split())
    if "work from home" in normalized or "wfh" in normalized:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*hours?\s*(?:\*|x|per\s+week\s+for|/week\s+for)?\s*"
            r"(\d+(?:\.\d+)?)\s*weeks?",
            normalized,
        )
        if match:
            hours, weeks = match.groups()
            facts.append(f"work from home hours: {hours} hours per week for {weeks} weeks")
    return facts


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
        logger.warning("memory: get_user_profile failed (returning empty)", exc_info=True)
        return ""


def remember(user_id: str, analysis: Optional[dict], question: str | None = None) -> None:
    """Persist confirmed facts from a Triage dump as user-scoped preferences.

    Deterministic (no LLM/extraction). Each preference is embedded via qwen
    (generate_embedding defaults True). Everything is stored as a preference
    because add_fact is NOT user-scoped.
    """
    if not settings.memory_enabled or not user_id or (not analysis and not question):
        return
    analysis = analysis or {}

    async def _run() -> None:
        client = await _get_client()
        yr = analysis.get("income_year")
        if yr:
            await client.long_term.add_preference(
                category="tax",
                preference=f"income year {yr}",
                user_identifier=user_id,
            )
        seen: set[str] = set()
        facts = [
            *(analysis.get("entities") or []),
            *(analysis.get("memory_facts") or []),
            *extract_durable_facts(question or ""),
        ]
        for ent in facts:
            ent = ent.strip() if ent else ""
            if ent and ent not in seen:
                seen.add(ent)
                await client.long_term.add_preference(
                    category="profile",
                    preference=ent,
                    user_identifier=user_id,
                )

    try:
        _submit(_run(), timeout=_WRITE_TIMEOUT)
    except Exception:
        logger.warning("memory: remember failed (skipping persist)", exc_info=True)
        return


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
                    # Also tag the metadata: add_message does NOT store
                    # user_identifier as a queryable Message property, so
                    # search_messages(metadata_filters={"user_identifier": ...})
                    # only matches when it lives in metadata.
                    metadata={"user_identifier": user_id},
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
        return _submit(_run(), timeout=_RECALL_TIMEOUT) or ""
    except Exception:
        logger.warning("memory: recall_conversation failed (returning empty)", exc_info=True)
        return ""


def get_user_context(user_id: str, query: str) -> str:
    """Combined recall injected by the API: durable preferences + relevant past messages."""
    parts = [p for p in (get_user_profile(user_id), recall_conversation(user_id, query)) if p]
    return "\n".join(parts).strip()


def extract_key_memory_facts(transcript: str) -> list[str]:
    """Run the memory extractor once for a completed chat transcript."""
    transcript = (transcript or "").strip()
    if not transcript:
        return []

    facts: list[str] = []
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from knowledge_engine.agent import prompts
        from knowledge_engine.agent.llm import structured
        from knowledge_engine.agent.state import MemoryFacts

        extracted: MemoryFacts = structured(MemoryFacts).invoke([
            SystemMessage(prompts.MEMORY_SYS),
            HumanMessage(transcript),
        ])
        facts.extend(f.strip() for f in extracted.facts if f and f.strip())
    except Exception:
        logger.warning("memory: extract_key_memory_facts failed", exc_info=True)

    facts.extend(extract_durable_facts(transcript))
    out: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        if fact not in seen:
            seen.add(fact)
            out.append(fact)
    return out


def remember_conversation(user_id: str, thread_id: str) -> None:
    """Persist long-term facts once, when a chat is explicitly closed."""
    if not settings.memory_enabled or not user_id or not thread_id:
        return
    messages = load_conversation(thread_id)
    user_lines = [
        str(m.get("content", "")).strip()
        for m in messages
        if str(m.get("role", "")).lower() == "user" and str(m.get("content", "")).strip()
    ]
    transcript = "\n".join(user_lines).strip()
    if not transcript:
        return
    facts = extract_key_memory_facts(transcript)
    if facts:
        remember(user_id, {"memory_facts": facts}, question=transcript)


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
