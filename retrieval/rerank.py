"""Rerank hybrid candidates via OpenRouter /rerank (Cohere rerank-4-fast).

API-based, so no local cross-encoder / torch. On any error we fall back to the
RRF order from hybrid search.
"""
from __future__ import annotations

from knowledge_engine.config import settings
from knowledge_engine.openrouter_client import client
from knowledge_engine.retrieval.vectorstore import Candidate


def rerank_candidates(query: str, candidates: list[Candidate],
                      top_n: int | None = None) -> list[Candidate]:
    top_n = top_n or settings.rerank_top_n
    if not candidates:
        return []
    try:
        r = client().post("/rerank", json={
            "model": settings.rerank_model,
            "query": query,
            "documents": [c.chunk_text for c in candidates],
            "top_n": top_n,
        })
        r.raise_for_status()
        results = r.json()["results"]
        out = []
        for item in results:
            c = candidates[item["index"]]
            c.score = float(item.get("relevance_score", c.score))
            out.append(c)
        return out[:top_n]
    except Exception:
        return candidates[:top_n]
