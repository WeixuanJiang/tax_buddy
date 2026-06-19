from knowledge_engine.agent import prompts
from knowledge_engine.eval import deterministic as det
from knowledge_engine.eval.harness import EvalCase

YEAR = "2025-26"


def _answer_state(**overrides):
    answer = (f"The Medicare levy is generally 2% of your taxable income [1].\n\n"
              f"_Applies to the {YEAR} income year._\n\n{prompts.DISCLAIMER}")
    state = {
        "route": "answer",
        "analysis": {"intent": "factual"},
        "income_year_label": YEAR,
        "answer": answer,
        "citations": [{"n": "1", "title": "Medicare levy",
                       "url": "https://www.ato.gov.au/medicare-levy"}],
        "retrieved": [{"url": "https://www.ato.gov.au/medicare-levy",
                       "heading": "Overview", "title": "Medicare levy",
                       "text": "2% levy"}],
    }
    state.update(overrides)
    return state


def _case(**kw):
    base = dict(question="What is the Medicare levy?", type="factual",
                expect="answer", intent="factual", url_contains=["medicare-levy"])
    base.update(kw)
    return EvalCase(**base)


def _named(checks, name):
    return next(c for c in checks if c.name == name)


def test_clean_answer_passes_all():
    checks = det.evaluate(_case(), _answer_state())
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_routing_flags_wrong_route():
    c = det.check_routing(_case(expect="refuse"), _answer_state())
    assert not c.passed


def test_intent_mismatch_fails():
    state = _answer_state(analysis={"intent": "procedural"})
    assert not det.check_intent(_case(intent="factual"), state).passed


def test_factual_and_definition_are_interchangeable():
    state = _answer_state(analysis={"intent": "definition"})
    assert det.check_intent(_case(intent="factual"), state).passed


def test_calculation_labelled_factual_still_fails():
    state = _answer_state(analysis={"intent": "factual"})
    assert not det.check_intent(_case(intent="calculation"), state).passed


def test_missing_disclaimer_fails():
    state = _answer_state(answer=f"The levy is 2% [1].\n\n_Applies to the {YEAR} income year._")
    assert not det.check_disclaimer(_case(), state).passed


def test_missing_income_year_fails():
    state = _answer_state(answer=f"The levy is 2% [1].\n\n{prompts.DISCLAIMER}")
    assert not det.check_income_year(_case(), state).passed


def test_dangling_citation_marker_fails():
    state = _answer_state(
        answer=(f"The levy is 2% [1]. See also [7].\n\n"
                f"_Applies to the {YEAR} income year._\n\n{prompts.DISCLAIMER}"))
    assert not det.check_citation_integrity(_case(), state).passed


def test_retrieved_but_uncited_fails():
    state = _answer_state(citations=[])
    assert not det.check_citation_integrity(_case(), state).passed


def test_template_leak_fails():
    state = _answer_state(answer="Levy applies for the {year_label} income year.")
    assert not det.check_no_template_leak(_case(), state).passed


def test_malformed_citation_url_fails():
    state = _answer_state(citations=[{"n": "1", "title": "x", "url": "ato.gov.au/x"}])
    assert not det.check_source_domain(_case(), state).passed


def test_pii_in_answer_fails():
    state = _answer_state(answer=f"{prompts.DISCLAIMER} Email me at a@b.com [1]. "
                                 f"_Applies to the {YEAR} income year._")
    assert not det.check_no_pii(_case(), state).passed


def test_refusal_clean():
    state = {"route": "refuse", "answer": "I can only help with individual tax.",
             "citations": []}
    assert det.check_refusal_clean(_case(expect="refuse", type="out_of_scope"), state).passed
    state_bad = {"route": "refuse", "answer": "", "citations": []}
    assert not det.check_refusal_clean(_case(expect="refuse", type="out_of_scope"), state_bad).passed
