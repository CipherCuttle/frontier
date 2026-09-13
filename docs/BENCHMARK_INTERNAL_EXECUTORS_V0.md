# BENCHMARK INTERNAL EXECUTORS V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority:

- `FRONTIER_VALUE_OBSERVATORY_V0`
- `BENCHMARK_CAPTURE_V0`
- `BENCHMARK_EXECUTOR_READINESS_V0`

Base SHA: `b6ae2e1392f7f8f73d1cd4f1b0bf83522cd7cfbd`.

## Objective

Add the smallest pure capture-adapter layer for the two internal FRONTIER benchmark arms:

- `FRONTIER_NAIVE_CONTROL`;
- `FRONTIER_EXISTING_EXPERIMENTAL`.

The adapters consume already-resolved exact-boundary artifacts and convert them into the frozen immutable `ValueObservatoryCapture` contract. They do not retrieve a boundary, schedule a run, persist observatory state, or create benchmark activation authority.

## Task envelope

```text
BASE_SHA: b6ae2e1392f7f8f73d1cd4f1b0bf83522cd7cfbd
OBJECTIVE: pure exact-boundary capture adapters for the two internal benchmark arms
AUTHORITY_REFS:
  - docs/FRONTIER_VALUE_OBSERVATORY_V0.md
  - docs/BENCHMARK_CAPTURE_V0.md
  - docs/BENCHMARK_EXECUTOR_READINESS_V0.md
  - experiments/value_observatory_v0/benchmark_capture_v0.json
ALLOWED_PATHS:
  - src/frontier/application/value_observatory_internal_executors.py
  - tests/unit/test_value_observatory_internal_executors.py
  - docs/BENCHMARK_INTERNAL_EXECUTORS_V0.md
FORBIDDEN_PATHS:
  - migrations/**
  - ordinary aggregation executor
  - Web-LLM executor
  - scheduler/runtime activation
  - scored observatory persistence
  - source registry
  - PEF_V1 implementation/freeze semantics
  - canonical public ranking/read-plane semantics
ACCEPTANCE_CHECKS:
  - uv lock --check
  - uv sync --all-extras --frozen
  - uv run python scripts/verify.py
  - normal repository CI
REVIEW_BUDGET: one hostile review; one targeted re-review only if Critical/High repair is required
MERGE_AUTHORITY: false
```

## Naive adapter

`build_naive_observatory_capture` accepts an already-retained `BaselineSnapshot` and its `ProjectionReceipt` plus an explicit requested benchmark knowledge horizon.

It fails closed unless:

- snapshot `as_of` equals the requested knowledge horizon exactly;
- receipt `as_of` equals that same horizon exactly;
- receipt status and baseline schema/projection/algorithm/ranking/config identities match the frozen baseline;
- receipt output digest binds the exact snapshot canonical payload;
- source ranks are contiguous from one.

The retained baseline rank is validated as source-artifact integrity but is not the benchmark comparator order. The adapter applies the frozen `BENCHMARK_CAPTURE_V0` naive-arm ordering directly: newest `last_observed_at` first, then canonical episode/item key lexical order, and emits at most K=5 items. The adapter does not recompute the baseline and does not read the database.

## PEF_V1 adapter

`build_pef_v1_observatory_capture` accepts an already-resolved `PefV1Artifact` and its `ProjectionReceipt` plus an explicit requested benchmark knowledge horizon.

It fails closed unless:

- artifact and receipt `as_of` both equal the requested horizon exactly;
- artifact is `RAN` and carries the frozen PEF_V1 experiment/candidate/configuration/schema/algorithm/ranking/authority identities;
- receipt is COMPLETE and carries the matching receipt family/projection/schema/algorithm/ranking/configuration identities;
- source-registry identity agrees;
- receipt output digest binds the exact PEF_V1 artifact;
- artifact and receipt generation timestamps agree;
- the frozen output was generated no later than the claimed capture time and no later than the frozen 30-minute capture deadline;
- source ranks are contiguous from one.

Complete internal captures also fail closed when `captured_at` itself exceeds the frozen 30-minute capture deadline.

The adapter consumes the supplied frozen artifact directly. It performs no PEF recomputation and provides no prior-boundary fallback.

The current Postgres confirmatory store already has an exact `experiment_id + as_of` lookup seam. Wiring that seam into this adapter is intentionally separate from the pure mapping contract.

## Explicit failure

`build_failed_internal_observatory_capture` emits the frozen FAILED capture shape for either internal arm, with no surfaced items and an explicit failure reason. This supports the benchmark rule that a missing/invalid internal boundary remains a recorded arm failure rather than disappearing or being backfilled.

## Evidence identity

For complete internal captures:

- `raw_response_digest` is the exact retained source artifact output digest;
- each item digest binds the source episode/ranking canonical payload;
- item evidence refs bind the source observation IDs;
- `input_digest` binds the internal arm, requested knowledge horizon, exact source artifact identity, and source receipt identity.

The executor identity remains a candidate identity supplied to the adapter and embedded in the capture. This phase does not promote it to trusted executor authority. `BENCHMARK_EXECUTOR_READINESS_V0` remains fail-closed pending a later separately reviewed authority/proof-verification phase.

## Non-escalation

This phase does not:

- mark either internal executor activation-ready;
- create an exact baseline Postgres read seam;
- alter or recompute PEF_V1;
- authorize prior-boundary fallback;
- create the ordinary-aggregation or Web-LLM comparators;
- schedule the 14-day run;
- persist scored observatory captures;
- authorize retry or backfill of missed scored boundaries;
- alter canonical public ranking;
- prove FRONTIER product superiority.
