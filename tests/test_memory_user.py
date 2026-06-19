import knowledge_engine.agent.memory as mem


def test_user_writes_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.register_user_profile("u1", "nurse", "3000") is None
    assert mem.save_turn("u1", "t1", "q", "a") is None
    assert mem.recall_conversation("u1", "q") == ""
    assert mem.get_user_context("u1", "q") == ""


def test_user_calls_swallow_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.register_user_profile("u1", "nurse", "3000") is None
    assert mem.save_turn("u1", "t1", "q", "a") is None
    assert mem.recall_conversation("u1", "q") == ""
    assert mem.get_user_context("u1", "q") == ""


def test_get_user_context_combines(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    monkeypatch.setattr(mem, "get_user_profile", lambda uid: "- profile: nurse")
    monkeypatch.setattr(mem, "recall_conversation", lambda uid, q: "- user: hi")
    out = mem.get_user_context("u1", "q")
    assert "- profile: nurse" in out and "- user: hi" in out
