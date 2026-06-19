import uuid

import pytest

import knowledge_engine.api.conversations as convo
import knowledge_engine.api.users as users
from knowledge_engine.api.security import hash_password
from knowledge_engine.db import get_conn


def _db() -> bool:
    try:
        with get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db(), reason="Postgres not available")


def test_touch_list_owner_delete():
    users.ensure_users_table()
    convo.ensure_conversations_table()
    uname = f"u_{uuid.uuid4().hex[:8]}"
    users.create_user(uname, hash_password("hunter2pw"), "nurse", "3000")
    t1, t2 = f"t_{uuid.uuid4().hex[:6]}", f"t_{uuid.uuid4().hex[:6]}"
    try:
        convo.touch_conversation(t1, uname, "How do I claim car expenses for work?")
        convo.touch_conversation(t2, uname, "Medicare levy threshold?")
        # second touch on t1 keeps title, bumps updated_at -> t1 becomes newest
        convo.touch_conversation(t1, uname, "this should NOT change the title")

        items = convo.list_conversations(uname)
        assert [i["thread_id"] for i in items] == [t1, t2]  # newest-first
        assert items[0]["title"] == "How do I claim car expenses for work?"

        assert convo.get_owner(t1) == uname
        assert convo.get_owner("missing") is None

        convo.delete_conversation(t1)
        assert convo.get_owner(t1) is None
        assert [i["thread_id"] for i in convo.list_conversations(uname)] == [t2]
    finally:
        with get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE username = %s", (uname,))
            cur.execute("DELETE FROM users WHERE username = %s", (uname,))
