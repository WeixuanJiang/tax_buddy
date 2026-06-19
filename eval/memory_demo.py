"""Manual demo: long-term user memory recalled across two separate threads.

Prerequisites:
  - MEMORY_ENABLED=true in .env
  - Neo4j running:  docker compose up -d neo4j
  - Postgres + corpus ingested (see README)

Run from the repo parent:  python -m knowledge_engine.eval.memory_demo
"""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage

from knowledge_engine.agent import memory
from knowledge_engine.agent.graph import build_graph
from knowledge_engine.config import settings


def _turn(graph, cfg, question: str, uid: str) -> dict:
    profile = memory.get_user_profile(uid)
    print(f"\n[recalled profile for {uid!r}]: {profile!r}")
    state = graph.invoke(
        {"messages": [HumanMessage(question)], "query": question,
         "user_profile": profile},
        cfg,
    )
    memory.remember(uid, state.get("analysis"))
    return state


def main() -> None:
    if not settings.memory_enabled:
        raise SystemExit("Set MEMORY_ENABLED=true and start Neo4j first.")
    graph = build_graph()  # stateless graph is fine; memory is the cross-session store
    uid = f"demo-{uuid.uuid4().hex[:8]}"

    print("=== Turn 1 (thread A): user states their situation ===")
    s1 = _turn(graph, {"configurable": {"thread_id": "A"}},
               "I'm a sole trader and I want to know about the 2025-26 income year.",
               uid)
    print("route:", s1.get("route"), "| analysis:", s1.get("analysis"))

    print("\n=== Turn 2 (thread B, fresh): a question that usually needs occupation ===")
    s2 = _turn(graph, {"configurable": {"thread_id": "B"}},
               "What work-related expenses can I claim?", uid)
    print("route:", s2.get("route"))
    print("(Expected: NOT 'clarify' — occupation was recalled from memory.)")


if __name__ == "__main__":
    main()
