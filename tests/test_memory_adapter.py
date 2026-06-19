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


def test_extract_durable_facts_captures_work_from_home_hours():
    facts = mem.extract_durable_facts(
        "I worked 37.5 hours * 48 weeks full time work from home hours for deduction"
    )

    assert "work from home hours: 37.5 hours per week for 48 weeks" in facts


def test_remember_persists_memory_facts_and_deterministic_facts(monkeypatch):
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    saved = []

    class FakeLongTerm:
        async def add_preference(self, **kwargs):
            saved.append(kwargs)

    class FakeClient:
        long_term = FakeLongTerm()

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr(mem, "_get_client", fake_get_client)

    mem.remember(
        "u1",
        {"memory_facts": ["occupation: software engineer"]},
        question="I worked 37.5 hours * 48 weeks full time work from home hours",
    )

    preferences = {item["preference"] for item in saved}
    assert "occupation: software engineer" in preferences
    assert "work from home hours: 37.5 hours per week for 48 weeks" in preferences


def test_remember_conversation_extracts_from_user_messages(monkeypatch):
    captured = {}
    monkeypatch.setattr(mem.settings, "memory_enabled", True)
    monkeypatch.setattr(
        mem,
        "load_conversation",
        lambda thread_id: [
            {"role": "user", "content": "I work as a software engineer."},
            {"role": "assistant", "content": "Okay."},
            {"role": "user", "content": "I worked 37.5 hours * 48 weeks work from home."},
        ],
    )
    monkeypatch.setattr(
        mem,
        "extract_key_memory_facts",
        lambda transcript: ["occupation: software engineer"],
    )
    monkeypatch.setattr(
        mem,
        "remember",
        lambda uid, analysis, question=None: captured.update(
            uid=uid, analysis=analysis, question=question
        ),
    )

    mem.remember_conversation("u1", "t1")

    assert captured["uid"] == "u1"
    assert captured["analysis"] == {"memory_facts": ["occupation: software engineer"]}
    assert "37.5 hours" in captured["question"]
