from knowledge_engine.agent.state import Triage
from knowledge_engine.api.models import ChatRequest


def test_triage_has_entities_field():
    t = Triage(in_scope=True, entities=["sole trader"])
    assert t.entities == ["sole trader"]


def test_triage_entities_defaults_empty():
    t = Triage(in_scope=True)
    assert t.entities == []


def test_chat_request_accepts_user_id():
    r = ChatRequest(question="hello there", thread_id="t1", user_id="u1")
    assert r.user_id == "u1"


def test_chat_request_user_id_optional():
    r = ChatRequest(question="hello there", thread_id="t1")
    assert r.user_id is None


from knowledge_engine.agent import nodes


def test_profile_block_empty_when_no_profile():
    assert nodes._profile_block({}) == ""
    assert nodes._profile_block({"user_profile": "   "}) == ""


def test_profile_block_includes_facts_and_guardrail():
    block = nodes._profile_block({"user_profile": "income year 2026; sole trader"})
    assert "income year 2026" in block
    assert "sole trader" in block
    assert "personalised advice" in block.lower()
