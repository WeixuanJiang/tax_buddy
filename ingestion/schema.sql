-- ATO knowledge-base schema (Postgres + pgvector).
-- Embedding dimension must match EMBED_DIM (qwen3-embedding-8b = 4096).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    url            TEXT PRIMARY KEY,
    title          TEXT,
    description    TEXT,
    category       TEXT,
    breadcrumb     TEXT,
    income_year    INTEGER,          -- NULL = evergreen (no year in URL)
    doc_type       TEXT,             -- topic | mytax-instruction | paper-instruction | occupation-guide | landing
    nat_number     TEXT,
    date_updated   TEXT,
    content_text   TEXT,
    child_links    JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    doc_url      TEXT NOT NULL REFERENCES documents(url) ON DELETE CASCADE,
    heading      TEXT,
    breadcrumb   TEXT,
    chunk_text   TEXT NOT NULL,
    has_table    BOOLEAN DEFAULT FALSE,
    token_count  INTEGER,
    income_year  INTEGER,
    category     TEXT,
    embedding    vector(4096),
    tsv          tsvector
);

-- Full-text vector kept in sync by trigger.
CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('english', coalesce(NEW.heading,'') || ' ' || coalesce(NEW.chunk_text,''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_tsv_trg ON chunks;
CREATE TRIGGER chunks_tsv_trg BEFORE INSERT OR UPDATE
    ON chunks FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();

-- Indexes. Note: pgvector HNSW/IVFFlat cap at 2000 dims, and 4096 exceeds that,
-- so dense search uses an exact (sequential) scan — trivial for ~9k rows.
CREATE INDEX IF NOT EXISTS chunks_tsv_idx        ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_year_idx       ON chunks (income_year);
CREATE INDEX IF NOT EXISTS chunks_category_idx   ON chunks (category);
