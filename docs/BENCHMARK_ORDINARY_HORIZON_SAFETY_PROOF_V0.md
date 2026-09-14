# BENCHMARK ORDINARY HORIZON SAFETY PROOF V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority:

- `FRONTIER_VALUE_OBSERVATORY_V0`
- `BENCHMARK_CAPTURE_V0`
- `BENCHMARK_EXECUTOR_READINESS_V0`

Base SHA: `5ab9b413876ad4f4c90594e0578a0c72f06ba137`.

## Objective

Prove, source by source, whether the frozen `ORDINARY_AGGREGATION` comparator can establish exact knowledge-horizon collection state before any ordinary-aggregation executor is implemented.

This phase is deliberately allowed to finish with a `BLOCKED` scientific verdict. A blocked source is not an implementation defect to be worked around. It means the frozen comparator does not yet have enough evidence to execute faithfully under `BENCHMARK_CAPTURE_V0`.

The proof gate does not perform network retrieval, construct a benchmark capture, authorize an executor, change the source set, or weaken the point-in-time rule.

## Task envelope

```text
BASE_SHA: 5ab9b413876ad4f4c90594e0578a0c72f06ba137
OBJECTIVE: source-by-source PIT feasibility proof for the frozen ordinary comparator
AUTHORITY_REFS:
  - docs/FRONTIER_VALUE_OBSERVATORY_V0.md
  - docs/BENCHMARK_CAPTURE_V0.md
  - docs/BENCHMARK_EXECUTOR_READINESS_V0.md
  - experiments/value_observatory_v0/benchmark_capture_v0.json
ALLOWED_PATHS:
  - src/frontier/application/value_observatory_ordinary_horizon_safety.py
  - tests/unit/test_value_observatory_ordinary_horizon_safety.py
  - experiments/value_observatory_v0/ordinary_horizon_safety_proof_v0.json
  - docs/BENCHMARK_ORDINARY_HORIZON_SAFETY_PROOF_V0.md
FORBIDDEN_PATHS:
  - migrations/**
  - sources/registry/**
  - acquisition runtime/fetcher implementation
  - ordinary-aggregation executor implementation
  - Web-LLM executor implementation
  - scheduler/runtime activation
  - scored observatory persistence
  - benchmark source-set or protocol mutation
  - canonical public ranking/read-plane semantics
  - executor/protocol activation authority
ACCEPTANCE_CHECKS:
  - uv lock --check
  - uv sync --all-extras --frozen
  - uv run python scripts/verify.py
  - normal repository CI
REVIEW_BUDGET: one hostile review; one targeted re-review only if Critical/High repair is required
MERGE_AUTHORITY: false
```

## Proof standard

`BENCHMARK_CAPTURE_V0` requires the ordinary comparator to use collection state available at, or reconstructable for, the exact `knowledge_horizon`.

The following are insufficient by themselves:

- an item publication or update timestamp less than or equal to the horizon;
- querying a mutable current collection after the horizon and filtering returned items by timestamp;
- a current search API whose result membership, ranking, tags, archive state, or index contents may have changed after the horizon;
- a provider claim that an item itself existed before the horizon when the comparator cannot prove that the collection state used to discover or rank it was horizon-safe.

A source may be marked `PROVEN_HORIZON_SAFE` only when a concrete mechanism can bind the collection state used by the comparator to the requested horizon. V0 recognizes these mechanism classes:

- `SOURCE_NATIVE_AS_OF` — the source itself exposes a historical/as-of collection query whose semantics establish the required state;
- `AUTHORITY_MIRROR_HISTORY` — an authorized same-authority mirror exposes immutable history that can reconstruct the collection state without using future state;
- `IMMUTABLE_PRECAPTURE_SNAPSHOT` — a separately authorized immutable public comparator snapshot is captured no later than the benchmark horizon and binds the exact collection state.

`NONE` means the current review did not establish a compliant path.

`BLOCKED_UNPROVEN` does not mean the source is impossible forever. It means executor implementation may not assume a path that has not been demonstrated.

## Frozen seven-source matrix

| Source | V0 proof result | Mechanism | Consequence |
|---|---|---|---|
| `arxiv.cs-ai` | `BLOCKED_UNPROVEN` | `NONE` | submission-date filtering does not by itself prove exact public/index collection state at the horizon |
| `cisa.kev` | `PROVEN_HORIZON_SAFE` | `AUTHORITY_MIRROR_HISTORY` | frozen contract already recognizes the CISA GitHub mirror as `SAME_AUTHORITY_MIRROR`; immutable git history can bind a no-later-than-horizon mirror state |
| `gdelt.frontier` | `BLOCKED_UNPROVEN` | `NONE` | publication-time bounds do not by themselves prove historical GDELT index/ingestion state |
| `github.ml-repos` | `BLOCKED_UNPROVEN` | `NONE` | current repository search cannot establish historical result membership/order/topic/archive state from item timestamps alone |
| `hf.models` | `BLOCKED_UNPROVEN` | `NONE` | current Hub model listing exposes mutable present state; no reviewed exact historical collection query is established |
| `hn.frontpage` | `BLOCKED_UNPROVEN` | `NONE` | current front-page/top-story state is mutable; no reviewed arbitrary historical front-page membership/ranking interface is established |
| `pypi.updates` | `BLOCKED_UNPROVEN` | `NONE` | Latest Updates RSS is a current finite feed; no reviewed arbitrary historical feed-state interface is established |

Current result:

```text
PROVEN: 1 / 7
BLOCKED_UNPROVEN: 6 / 7
ORDINARY_AGGREGATION_EXECUTOR_IMPLEMENTATION: BLOCKED
```

The evidence matrix is frozen in:

`experiments/value_observatory_v0/ordinary_horizon_safety_proof_v0.json`

## Pure proof gate

`assess_ordinary_horizon_safety_v0` consumes exactly one proof row for every frozen ordinary source.

It fails closed when:

- a frozen source proof is missing;
- an extra source is supplied;
- the same source appears more than once;
- a `PROVEN_HORIZON_SAFE` row has no explicit proof mechanism;
- a blocked row claims a mechanism as though it were already proven.

The result is `READY_FOR_EXECUTOR_IMPLEMENTATION` only when all seven frozen source rows are `PROVEN_HORIZON_SAFE`.

The proof gate is not executor readiness or activation authority. Even an all-green proof matrix would only permit a separately bounded executor implementation phase to begin. `BENCHMARK_EXECUTOR_READINESS_V0` and the later trusted executor/protocol authority remain separate gates.

## Non-escalation

This phase does not:

- remove or replace a frozen source;
- reinterpret item timestamps as collection-state proof;
- use post-horizon mutable state to reconstruct a scored boundary;
- use FRONTIER private/history/grouping/projection/PEF/feature-ledger state for the public comparator;
- implement network retrieval for the comparator;
- create a benchmark executor identity;
- construct or persist a scored capture;
- authorize retries, backfill, scheduling, or activation;
- alter PEF_V1 or canonical public ranking.

If one or more sources remain blocked, the correct V0 result is to preserve that block. A source-set change, horizon-rule change, or other semantic workaround requires a separately authorized new benchmark protocol identity rather than mutation of the frozen V0 protocol.

## Verdict and next consequence

Current bounded verdict:

`BLOCKED_ORDINARY_EXECUTOR_HORIZON_SAFETY_1_OF_7_PROVEN`

The next permitted work is additional source-specific proof of compliant horizon-safe paths for the six blocked sources, without implementing the ordinary comparator and without changing `BENCHMARK_CAPTURE_V0`.

If such proof cannot be established for all seven sources, V0 remains blocked. The project may later choose, under separate authority, to freeze a new benchmark protocol identity with different source or horizon semantics. It must not silently weaken V0 to obtain an executable comparator.
