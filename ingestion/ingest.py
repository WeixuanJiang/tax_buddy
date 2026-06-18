"""Ingestion pipeline: JSON pages -> filter (current year + evergreen) -> chunk ->
embed -> Postgres (documents, chunks).

Run:  python -m knowledge_engine.ingestion.ingest
Idempotent: truncates and rebuilds both tables on each run.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import psycopg
from pgvector.psycopg import register_vector

from knowledge_engine.config import settings
from knowledge_engine.ingestion import parse
from knowledge_engine.ingestion.chunk import chunk_document
from knowledge_engine.ingestion.embed import embed_passages

SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")
SKIP = {"_failures.json", "index.json"}


def load_pages() -> list[dict]:
    files = [
        f for f in glob.glob(os.path.join(str(settings.data_path), "**", "*.json"),
                             recursive=True)
        if os.path.basename(f) not in SKIP
    ]
    pages = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                pages.append(json.load(fh))
        except Exception as e:  # noqa: BLE001
            print(f"  ! skip unreadable {f}: {e}")
    return pages


def in_corpus(url: str) -> bool:
    """Current-year-only policy: keep evergreen + the configured income year."""
    y = parse.income_year(url)
    return y is None or y == settings.current_tax_year


def build_records(pages: list[dict]):
    docs, chunk_rows = [], []
    for p in pages:
        url = p.get("url")
        if not url or not in_corpus(url):
            continue
        bc = parse.breadcrumb(url)
        yr = parse.income_year(url)
        dtype = parse.doc_type(url)
        cat = p.get("category", "")
        docs.append((
            url, p.get("title", ""), p.get("description", ""), cat, bc, yr, dtype,
            p.get("nat_number", ""), p.get("date_updated", ""),
            p.get("content_text", ""), json.dumps(p.get("child_links", [])),
        ))
        for c in chunk_document(p, bc):
            chunk_rows.append({
                "doc_url": url, "heading": c.heading, "breadcrumb": bc,
                "chunk_text": c.chunk_text, "has_table": c.has_table,
                "token_count": c.token_count, "income_year": yr, "category": cat,
            })
    return docs, chunk_rows


def main() -> int:
    print(f"Data dir: {settings.data_path}")
    print(f"Corpus: evergreen + income year {settings.current_tax_year} "
          f"({settings.tax_year_label})")
    pages = load_pages()
    print(f"Loaded {len(pages)} JSON pages from disk")

    docs, chunk_rows = build_records(pages)
    print(f"In-corpus documents: {len(docs)}  | chunks: {len(chunk_rows)}")
    if not chunk_rows:
        print("Nothing to ingest. Check DATA_DIR / CURRENT_TAX_YEAR.")
        return 1

    print(f"Embedding {len(chunk_rows)} chunks with {settings.embed_model} ...")
    vectors = embed_passages([c["chunk_text"] for c in chunk_rows])

    with psycopg.connect(settings.database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Drop + recreate so embedding-dimension changes take effect cleanly.
            cur.execute("DROP TABLE IF EXISTS chunks CASCADE;")
            cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
            with open(SCHEMA, encoding="utf-8") as fh:
                cur.execute(fh.read())
        conn.commit()
        register_vector(conn)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO documents (url,title,description,category,breadcrumb,"
                "income_year,doc_type,nat_number,date_updated,content_text,child_links)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                docs,
            )
            params = [
                (c["doc_url"], c["heading"], c["breadcrumb"], c["chunk_text"],
                 c["has_table"], c["token_count"], c["income_year"], c["category"], v)
                for c, v in zip(chunk_rows, vectors)
            ]
            cur.executemany(
                "INSERT INTO chunks (doc_url,heading,breadcrumb,chunk_text,has_table,"
                "token_count,income_year,category,embedding)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                params,
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents")
            nd = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM chunks")
            nc = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM chunks WHERE has_table")
            nt = cur.fetchone()[0]
    print(f"Done. documents={nd}  chunks={nc}  chunks_with_table={nt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
