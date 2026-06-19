import knowledge_engine.api.main as main
import knowledge_engine.api.security as sec


def test_current_username_guest():
    assert main.current_username(None) is None
    assert main.current_username("Bearer ") is None
    assert main.current_username("garbage") is None


def test_current_username_from_token(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert main.current_username(f"Bearer {tok}") == "alice"


def test_memory_read_guest_short_circuits(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("knowledge_engine.agent.memory.get_user_context",
                        lambda u, q: called.__setitem__("n", called["n"] + 1) or "x")
    assert main._memory_read(None, "q") == ""
    assert called["n"] == 0


def test_memory_write_guest_short_circuits(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.agent.memory.save_turn",
                        lambda *a, **k: calls.append("save"))
    monkeypatch.setattr("knowledge_engine.agent.memory.remember",
                        lambda *a, **k: calls.append("remember"))
    monkeypatch.setattr("knowledge_engine.api.conversations.touch_conversation",
                        lambda *a, **k: None)
    main._memory_write(None, "t1", "q", {"route": "answer", "answer": "a"})   # guest
    assert calls == []


def test_memory_write_persists_completed_routes(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.agent.memory.save_turn",
                        lambda u, t, q, a: calls.append(("save", u, t, q, a)))
    monkeypatch.setattr("knowledge_engine.agent.memory.remember",
                        lambda *a, **k: calls.append(("remember",)))
    monkeypatch.setattr("knowledge_engine.api.conversations.touch_conversation",
                        lambda *a, **k: None)
    state = {"route": "refuse", "answer": "hello", "analysis": {"income_year": 2026}}
    main._memory_write("alice", "t1", "q", state)
    assert ("save", "alice", "t1", "q", "hello") in calls
    assert ("remember",) not in calls
