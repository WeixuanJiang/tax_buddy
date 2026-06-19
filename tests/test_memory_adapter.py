import knowledge_engine.agent.memory as mem


def test_get_profile_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.get_user_profile("u1") == ""


def test_get_profile_empty_user_returns_empty(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    assert mem.get_user_profile("") == ""


def test_remember_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", False)
    assert mem.remember("u1", {"income_year": 2026}) is None


def test_get_profile_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()  # avoid "coroutine never awaited" warning
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.get_user_profile("u1") == ""


def test_remember_swallows_errors(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)

    def boom(coro, *args, **kwargs):
        coro.close()
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mem, "_submit", boom)
    assert mem.remember("u1", {"income_year": 2026, "entities": ["sole trader"]}) is None
