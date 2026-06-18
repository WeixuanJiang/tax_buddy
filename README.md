# ATO Tax-Return Knowledge Engine

An LLM-agent (LangGraph) + RAG service that answers **Australian individual
tax-return** questions, grounded only in the extracted ATO content in `../output/`,
with source citations and a general-info disclaimer.

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
- **Store:** Postgres + pgvector. **API:** FastAPI.
- **Corpus:** current income year + evergreen pages only (avoids stale year versions).

## Run with Docker (full stack)

Everything (Postgres+pgvector, the API, the web UI) runs in containers.

```bash
cd knowledge_engine
cp .env.example .env          # set OPENROUTER_API_KEY (model defaults to deepseek/deepseek-v4-flash)

docker compose up -d --build  # builds api + web, starts db/api/web

# one-time: load the corpus into the DB (embeds via OpenRouter; a few minutes)
docker compose run --rm api python -m knowledge_engine.ingestion.ingest

# open the app
#   web UI   -> http://localhost:5173
#   API docs -> http://localhost:8000/docs
#   health   -> http://localhost:8000/health
```

Compose wires the services together: the web container's nginx proxies `/api/*`
to the API, and the API talks to the `db` service. Embedding/rerank model weights
are cached in the `models` volume; the corpus is mounted read-only from `../output`.
Re-run the `ingest` command after changing `CURRENT_TAX_YEAR` or the source data.

## Setup (run locally, without Docker for the app)

```bash
# 1. Python deps (a venv is recommended)
pip install -r requirements.txt

# 2. Config
cp .env.example .env          # then edit OPENROUTER_API_KEY (+ confirm model slug)

# 3. Database (Postgres + pgvector)
docker compose up -d          # exposes localhost:5433

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

## Layout

```
knowledge_engine/
  config.py            settings (.env)
  db.py                pgvector-aware connection
  docker-compose.yml   postgres + pgvector
  ingestion/  parse.py chunk.py embed.py ingest.py schema.sql
  retrieval/  vectorstore.py (hybrid+RRF) rerank.py retriever.py
  agent/      state.py prompts.py llm.py nodes.py graph.py
  api/        models.py main.py
  eval/       questions.yaml run_eval.py
```

## Notes / knobs
- `CURRENT_TAX_YEAR` (default 2026 = 2025-26) selects the served income year; only
  evergreen + that year are indexed. Prior-year questions are out-of-corpus by design.
- Confirm the exact DeepSeek slug on OpenRouter (`OPENROUTER_MODEL`); if a model
  lacks tool-calling, `agent/llm.py` falls back to JSON-mode structured output.
- First run downloads the embedding/rerank models (~hundreds of MB).
- Retrieval knobs (`HYBRID_TOP_K`, `RERANK_TOP_N`, loop caps) live in `.env`.
