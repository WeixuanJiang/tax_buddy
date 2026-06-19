"""Layer 1 — Deterministic evaluation.

Cheap, non-LLM checks over the agent's final state: routing/intent
classification, output formatting (disclaimer, income-year line, no template
leakage), citation integrity (every [n] marker resolves to a listed source),
source-domain validation, and PII leakage.

Every function here is pure given (case, state), so they are unit-testable
without a database or model and are the bulk of what runs in CI.
"""
from __future__ import annotations

import re

from knowledge_engine.agent import prompts

from .checks import Check
from .harness import EvalCase
from .pii import find_pii

_CITATION = re.compile(r"\[(\d+)\]")
# Leftover template tokens that indicate a formatting bug.
_TEMPLATE_TOKENS = ("{year_label}", "{year}", "{{", "}}")

# Intent equivalence: "factual" and "definition" are near-synonyms for a
# straight informational lookup, so we don't penalise the model for choosing
# either. Gross misclassification (e.g. a calculation labelled factual) still fails.
_INTENT_EQUIV = {"factual": "informational", "definition": "informational"}


def _intent_class(intent: str | None) -> str | None:
    return _INTENT_EQUIV.get(intent, intent)


def _is_answer(state: dict) -> bool:
    return state.get("route") == "answer"


def check_routing(case: EvalCase, state: dict) -> Check:
    """Intent classification at the routing level: refuse vs answer."""
    route = state.get("route", "")
    if case.expect == "refuse":
        ok = route == "refuse"
        return Check("deterministic", "routing", ok,
                     "" if ok else f"expected refuse, got {route!r}")
    # answer-expected: clarify is acceptable, refuse is not
    ok = route in {"answer", "clarify"}
    return Check("deterministic", "routing", ok,
                 "" if ok else f"expected answer, got {route!r}")


def check_intent(case: EvalCase, state: dict) -> Check:
    """Fine-grained intent classification accuracy (answer cases only)."""
    expected = case.expected_intent
    if expected is None or not _is_answer(state):
        return Check("deterministic", "intent", True, "n/a")
    got = (state.get("analysis") or {}).get("intent")
    ok = _intent_class(got) == _intent_class(expected)
    return Check("deterministic", "intent", ok,
                 "" if ok else f"expected intent {expected!r}, got {got!r}")


def check_disclaimer(case: EvalCase, state: dict) -> Check:
    if not _is_answer(state):
        return Check("deterministic", "disclaimer", True, "n/a")
    answer = state.get("answer", "")
    ok = prompts.DISCLAIMER in answer
    return Check("deterministic", "disclaimer", ok,
                 "" if ok else "general-info disclaimer missing from answer")


def check_income_year(case: EvalCase, state: dict) -> Check:
    if not _is_answer(state):
        return Check("deterministic", "income_year", True, "n/a")
    answer = state.get("answer", "")
    label = state.get("income_year_label", "")
    ok = bool(label) and f"{label} income year" in answer
    return Check("deterministic", "income_year", ok,
                 "" if ok else f"income-year line for {label!r} missing")


def check_no_template_leak(case: EvalCase, state: dict) -> Check:
    answer = state.get("answer", "")
    leaked = [t for t in _TEMPLATE_TOKENS if t in answer]
    return Check("deterministic", "no_template_leak", not leaked,
                 "" if not leaked else f"unrendered tokens: {leaked}")


def check_citation_integrity(case: EvalCase, state: dict) -> Check:
    """Every [n] in the answer must resolve to a listed citation, and an
    answer that draws on sources must cite at least one."""
    if not _is_answer(state):
        return Check("deterministic", "citation_integrity", True, "n/a")
    answer = state.get("answer", "")
    citations = state.get("citations", []) or []
    retrieved = state.get("retrieved", []) or []
    markers = {int(n) for n in _CITATION.findall(answer)}
    listed = {int(c["n"]) for c in citations if str(c.get("n", "")).isdigit()}

    dangling = markers - listed
    if dangling:
        return Check("deterministic", "citation_integrity", False,
                     f"answer references {sorted(dangling)} with no matching source")
    # If we had sources to ground in, the answer should cite something.
    if retrieved and not citations:
        return Check("deterministic", "citation_integrity", False,
                     "sources were retrieved but the answer cites none")
    return Check("deterministic", "citation_integrity", True)


def check_source_domain(case: EvalCase, state: dict) -> Check:
    """Cited URLs must be well-formed http(s) links (sourced from the ATO corpus)."""
    if not _is_answer(state):
        return Check("deterministic", "source_domain", True, "n/a")
    bad = [c.get("url", "") for c in (state.get("citations") or [])
           if not str(c.get("url", "")).startswith(("http://", "https://"))]
    return Check("deterministic", "source_domain", not bad,
                 "" if not bad else f"malformed citation URLs: {bad}")


def check_no_pii(case: EvalCase, state: dict) -> Check:
    answer = state.get("answer", "")
    hits = find_pii(answer)
    return Check("deterministic", "no_pii", not hits,
                 "" if not hits else
                 "leaked PII: " + ", ".join(f"{h.kind}:{h.value}" for h in hits[:3]))


def check_refusal_clean(case: EvalCase, state: dict) -> Check:
    """A refusal should be a non-empty redirect with no citations attached."""
    if case.expect != "refuse" or state.get("route") != "refuse":
        return Check("deterministic", "refusal_clean", True, "n/a")
    answer = (state.get("answer") or "").strip()
    cites = state.get("citations") or []
    ok = bool(answer) and not cites
    return Check("deterministic", "refusal_clean", ok,
                 "" if ok else "refusal empty or carried citations")


_CHECKS = (
    check_routing, check_intent, check_disclaimer, check_income_year,
    check_no_template_leak, check_citation_integrity, check_source_domain,
    check_no_pii, check_refusal_clean,
)


def evaluate(case: EvalCase, state: dict) -> list[Check]:
    return [fn(case, state) for fn in _CHECKS]
