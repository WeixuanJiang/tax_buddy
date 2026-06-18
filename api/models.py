"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2)
    reasoning: bool = Field(default=False, description="Enable LLM 'thinking' mode.")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2)
    thread_id: str = Field(..., description="Conversation id for multi-turn memory.")
    reasoning: bool = Field(default=False, description="Enable LLM 'thinking' mode.")


class Citation(BaseModel):
    n: str
    title: str
    url: str


class Link(BaseModel):
    title: str
    url: str


class AnswerResponse(BaseModel):
    answer: str
    route: str                       # answer | refuse | clarify
    clarification_needed: bool = False
    income_year: str | None = None
    citations: list[Citation] = []
    related_links: list[Link] = []
    suggestions: list[str] = []
