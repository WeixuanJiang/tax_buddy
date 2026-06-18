"""End-to-end retrieval: hybrid search -> rerank -> parent-doc enrichment.

Public:
  retrieve(query, category, top_n) -> list[RetrievedChunk]
  get_document(url) -> dict     # full page, for parent-document expansion
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

from knowledge_engine.config import settings
from knowledge_engine.db import get_conn
from knowledge_engine.retrieval.rerank import rerank_candidates
from knowledge_engine.retrieval.vectorstore import hybrid_search


@dataclass
class RetrievedChunk:
    url: str
    title: str
    heading: str
    breadcrumb: str
    text: str
    income_year: int | None
    has_table: bool
    score: float


def _titles_for(urls: list[str]) -> dict[str, str]:
    if not urls:
        return {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT url, title FROM documents WHERE url = ANY(%s)", (urls,))
        return {u: t for u, t in cur.fetchall()}


def retrieve(query: str, category: str | None = None,
             top_n: int | None = None) -> list[RetrievedChunk]:
    cands = hybrid_search(query, category=category)
    top = rerank_candidates(query, cands, top_n=top_n)
    titles = _titles_for(list({c.doc_url for c in top}))
    return [
        RetrievedChunk(
            url=c.doc_url, title=titles.get(c.doc_url, ""), heading=c.heading,
            breadcrumb=c.breadcrumb, text=c.chunk_text, income_year=c.income_year,
            has_table=c.has_table, score=round(c.score, 4),
        )
        for c in top
    ]


def get_document(url: str) -> dict | None:
    """Full page for parent-document expansion."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT url,title,description,category,breadcrumb,income_year,doc_type,"
            "nat_number,date_updated,content_text,child_links FROM documents WHERE url=%s",
            (url,),
        )
        row = cur.fetchone()
    if not row:
        return None
    keys = ["url", "title", "description", "category", "breadcrumb", "income_year",
            "doc_type", "nat_number", "date_updated", "content_text", "child_links"]
    return dict(zip(keys, row))


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True)
    ap.add_argument("--category", default=None)
    ap.add_argument("--n", type=int, default=settings.rerank_top_n)
    args = ap.parse_args()
    for i, r in enumerate(retrieve(args.q, category=args.category, top_n=args.n), 1):
        print(f"\n[{i}] score={r.score} year={r.income_year} table={r.has_table}")
        print(f"    {r.title}  ({r.heading})")
        print(f"    {r.url}")
        print(f"    {r.text[:220].replace(chr(10), ' ')}")


if __name__ == "__main__":
    _cli()
