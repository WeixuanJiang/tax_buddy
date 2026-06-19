"""Layered evaluation runner for the tax-return agent.

Three architectural layers (see eval/README.md):
  1. deterministic  — cheap regex/format/intent/PII checks (no extra LLM)
  2. semantic       — LLM-as-judge groundedness / relevance / safety (expensive)
  3. behavioral     — node-trace checks: routing efficiency, loops, tool use

Governance (cost control):
  * CI on every push:   --ci --layers deterministic,behavioral
                        (small tagged subset, no judge LLM)
  * Merge to main:      --layers all
                        (full dataset incl. the semantic judge)

Each layer degrades gracefully: if the agent can't run (no DB / no API key) the
case is recorded as an error rather than crashing the suite.

Examples:
  python -m knowledge_engine.eval.run_evals --ci --layers deterministic,behavioral
  python -m knowledge_engine.eval.run_evals --layers all --json eval_report.json
"""
from __future__ import annotations

import argparse
import sys
import time

from . import behavioral, deterministic, semantic
from .checks import CaseResult, Report
from .harness import load_cases, run_traced

ALL_LAYERS = ("deterministic", "semantic", "behavioral")


def _log(msg: str) -> None:
    """Progress line, flushed immediately so it streams during slow runs."""
    print(msg, flush=True)


def _parse_layers(value: str) -> list[str]:
    if value == "all":
        return list(ALL_LAYERS)
    picked = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in picked if v not in ALL_LAYERS]
    if bad:
        raise SystemExit(f"unknown layer(s): {bad}; choose from {ALL_LAYERS} or 'all'")
    return picked


def run(layers: list[str], ci_only: bool, reasoning: bool,
        limit: int | None = None, progress: bool = True) -> Report:
    cases = load_cases(ci_only=ci_only)
    if limit:
        cases = cases[:limit]
    report = Report()

    scope = "CI subset" if ci_only else "full dataset"
    n = len(cases)
    run_start = time.perf_counter()
    _log(f"Running {layers} on {scope} ({n} cases)...\n")

    for i, case in enumerate(cases, 1):
        if progress:
            _log(f"[{i}/{n}] {case.question[:64]}")
        t0 = time.perf_counter()

        trace = run_traced(case.question, reasoning=reasoning)
        result = CaseResult(question=case.question)
        if trace.error:
            result.error = trace.error
            report.add(result)
            if progress:
                _log(f"      ! agent error: {trace.error[:80]}  "
                     f"({time.perf_counter() - t0:.1f}s)")
            continue

        if "deterministic" in layers:
            result.checks += deterministic.evaluate(case, trace.state)
        if "behavioral" in layers:
            result.checks += behavioral.evaluate(case, trace)
        if "semantic" in layers:
            if progress:
                _log("      judging (groundedness / relevance / safety)...")
            result.checks += semantic.evaluate(case, trace.state)
        report.add(result)

        if progress:
            passed = sum(c.passed for c in result.checks)
            total = len(result.checks)
            mark = "ok  " if passed == total else f"FAIL({total - passed})"
            _log(f"      {mark} {passed}/{total} checks  "
                 f"route={trace.state.get('route', '?')}  "
                 f"({time.perf_counter() - t0:.1f}s)")

    if progress:
        done = sum(1 for c in report.cases if not c.error)
        _log(f"\nFinished {done}/{n} cases in {time.perf_counter() - run_start:.1f}s")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", default="all",
                    help="comma list of deterministic,semantic,behavioral or 'all'")
    ap.add_argument("--ci", action="store_true",
                    help="run only the CI-tagged subset (cheap smoke set)")
    ap.add_argument("--reasoning", action="store_true",
                    help="run the agent with thinking mode on")
    ap.add_argument("--limit", type=int, default=None, help="cap number of cases")
    ap.add_argument("--json", dest="json_path", default=None,
                    help="write a machine-readable report to this path")
    ap.add_argument("--min-pass-rate", type=float, default=0.0,
                    help="exit non-zero if overall pass rate is below this (0..1)")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    args = ap.parse_args()

    layers = _parse_layers(args.layers)
    report = run(layers, ci_only=args.ci, reasoning=args.reasoning,
                 limit=args.limit, progress=not args.quiet)
    report.print_summary(verbose=not args.quiet)

    if args.json_path:
        report.write_json(args.json_path)
        print(f"\nWrote JSON report to {args.json_path}")

    if report.errored() and len(report.errored()) == len(report.cases):
        print("\nAll cases errored (agent could not run — DB / API key missing?).")
        return 2
    if report.pass_rate() < args.min_pass_rate:
        print(f"\nFAIL: pass rate {report.pass_rate():.0%} < "
              f"threshold {args.min_pass_rate:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
