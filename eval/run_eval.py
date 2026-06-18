"""Evaluate the knowledge engine.

Two layers, each degrades gracefully if its dependency is missing:
  1. Retrieval recall@k  (needs the DB populated)  -- python -m ...run_eval --mode retrieval
  2. Agent end-to-end     (needs DB + OpenRouter)  -- python -m ...run_eval --mode agent

Default runs both.
"""
from __future__ import annotations

import argparse
import os

import yaml

HERE = os.path.dirname(__file__)
QFILE = os.path.join(HERE, "questions.yaml")


def load_questions() -> list[dict]:
    with open(QFILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def eval_retrieval(qs: list[dict], k: int = 8) -> None:
    from knowledge_engine.retrieval.retriever import retrieve

    scored = [q for q in qs if q.get("url_contains")]
    hits = 0
    print(f"\n== Retrieval recall@{k} ({len(scored)} answerable questions) ==")
    for q in scored:
        urls = [r.url for r in retrieve(q["q"], top_n=k)]
        hit = any(any(sub in u for u in urls) for sub in q["url_contains"])
        hits += hit
        print(f"  [{'HIT ' if hit else 'MISS'}] {q['q'][:60]}")
        if not hit:
            print(f"          wanted ~{q['url_contains']}; got {[u.split('/')[-1] for u in urls[:3]]}")
    print(f"  recall@{k} = {hits}/{len(scored)} = {hits / max(1, len(scored)):.0%}")


def eval_agent(qs: list[dict]) -> None:
    from knowledge_engine.agent.graph import answer_question

    ok_route = ok_cite = ok_year = 0
    n_answer = sum(1 for q in qs if q["expect"] == "answer")
    print(f"\n== Agent end-to-end ({len(qs)} questions) ==")
    for q in qs:
        s = answer_question(q["q"])
        route = s.get("route")
        route_ok = (route == "refuse") == (q["expect"] == "refuse")
        ok_route += route_ok
        tag = "OK " if route_ok else "BAD"
        print(f"  [{tag}] expect={q['expect']:<7} got={route:<8} | {q['q'][:50]}")
        if q["expect"] == "answer" and route == "answer":
            if s.get("citations"):
                ok_cite += 1
            if (s.get("income_year_label") or "") in s.get("answer", ""):
                ok_year += 1
    print(f"  routing correct : {ok_route}/{len(qs)}")
    print(f"  cited (of answerable): {ok_cite}/{n_answer}")
    print(f"  year stated (of answerable): {ok_year}/{n_answer}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["retrieval", "agent", "both"], default="both")
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()
    qs = load_questions()

    if args.mode in ("retrieval", "both"):
        try:
            eval_retrieval(qs, k=args.k)
        except Exception as e:  # noqa: BLE001
            print(f"[skip retrieval] {e}")
    if args.mode in ("agent", "both"):
        try:
            eval_agent(qs)
        except Exception as e:  # noqa: BLE001
            print(f"[skip agent] {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
