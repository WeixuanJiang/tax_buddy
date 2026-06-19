from knowledge_engine.api import main


def test_memory_read_delegates(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_context",
        lambda uid, query: f"profile:{uid}",
    )
    assert main._memory_read("u1", "q") == "profile:u1"


def test_memory_read_blank_user_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_context",
        lambda uid, query: "should-not-be-called",
    )
    assert main._memory_read("", "q") == ""


def test_memory_write_delegates(monkeypatch):
    captured = {}
    remembered = {"called": False}
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.save_turn",
        lambda u, t, q, a: captured.update(uid=u, thread=t, question=q, answer=a),
    )
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.remember",
        lambda *args, **kwargs: remembered.update(called=True),
    )
    main._memory_write("u1", "t1", "q", {"route": "clarify", "answer": "ans",
                                          "analysis": {"income_year": 2026}})
    assert captured["uid"] == "u1"
    assert remembered["called"] is False


def test_should_recommend_tax_agents_when_no_retrieved_sources():
    assert main._should_recommend_tax_agents({"route": "answer", "retrieved": []})


def test_should_recommend_tax_agents_when_refusal_points_to_tax_agent():
    assert main._should_recommend_tax_agents({
        "route": "refuse",
        "answer": "For this topic, please see ato.gov.au or a registered tax agent.",
    })


def test_add_tax_agents_to_answer_uses_user_postcode(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.api.users.get_user",
        lambda username: {"username": username, "postcode": "2000"},
    )
    monkeypatch.setattr(
        "knowledge_engine.api.tax_agents.search_tax_agents",
        lambda postcode: [
            {
                "name": "Agent A",
                "address": "1 Example St",
                "phone": "(02) 1234 5678",
                "rating": 4.9,
                "user_rating_count": 120,
                "google_maps_uri": "https://maps.example/a",
            }
        ],
    )
    response = main._to_response({"answer": "Base answer", "route": "answer"})

    enriched = main._add_tax_agent_recommendations(
        response,
        username="alice",
        state={"route": "answer", "retrieved": [], "verification": {}},
    )

    assert "Nearby tax agents" in enriched.answer
    assert "| Tax agent | Address | Contact number | Google rating |" in enriched.answer
    assert "Agent A" in enriched.answer
    assert "(02) 1234 5678" in enriched.answer
    assert "4.9" in enriched.answer
    assert "maps.example" not in enriched.answer


def test_memory_write_response_saves_enriched_answer(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.save_turn",
        lambda u, t, q, a: captured.update(answer=a),
    )
    monkeypatch.setattr(
        "knowledge_engine.api.conversations.touch_conversation",
        lambda *args, **kwargs: None,
    )
    response = main._to_response({"answer": "Base answer", "route": "answer"})
    response.answer = "Base answer\n\nNearby tax agents\n\n<table></table>"

    main._memory_write_response("alice", "t1", "q", response)

    assert "Nearby tax agents" in captured["answer"]
    assert "<table>" in captured["answer"]
