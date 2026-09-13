# BENCHMARK EXECUTOR READINESS V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority: `BENCHMARK_CAPTURE_V0`.

Base SHA: `55f79eb7463a8c75750a75f39bfba97902921a23`.

## Objective

Add a pure, fail-closed evidence-completeness gate for the four frozen `BENCHMARK_CAPTURE_V0` arms before any scheduler, persistence loop, live comparator call, or scored benchmark capture is authorized.

This phase does not execute benchmark arms and does not create executor authority. It represents the capabilities a candidate executor must eventually prove, while refusing to convert caller-supplied identity/protocol/proof claims into activation readiness.

## Task envelope

```text
BASE_SHA: 55f79eb7463a8c75750a75f39bfba97902921a23
OBJECTIVE: pure executor-readiness evidence gate for BENCHMARK_CAPTURE_V0
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

Every arm's candidate evidence must contain:

- an exact `BenchmarkExecutorIdentity`, including configuration digest;
- a benchmark protocol digest claim;
- an auditable proof-artifact reference plus claimed content digest;
- exact benchmark knowledge-horizon enforcement;
- immutable `ValueObservatoryCapture` emission capability;
- explicit failed-capture emission instead of silent dropping.

The gate validates internal completeness and consistency of those claims. It does **not** trust the caller as authority and does **not** dereference or independently verify proof artifacts in this phase.

Therefore the strongest possible result from this module is:

`EVIDENCE_COMPLETE_PENDING_AUTHORITY`

There is deliberately no `READY` status. A separately reviewed later authority phase must anchor the exact executor identities and frozen protocol digest outside the evidence caller and verify the referenced proof artifacts before any arm can satisfy the activation requirement `requires_all_four_executors_ready=true`.

Additional arm-specific requirements are fail-closed.

### FRONTIER_NAIVE_CONTROL

Requires a canonical point-in-time candidate population, frozen naive ordering, and evidence that no experimental score influences the arm.

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

All seven must claim horizon-safe collection state. The executor evidence must preserve per-source attempt status and raw payload digests, must not claim FRONTIER private/history/grouping/projection/PEF/feature state, and must represent the frozen deterministic timestamp ordering. These remain claims until separately verified.

### WEB_LLM_BENCHMARK

Requires provider identity, exact model identity, prompt digest, raw response digest, citations, no FRONTIER private state, no silent provider/model fallback, and retrieval-level enforcement of the benchmark knowledge cutoff. Citation or publication timestamps alone are insufficient. Candidate Web-LLM identity is structurally incomplete unless provider, model, and prompt digest are all present.

## Current implementation audit at base SHA

The gate itself does not claim any executor is ready. Repository state remains blocked for activation:

| Arm | Current audit | Activation consequence |
|---|---|---|
| `FRONTIER_NAIVE_CONTROL` | PIT construction exists, but there is not yet a benchmark executor that binds exact retained boundary input and emits the observatory capture contract | `BLOCKED` |
| `FRONTIER_EXISTING_EXPERIMENTAL` | PEF_V1 confirmatory storage has an exact `experiment_id + as_of` lookup seam, but no observatory executor adapter yet binds that output into the frozen capture contract | `BLOCKED` |
| `ORDINARY_AGGREGATION` | no frozen seven-source benchmark comparator executor exists; horizon-safe collection-state support is not yet proven source-by-source | `BLOCKED` |
| `WEB_LLM_BENCHMARK` | prompt/identity rules are frozen, but no provider/model executor has proven retrieval-level knowledge-cutoff enforcement | `BLOCKED` |

This is intentional. Nearby infrastructure, capability enums, candidate identities, protocol-digest claims, and claimed proof references cannot create activation readiness.

## Hostile review history

The first independent hostile review found one P1: capability enumeration could produce `READY` without binding the claim to an exact executor/protocol/proof artifact.

The first repair added candidate executor identity, protocol digest, and proof reference/digest fields. The single targeted re-review correctly found that this still failed the authority boundary: the same caller controlled the supposed expected identity, protocol digest, evidence, and unverified proof reference, so self-declaration could still produce `READY`.

The final bounded repair therefore removes the `READY` path entirely from this phase. Self-declared complete bundles can only produce `EVIDENCE_COMPLETE_PENDING_AUTHORITY`. Missing or internally inconsistent claims still produce `BLOCKED` with explicit blocker codes.

No further review is authorized by the bounded review budget. Final closure is therefore gated by exact-head CI plus the explicit non-escalation above; a future executor-authority phase must receive its own authority and review.

## Non-escalation

`EVIDENCE_COMPLETE_PENDING_AUTHORITY` does not:

- mark any executor ready;
- activate the 14-day scored run;
- authorize persistence or scheduling;
- authorize backfill or retry of missed scored boundaries;
- verify a proof artifact merely because a ref/digest is present;
- freeze an executor identity or protocol digest;
- alter PEF_V1;
- alter canonical ranking;
- grant an LLM truth or ranking authority;
- prove FRONTIER product superiority.

Activation still requires every prerequisite frozen by `BENCHMARK_CAPTURE_V0`, including population and opportunity completeness, preregistered outcome bindings, immutable trusted protocol/executor authority, verified proof artifacts for all four real executors, and the required independent review gate.
