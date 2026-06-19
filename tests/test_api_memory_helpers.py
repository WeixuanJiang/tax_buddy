from knowledge_engine.api import main


def test_memory_read_delegates(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_profile",
        lambda uid: f"profile:{uid}",
    )
    assert main._memory_read("u1") == "profile:u1"


def test_memory_read_blank_user_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.get_user_profile",
        lambda uid: "should-not-be-called",
    )
    assert main._memory_read("") == ""


def test_memory_write_delegates(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "knowledge_engine.agent.memory.remember",
        lambda uid, analysis: captured.update(uid=uid, analysis=analysis),
    )
    main._memory_write("u1", {"analysis": {"income_year": 2026}})
    assert captured == {"uid": "u1", "analysis": {"income_year": 2026}}
