from knowledge_engine.agent.state import MemoryFacts, Triage


def test_triage_has_entities_field():
    t = Triage(in_scope=True, entities=["sole trader"])
    assert t.entities == ["sole trader"]


def test_triage_entities_defaults_empty():
    t = Triage(in_scope=True)
    assert t.entities == []


def test_memory_facts_schema_keeps_key_facts():
    facts = MemoryFacts(facts=["work from home 37.5 hours per week for 48 weeks"])
    assert facts.facts == ["work from home 37.5 hours per week for 48 weeks"]


from knowledge_engine.agent import nodes
from langchain_core.messages import HumanMessage


def test_profile_block_empty_when_no_profile():
    assert nodes._profile_block({}) == ""
    assert nodes._profile_block({"user_profile": "   "}) == ""


def test_profile_block_includes_facts_and_guardrail():
    block = nodes._profile_block({"user_profile": "income year 2026; sole trader"})
    assert "income year 2026" in block
    assert "sole trader" in block
    assert "personalised advice" in block.lower()


def test_compute_includes_recalled_profile_in_calculation_prompt(monkeypatch):
    captured = {}

    class FakeBoundLLM:
        def invoke(self, messages):
            captured["messages"] = messages
            return type("AI", (), {"tool_calls": []})()

    class FakeLLM:
        def bind_tools(self, tools):
            return FakeBoundLLM()

    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM())

    nodes.compute({
        "analysis": {"intent": "calculation"},
        "query": "how much deductions available for me?",
        "user_profile": "- tax: work from home hours: 37.5 hours per week for 48 weeks",
    })

    prompt = next(m.content for m in captured["messages"] if isinstance(m, HumanMessage))
    assert "37.5 hours per week for 48 weeks" in prompt


def test_refuse_redirect_uses_question_specific_response(monkeypatch):
    captured = {}

    class FakeLLM:
        def invoke(self, messages):
            captured["messages"] = messages
            return type("AI", (), {"content": "I cannot help plan a holiday, but I can help with individual tax return questions."})()

    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM())

    out = nodes.refuse_redirect({"query": "Can you plan my holiday?"})

    assert "holiday" in captured["messages"][-1].content
    assert out["answer"].startswith("I cannot help plan a holiday")
    assert out["route"] == "refuse"


def test_refuse_redirect_falls_back_when_llm_fails(monkeypatch):
    class BrokenLLM:
        def invoke(self, messages):
            raise RuntimeError("model down")

    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: BrokenLLM())

    out = nodes.refuse_redirect({"query": "Can you plan my holiday?"})

    assert "Australian individual income-tax" in out["answer"]
    assert out["route"] == "refuse"
