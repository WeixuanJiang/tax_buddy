from knowledge_engine.agent.state import Triage


def test_triage_has_entities_field():
    t = Triage(in_scope=True, entities=["sole trader"])
    assert t.entities == ["sole trader"]


def test_triage_entities_defaults_empty():
    t = Triage(in_scope=True)
    assert t.entities == []


from knowledge_engine.agent import nodes


def test_profile_block_empty_when_no_profile():
    assert nodes._profile_block({}) == ""
    assert nodes._profile_block({"user_profile": "   "}) == ""


def test_profile_block_includes_facts_and_guardrail():
    block = nodes._profile_block({"user_profile": "income year 2026; sole trader"})
    assert "income year 2026" in block
    assert "sole trader" in block
    assert "personalised advice" in block.lower()
