"""Agent state + structured-output schemas."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

IntentType = Literal[
    "factual", "eligibility", "procedural", "calculation", "definition", "other"
]


# ---- structured LLM outputs ------------------------------------------------

class IntakeResult(BaseModel):
    in_scope: bool = Field(description="True if about Australian individual income "
                                       "tax / tax returns (incl. deductions, super, "
                                       "CGT, Medicare levy, offsets).")
    unsafe: bool = Field(default=False, description="True if requesting tax evasion, "
                                                    "fraud, or how to deceive the ATO.")
    reason: str = Field(default="", description="Short reason for the routing.")


class QueryAnalysis(BaseModel):
    intent: IntentType = "factual"
    topics: list[str] = Field(default_factory=list,
                              description="Key tax topics, e.g. 'work-related car "
                                          "expenses', 'CGT discount'.")
    entities: list[str] = Field(default_factory=list,
                                description="Occupations, asset types, etc.")
    income_year: Optional[int] = Field(
        default=None, description="Income year the user asked about (year ending 30 "
                                  "June), if explicitly stated; else null.")
    needs_clarification: bool = False
    clarifying_question: str = ""


class SubQueries(BaseModel):
    queries: list[str] = Field(
        default_factory=list,
        description="1-4 focused search queries covering the question.")


class Triage(BaseModel):
    """One-shot intake + analysis + query planning (saves LLM round-trips)."""
    in_scope: bool = Field(
        description="True if about Australian individual income tax / tax returns "
                    "(incl. deductions, super, CGT, Medicare levy, offsets).")
    unsafe: bool = Field(
        default=False,
        description="True only if seeking tax evasion, fraud, or to deceive the ATO.")
    intent: IntentType = "factual"
    income_year: Optional[int] = Field(
        default=None,
        description="Income year the user named (year ending 30 June), else null.")
    entities: list[str] = Field(
        default_factory=list,
        description="Durable facts about the user worth remembering across "
                    "sessions: occupation, residency status, asset types, and "
                    "deduction-relevant facts such as work-from-home hours/weeks "
                    "(e.g. 'sole trader', 'foreign resident', 'rental property', "
                    "'works from home 37.5 hours per week for 48 weeks'). "
                    "Only include facts the user actually stated.")
    needs_clarification: bool = Field(
        default=False,
        description="True only when a quick missing detail (e.g. occupation, "
                    "residency) would materially change the answer.")
    clarifying_question: str = ""
    search_queries: list[str] = Field(
        default_factory=list,
        description="1-4 focused ATO search queries covering the question.")


class RelevanceGrade(BaseModel):
    sufficient: bool = Field(description="True if the retrieved context can answer "
                                         "the question.")
    refined_query: str = Field(default="", description="A better search query if not "
                                                       "sufficient.")


class FollowUps(BaseModel):
    questions: list[str] = Field(
        default_factory=list,
        description="2-4 short, natural follow-up questions the user might ask "
                    "next, each self-contained and answerable from ATO content.")


class GroundingCheck(BaseModel):
    grounded: bool = Field(description="True if every factual claim in the answer is "
                                       "supported by the provided sources.")
    issues: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class MemoryFacts(BaseModel):
    facts: list[str] = Field(
        default_factory=list,
        description="Key durable tax/profile facts the user explicitly stated and "
                    "may expect remembered across chats. Include occupation, "
                    "residency, income year, work patterns, work-from-home hours/"
                    "weeks, deductible expense facts, asset/rental/vehicle facts, "
                    "and other stable tax-return inputs. Exclude generic questions, "
                    "legal rules, assistant conclusions, and unstated facts.")


# ---- graph state -----------------------------------------------------------

class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    query: str
    user_profile: str               # facts recalled from long-term memory
    reasoning: bool                  # per-request "thinking mode" toggle
    route: str                       # 'answer' | 'refuse' | 'clarify'
    analysis: dict[str, Any]
    sub_queries: list[str]
    calculations: list[dict[str, str]]  # [{expression, result}] from the calculator
    retrieved: list[dict[str, Any]]  # serialized RetrievedChunk dicts
    draft: str
    verification: dict[str, Any]
    answer: str
    citations: list[dict[str, str]]
    related_links: list[dict[str, str]]
    suggestions: list[str]
    income_year_label: str
    retrieve_rounds: int
    verify_rounds: int
