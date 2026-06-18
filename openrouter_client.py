"""Shared OpenRouter HTTP client (embeddings + rerank)."""
from __future__ import annotations

from functools import lru_cache

import httpx

from knowledge_engine.config import settings


@lru_cache(maxsize=1)
def client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.openrouter_base_url,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_title,
        },
        timeout=120,
    )
