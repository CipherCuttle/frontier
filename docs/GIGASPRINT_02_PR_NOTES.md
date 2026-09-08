# GIGASPRINT_02 — Pre-confirmatory integrity + launch closure

## Status

`MERGE_READY_ON_GREEN_EXACT_HEAD_CI / NO_REAL_FREEZE / NO_CONFIRMATORY_EVIDENCE`

Base: `main@86ea43e6926213c4ff1252365cc3998b3dd8ac05` (PR #34 merge).

This document is build/review notes only. It does not grant scientific, governance, freeze, confirmatory, or promotion authority. Frozen authority remains the accepted repository governance and `experiments/advanced_intelligence/pef_v0/preregistration.json`.

## Objective

Close the remaining pre-confirmatory trust-boundary defects left after GIGASPRINT_01 so PEF_V0 can be truthfully frozen and launched without changing the preregistered candidate ranking semantics.

The sprint is deliberately narrow: no new product surface, no ranking redesign, no new source, no model/LLM/embedding work, no second scheduler/state model, and no real candidate freeze.

## Required closures

### G2-01 — Frozen-registry confinement

Current paired baseline construction must not admit scientific-universe drift from mutable database source state.

For CONFIRMATORY execution:

- observations are limited to the exact source IDs frozen by the bound candidate-freeze identity;
- source signal roles come from the immutable frozen source contracts, not mutable `sources.signal_roles` rows;
- grouping relations are retained only when both endpoints belong to the frozen observation universe;
- health is read only for frozen source IDs;
- current DB `sources.enabled` state cannot silently add or remove the scientific universe;
- an extra/stale DB source must be proven unable to contaminate either arm.

DEV behavior may remain broader where already intended, but CONFIRMATORY must fail closed on any inability to reconstruct the frozen universe exactly.

Closure: `CLOSED_VERIFIED` on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`.

### G2-02 — Freeze clock authority reconciliation

The preregistration freezes the ranking-window start as:

> first UTC epoch-multiple-of-300 boundary strictly after the GitHub `main` merge-commit committer timestamp that durably publishes the candidate-freeze receipt.

GIGASPRINT_01 also introduced canonical-DB `durable_freeze_at` as the database durability fact.

These are separate facts and must not be collapsed or silently reinterpreted.

Required end state:

- canonical DB durability remains explicit;
- GitHub durable publication timestamp remains the scientific window-start authority required by the preregistration;
- the bound receipt/runtime record can prove which GitHub publication commit/timestamp established the scientific start;
- confirmatory scheduling derives the fixed `[start,start+2419200)` interval from that publication timestamp;
- local wall clocks and DB clocks cannot move the preregistered start/end;
- no missing boundary may shift the fixed window.

Do not edit preregistered scientific semantics merely to fit the implementation. If a contract cannot be satisfied without changing the preregistration, stop and report `RESTART_AUTHORITY_REQUIRED` instead.

Closure: `CLOSED_VERIFIED` on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`. Production publication persistence now derives and verifies the exact canonical GitHub `refs/heads/main` publication before insertion; raw production publication writes are forbidden, persisted publication payload/digest identity is revalidated on load, and synthetic publication insertion exists only under `tests/`.

### G2-03 — D011 confirmatory-evaluation bypass

Close the path where a confirmatory-looking evaluation can be produced outside the full confirmatory authority path.

Required end state:

- evaluation class is explicit, or an equivalent typed authority boundary exists;
- CONFIRMATORY evaluation requires the same bound freeze, durability/publication, canonical-context, drift, and scientific-window gates as CONFIRMATORY execution;
- caller-supplied timestamps/flags alone cannot manufacture confirmatory evidence;
- DEV results remain permanently DEV and cannot be relabeled retroactively.

Closure: `CLOSED_VERIFIED` on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`.

### G2-04 — D012 persistence authorization below CLI

`FRONTIER_FREEZE_PERSIST_AUTHORIZED` was previously enforced at the CLI boundary only.

Required end state:

- the shared freeze persistence path itself requires an explicit authorization capability/context;
- direct repository/application callers cannot persist a real freeze merely by bypassing the CLI;
- fixture/test persistence stays possible only through an explicit test authorization path;
- unauthorized persistence fails before a database write;
- the CLI remains an operator UX layer, not the security boundary.

Closure: `CLOSED_VERIFIED`; implementation commit `320a54a618bab2581a84dd3d293c7e1d5cab59cf`, carried and reverified on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`.

### G2-05 — D014 DB-side confirmatory time gate

Remove the application-vs-DB clock-skew residual before CONFIRMATORY execution goes live.

Required end state:

- the authoritative `as_of` eligibility check against DB durability/publication bindings is evaluated using canonical persisted facts inside the same DB transaction/authority boundary used to claim the confirmatory attempt;
- application wall-clock skew cannot admit an otherwise ineligible confirmatory boundary;
- exact-boundary and skew regressions fail closed.

Closure: `CLOSED_VERIFIED` on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`.

## Fixed scientific invariants

Do not change during this sprint:

- candidate id/version/configuration/ranking order;
- baseline ranking authority;
- global K = 100;
- cadence = 300 seconds, UTC epoch aligned;
- ranking window = 2,419,200 seconds (28 days);
- no early stopping;
- no window extension for sample size;
- missing boundaries cannot shift start or end;
- exact frozen source registry requirement;
- opportunity/outcome definitions;
- domain/sample/statistical thresholds;
- promotion remains separate authority;
- PEF remains `EXPERIMENTAL_SHADOW`.

## Work discipline

For each bounded work package:

`IMPLEMENT -> TEST -> ONE independent hostile review -> fix Critical/High -> ONE targeted re-review only if Critical/High repairs were required -> COMMIT -> MOVE FORWARD`

Medium/Low findings do not restart the sprint unless they undermine the sprint objective, violate a frozen invariant/contract, corrupt evidence, or create fail-open authority ambiguity.

## Required verification

Before this sprint can be called merge-ready:

1. exact-head static repository verification passes;
2. live PostgreSQL integration suite passes;
3. existing ops-recovery / ops-capacity / preflight contracts remain green;
4. extra-source contamination regression proves the frozen universe is exact;
5. direct non-CLI freeze persistence without authority is rejected and writes zero rows;
6. DB/application clock-skew regression cannot admit confirmatory work;
7. GitHub publication timestamp -> first legal 300-second boundary derivation is deterministic and prereg-compatible;
8. DEV output cannot become CONFIRMATORY by caller flags or supplied timestamps;
9. one bounded hostile review reports zero unresolved Critical/High findings.

## Closure evidence

Final runtime/code head before this docs-only closure commit:

`93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`

Standard exact-head CI on that code head:

- `verify #401` / run `34208795484` — PASS;
- `e2e-postgres #60` / run `34208795369` — PASS;
- `ops-capacity #237` / run `34208795219` — PASS;
- `ops-recovery #241` / run `34208795236` — PASS.

The bounded hostile review found one real High in the publication-authority chain. The first repair bound publication to canonical GitHub `main`. The permitted targeted re-review then found an unchecked production fixture writer; that seam was removed in `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`. Final unresolved review disposition: `CRITICAL=0 / HIGH=0`.

This closure commit is documentation-only. It must itself receive the normal exact-head workflows. If `verify`, `e2e-postgres`, `ops-capacity`, and `ops-recovery` are all green on that docs-only head, the sprint verdict becomes `GIGASPRINT_02_READY_FOR_MERGE` without another receipt-only commit.

## Explicit non-scope

- no real candidate freeze;
- no confirmatory evidence collection;
- no promotion decision;
- no source-registry change;
- no ranking/feature/statistics change;
- no deployment-platform expansion;
- no Agent Context/MCP/vector/LLM implementation;
- no second orchestration/state model;
- no speculative infrastructure.

## Completion verdicts

Exactly one:

- `GIGASPRINT_02_READY_FOR_MERGE`
- `GIGASPRINT_02_REPAIR_REQUIRED`
- `GIGASPRINT_02_BLOCKED_RESTART_AUTHORITY_REQUIRED`

After merge and canonical-main verification, the next phase is a **new** replacement candidate freeze bound to the final implementation commit/tree, followed by durable GitHub publication and derivation of the first legal confirmatory boundary. The old v0 receipt remains historical evidence only.
