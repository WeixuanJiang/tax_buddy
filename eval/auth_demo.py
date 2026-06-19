"""Manual end-to-end: register a user, then show the agent recalls their
occupation in a fresh thread (no clarifying question).

Prereqs: AUTH_SECRET set, MEMORY_ENABLED=true, Neo4j + Postgres up, corpus ingested.
Run from the repo parent:  python -m knowledge_engine.eval.auth_demo
"""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage

from knowledge_engine.agent import memory
from knowledge_engine.agent.graph import build_graph
from knowledge_engine.api import security, users
from knowledge_engine.config import settings


def main() -> None:
    if not settings.memory_enabled or not settings.auth_secret:
        raise SystemExit("Set MEMORY_ENABLED=true and AUTH_SECRET, and start Neo4j/Postgres.")
    users.ensure_users_table()
    uname = f"demo_{uuid.uuid4().hex[:8]}"

    # Register (seeds occupation/postcode preferences in Neo4j)
    users.create_user(uname, security.hash_password("hunter2pw"), "electrician", "3000")
    memory.register_user_profile(uname, "electrician", "3000")
    print(f"registered {uname} (electrician, 3000)")

    graph = build_graph()
    q = "What work-related expenses can I claim?"
    profile = memory.get_user_context(uname, q)
    print(f"\nrecalled context:\n{profile or '(empty)'}")
    s = graph.invoke({"messages": [HumanMessage(q)], "query": q, "user_profile": profile})
    print("\nroute:", s.get("route"))
    print("(Expected: NOT 'clarify' — occupation recalled from the user's profile.)")
    memory.save_turn(uname, "thread-A", q, s.get("answer", ""))
    print("saved turn to conversation.")


if __name__ == "__main__":
    main()
