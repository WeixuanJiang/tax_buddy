"""Shared result types and reporting for the layered evaluation suite.

A `Check` is the atomic pass/fail unit. Layers (deterministic / semantic /
behavioral) each emit a list of `Check`s per evaluated case. `Report` aggregates
them and renders a console summary plus a machine-readable dict.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

LAYERS = ("deterministic", "semantic", "behavioral")


@dataclass
class Check:
    """One assertion about one case."""
    layer: str
    name: str
    passed: bool
    detail: str = ""
    score: Optional[float] = None       # optional 0..1 (e.g. judge confidence)

    def to_dict(self) -> dict:
        return {
            "layer": self.layer, "name": self.name, "passed": self.passed,
            "detail": self.detail, "score": self.score,
        }


@dataclass
class CaseResult:
    question: str
    checks: list[Check] = field(default_factory=list)
    error: str = ""                     # set when the agent run itself failed

    def passed(self) -> bool:
        return not self.error and all(c.passed for c in self.checks)


@dataclass
class Report:
    cases: list[CaseResult] = field(default_factory=list)

    def add(self, case: CaseResult) -> None:
        self.cases.append(case)

    # -- aggregates ---------------------------------------------------------
    def by_layer(self) -> dict[str, tuple[int, int]]:
        """layer -> (passed_checks, total_checks)."""
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for case in self.cases:
            for c in case.checks:
                agg[c.layer][1] += 1
                agg[c.layer][0] += int(c.passed)
        return {k: (v[0], v[1]) for k, v in agg.items()}

    def by_check(self) -> dict[tuple[str, str], tuple[int, int]]:
        agg: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for case in self.cases:
            for c in case.checks:
                agg[(c.layer, c.name)][1] += 1
                agg[(c.layer, c.name)][0] += int(c.passed)
        return {k: (v[0], v[1]) for k, v in agg.items()}

    def total(self) -> tuple[int, int]:
        passed = sum(int(c.passed) for case in self.cases for c in case.checks)
        total = sum(1 for case in self.cases for c in case.checks)
        return passed, total

    def pass_rate(self) -> float:
        passed, total = self.total()
        return passed / total if total else 1.0

    def errored(self) -> list[CaseResult]:
        return [c for c in self.cases if c.error]

    # -- rendering ----------------------------------------------------------
    def print_summary(self, verbose: bool = True) -> None:
        if verbose:
            for case in self.cases:
                if case.error:
                    print(f"\n[ERROR] {case.question[:70]}\n        {case.error}")
                    continue
                fails = [c for c in case.checks if not c.passed]
                mark = "PASS" if not fails else f"FAIL ({len(fails)})"
                print(f"\n[{mark}] {case.question[:70]}")
                for c in case.checks:
                    if not c.passed:
                        sc = f" score={c.score:.2f}" if c.score is not None else ""
                        print(f"    - {c.layer}/{c.name}: {c.detail}{sc}")

        print("\n" + "=" * 64)
        print("Per-check pass rate")
        print("-" * 64)
        for (layer, name), (p, t) in sorted(self.by_check().items()):
            bar = "ok " if p == t else "!! "
            print(f"  {bar}{layer:<14} {name:<28} {p}/{t}")

        print("-" * 64)
        print("Per-layer pass rate")
        for layer, (p, t) in sorted(self.by_layer().items()):
            print(f"  {layer:<14} {p}/{t}  ({(p / t if t else 1):.0%})")

        p, t = self.total()
        print("-" * 64)
        print(f"  OVERALL        {p}/{t}  ({self.pass_rate():.0%})")
        if self.errored():
            print(f"  ({len(self.errored())} case(s) could not run the agent)")
        print("=" * 64)

    def to_dict(self) -> dict:
        return {
            "overall_pass_rate": self.pass_rate(),
            "by_layer": {k: {"passed": v[0], "total": v[1]}
                         for k, v in self.by_layer().items()},
            "by_check": {f"{layer}/{name}": {"passed": v[0], "total": v[1]}
                         for (layer, name), v in self.by_check().items()},
            "cases": [
                {"question": c.question, "error": c.error,
                 "checks": [ck.to_dict() for ck in c.checks]}
                for c in self.cases
            ],
        }

    def write_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
