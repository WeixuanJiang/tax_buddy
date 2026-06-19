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
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.save_turn",
        lambda u, t, q, a: captured.update(uid=u, thread=t, question=q, answer=a),
    )
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.remember",
        lambda uid, analysis: captured.update(analysis=analysis),
    )
    main._memory_write("u1", "t1", "q", {"route": "answer", "answer": "ans",
                                          "analysis": {"income_year": 2026}})
    assert captured["uid"] == "u1"
    assert captured["analysis"] == {"income_year": 2026}
