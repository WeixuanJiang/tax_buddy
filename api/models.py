"""API request/response schemas."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2)
    reasoning: bool = Field(default=False, description="Enable LLM 'thinking' mode.")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    occupation: str = Field(..., min_length=1)
    postcode: str = Field(...)

    @field_validator("username")
    @classmethod
    def _username_chars(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError("username may contain only letters, digits, underscore")
        return v

    @field_validator("postcode")
    @classmethod
    def _postcode_au(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("postcode must be exactly 4 digits")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    username: str
    occupation: str | None = None


class Message(BaseModel):
    role: str
    content: str


class ConversationSummary(BaseModel):
    thread_id: str
    title: str
    updated_at: str


class ConversationDetail(BaseModel):
    thread_id: str
    messages: list[Message] = []


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


class SuggestionsResponse(BaseModel):
    """Starter questions for the empty state, tailored to the user's work."""
    occupation: str | None = None
    suggestions: list[str] = []
