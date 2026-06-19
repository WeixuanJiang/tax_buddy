# Agent evaluation suite

A layered evaluation framework for the tax-return agent, organised into the three
architectural layers from the evaluation playbook. Each layer answers a different
question and has a different cost profile.

## The three layers

### 1. Deterministic (`deterministic.py`)
Cheap, traditional coding checks — no extra LLM calls. Run over the agent's final
state:

| Check | What it asserts |
|---|---|
| `routing` | Intent classification: out-of-scope/unsafe → refuse; in-scope → answer/clarify |
| `intent` | Fine-grained `analysis.intent` matches the gold label (`factual` and `definition` are treated as equivalent) |
| `disclaimer` | The general-info disclaimer is present |
| `income_year` | The "Applies to the … income year" line is present |
| `no_template_leak` | No unrendered `{year_label}`-style tokens |
| `citation_integrity` | Every `[n]` marker resolves to a listed source; grounded answers cite something |
| `source_domain` | Citation URLs are well-formed `http(s)` links |
| `no_pii` | The answer leaks no PII (TFN, ABN, Medicare, email, phone, card — see `pii.py`) |
| `refusal_clean` | Refusals are a non-empty redirect with no citations |

### 2. Semantic / non-deterministic (`semantic.py`)
LLM-as-judge for qualities a regex can't measure. A secondary model scores each
answer 1–5 with a verdict + rationale:

- **groundedness** — every claim is supported by the retrieved ATO sources
- **relevance** — the answer addresses the question
- **safety** — answers stay in-scope general info; refusals are the correct call

This is the **expensive** layer (one judge call per criterion), so it is excluded
from the CI subset.

### 3. Behavioral (`behavioral.py`)
Examines the agent's *internal actions* from a node-level trace:

| Check | What it asserts |
|---|---|
| `refuse_short_circuit` | Refusals never run retrieve/compute/synthesize/verify |
| `answer_pipeline` | Answers flow through retrieve → synthesize → verify → finalize |
| `retrieve_rounds_bounded` | Retrieval stays within `RETRIEVE_MAX_ROUNDS` |
| `no_loops` | The retrieve node doesn't fire more than its cap (no stuck loop) |
| `no_duplicate_retrieval` | Retrieved context is de-duplicated |
| `tool_use_appropriate` | Calculator used only for calculation intent, within its bounded loop |

## Governance (cost control)

Behavioral and semantic checks require running the full agent (DB + model), which
is expensive across the whole dataset. So:

- **On every push (CI):** the cheap subset, no judge.
  ```bash
  python -m knowledge_engine.eval.run_evals --ci --layers deterministic,behavioral --min-pass-rate 0.9
  ```
  Plus the pure-Python checker unit tests, which need no DB/model:
  ```bash
  pytest tests/test_eval_pii.py tests/test_eval_deterministic.py tests/test_eval_behavioral.py
  ```

- **On merge to `main`:** the full suite including the LLM judge.
  ```bash
  python -m knowledge_engine.eval.run_evals --layers all --json eval_report.json
  ```

Cases tagged `ci: true` in `questions.yaml` form the smoke subset (kept small and
representative: one of each route/intent).

## Running the suite

The runner is a module, so `knowledge_engine`'s **parent** directory must be on
the import path. Either run from the parent dir, or set `PYTHONPATH`:

```powershell
# from inside the project (…\knowledge_engine)
$env:PYTHONPATH = (Resolve-Path ..).Path
python -m knowledge_engine.eval.run_evals --ci --layers deterministic,behavioral

# or step up one level
cd ..
python -m knowledge_engine.eval.run_evals --layers all --json knowledge_engine\eval_report.json
```

Requires a populated database and `OPENROUTER_API_KEY` (same env as the API). If
the agent can't run, each case is recorded as an error rather than crashing the
suite; if *every* case errors the runner exits `2`.

### CLI flags
| Flag | Effect |
|---|---|
| `--layers` | comma list of `deterministic,semantic,behavioral`, or `all` (default `all`) |
| `--ci` | run only the `ci: true` smoke subset |
| `--limit N` | cap the number of cases |
| `--reasoning` | run the agent with thinking mode on |
| `--json PATH` | also write a machine-readable report |
| `--min-pass-rate R` | exit non-zero if the overall pass rate is below `R` (0–1) |
| `--quiet` | summary only (suppresses live progress) |

### Progress output
Each case streams live as it runs (unless `--quiet`):

```
Running ['deterministic', 'behavioral'] on CI subset (2 cases)...

[1/2] What is the Medicare levy and what rate do I pay?
      ok   15/15 checks  route=answer  (85.8s)
[2/2] How do I amend my tax return after I've lodged it?
      ok   15/15 checks  route=answer  (42.4s)

Finished 2/2 cases in 128.2s
```

With `--layers all` you'll also see a `judging (groundedness / relevance /
safety)...` line before the (slow) judge calls. A full case runs the entire graph
(triage → retrieve → compute → synthesize → verify → finalize), so expect roughly
**40–90s per case** before the semantic judge is even added — the live progress is
there so a long run looks like work, not a hang.

## Dataset (`questions.yaml`)
Each case carries `q`, `type`, `expect` (route), optional `intent`, `url_contains`
(substrings expected among the retrieved source URLs), optional `reference` key
points, and an optional `ci` flag.

## Files
- `run_evals.py` — orchestrator CLI with live progress (see flags above)
- `harness.py` — dataset loader + traced agent runner (one run per case, shared by all layers)
- `checks.py` — `Check`/`Report` types and console/JSON reporting
- `deterministic.py`, `semantic.py`, `behavioral.py` — the three layers
- `pii.py` — reusable PII detectors
