import knowledge_engine.agent.memory as mem


def test_history_disabled(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.load_conversation("t1") == []
    assert mem.delete_conversation_messages("t1") is None


def test_history_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.load_conversation("t1") == []
    assert mem.delete_conversation_messages("t1") is None
