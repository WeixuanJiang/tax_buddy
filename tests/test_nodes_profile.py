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
