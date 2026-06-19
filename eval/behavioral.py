"""Layer 3 — Behavioral evaluation.

Examines the agent's internal actions rather than its text: which nodes fired,
how many retrieval rounds it took, whether it looped, whether it made wasteful
tool calls, and whether cheap paths (refuse/clarify) short-circuited before the
expensive retrieve→synthesize→verify pipeline.

Pure functions over a `Trace`, so they're unit-testable with a synthetic trace.
"""
from __future__ import annotations

from knowledge_engine.config import settings

from .checks import Check
from .harness import EvalCase, Trace

# Nodes that cost a DB hit or an LLM call; a refusal should touch none of them.
_EXPENSIVE_NODES = ("retrieve", "compute", "synthesize", "verify")
_MAX_COMPUTE_CALCS = 4  # the calculator loop in nodes.compute is bounded to 4


def check_refuse_short_circuits(case: EvalCase, trace: Trace) -> Check:
    """Out-of-scope / unsafe questions must not run retrieval or synthesis."""
    if case.expect != "refuse":
        return Check("behavioral", "refuse_short_circuit", True, "n/a")
    wasted = [n for n in _EXPENSIVE_NODES if trace.visited(n)]
    return Check("behavioral", "refuse_short_circuit", not wasted,
                 "" if not wasted else f"refusal still ran expensive nodes: {wasted}")


def check_answer_pipeline(case: EvalCase, trace: Trace) -> Check:
    """Answerable questions should flow through the full grounding pipeline."""
    if case.expect != "answer" or trace.state.get("route") != "answer":
        return Check("behavioral", "answer_pipeline", True, "n/a")
    required = ("retrieve", "synthesize", "verify", "finalize")
    missing = [n for n in required if not trace.visited(n)]
    return Check("behavioral", "answer_pipeline", not missing,
                 "" if not missing else f"answer skipped nodes: {missing}")


def check_retrieve_rounds_bounded(case: EvalCase, trace: Trace) -> Check:
    """No retrieval loops beyond the configured cap."""
    rounds = trace.state.get("retrieve_rounds", 0)
    cap = settings.retrieve_max_rounds
    ok = rounds <= cap
    return Check("behavioral", "retrieve_rounds_bounded", ok,
                 "" if ok else f"retrieve ran {rounds} rounds (cap {cap})",
                 score=float(rounds))


def check_no_loops(case: EvalCase, trace: Trace) -> Check:
    """A node firing far more than its allowed rounds signals a stuck loop."""
    cap = settings.retrieve_max_rounds
    retrieve_visits = trace.visit_count("retrieve")
    ok = retrieve_visits <= cap
    return Check("behavioral", "no_loops", ok,
                 "" if ok else f"retrieve node fired {retrieve_visits}x (cap {cap})")


def check_no_duplicate_retrieval(case: EvalCase, trace: Trace) -> Check:
    """Retrieved context must be de-duplicated (no repeated url+heading chunks)."""
    retrieved = trace.state.get("retrieved", []) or []
    keys = [(c.get("url"), c.get("heading")) for c in retrieved]
    dupes = len(keys) - len(set(keys))
    return Check("behavioral", "no_duplicate_retrieval", dupes == 0,
                 "" if dupes == 0 else f"{dupes} duplicate retrieved chunk(s)")


def check_tool_use_appropriate(case: EvalCase, trace: Trace) -> Check:
    """The calculator should be used for calculation intent and left alone
    otherwise; when used it must stay within its bounded loop."""
    calcs = trace.state.get("calculations", []) or []
    intent = (trace.state.get("analysis") or {}).get("intent")
    if len(calcs) > _MAX_COMPUTE_CALCS:
        return Check("behavioral", "tool_use_appropriate", False,
                     f"calculator ran {len(calcs)}x (cap {_MAX_COMPUTE_CALCS})")
    if intent != "calculation" and calcs:
        return Check("behavioral", "tool_use_appropriate", False,
                     f"calculator used on non-calculation intent {intent!r}")
    return Check("behavioral", "tool_use_appropriate", True,
                 f"{len(calcs)} calc(s)", score=float(len(calcs)))


_CHECKS = (
    check_refuse_short_circuits, check_answer_pipeline,
    check_retrieve_rounds_bounded, check_no_loops,
    check_no_duplicate_retrieval, check_tool_use_appropriate,
)


def evaluate(case: EvalCase, trace: Trace) -> list[Check]:
    return [fn(case, trace) for fn in _CHECKS]
