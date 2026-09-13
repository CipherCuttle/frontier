# BENCHMARK EXECUTOR READINESS V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority: `BENCHMARK_CAPTURE_V0`.

Base SHA: `55f79eb7463a8c75750a75f39bfba97902921a23`.

## Objective

Add a pure, fail-closed readiness gate for the four frozen `BENCHMARK_CAPTURE_V0` arms before any scheduler, persistence loop, live comparator call, or scored benchmark capture is authorized.

This phase does not execute benchmark arms. It only represents the capabilities each executor must prove before activation may proceed.

## Task envelope

```text
BASE_SHA: 55f79eb7463a8c75750a75f39bfba97902921a23
OBJECTIVE: pure executor-readiness gate for BENCHMARK_CAPTURE_V0
AUTHORITY_REFS:
  - docs/FRONTIER_VALUE_OBSERVATORY_V0.md
  - docs/BENCHMARK_CAPTURE_V0.md
  - experiments/value_observatory_v0/benchmark_capture_v0.json
ALLOWED_PATHS:
  - src/frontier/application/value_observatory_executor_readiness.py
  - tests/unit/test_value_observatory_executor_readiness.py
  - docs/BENCHMARK_EXECUTOR_READINESS_V0.md
FORBIDDEN_PATHS:
  - migrations/**
  - source registry
  - PEF_V1 implementation/freeze/window/operator state
  - canonical public ranking/read-plane semantics
  - scheduler/runtime deployment
  - scored observatory persistence
ACCEPTANCE_CHECKS:
  - uv lock --check
  - uv sync --all-extras --frozen
  - uv run python scripts/verify.py
  - normal repository CI
REVIEW_BUDGET: one hostile review; one targeted re-review only if Critical/High repair is required
MERGE_AUTHORITY: false
```

## Frozen executor requirements represented by the gate

Every arm must prove:

- an executor exists;
- the readiness record is bound to the trusted exact `BenchmarkExecutorIdentity`, including its configuration digest;
- the readiness record binds the exact frozen benchmark protocol digest;
- the capability claim is accompanied by an auditable proof artifact reference plus content digest;
- the exact benchmark knowledge horizon is enforced;
- an immutable `ValueObservatoryCapture` shape can be emitted;
- executor failure can be emitted explicitly as a failed capture instead of being silently dropped.

A capability enum alone is never enough to produce `READY`. Missing trusted executor identity, protocol mismatch, executor-identity drift, or missing/malformed proof binding fails closed. The pure gate does not fetch proof artifacts; the reference plus digest makes the evidence independently inspectable and prevents later executor/configuration substitution from inheriting an earlier readiness result.

Additional arm-specific requirements are fail-closed.

### FRONTIER_NAIVE_CONTROL

Requires a canonical point-in-time candidate population, frozen naive ordering, and proof that no experimental score influences the arm.

### FRONTIER_EXISTING_EXPERIMENTAL

Requires exact-boundary valid frozen PEF_V1 output, no prior-boundary fallback, and no later recomputation substituted for the frozen output.

### ORDINARY_AGGREGATION

Requires the exact frozen seven-source set:

- `hn.frontpage`;
- `pypi.updates`;
- `github.ml-repos`;
- `arxiv.cs-ai`;
- `cisa.kev`;
- `hf.models`;
- `gdelt.frontier`.

All seven must prove horizon-safe collection state. The executor must preserve per-source attempt status and raw payload digests, must not read FRONTIER private/history/grouping/projection/PEF/feature state, and must use the frozen deterministic timestamp ordering.

### WEB_LLM_BENCHMARK

Requires provider identity, exact model identity, prompt digest, raw response digest, citations, no FRONTIER private state, no silent provider/model fallback, and retrieval-level enforcement of the benchmark knowledge cutoff. Citation or publication timestamps alone are insufficient. The trusted expected executor identity itself must contain provider, model, and prompt digest before it can participate in a `READY` assessment.

## Current implementation audit at base SHA

The readiness gate itself does not claim any executor is ready. The repository state at the base SHA remains blocked for activation:

| Arm | Current audit | Readiness consequence |
|---|---|---|
| `FRONTIER_NAIVE_CONTROL` | PIT construction exists, but there is not yet a benchmark executor that binds exact retained boundary input and emits the observatory capture contract | `BLOCKED` |
| `FRONTIER_EXISTING_EXPERIMENTAL` | PEF_V1 confirmatory storage has an exact `experiment_id + as_of` lookup seam, but no observatory executor adapter yet binds that output into the frozen capture contract | `BLOCKED` |
| `ORDINARY_AGGREGATION` | no frozen seven-source benchmark comparator executor exists; horizon-safe collection-state support is not yet proven source-by-source | `BLOCKED` |
| `WEB_LLM_BENCHMARK` | prompt/identity rules are frozen, but no provider/model executor has proven retrieval-level knowledge-cutoff enforcement | `BLOCKED` |

This is intentional. Missing executor evidence remains a blocker; the gate must never infer readiness from nearby infrastructure.

## Hostile review repair

The first independent hostile review found one P1: a caller could previously enumerate every capability and obtain `READY` without binding the claim to a real executor, frozen protocol identity, or auditable proof artifact.

The repair requires:

1. a trusted expected `BenchmarkExecutorIdentity` for each frozen arm;
2. exact equality between that identity and the executor identity in the readiness evidence;
3. exact frozen protocol-digest equality;
4. a non-empty proof artifact reference and digest on every readiness record;
5. complete provider/model/prompt identity for the Web-LLM arm.

This repair does not create any executor or make the current repository ready. It only prevents self-declared capability sets from clearing the gate.

## Non-escalation

Passing this readiness gate later will not by itself:

- activate the 14-day scored run;
- authorize persistence or scheduling;
- authorize backfill or retry of missed scored boundaries;
- alter PEF_V1;
- alter canonical ranking;
- grant an LLM truth or ranking authority;
- prove FRONTIER product superiority.

Activation still requires every prerequisite frozen by `BENCHMARK_CAPTURE_V0`, including population and opportunity completeness, preregistered outcome bindings, exact protocol identity, all four real executors, and the bounded independent review gate.
