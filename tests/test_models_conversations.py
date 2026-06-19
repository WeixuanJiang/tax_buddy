from knowledge_engine.api.models import ConversationSummary, ConversationDetail, Message


def test_summary_and_detail():
    s = ConversationSummary(thread_id="t1", title="Car expenses", updated_at="2026-06-19T00:00:00+00:00")
    assert s.thread_id == "t1"
    d = ConversationDetail(thread_id="t1", messages=[Message(role="user", content="hi")])
    assert d.messages[0].role == "user"
