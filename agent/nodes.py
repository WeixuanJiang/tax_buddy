"""LangGraph node implementations.

Each node takes the AgentState and returns a partial update. LLM calls are wrapped
defensively: if structured output fails, we fall back to safe defaults so the graph
keeps making progress.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage,
)

try:  # trim_messages location is stable, but guard for older cores
    from langchain_core.messages import trim_messages
except ImportError:  # pragma: no cover
    trim_messages = None

from knowledge_engine.agent import prompts
from knowledge_engine.agent.llm import get_llm, structured
from knowledge_engine.agent.tools import calculator
from knowledge_engine.agent.state import (
    AgentState, FollowUps, GroundingCheck, IntakeResult, QueryAnalysis,
    RelevanceGrade, SubQueries, Triage,
)
from knowledge_engine.config import settings
from knowledge_engine.retrieval.retriever import get_document, retrieve


def _user_query(state: AgentState) -> str:
    if state.get("query"):
        return state["query"]
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.content
    return ""


def _recent_messages(state: AgentState, max_messages: int = 8) -> list:
    """Recent conversation turns to give the model, selected with LangChain's
    `trim_messages` (counting by message). Memory itself is the LangGraph
    checkpointer (persisted `messages`); this just bounds how much we show.

    The current question is the last item in state['messages'] (appended by the
    reducer before nodes run), so we exclude it. Returns [] on the first turn or
    the stateless /ask path (no checkpointer)."""
    prior = state.get("messages", [])[:-1]
    if not prior:
        return []
    if trim_messages is None:
        return prior[-max_messages:]
    try:
        return trim_messages(
            prior, max_tokens=max_messages, strategy="last",
            token_counter=len, start_on="human", include_system=False,
            allow_partial=False,
        )
    except Exception:
        return prior[-max_messages:]


# ---- nodes -----------------------------------------------------------------

def triage(state: AgentState) -> dict:
    """Intake + analysis + query planning in a single LLM call (low latency)."""
    q = _user_query(state)
    history = _recent_messages(state)
    reasoning = state.get("reasoning")
    try:
        t: Triage = structured(Triage, reasoning=reasoning).invoke(
            [SystemMessage(prompts.TRIAGE_SYS), *history, HumanMessage(q)]
        )
        if not t.in_scope or t.unsafe:
            route = "refuse"
        elif t.needs_clarification:
            route = "clarify"
        else:
            route = "retrieve"
        analysis = t.model_dump()
        queries = [s for s in t.search_queries if s.strip()][:4] or [q]
    except Exception:
        route, analysis, queries = "retrieve", {}, [q]
    return {
        "query": q,
        "route": route,
        "analysis": analysis,
        "sub_queries": queries,
        "income_year_label": settings.tax_year_label,
        "retrieve_rounds": 0,
        "verify_rounds": 0,
    }


def guardrail_intake(state: AgentState) -> dict:
    q = _user_query(state)
    try:
        res: IntakeResult = structured(IntakeResult).invoke(
            [SystemMessage(prompts.INTAKE_SYS), HumanMessage(q)]
        )
        route = "refuse" if (not res.in_scope or res.unsafe) else "analyze"
    except Exception:
        route = "analyze"  # fail open to answering; later nodes still ground in ATO data
    return {"query": q, "route": route}


def analyze_query(state: AgentState) -> dict:
    q = state["query"]
    try:
        a: QueryAnalysis = structured(QueryAnalysis).invoke(
            [SystemMessage(prompts.ANALYZE_SYS), HumanMessage(q)]
        )
        analysis = a.model_dump()
    except Exception:
        analysis = QueryAnalysis().model_dump()
    return {
        "analysis": analysis,
        "income_year_label": settings.tax_year_label,
        "route": "clarify" if analysis.get("needs_clarification") else "plan",
        "retrieve_rounds": 0,
        "verify_rounds": 0,
    }


def ask_clarification(state: AgentState) -> dict:
    q = state["analysis"].get("clarifying_question") or (
        "Could you share a bit more detail so I can find the right ATO guidance?"
    )
    return {"answer": q, "route": "clarify",
            "messages": [AIMessage(q)]}


def plan_retrieval(state: AgentState) -> dict:
    q = state["query"]
    try:
        sq: SubQueries = structured(SubQueries).invoke(
            [SystemMessage(prompts.PLAN_SYS), HumanMessage(q)]
        )
        queries = [s for s in sq.queries if s.strip()][:4] or [q]
    except Exception:
        queries = [q]
    return {"sub_queries": queries}


def _merge_unique(existing: list[dict], new: list[dict]) -> list[dict]:
    seen = {(c["url"], c["heading"]) for c in existing}
    out = list(existing)
    for c in new:
        key = (c["url"], c["heading"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def retrieve_node(state: AgentState) -> dict:
    retrieved = list(state.get("retrieved", []))
    for sq in state.get("sub_queries", [state["query"]]):
        chunks = retrieve(sq)
        retrieved = _merge_unique(retrieved, [asdict(c) for c in chunks])
    return {"retrieved": retrieved,
            "retrieve_rounds": state.get("retrieve_rounds", 0) + 1}


def _grouped_sources(retrieved: list[dict]) -> list[dict]:
    """One entry per unique URL, in retrieved order, with all its chunk texts.

    This single canonical list is used for BOTH the prompt and the citation panel
    so the inline [n] markers always line up with the displayed sources.
    """
    order: list[dict] = []
    idx: dict[str, int] = {}
    for c in retrieved:
        u = c["url"]
        if u not in idx:
            idx[u] = len(order)
            order.append({"url": u, "title": c["title"],
                          "heading": c.get("heading") or "", "texts": [c["text"]]})
        else:
            order[idx[u]]["texts"].append(c["text"])
    return order


def _format_sources(retrieved: list[dict]) -> str:
    lines = []
    for i, s in enumerate(_grouped_sources(retrieved), 1):
        body = "\n".join(s["texts"])
        lines.append(f"[{i}] {s['title']} — {s['heading']}\nURL: {s['url']}\n{body}")
    return "\n\n".join(lines)


def grade_relevance(state: AgentState) -> dict:
    q = state["query"]
    retrieved = state.get("retrieved", [])
    sufficient = bool(retrieved)
    refined = ""
    if retrieved:
        try:
            g: RelevanceGrade = structured(RelevanceGrade).invoke([
                SystemMessage(prompts.GRADE_SYS),
                HumanMessage(f"Question: {q}\n\nRetrieved:\n{_format_sources(retrieved)}"),
            ])
            sufficient, refined = g.sufficient, g.refined_query
        except Exception:
            sufficient = True
    exhausted = state.get("retrieve_rounds", 0) >= settings.retrieve_max_rounds
    if sufficient or exhausted or not refined:
        return {"route": "synthesize"}
    return {"route": "retrieve", "sub_queries": [refined]}


def compute(state: AgentState) -> dict:
    """Run the calculator tool for calculation-type questions (bounded loop).

    Skips quickly for non-calculation intents. Produces verified figures that
    synthesize uses, so arithmetic in the answer is correct."""
    if state.get("analysis", {}).get("intent") != "calculation":
        return {}
    try:
        llm = get_llm(reasoning=state.get("reasoning")).bind_tools([calculator])
    except Exception:
        return {}
    msgs = [SystemMessage(prompts.COMPUTE_SYS), HumanMessage(state["query"])]
    calcs: list[dict[str, str]] = []
    try:
        for _ in range(4):
            ai = llm.invoke(msgs)
            msgs.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break
            for tc in tool_calls:
                expr = tc.get("args", {}).get("expression", "")
                result = calculator.invoke(tc["args"])
                calcs.append({"expression": expr, "result": str(result)})
                msgs.append(ToolMessage(str(result), tool_call_id=tc["id"]))
    except Exception:
        pass
    return {"calculations": calcs}


def synthesize(state: AgentState) -> dict:
    q = state["query"]
    retrieved = state.get("retrieved", [])
    if not retrieved:
        msg = ("I couldn't find ATO content covering that. You may find it on "
               "ato.gov.au or via a registered tax agent.")
        return {"draft": msg, "route": "finalize"}
    sys = prompts.SYNTH_SYS.format(year_label=state.get("income_year_label",
                                                        settings.tax_year_label))
    history = _recent_messages(state)
    calcs = state.get("calculations") or []
    calc_block = ""
    if calcs:
        lines = "\n".join(f"{c['expression']} = {c['result']}" for c in calcs)
        calc_block = f"Verified calculations (use these exact figures):\n{lines}\n\n"
    human = (f"{calc_block}Question: {q}\n\n"
             f"ATO sources:\n{_format_sources(retrieved)}")
    try:
        out = get_llm(temperature=0.0, reasoning=state.get("reasoning")).invoke(
            [SystemMessage(sys), *history, HumanMessage(human)]
        )
        draft = out.content
    except Exception as e:  # noqa: BLE001
        draft = f"(Unable to generate an answer right now: {e})"
    return {"draft": draft}


def verify_grounding(state: AgentState) -> dict:
    draft = state.get("draft", "")
    retrieved = state.get("retrieved", [])
    grounded, confidence, issues = True, "medium", []
    if draft and retrieved:
        try:
            v: GroundingCheck = structured(
                GroundingCheck, reasoning=state.get("reasoning")
            ).invoke([
                SystemMessage(prompts.VERIFY_SYS),
                HumanMessage(f"Sources:\n{_format_sources(retrieved)}\n\nDraft answer:\n{draft}"),
            ])
            grounded, confidence, issues = v.grounded, v.confidence, v.issues
        except Exception:
            grounded = True
    verification = {"grounded": grounded, "confidence": confidence, "issues": issues}
    # Single grounding pass (no re-synthesis loop): the answer is already streamed,
    # so we surface a caveat in finalize rather than regenerate.
    return {"verification": verification, "route": "finalize"}


def _related_links(retrieved: list[dict], limit: int = 5) -> list[dict]:
    out, seen = [], set()
    for c in retrieved[:3]:
        doc = get_document(c["url"])
        if not doc:
            continue
        for link in (doc.get("child_links") or []):
            u = link.get("url")
            if u and u not in seen:
                seen.add(u)
                out.append({"title": link.get("title", ""), "url": u})
            if len(out) >= limit:
                return out
    return out


def _suggest_followups(state: AgentState, draft: str) -> list[str]:
    q = state.get("query", "")
    try:
        f: FollowUps = structured(FollowUps, reasoning=state.get("reasoning")).invoke([
            SystemMessage(prompts.SUGGEST_SYS),
            HumanMessage(f"Question: {q}\n\nAnswer:\n{draft[:1500]}"),
        ])
        return [s.strip() for s in f.questions if s.strip()][:3]
    except Exception:
        return []


def finalize_response(state: AgentState) -> dict:
    draft = state.get("draft", "")
    retrieved = state.get("retrieved", [])
    cited = set(re.findall(r"\[(\d+)\]", draft))
    citations = [
        {"n": str(i), "title": s["title"], "url": s["url"]}
        for i, s in enumerate(_grouped_sources(retrieved), 1)
        if not cited or str(i) in cited  # show only referenced sources (fallback: all)
    ]
    verification = state.get("verification", {})
    note = ""
    if verification.get("confidence") == "low" or verification.get("issues"):
        note = "\n\n_Note: parts of this may not be fully covered by the cited ATO " \
               "pages — please verify._"
    answer = (f"{draft}{note}\n\n_Applies to the {state.get('income_year_label')} "
              f"income year._\n\n{prompts.DISCLAIMER}")
    suggestions = _suggest_followups(state, draft) if retrieved else []
    return {
        "answer": answer,
        "citations": citations,
        "related_links": _related_links(retrieved),
        "suggestions": suggestions,
        "route": "answer",
        "messages": [AIMessage(answer)],
    }


def refuse_redirect(state: AgentState) -> dict:
    return {"answer": prompts.REFUSE_MSG, "route": "refuse",
            "citations": [], "related_links": [],
            "messages": [AIMessage(prompts.REFUSE_MSG)]}
