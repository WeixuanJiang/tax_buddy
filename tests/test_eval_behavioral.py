from knowledge_engine.config import settings
from knowledge_engine.eval import behavioral as beh
from knowledge_engine.eval.harness import EvalCase, Trace


def _answer_case():
    return EvalCase(question="What is the Medicare levy?", type="factual",
                    expect="answer", intent="factual")


def _refuse_case():
    return EvalCase(question="What's the weather?", type="out_of_scope",
                    expect="refuse")


def _answer_trace(**state):
    base = {
        "route": "answer", "retrieve_rounds": 1, "analysis": {"intent": "factual"},
        "retrieved": [{"url": "u1", "heading": "h1"}, {"url": "u2", "heading": "h2"}],
        "calculations": [],
    }
    base.update(state)
    return Trace(question="q", state=base,
                 nodes=["triage", "retrieve", "compute", "synthesize",
                        "verify", "finalize"])


def test_clean_answer_trace_passes():
    checks = beh.evaluate(_answer_case(), _answer_trace())
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_refuse_short_circuits():
    trace = Trace(question="q", state={"route": "refuse"}, nodes=["triage", "refuse"])
    assert beh.check_refuse_short_circuits(_refuse_case(), trace).passed


def test_refuse_that_ran_retrieval_fails():
    trace = Trace(question="q", state={"route": "refuse"},
                  nodes=["triage", "retrieve", "synthesize", "refuse"])
    assert not beh.check_refuse_short_circuits(_refuse_case(), trace).passed


def test_answer_missing_pipeline_node_fails():
    trace = _answer_trace()
    trace.nodes = ["triage", "retrieve", "finalize"]  # skipped synthesize/verify
    assert not beh.check_answer_pipeline(_answer_case(), trace).passed


def test_retrieve_rounds_over_cap_fails():
    trace = _answer_trace(retrieve_rounds=settings.retrieve_max_rounds + 5)
    assert not beh.check_retrieve_rounds_bounded(_answer_case(), trace).passed


def test_loop_detection():
    trace = _answer_trace()
    trace.nodes = ["triage"] + ["retrieve"] * (settings.retrieve_max_rounds + 2)
    assert not beh.check_no_loops(_answer_case(), trace).passed


def test_duplicate_retrieval_fails():
    trace = _answer_trace(retrieved=[{"url": "u", "heading": "h"},
                                     {"url": "u", "heading": "h"}])
    assert not beh.check_no_duplicate_retrieval(_answer_case(), trace).passed


def test_calculator_on_non_calculation_intent_fails():
    trace = _answer_trace(analysis={"intent": "factual"},
                          calculations=[{"expression": "1+1", "result": "2"}])
    assert not beh.check_tool_use_appropriate(_answer_case(), trace).passed


def test_calculator_loop_overrun_fails():
    trace = _answer_trace(analysis={"intent": "calculation"},
                          calculations=[{"expression": "x", "result": "1"}] * 9)
    assert not beh.check_tool_use_appropriate(_answer_case(), trace).passed
