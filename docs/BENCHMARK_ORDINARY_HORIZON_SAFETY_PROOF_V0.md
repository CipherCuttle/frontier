# BENCHMARK ORDINARY HORIZON SAFETY PROOF V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority:

- `FRONTIER_VALUE_OBSERVATORY_V0`
- `BENCHMARK_CAPTURE_V0`
- `BENCHMARK_EXECUTOR_READINESS_V0`

Base SHA: `5ab9b413876ad4f4c90594e0578a0c72f06ba137`.

## Objective

Audit, source by source, whether there is sufficient evidence for the frozen `ORDINARY_AGGREGATION` comparator to establish exact knowledge-horizon collection state before any ordinary-aggregation executor is implemented.

This phase is deliberately allowed to finish with a `BLOCKED` scientific verdict. A blocked source is not an implementation defect to be worked around. It means the frozen comparator does not yet have enough evidence to execute faithfully under `BENCHMARK_CAPTURE_V0`.

The proof gate does not perform network retrieval, construct a benchmark capture, authorize an executor, change the source set, or weaken the point-in-time rule. Caller-supplied proof claims cannot authorize executor implementation.

## Task envelope

```text
BASE_SHA: 5ab9b413876ad4f4c90594e0578a0c72f06ba137
OBJECTIVE: source-by-source PIT evidence audit for the frozen ordinary comparator
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

## Evidence standard

`BENCHMARK_CAPTURE_V0` requires the ordinary comparator to use collection state available at, or reconstructable for, the exact `knowledge_horizon`.

The following are insufficient by themselves:

- an item publication or update timestamp less than or equal to the horizon;
- querying a mutable current collection after the horizon and filtering returned items by timestamp;
- a current search API whose result membership, ranking, tags, archive state, or index contents may have changed after the horizon;
- a provider claim that an item itself existed before the horizon when the comparator cannot prove that the collection state used to discover or rank it was horizon-safe;
- a git commit's embedded author/committer timestamp without a trustworthy independent publication or receipt-time anchor proving when the commit became publicly available.

A source claim may be marked `EVIDENCE_COMPLETE_PENDING_AUTHORITY` only when a concrete mechanism and nonempty evidence references are supplied. V0 recognizes these mechanism classes as evidence claims, not trusted authority:

- `SOURCE_NATIVE_AS_OF` — the source itself exposes a historical/as-of collection query whose semantics are claimed to establish the required state;
- `AUTHORITY_MIRROR_HISTORY` — an authorized same-authority mirror exposes immutable history plus the material needed to establish public availability at the requested horizon;
- `IMMUTABLE_PRECAPTURE_SNAPSHOT` — a separately authorized immutable public comparator snapshot is captured no later than the benchmark horizon and binds the exact collection state.

`NONE` means the current review did not establish a compliant path.

`BLOCKED_UNPROVEN` does not mean the source is impossible forever. It means executor implementation may not assume a path that has not been demonstrated and independently trusted.

## Frozen seven-source matrix

| Source | V0 evidence result | Mechanism | Consequence |
|---|---|---|---|
| `arxiv.cs-ai` | `BLOCKED_UNPROVEN` | `NONE` | submission-date filtering does not by itself prove exact public/index collection state at the horizon |
| `cisa.kev` | `BLOCKED_UNPROVEN` | `NONE` | the same-authority Git mirror preserves content history, but git commit timestamps do not prove when GitHub publicly exposed each commit; no trusted publication-time anchor is established |
| `gdelt.frontier` | `BLOCKED_UNPROVEN` | `NONE` | publication-time bounds do not by themselves prove historical GDELT index/ingestion state |
| `github.ml-repos` | `BLOCKED_UNPROVEN` | `NONE` | current repository search cannot establish historical result membership/order/topic/archive state from item timestamps alone |
| `hf.models` | `BLOCKED_UNPROVEN` | `NONE` | current Hub model listing exposes mutable present state; no reviewed exact historical collection query is established |
| `hn.frontpage` | `BLOCKED_UNPROVEN` | `NONE` | current front-page/top-story state is mutable; no reviewed arbitrary historical front-page membership/ranking interface is established |
| `pypi.updates` | `BLOCKED_UNPROVEN` | `NONE` | Latest Updates RSS is a current finite feed; no reviewed arbitrary historical feed-state interface is established |

Current result:

```text
EVIDENCE_COMPLETE_PENDING_AUTHORITY: 0 / 7
BLOCKED_UNPROVEN: 7 / 7
ORDINARY_AGGREGATION_EXECUTOR_IMPLEMENTATION: NOT AUTHORIZED
```

The evidence matrix is frozen in:

`experiments/value_observatory_v0/ordinary_horizon_safety_proof_v0.json`

## Pure evidence gate

`assess_ordinary_horizon_safety_v0` consumes exactly one caller-supplied evidence row for every frozen ordinary source.

It fails closed when:

- a frozen source row is missing;
- an extra source is supplied;
- the same source appears more than once;
- an `EVIDENCE_COMPLETE_PENDING_AUTHORITY` row has no explicit mechanism;
- a blocked row claims a mechanism as though it were already complete.

All rows are caller supplied. Therefore, even if all seven rows claim internally complete evidence, the strongest possible result is:

`EVIDENCE_COMPLETE_PENDING_AUTHORITY`

There is deliberately no `READY_FOR_EXECUTOR_IMPLEMENTATION` state in this phase. A later separately reviewed authority phase must bind the exact approved proof artifact outside the evidence caller and independently verify its referenced evidence before executor implementation can be authorized.

This mirrors the existing `BENCHMARK_EXECUTOR_READINESS_V0` rule that evidence completeness is not authority.

## Hostile review repair

The bounded hostile review found two authority defects:

1. `P1` — caller-supplied seven-of-seven proof claims could produce `READY_FOR_EXECUTOR_IMPLEMENTATION`. The repair removes that state; complete claims can only produce `EVIDENCE_COMPLETE_PENDING_AUTHORITY`.
2. `P2` — the initial CISA row overclaimed same-authority git history as point-in-time proof. A git SHA binds content and ancestry, but its embedded timestamp does not establish when GitHub received or publicly exposed the commit. The repair returns `cisa.kev` to `BLOCKED_UNPROVEN` until a trustworthy publication/receipt-time anchor or authorized pre-horizon snapshot exists.

These repairs strengthen fail-closed semantics and do not weaken the frozen benchmark protocol.

## Non-escalation

This phase does not:

- remove or replace a frozen source;
- reinterpret item timestamps as collection-state proof;
- trust a git commit timestamp as public-availability proof;
- use post-horizon mutable state to reconstruct a scored boundary;
- use FRONTIER private/history/grouping/projection/PEF/feature-ledger state for the public comparator;
- implement network retrieval for the comparator;
- create a benchmark executor identity;
- authorize ordinary-executor implementation from caller-supplied evidence;
- construct or persist a scored capture;
- authorize retries, backfill, scheduling, or activation;
- alter PEF_V1 or canonical public ranking.

If one or more sources remain blocked, the correct V0 result is to preserve that block. A source-set change, horizon-rule change, or other semantic workaround requires a separately authorized new benchmark protocol identity rather than mutation of the frozen V0 protocol.

## Verdict and next consequence

Current bounded verdict:

`BLOCKED_ORDINARY_HORIZON_SAFETY_EVIDENCE_0_OF_7_COMPLETE`

The next permitted work is additional source-specific evidence acquisition for compliant horizon-safe paths for the seven blocked sources, without implementing the ordinary comparator and without changing `BENCHMARK_CAPTURE_V0`.

Even a later seven-of-seven evidence bundle remains pending trusted authority until a separately reviewed authority phase verifies and binds it.

If sufficient evidence cannot be established for all seven sources, V0 remains blocked. The project may later choose, under separate authority, to freeze a new benchmark protocol identity with different source or horizon semantics. It must not silently weaken V0 to obtain an executable comparator.
