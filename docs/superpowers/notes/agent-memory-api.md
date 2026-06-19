# neo4j-agent-memory Real API Notes

Recorded: 2026-06-19
Package: `neo4j-agent-memory` v0.5.0 (extras: `[sentence-transformers]`)
PyPI package name: `neo4j-agent-memory` (import as `neo4j_agent_memory`)

## Top-level exports (partial, relevant names)

```
MemoryClient, MemorySettings, MemoryConfig
LongTermMemory, LongTermProtocol
ShortTermMemory, ShortTermProtocol
Neo4jConfig, EmbeddingConfig, LLMConfig
EmbeddingProvider, LLMProvider
Preference, Fact, Entity, EntityType, Relationship
SearchConfig, ExtractionConfig, ResolutionConfig
```

---

## MemoryClient construction

```python
MemoryClient(
    settings: MemorySettings | None = None,
    *,
    embedder=None,
    extractor=None,
    resolver=None,
    geocoder=None,
    enrichment_provider=None,
)
```

- Async context manager (`async with MemoryClient(settings) as client: ...`).
- Or call `await client.connect()` / `await client.close()` manually.
- Access sub-systems via properties: `client.long_term`, `client.short_term`, `client.reasoning`, `client.users`.

---

## MemorySettings fields

```python
MemorySettings(
    neo4j: Neo4jConfig,       # required: uri, username, password, database
    embedding: Any,           # EmbeddingConfig instance
    llm: Any,                 # LLMConfig instance
    schema_config: SchemaConfig,
    extraction: ExtractionConfig,
    resolution: ResolutionConfig,
    memory: MemoryConfig,
    search: SearchConfig,
    geocoding: GeocodingConfig,
    enrichment: EnrichmentConfig,
    backend: Literal['bolt', 'nams'] | None,
    nams: NamsConfig,
)
```

### Neo4jConfig fields
`uri, username, password, database, max_connection_pool_size, connection_timeout, max_transaction_retry_time, max_connection_lifetime, liveness_check_timeout, keep_alive`

### EmbeddingConfig fields
`provider, model, dimensions, api_key, batch_size, device, project_id, location, task_type, aws_region, aws_profile`

Provider enum values: `openai, anthropic, sentence_transformers, vertex_ai, bedrock, custom`

### LLMConfig fields
`provider, model, api_key, temperature, max_tokens`

Provider enum values: `openai, anthropic, custom`

---

## Long-term memory: LongTermMemory (client.long_term)

### add_preference

```python
await client.long_term.add_preference(
    category: str,
    preference: str,
    *,
    context: str | None = None,
    confidence: float = 1.0,
    generate_embedding: bool = True,
    metadata: dict[str, Any] | None = None,
    user_identifier: str | None = None,   # <-- user-scoping kwarg (CONFIRMED name)
    applies_to: list | None = None,
) -> Preference
```

### add_fact

```python
await client.long_term.add_fact(
    subject: str,
    predicate: str,
    obj: str,                             # NOTE: 'obj', not 'object'
    *,
    confidence: float = 1.0,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    generate_embedding: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Fact
```

### add_entity

```python
await client.long_term.add_entity(
    name: str,
    entity_type: EntityType | str,
    *,
    subtype: str | None = None,
    description: str | None = None,
    aliases: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
    resolve: bool = True,
    generate_embedding: bool = True,
    deduplicate: bool = True,
    geocode: bool = True,
    enrich: bool = True,
    coordinates: tuple[float, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Entity, DeduplicationResult]
```

### get_context (on LongTermMemory)

```python
await client.long_term.get_context(query: str, **kwargs) -> str
```

---

## MemoryClient.get_context (top-level, combines short+long+reasoning)

```python
await client.get_context(
    query: str,
    *,
    session_id: str | None = None,
    include_short_term: bool = True,
    include_long_term: bool = True,
    include_reasoning: bool = True,
    max_items: int = 10,
) -> str
```

**Note:** `MemoryClient.get_context` does NOT accept `user_identifier` directly.
User scoping is handled by `client.users` (UserMemory) or by passing
`user_identifier` to the individual `add_*` methods on `long_term`.

---

## User-scoping kwarg: CONFIRMED name = `user_identifier`

- `add_preference` accepts `user_identifier: str | None = None` (confirmed).
- `get_preferences_for(user_identifier: str, ...)` uses it to retrieve scoped prefs.
- The spec's assumption of `user_identifier` is CORRECT.
- `client.users` property returns a `UserMemory` object for multi-tenant identity management.

---

## Other long_term search methods

```python
await client.long_term.search_preferences(query: str, *, category: str | None = None, limit: int = 10, threshold: float = 0.7) -> list[Preference]
await client.long_term.search_facts(query: str, *, limit: int = 10, threshold: float = 0.7) -> list[Fact]
await client.long_term.search_entities(query: str, *, entity_types: list | None = None, limit: int = 10, threshold: float = 0.7) -> list[Entity]
await client.long_term.get_preferences_for(user_identifier: str, *, applies_to: Any | None = None, active_only: bool = True, as_of: datetime | None = None) -> list[Preference]
await client.long_term.get_facts_about(entity_name: str) -> list[Fact]
```

---

## Mapping from spec assumptions to real API

| Spec assumption | Real name | Match? |
|---|---|---|
| `MemoryClient` | `MemoryClient` | YES |
| `MemorySettings` | `MemorySettings` | YES |
| `add_preference` | `add_preference` | YES |
| `add_fact` | `add_fact` | YES |
| `add_entity` | `add_entity` | YES |
| `get_context` | `get_context` (on MemoryClient AND LongTermMemory) | YES |
| `user_identifier` kwarg | `user_identifier` | YES (confirmed on add_preference, get_preferences_for) |
| `object` param on add_fact | `obj` | NO — actual param is `obj`, not `object` |

**Key difference:** `add_fact`'s third positional arg is `obj`, not `object`.
Task 3 must use `obj=` not `object=` when calling `add_fact`.

---

## Package/extra names for requirements.txt

```
neo4j-agent-memory[sentence-transformers]>=0.5.0
```

Extra `[sentence-transformers]` is valid and installs `sentence-transformers` v5.2.3.
