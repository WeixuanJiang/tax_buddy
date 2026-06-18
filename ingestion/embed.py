"""Embeddings via OpenRouter (qwen/qwen3-embedding-8b, OpenAI-compatible).

Qwen3-Embedding works best with an instruction prefix on *queries*; passages are
embedded as-is. Vectors are returned at EMBED_DIM (4096 by default; the model
supports Matryoshka reduction via the `dimensions` param).
"""
from __future__ import annotations

import time

from knowledge_engine.config import settings
from knowledge_engine.openrouter_client import client

_QUERY_INSTRUCT = (
    "Instruct: Given a tax-return question, retrieve relevant ATO guidance "
    "passages.\nQuery: "
)


def _embed(inputs: list[str]) -> list[list[float]]:
    payload = {
        "model": settings.embed_model,
        "input": inputs,
        "dimensions": settings.embed_dim,
    }
    last = None
    for attempt in range(4):
        try:
            r = client().post("/embeddings", json=payload)
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            # Coerce to float: providers sometimes return an int (e.g. 0) mixed
            # with floats, which pgvector's adapter refuses to dump.
            return [[float(x) for x in d["embedding"]] for d in data]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"embeddings request failed: {last}")


def embed_passages(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        out.extend(_embed(texts[i:i + batch_size]))
        if len(texts) > batch_size:
            print(f"  embedded {min(i + batch_size, len(texts))}/{len(texts)}",
                  flush=True)
    return out


def embed_query(text: str) -> list[float]:
    return _embed([_QUERY_INSTRUCT + text])[0]
