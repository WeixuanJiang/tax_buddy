"""Dataset loading and the traced agent runner shared by every layer.

We run the agent ONCE per question and capture a `Trace` (final state + the
ordered list of graph nodes that fired). All three evaluation layers then read
from that single trace, so we never pay for the agent more than once per case.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

HERE = os.path.dirname(__file__)
QFILE = os.path.join(HERE, "questions.yaml")

# type -> expected agent IntentType (None means it should be refused, so intent
# is not asserted). Mirrors knowledge_engine.agent.state.IntentType.
_TYPE_TO_INTENT = {
    "factual": "factual",
    "eligibility": "eligibility",
    "procedural": "procedural",
    "calculation": "calculation",
    "definition": "definition",
    "out_of_scope": None,
    "unsafe": None,
}


@dataclass
class EvalCase:
    question: str
    type: str
    expect: str                          # "answer" | "refuse"
    url_contains: list[str] = field(default_factory=list)
    intent: Optional[str] = None         # expected analysis.intent (answer cases)
    reference: list[str] = field(default_factory=list)  # key points for the judge
    ci: bool = False                     # part of the cheap CI subset

    @property
    def expected_intent(self) -> Optional[str]:
        if self.intent:
            return self.intent
        return _TYPE_TO_INTENT.get(self.type)


@dataclass
class Trace:
    question: str
    state: dict[str, Any]
    nodes: list[str] = field(default_factory=list)   # order nodes fired
    error: str = ""

    def visited(self, node: str) -> bool:
        return node in self.nodes

    def visit_count(self, node: str) -> int:
        return self.nodes.count(node)


def load_cases(path: str = QFILE, ci_only: bool = False) -> list[EvalCase]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    cases = [
        EvalCase(
            question=item["q"],
            type=item.get("type", "factual"),
            expect=item.get("expect", "answer"),
            url_contains=item.get("url_contains", []) or [],
            intent=item.get("intent"),
            reference=item.get("reference", []) or [],
            ci=bool(item.get("ci", False)),
        )
        for item in raw
    ]
    return [c for c in cases if c.ci] if ci_only else cases


def run_traced(question: str, reasoning: bool = False) -> Trace:
    """Invoke the agent and record the nodes that fired plus the final state."""
    from langchain_core.messages import HumanMessage
    from knowledge_engine.agent.graph import build_graph

    graph = build_graph()
    inp = {"messages": [HumanMessage(question)], "query": question,
           "reasoning": reasoning}
    nodes: list[str] = []
    final: dict[str, Any] = {}
    try:
        for mode, data in graph.stream(inp, stream_mode=["updates", "values"]):
            if mode == "updates":
                nodes.extend(n for n in data.keys())
            elif mode == "values":
                final = data
    except Exception as e:  # noqa: BLE001
        return Trace(question=question, state={}, nodes=nodes, error=str(e))
    return Trace(question=question, state=final, nodes=nodes)
