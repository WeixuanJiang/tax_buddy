"""LLM clients (DeepSeek via OpenRouter, OpenAI-compatible)."""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from knowledge_engine.config import settings


def _headers() -> dict:
    # OpenRouter attribution (optional, recommended).
    return {
        "HTTP-Referer": settings.openrouter_app_url,
        "X-Title": settings.openrouter_app_title,
    }


@lru_cache(maxsize=8)
def get_llm(fast: bool = False, temperature: float = 0.0,
            reasoning: bool | None = None) -> ChatOpenAI:
    if reasoning is None:
        reasoning = settings.reasoning_enabled
    kwargs = dict(
        model=settings.fast_model if fast else settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers=_headers(),
        timeout=60,
        max_retries=2,
    )
    # When "thinking" is off, send OpenRouter's `reasoning: {enabled: false}` to
    # skip DeepSeek reasoning tokens (lower latency). extra_body is the channel;
    # fall back to model_kwargs on older SDKs.
    if not reasoning:
        body = {"reasoning": {"enabled": False}}
        try:
            return ChatOpenAI(**kwargs, extra_body=body)
        except Exception:
            return ChatOpenAI(**kwargs, model_kwargs={"extra_body": body})
    return ChatOpenAI(**kwargs)


def structured(schema, fast: bool = True, reasoning: bool | None = None):
    """Bind a Pydantic schema for structured output.

    Tries native function-calling; callers should be resilient (nodes wrap calls
    in try/except and fall back to safe defaults) because not every OpenRouter
    model implements tool-calling identically.
    """
    llm = get_llm(fast=fast, reasoning=reasoning)
    try:
        return llm.with_structured_output(schema, method="function_calling")
    except Exception:
        return llm.with_structured_output(schema, method="json_mode")
