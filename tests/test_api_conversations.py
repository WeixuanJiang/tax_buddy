import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException

import knowledge_engine.api.main as main


def test_list_requires_login():
    with pytest.raises(HTTPException) as e:
        main.list_conversations_route(username=None)
    assert e.value.status_code == 401


def test_get_unknown_is_404(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: None)
    with pytest.raises(HTTPException) as e:
        main.get_conversation_route("t1", username="alice")
    assert e.value.status_code == 404


def test_get_not_owner_is_403(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "bob")
    with pytest.raises(HTTPException) as e:
        main.get_conversation_route("t1", username="alice")
    assert e.value.status_code == 403


def test_get_owner_loads(monkeypatch):
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "alice")
    monkeypatch.setattr("knowledge_engine.agent.memory.load_conversation",
                        lambda t: [{"role": "user", "content": "hi"}])
    out = main.get_conversation_route("t1", username="alice")
    assert out["thread_id"] == "t1"
    assert out["messages"] == [{"role": "user", "content": "hi"}]


def test_delete_owner_purges_both(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "alice")
    monkeypatch.setattr("knowledge_engine.api.conversations.delete_conversation",
                        lambda t: calls.append(("row", t)))
    monkeypatch.setattr("knowledge_engine.agent.memory.delete_conversation_messages",
                        lambda t: calls.append(("msgs", t)))
    out = main.delete_conversation_route("t1", username="alice")
    assert out == {"deleted": "t1"}
    assert ("row", "t1") in calls and ("msgs", "t1") in calls


def test_close_owner_schedules_long_term_memory(monkeypatch):
    calls = []
    monkeypatch.setattr("knowledge_engine.api.conversations.get_owner", lambda t: "alice")
    monkeypatch.setattr("knowledge_engine.agent.memory.remember_conversation",
                        lambda u, t: calls.append(("remember", u, t)))
    background = BackgroundTasks()

    out = main.close_conversation_route("t1", background_tasks=background, username="alice")

    assert out == {"closed": "t1"}
    assert calls == []
    assert len(background.tasks) == 1
    background.tasks[0].func(*background.tasks[0].args, **background.tasks[0].kwargs)
    assert calls == [("remember", "alice", "t1")]
