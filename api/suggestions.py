"""AI-recommended starter questions, tailored to a user's occupation.

Generated once per user (the route caches the result in the users table), so the
LLM cost is paid a single time rather than on every empty-state render.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from knowledge_engine.agent.llm import structured

N_SUGGESTIONS = 6


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _fallback(occupation: str) -> list[str]:
    """Template questions used when the LLM is unavailable or returns nothing.

    Mirrors the previous client-side behaviour so the empty state is never blank.
    """
    occ = (occupation or "").strip()
    if not occ:
        return [
            "How do I amend my tax return after lodging?",
            "What can I claim for working from home?",
            "How does the capital gains tax discount work?",
            "Can I claim a deduction for personal super contributions?",
            "What is the Medicare levy and what rate do I pay?",
            "What records do I need to keep for my deductions?",
        ]
    a = _article(occ)
    return [
        f"What work-related expenses can I claim as {a} {occ}?",
        f"Can I claim tools, equipment, or a uniform as {a} {occ}?",
        f"What car and travel expenses can I claim as {a} {occ}?",
        f"What self-education or training can {a} {occ} deduct?",
        "What can I claim for working from home?",
        "How does the capital gains tax discount work?",
    ]


class _Suggestions(BaseModel):
    questions: list[str] = Field(
        default_factory=list,
        description="Starter tax-return questions tailored to the occupation.",
    )


_SYSTEM = (
    "You suggest starter questions for an Australian individual income tax-return "
    "assistant grounded in ATO content. Given a person's occupation, propose "
    f"{N_SUGGESTIONS} short, natural questions they would plausibly ask. "
    "Rules: write in the first person ('I'/'my'); keep each under ~14 words; make "
    "them specific to the occupation's likely deductions, income, and records "
    "where relevant, but include one or two broadly useful ones; cover general "
    "tax-return topics only (deductions, work expenses, income, offsets, records, "
    "CGT, super); do not give advice or answers; no numbering or punctuation tricks."
)


def generate_suggestions(occupation: str) -> list[str]:
    """Generate occupation-tailored starter questions; fall back to templates."""
    occ = (occupation or "").strip()
    try:
        llm = structured(_Suggestions, fast=True, reasoning=False)
        result = llm.invoke([
            SystemMessage(_SYSTEM),
            HumanMessage(f"Occupation: {occ or 'unspecified'}"),
        ])
        questions = [q.strip() for q in (result.questions or []) if q and q.strip()]
        # De-dupe while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for q in questions:
            key = q.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(q)
        if deduped:
            return deduped[:N_SUGGESTIONS]
    except Exception as e:  # noqa: BLE001 - never let suggestions break the page
        print(f"[warn] suggestion generation failed ({e}); using fallback")
    return _fallback(occ)
