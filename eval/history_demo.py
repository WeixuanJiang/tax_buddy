"""Manual end-to-end: a user with two conversations — list, resume, delete.

Prereqs: AUTH_SECRET set, MEMORY_ENABLED=true, Neo4j + Postgres up.
Run from the repo parent:  python -m knowledge_engine.eval.history_demo
"""
from __future__ import annotations

import uuid

from knowledge_engine.agent import memory
from knowledge_engine.api import conversations, security, users
from knowledge_engine.config import settings


def main() -> None:
    if not settings.memory_enabled or not settings.auth_secret:
        raise SystemExit("Set MEMORY_ENABLED=true and AUTH_SECRET, and start Neo4j/Postgres.")
    users.ensure_users_table()
    conversations.ensure_conversations_table()
    uname = f"hist_{uuid.uuid4().hex[:8]}"
    users.create_user(uname, security.hash_password("hunter2pw"), "teacher", "3000")

    t1, t2 = f"thr_{uuid.uuid4().hex[:6]}", f"thr_{uuid.uuid4().hex[:6]}"
    memory.save_turn(uname, t1, "Can I claim a home office?", "Home office expenses may be claimable...")
    conversations.touch_conversation(t1, uname, "Can I claim a home office?")
    memory.save_turn(uname, t2, "What is the Medicare levy?", "The Medicare levy is 2%...")
    conversations.touch_conversation(t2, uname, "What is the Medicare levy?")

    print("conversations (newest first):")
    for c in conversations.list_conversations(uname):
        print(f"  {c['thread_id']}  {c['title']!r}  {c['updated_at']}")

    print(f"\nresume {t1}:")
    for m in memory.load_conversation(t1):
        print(f"  {m['role']}: {m['content'][:60]}")

    print(f"\ndelete {t1} ...")
    conversations.delete_conversation(t1)
    memory.delete_conversation_messages(t1)
    print("remaining:", [c["thread_id"] for c in conversations.list_conversations(uname)])
    print("messages after delete:", memory.load_conversation(t1))


if __name__ == "__main__":
    main()
