# FRONTIER ZERO-DAY V0

Status: DIAGNOSTIC_PROTOCOL_V0

Parent: `main@ac916e85e6aed7ddb0501600fd1e6831d82e8489`.

FRONTIER ZERO-DAY is a read-only diagnostic for the question:

> Can FRONTIER surface a development before ordinary attention/discovery evidence makes it obvious?

It is deliberately **not** a promotion experiment, ranking authority, outcome-label authority, entity-truth authority, or replacement for PEF_V1 confirmatory evaluation.

## Non-escalation boundary

ZERO-DAY MUST NOT:

- change PEF_V1 candidate code, configuration, freeze identity, confirmatory window, or rank budget;
- write to canonical observations, grouping, baseline, PEF artifacts, confirmatory runs, attempts, opportunities, outcomes, or evaluation receipts;
- reuse ZERO-DAY hits/misses as PEF_V1 confirmatory evidence;
- select a historical boundary after inspecting later outcomes;
- backfill a missed ZERO-DAY seal;
- infer factual confirmation, provenance independence, entity truth, causal ancestry, or importance from later attention;
- treat missing ATTENTION/DISCOVERY evidence as proof that no attention/discovery existed outside FRONTIER coverage.

ZERO-DAY output is `DIAGNOSTIC_ONLY`.

## Input authority

A seal may be derived only from one persisted COMPLETE/RAN **PEF_V1 CONFIRMATORY** paired run and its exactly bound PEF_V1 candidate artifact.

The seal binds at minimum:

- PEF_V1 run id and run digest;
- candidate artifact id and output digest;
- candidate freeze receipt id;
- source-registry version;
- exact `as_of` boundary;
- candidate and control ranks used for selection.

The candidate and control universe must be identical. A failed, partial, freeze-unbound, non-confirmatory, or identity-mismatched run fails closed.

## Seal cadence

ZERO-DAY V0 has four deterministic UTC seal opportunities per day:

`00:00`, `06:00`, `12:00`, `18:00` UTC.

Equivalently, an eligible `as_of` is an exact six-hour Unix-epoch multiple.

A seal uses only the PEF_V1 confirmatory run at that exact boundary. If that run is absent, failed, delayed past persistence, or otherwise unavailable, the ZERO-DAY boundary is **MISSING**. It is never replaced by a nearby or later boundary and is never backfilled.

A valid live seal must be created no earlier than its source boundary and no later than **30 minutes** after that boundary. A boundary whose seal is not durably derivable inside this window is **MISSING**. This latency bound prevents historical reconstruction from masquerading as a live sealed forecast.

This cadence is a diagnostic cadence only. It does not alter PEF_V1's five-minute confirmatory schedule.

## Cohort selection

Cohort size is fixed at **5**.

Walk the PEF_V1 candidate ranking in ascending candidate-rank order and retain the first five episodes satisfying all of these conditions at seal `as_of`:

1. `has_prospective_primary_emission == true`;
2. the candidate ranks the episode strictly earlier/higher than the paired naive control (`candidate_rank < control_rank`);
3. among the exact observations belonging to that sealed episode and known by `as_of`, FRONTIER has observed **no** `ATTENTION` or `DISCOVERY` signal role.

If fewer than five episodes satisfy the rule, retain the smaller cohort. An empty cohort is valid and explicit.

There is no secondary score, manual curation, threshold tuning, or post-hoc reorder. `rank_advantage = control_rank - candidate_rank` is reported for interpretation but does not determine cohort order.

The no-attention condition means only `NO_ATTENTION_OR_DISCOVERY_OBSERVED_BY_FRONTIER_AT_SEAL`. It is not a claim of real-world absence.

## Seal identity

A seal is canonical JSON with a content-derived SHA-256 identity. Recomputing the same seal inputs must produce the same seal id.

Every cohort member records:

- position in the sealed cohort;
- episode id;
- exact observation ids present in the sealed episode;
- candidate rank;
- control rank;
- rank advantage;
- prospective-primary freshness timestamp/age exposed by PEF.

## Follow-on grading

V0 diagnostic horizons are fixed at:

- +6 hours;
- +24 hours;
- +72 hours;
- +168 hours (7 days).

A follow-on HIT requires at least one eligible `ATTENTION` or `DISCOVERY` observation first known by FRONTIER strictly after the seal boundary and no later than the requested horizon cutoff.

A grade before its cutoff is `PENDING`. At or after the cutoff, a member with at least one qualifying follow-on observation is `HIT`; otherwise it is `MISS`.

All misses remain in the grade. No denominator editing is allowed.

The pure V0 grader does **not** perform future entity resolution. Follow-on evidence supplied to it must already be bound to a sealed episode by a separately auditable adapter/projection. Until such a binding is available, the corresponding member is not silently guessed into a HIT.

Attention/discovery is an observable follow-on signal, not a factual-quality label. ZERO-DAY grades therefore cannot substitute for PEF's preregistered outcome-label machinery.

## Required public interpretation

A ZERO-DAY HIT means:

> FRONTIER's frozen PEF_V1 candidate ranked this already-observed primary-emission episode ahead of the naive control before FRONTIER later observed ATTENTION/DISCOVERY evidence for the bound episode.

It does **not** mean:

- FRONTIER predicted the future;
- the development was objectively important;
- later sources were independent confirmation;
- the episode identity is canonical entity truth;
- PEF_V1 passed its promotion gate.

## Implementation sequence

V0 implementation is intentionally narrow:

1. pure deterministic seal/grade domain logic;
2. hostile unit tests for leakage, identity mismatch, manual boundary selection, attention-at-seal exclusion, denominator retention, and deterministic identity;
3. later read-only adapter that reconstructs inputs from persisted PEF_V1 artifacts/runs and auditable follow-on membership;
4. later presentation surface showing hits, misses, and missing seals together.

No database migration or scheduled writer is authorized by this V0 protocol.
