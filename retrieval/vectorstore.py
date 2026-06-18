"""Hybrid retrieval over pgvector: dense (cosine) + sparse (BM25/tsvector),
fused with Reciprocal Rank Fusion. All queries are filtered to the current income
year + evergreen content.
"""
from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine.config import settings
from knowledge_engine.db import get_conn
from knowledge_engine.ingestion.embed import embed_query


@dataclass
class Candidate:
    chunk_id: int
    doc_url: str
    heading: str
    breadcrumb: str
    chunk_text: str
    has_table: bool
    income_year: int | None
    category: str
    score: float = 0.0


_YEAR_FILTER = "(income_year = %(year)s OR income_year IS NULL)"


def _dense(cur, query: str, top_k: int, category: str | None):
    qv = embed_query(query)
    cat = "AND category = %(cat)s" if category else ""
    cur.execute(
        f"""
        SELECT id, doc_url, heading, breadcrumb, chunk_text, has_table,
               income_year, category
        FROM chunks
        WHERE {_YEAR_FILTER} {cat}
        ORDER BY embedding <=> %(qv)s::vector
        LIMIT %(k)s
        """,
        {"qv": qv, "k": top_k, "year": settings.current_tax_year, "cat": category},
    )
    return cur.fetchall()


def _sparse(cur, query: str, top_k: int, category: str | None):
    cat = "AND category = %(cat)s" if category else ""
    cur.execute(
        f"""
        SELECT id, doc_url, heading, breadcrumb, chunk_text, has_table,
               income_year, category
        FROM chunks
        WHERE tsv @@ websearch_to_tsquery('english', %(q)s) AND {_YEAR_FILTER} {cat}
        ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %(q)s)) DESC
        LIMIT %(k)s
        """,
        {"q": query, "k": top_k, "year": settings.current_tax_year, "cat": category},
    )
    return cur.fetchall()


def _row_to_candidate(row) -> Candidate:
    return Candidate(
        chunk_id=row[0], doc_url=row[1], heading=row[2], breadcrumb=row[3],
        chunk_text=row[4], has_table=row[5], income_year=row[6], category=row[7],
    )


def hybrid_search(query: str, top_k: int | None = None,
                  category: str | None = None, rrf_k: int = 60) -> list[Candidate]:
    """Return RRF-fused candidates from dense + sparse retrieval."""
    top_k = top_k or settings.hybrid_top_k
    with get_conn() as conn, conn.cursor() as cur:
        dense_rows = _dense(cur, query, top_k, category)
        sparse_rows = _sparse(cur, query, top_k, category)

    scores: dict[int, float] = {}
    cands: dict[int, Candidate] = {}
    for rows in (dense_rows, sparse_rows):
        for rank, row in enumerate(rows):
            cid = row[0]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            cands.setdefault(cid, _row_to_candidate(row))

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for cid, sc in ordered:
        c = cands[cid]
        c.score = sc
        out.append(c)
    return out
