"""FastAPI service for the ATO tax-return knowledge engine.

  POST /ask         one-shot question (stateless)
  POST /chat        multi-turn (persists state per thread_id)
  POST /chat/stream multi-turn, streams the answer as Server-Sent Events
  GET  /health

Run:  uvicorn knowledge_engine.api.main:app --reload
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from knowledge_engine.agent.graph import build_graph
from knowledge_engine.api.models import AnswerResponse, AskRequest, ChatRequest
from knowledge_engine.config import settings

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Stateless graph for /ask
    _state["graph"] = build_graph()
    # Persistent graph for /chat (Postgres checkpointer)
    try:
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        pool = ConnectionPool(settings.database_url, max_size=8, open=True,
                              kwargs={"autocommit": True})
        saver = PostgresSaver(pool)
        saver.setup()
        _state["pool"] = pool
        _state["chat_graph"] = build_graph(checkpointer=saver)
    except Exception as e:  # noqa: BLE001 - chat persistence optional
        print(f"[warn] chat checkpointer unavailable ({e}); /chat falls back to stateless")
        _state["chat_graph"] = _state["graph"]
    yield
    pool = _state.get("pool")
    if pool:
        pool.close()


app = FastAPI(title="ATO Tax-Return Knowledge Engine", lifespan=lifespan)

# Allow the local Vite dev server (and same-origin prod) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_response(s: dict) -> AnswerResponse:
    return AnswerResponse(
        answer=s.get("answer", ""),
        route=s.get("route", "answer"),
        clarification_needed=s.get("route") == "clarify",
        income_year=s.get("income_year_label") or settings.tax_year_label,
        citations=s.get("citations", []),
        related_links=s.get("related_links", []),
        suggestions=s.get("suggestions", []),
    )


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


@app.get("/health")
def health():
    return {"status": "ok", "model": settings.openrouter_model,
            "tax_year": settings.tax_year_label}


@app.post("/ask", response_model=AnswerResponse)
def ask(req: AskRequest):
    try:
        s = _state["graph"].invoke({
            "messages": [HumanMessage(req.question)], "query": req.question,
            "reasoning": req.reasoning,
        })
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"agent error: {e}")
    return _to_response(s)


@app.post("/chat", response_model=AnswerResponse)
def chat(req: ChatRequest):
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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream the answer token-by-token (SSE).

    Emits `token` events while the `synthesize` node generates the answer, then a
    single `done` event carrying the finalized answer + citations + related links.
    """
    uid = req.user_id or req.thread_id
    cfg = {"configurable": {"thread_id": req.thread_id}}
    inp = {"messages": [HumanMessage(req.question)], "query": req.question,
           "reasoning": req.reasoning, "user_profile": _memory_read(uid)}

    stages = {
        "triage": "Understanding your question",
        "retrieve": "Searching ATO content",
        "compute": "Calculating",
        "synthesize": "Writing the answer",
        "verify": "Checking the sources",
        "finalize": "Finishing up",
    }

    def gen():
        final = None
        try:
            for mode, data in _state["chat_graph"].stream(
                inp, cfg, stream_mode=["updates", "messages", "values"]
            ):
                if mode == "updates":
                    for node in data:
                        if node in stages:
                            yield _sse("stage", {"node": node, "label": stages[node]})
                elif mode == "messages":
                    chunk, meta = data
                    if meta.get("langgraph_node") == "synthesize":
                        text = getattr(chunk, "content", "") or ""
                        if text:
                            yield _sse("token", {"text": text})
                elif mode == "values":
                    final = data
            _memory_write(uid, final or {})
            yield _sse("done", _to_response(final or {}).model_dump())
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
