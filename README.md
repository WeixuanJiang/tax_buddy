# Roboti Tax

An LLM-agent (LangGraph) + RAG service that answers **Australian individual
tax-return** questions, grounded only in the extracted ATO content in `../output/`,
with source citations and a general-info disclaimer. The web UI is branded as
Roboti Tax.

- **Orchestration:** LangGraph state graph (intake → analyze → plan → retrieve →
  grade → synthesize → verify → finalize, with clarification & refusal branches).
- **LLM:** DeepSeek via OpenRouter (OpenAI-compatible).
- **Retrieval:** hybrid (pgvector cosine + Postgres BM25/tsvector, fused by RRF) →
  rerank → parent-document enrichment.
- **Embeddings:** OpenRouter `qwen/qwen3-embedding-8b` (4096-dim; exact search since
  that exceeds pgvector's 2000-dim index limit — trivial for ~9k rows).
- **Reranker:** OpenRouter `/rerank` with `cohere/rerank-4-fast` (API, no local ML).
- **Streaming:** `POST /chat/stream` (SSE) streams the answer token-by-token + stage
  events; the web UI renders progressively.
- **Accounts + history:** FastAPI auth stores users in Postgres; the sidebar lists
  saved chat threads per user.
- **Memory:** optional Neo4j long-term memory stores durable user tax/profile facts.
  Extraction runs when a chat is closed, not after every question.
- **Tax-agent fallback:** optional Google Places Text Search recommends nearby tax
  agents from the user's postcode when ATO grounding is unavailable or confidence is low.
- **Store:** Postgres + pgvector, Neo4j for optional memory. **API:** FastAPI.
- **Corpus:** current income year + evergreen pages only (avoids stale year versions).

## Run with Docker (full stack)

Everything (Postgres+pgvector, Neo4j, the API, and the web UI) runs in containers.

```bash
cd knowledge_engine
cp .env.example .env          # set OPENROUTER_API_KEY, AUTH_SECRET, NEO4J_PASSWORD

docker compose up -d --build  # builds api + web, starts db/neo4j/api/web

# one-time: load the corpus into the DB (embeds via OpenRouter; a few minutes)
docker compose run --rm api python -m knowledge_engine.ingestion.ingest

# open the app
#   web UI   -> http://localhost:5173
#   API docs -> http://localhost:8000/docs
#   health   -> http://localhost:8000/health
#   Neo4j UI -> http://localhost:7474
```

Compose wires the services together: the web container's nginx proxies `/api/*`
to the API, and the API talks to the `db` and `neo4j` services. The corpus is
mounted read-only from `../output`. Re-run the `ingest` command after changing
`CURRENT_TAX_YEAR` or the source data.

The Google Places fallback is disabled unless `GOOGLE_MAPS_API_KEY` is set. It
uses a Text Search query like `tax agent near <postcode>` and renders up to five
results in a table with address, contact number, and Google rating. It does not
show Google Maps URLs.

## Setup (run locally, without Docker for the app)

```bash
# 1. Python deps (a venv is recommended)
pip install -r requirements.txt

# 2. Config
cp .env.example .env          # then edit OPENROUTER_API_KEY, AUTH_SECRET, NEO4J_PASSWORD

# 3. Datastores (Postgres + pgvector, Neo4j)
docker compose up -d          # exposes localhost:5433, 7474, 7687

# 4. Ingest the corpus  (run from the repo root: .../ato_data)
cd ..
python -m knowledge_engine.ingestion.ingest
#   -> documents=~1279  chunks=~9000

# 5. Try it
python -m knowledge_engine.retrieval.retriever --q "medicare levy threshold"
python -m knowledge_engine.agent.graph --q "how do I amend my tax return?"

# 6. Serve
uvicorn knowledge_engine.api.main:app --reload
#   POST /ask   {"question": "..."}
#   POST /chat  {"question": "...", "thread_id": "abc"}
#   POST /chat/stream
#   GET/DELETE /conversations/{thread_id}
#   POST /conversations/{thread_id}/close
#   GET  /health

# 7. Web UI (React) — in a second terminal
cd knowledge_engine/web && npm install && npm run dev   # http://localhost:5173
```

The React chat UI lives in [`web/`](web/README.md) and talks to this API.

> Run module commands from the **`ato_data`** directory so `knowledge_engine` is
> importable as a package.

## Evaluation

```bash
python -m knowledge_engine.eval.run_eval               # retrieval recall + agent routing
python -m knowledge_engine.eval.run_eval --mode retrieval
```

## Accounts, Memory, and History

- Register/login requires `AUTH_SECRET`.
- Each user profile stores username, password hash, occupation, and postcode in
  Postgres. The postcode is used only for nearby tax-agent lookup.
- Short-term chat turns are saved to Neo4j so the history sidebar can reopen
  conversations.
- Long-term memory is optional (`MEMORY_ENABLED=true`). When the current chat is
  closed through `New question` or logout, the API schedules a background memory
  extraction task. The UI does not wait for that LLM call.
- Deleting a chat removes its Postgres history row and Neo4j short-term messages.

## Layout

```
knowledge_engine/
  config.py            settings (.env)
  db.py                pgvector-aware connection
  docker-compose.yml   postgres + pgvector + neo4j
  ingestion/  parse.py chunk.py embed.py ingest.py schema.sql
  retrieval/  vectorstore.py (hybrid+RRF) rerank.py retriever.py
  agent/      state.py prompts.py llm.py nodes.py graph.py memory.py
  api/        models.py main.py users.py conversations.py tax_agents.py
  eval/       questions.yaml run_eval.py
```

## Notes / knobs
- `CURRENT_TAX_YEAR` (default 2026 = 2025-26) selects the served income year; only
  evergreen + that year are indexed. Prior-year questions are out-of-corpus by design.
- Confirm the exact DeepSeek slug on OpenRouter (`OPENROUTER_MODEL`); if a model
  lacks tool-calling, `agent/llm.py` falls back to JSON-mode structured output.
- Retrieval knobs (`HYBRID_TOP_K`, `RERANK_TOP_N`, loop caps) live in `.env`.
- `MEMORY_ENABLED`, `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` control
  cross-chat user memory.
- `GOOGLE_MAPS_API_KEY` enables tax-agent recommendations; `TAX_AGENT_MAX_RESULTS`
  caps results at a maximum of 5.
