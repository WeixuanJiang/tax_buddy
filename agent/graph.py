"""LangGraph assembly for the tax-return agent.

Flow (one LLM call before retrieval keeps latency low):
  triage -> (refuse -> END | clarify -> END | retrieve)
  retrieve -> synthesize -> verify -> finalize -> END
"""
from __future__ import annotations

import argparse

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from knowledge_engine.agent import nodes
from knowledge_engine.agent.state import AgentState


def _route(state: AgentState) -> str:
    return state.get("route", "")


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    g.add_node("triage", nodes.triage)
    g.add_node("clarify", nodes.ask_clarification)
    g.add_node("retrieve", nodes.retrieve_node)
    g.add_node("compute", nodes.compute)
    g.add_node("synthesize", nodes.synthesize)
    g.add_node("verify", nodes.verify_grounding)
    g.add_node("finalize", nodes.finalize_response)
    g.add_node("refuse", nodes.refuse_redirect)

    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", _route,
                            {"refuse": "refuse", "clarify": "clarify",
                             "retrieve": "retrieve"})
    g.add_edge("clarify", END)
    g.add_edge("retrieve", "compute")
    g.add_edge("compute", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("refuse", END)

    return g.compile(checkpointer=checkpointer)


def answer_question(question: str) -> AgentState:
    graph = build_graph()
    return graph.invoke({"messages": [HumanMessage(question)], "query": question})


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True)
    args = ap.parse_args()
    state = answer_question(args.q)
    print("\n=== ANSWER ===\n")
    print(state.get("answer", "(no answer)"))
    cites = state.get("citations", [])
    if cites:
        print("\n=== SOURCES ===")
        for c in cites:
            print(f"  [{c['n']}] {c['title']} — {c['url']}")
    rel = state.get("related_links", [])
    if rel:
        print("\n=== RELATED ===")
        for r in rel:
            print(f"  - {r['title']} — {r['url']}")


if __name__ == "__main__":
    _cli()
