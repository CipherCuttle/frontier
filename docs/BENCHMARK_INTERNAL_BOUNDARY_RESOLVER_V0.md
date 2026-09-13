# BENCHMARK INTERNAL BOUNDARY RESOLVER V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority:

- `FRONTIER_VALUE_OBSERVATORY_V0`
- `BENCHMARK_CAPTURE_V0`
- `BENCHMARK_EXECUTOR_READINESS_V0`
- `BENCHMARK_INTERNAL_EXECUTORS_V0`

Base SHA: `0b976784aff4c4b4ed93bd5231d3aca321340240`.

## Objective

Resolve already-persisted evidence for the two internal `BENCHMARK_CAPTURE_V0` arms at one exact requested `knowledge_horizon` without introducing latest, nearest, carry-forward, recomputation, retry, or backfill semantics.

The resolver remains a storage boundary. The pure capture adapters from `BENCHMARK_INTERNAL_EXECUTORS_V0` continue to own capture construction and frozen comparator validation.

## Task envelope

```text
BASE_SHA: 0b976784aff4c4b4ed93bd5231d3aca321340240
OBJECTIVE: exact persisted boundary resolution for the two internal benchmark arms
AUTHORITY_REFS:
  - docs/FRONTIER_VALUE_OBSERVATORY_V0.md
  - docs/BENCHMARK_CAPTURE_V0.md
  - docs/BENCHMARK_EXECUTOR_READINESS_V0.md
  - docs/BENCHMARK_INTERNAL_EXECUTORS_V0.md
  - experiments/value_observatory_v0/benchmark_capture_v0.json
ALLOWED_PATHS:
  - src/frontier/application/value_observatory_internal_boundary.py
  - src/frontier/adapters/postgres/value_observatory_internal_boundary.py
  - tests/integration/test_value_observatory_internal_boundary_postgres.py
  - docs/BENCHMARK_INTERNAL_BOUNDARY_RESOLVER_V0.md
FORBIDDEN_PATHS:
  - migrations/**
  - scheduler/runtime activation
  - scored observatory persistence
  - ordinary aggregation executor
  - Web-LLM executor
  - source registry mutation
  - PEF_V1 recomputation/mutation
  - canonical public ranking/read-plane semantics
  - executor/protocol activation authority
ACCEPTANCE_CHECKS:
  - uv lock --check
  - uv sync --all-extras --frozen
  - uv run python scripts/verify.py
  - normal repository CI, including e2e-postgres
REVIEW_BUDGET: one hostile review; one targeted re-review only if Critical/High repair is required
MERGE_AUTHORITY: false
```

## Resolver contract

`InternalBenchmarkBoundaryResolver` exposes two exact reads:

- `resolve_naive(knowledge_horizon)`;
- `resolve_pef_v1(knowledge_horizon)`.

A missing exact row returns `None`. The later orchestration slice must convert that absence into the existing explicit FAILED internal capture rather than dropping the arm.

Persistence ambiguity or integrity drift raises and fails closed. It is never converted into an arbitrary winner by sorting and taking one row.

## Naive boundary

The PostgreSQL resolver reads `baseline_intelligence_snapshots` only where:

```text
as_of == requested knowledge_horizon
```

It joins the snapshot's bound `projection_receipts` row and reconstructs the immutable `BaselineSnapshot` and `ProjectionReceipt`.

The resolver verifies:

- there is at most one exact snapshot;
- stored snapshot id hashes the stored canonical payload;
- typed canonical reconstruction exactly matches the stored JSON;
- snapshot/row/receipt all bind the requested horizon;
- persisted snapshot identity columns match the canonical payload;
- stored output digest and receipt output digest bind that snapshot;
- the receipt is COMPLETE and carries the frozen baseline receipt/projection/schema/algorithm/ranking/configuration identity.

It deliberately does not call `latest_complete_snapshot_id()`.

A prior or later retained snapshot is irrelevant to an exact lookup.

## PEF_V1 boundary

The PostgreSQL resolver starts from `shadow_experiment_runs` only where:

```text
experiment_id == PEF_V1_EXPERIMENT_ID
as_of == requested knowledge_horizon
```

It does not use the existing `ORDER BY run_id DESC LIMIT 1` convenience pattern. Zero exact rows means missing evidence; more than one exact PEF_V1 run is an ambiguous boundary and fails closed.

The single exact run must be a freeze-bound `CONFIRMATORY` PEF_V1 run. The resolver joins its exact candidate artifact and projection receipt, then verifies:

- run id and run digest bind the stored canonical run JSON;
- run experiment/candidate/schema/algorithm/configuration/authority identities are frozen PEF_V1 identities;
- the run carries a candidate freeze-receipt binding;
- artifact id hashes the stored canonical artifact payload;
- typed artifact reconstruction exactly matches stored JSON;
- run, artifact, and receipt bind the same exact horizon;
- run/artifact control snapshot and receipt references agree;
- run/artifact/receipt output digests agree;
- artifact/receipt source-registry and frozen projection identities agree;
- RAN/COMPLETE and FAILED/FAILED status pairs remain consistent.

A persisted FAILED PEF_V1 boundary is returned as FAILED evidence rather than disappearing. The later capture orchestration must turn that into an explicit FAILED benchmark capture.

## No fallback / no escalation

This phase does not:

- select the latest baseline snapshot;
- select the latest PEF run at an exact horizon;
- choose among ambiguous same-horizon rows;
- substitute the previous or next boundary;
- recompute baseline or PEF output;
- construct benchmark captures;
- schedule benchmark execution;
- persist scored observatory artifacts;
- authorize retries or backfill;
- create external comparators;
- activate any executor as trusted authority.

The resulting data path remains:

```text
exact PostgreSQL resolver
        ↓
exact immutable internal artifact + receipt
        ↓
pure internal capture adapter
        ↓
ValueObservatoryCapture
```
