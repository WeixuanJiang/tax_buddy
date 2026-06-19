import uuid

import pytest

import knowledge_engine.api.users as users
from knowledge_engine.db import get_conn


def _db_available() -> bool:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not available")


def test_create_get_and_duplicate():
    users.ensure_users_table()
    uname = f"u_{uuid.uuid4().hex[:10]}"
    try:
        assert users.create_user(uname, "hash1", "nurse", "3000") is True
        got = users.get_user(uname)
        assert got["username"] == uname
        assert got["occupation"] == "nurse"
        assert got["postcode"] == "3000"
        # duplicate username rejected
        assert users.create_user(uname, "hash2", "x", "2000") is False
        assert users.get_user("missing_" + uname) is None
    finally:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (uname,))
