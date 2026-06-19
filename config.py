"""Central configuration, loaded from environment / .env (pydantic-settings)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # OpenRouter (chat)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(default="deepseek/deepseek-chat", alias="OPENROUTER_MODEL")
    openrouter_fast_model: str = Field(default="", alias="OPENROUTER_FAST_MODEL")
    openrouter_app_url: str = Field(default="http://localhost:8000", alias="OPENROUTER_APP_URL")
    openrouter_app_title: str = Field(
        default="ATO Tax-Return Knowledge Engine", alias="OPENROUTER_APP_TITLE"
    )
    # DeepSeek "thinking" tokens add latency; off by default for this Q&A use.
    reasoning_enabled: bool = Field(default=False, alias="REASONING_ENABLED")

    # Database
    database_url: str = Field(
        default="postgresql://ato:ato@localhost:5433/ato_kb", alias="DATABASE_URL"
    )

    # Corpus
    current_tax_year: int = Field(default=2026, alias="CURRENT_TAX_YEAR")
    data_dir: str = Field(default=str(BASE_DIR.parent / "output"), alias="DATA_DIR")

    # Embeddings (OpenRouter; qwen3-embedding-8b is 4096-dim, supports MRL)
    embed_model: str = Field(default="qwen/qwen3-embedding-8b", alias="EMBED_MODEL")
    embed_dim: int = Field(default=4096, alias="EMBED_DIM")

    # Reranker (OpenRouter /rerank, Cohere)
    rerank_model: str = Field(default="cohere/rerank-4-fast", alias="RERANK_MODEL")

    # Retrieval knobs
    hybrid_top_k: int = Field(default=40, alias="HYBRID_TOP_K")
    rerank_top_n: int = Field(default=8, alias="RERANK_TOP_N")
    retrieve_max_rounds: int = Field(default=2, alias="RETRIEVE_MAX_ROUNDS")
    verify_max_rounds: int = Field(default=1, alias="VERIFY_MAX_ROUNDS")

    # --- Long-term memory (trial: neo4j-labs/agent-memory) ---
    memory_enabled: bool = Field(default=False, alias="MEMORY_ENABLED")
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")
    # Memory reuses the corpus embedding model/dims (EMBED_MODEL / EMBED_DIM,
    # qwen via OpenRouter) — see agent/memory.py — so there is no separate
    # memory embedding setting.

    @property
    def fast_model(self) -> str:
        return self.openrouter_fast_model or self.openrouter_model

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def tax_year_label(self) -> str:
        """ATO income-year label, e.g. year folder 2026 -> '2025-26'."""
        y = self.current_tax_year
        return f"{y - 1}-{str(y)[-2:]}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
