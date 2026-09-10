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
- reuse ZERO-DAY results as PEF_V1 confirmatory evidence;
- select a historical boundary after inspecting later outcomes;
- backfill a missed ZERO-DAY seal;
- infer factual confirmation, provenance independence, entity truth, causal ancestry, or importance from later attention;
- treat missing ATTENTION/DISCOVERY evidence as proof that no attention/discovery existed outside FRONTIER coverage.

ZERO-DAY output is `DIAGNOSTIC_ONLY`.

## Input authority

A seal may be derived only from one persisted COMPLETE/RAN **PEF_V1 CONFIRMATORY** paired run, its exactly bound PEF_V1 candidate artifact, and the candidate projection receipt referenced by the persisted artifact row.

The read-only persistence adapter must provide the append-only row `created_at` values for:

- the PEF candidate artifact;
- the candidate projection receipt;
- the paired shadow run.

The pure seal builder rejects any source row whose trusted persistence timestamp is later than the claimed `sealed_at`. A caller-supplied earlier timestamp cannot substitute for database persistence evidence.

The seal binds at minimum:

- PEF_V1 run id and run digest;
- run persistence time;
- candidate artifact id and output digest;
- candidate artifact persistence time;
- persisted candidate receipt id and exact input digest;
- candidate receipt persistence time;
- candidate freeze receipt id;
- source-registry version;
- exact `as_of` boundary;
- candidate and control ranks used for selection.

The candidate receipt input digest is recomputed over the complete seal-time `BaselineObservationInput` set plus the exact control snapshot id. This binds observation ids together with their timestamps, source identities, signal roles, grouping inputs, collection reason, and recovered/backfill semantics. Substituting an observation object while retaining its id therefore fails closed.

The candidate and control universe must be identical. A failed, partial, freeze-unbound, non-confirmatory, receipt-mismatched, input-digest-mismatched, or identity-mismatched run fails closed.

## Seal-time health authority

ZERO-DAY's "no attention/discovery observed" predicate is valid only when the paired run's aggregate:

- transport state;
- freshness state;
- coverage state;
- schema state

are all `OK`.

Any `DEGRADED`, `FAILED`, or `UNKNOWN` state makes the entire ZERO-DAY boundary unavailable. The boundary is **MISSING**, not a smaller or apparently attention-free cohort.

This is intentionally conservative: coverage failure must never become evidence of absence.

## Seal cadence

ZERO-DAY V0 has four deterministic UTC seal opportunities per day:

`00:00`, `06:00`, `12:00`, `18:00` UTC.

Equivalently, an eligible `as_of` is an exact six-hour Unix-epoch multiple.

A seal uses only the PEF_V1 confirmatory run at that exact boundary. If that run is absent, failed, delayed past persistence, unhealthy, or otherwise unavailable, the ZERO-DAY boundary is **MISSING**. It is never replaced by a nearby or later boundary and is never backfilled.

A valid live seal must be created no earlier than its source boundary and no later than **30 minutes** after that boundary. In addition, the candidate artifact, its referenced candidate receipt, and paired shadow run must all have trusted append-only persistence timestamps no later than the claimed seal time.

A boundary whose source evidence is not durably available inside this window is **MISSING**. This prevents historical reconstruction from masquerading as a live sealed forecast.

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

Every seal records the trusted persistence times and candidate receipt/input digest that make the live claim auditable.

Every cohort member records:

- position in the sealed cohort;
- episode id;
- exact observation ids present in the sealed episode;
- candidate rank;
- control rank;
- rank advantage;
- prospective-primary freshness timestamp/age exposed by PEF.

## Follow-on grading

V0 diagnostic horizons remain fixed at:

- +6 hours;
- +24 hours;
- +72 hours;
- +168 hours (7 days).

However, this first ZERO-DAY slice does **not** yet possess a separately auditable follow-on episode-membership and coverage projection.

Therefore the pure V0 grader is fail-closed:

- before a horizon cutoff, the grade is `PENDING`;
- at or after the cutoff, the grade is `UNVERIFIED`;
- caller-supplied follow-on evidence is rejected;
- V0 cannot emit `HIT` or `MISS`.

A string shaped like a receipt id is not membership authority. An observation must eventually be bound to the sealed episode by a separately auditable persisted projection, and follow-on coverage must be sufficient to support both positive and negative grading.

Only after that separate adapter/projection exists may a successor slice authorize:

- `HIT`: eligible ATTENTION/DISCOVERY first observed strictly after the seal and by the horizon cutoff, with verified episode membership;
- `MISS`: no qualifying follow-on by cutoff, with sufficient verified follow-on coverage.

All sealed members must remain in the denominator. No denominator editing is allowed.

Attention/discovery is an observable follow-on signal, not a factual-quality label. Even future verified ZERO-DAY grades cannot substitute for PEF's preregistered outcome-label machinery.

## Required public interpretation

A future verified ZERO-DAY HIT may mean only:

> FRONTIER's frozen PEF_V1 candidate ranked this already-observed primary-emission episode ahead of the naive control before FRONTIER later observed ATTENTION/DISCOVERY evidence for an auditable bound version of that episode.

It does **not** mean:

- FRONTIER predicted the future;
- the development was objectively important;
- later sources were independent confirmation;
- the episode identity is canonical entity truth;
- PEF_V1 passed its promotion gate.

Until the follow-on membership/coverage projection is implemented, ZERO-DAY V0 must not publish HIT/MISS claims.

## Implementation sequence

V0 implementation is intentionally narrow:

1. pure deterministic seal domain logic;
2. trusted persistence binding for candidate artifact / receipt / run availability;
3. exact candidate-input-digest verification;
4. fail-closed health gating;
5. fail-closed `PENDING` / `UNVERIFIED` grading placeholder;
6. hostile unit tests for leakage, identity mismatch, persistence timing, input substitution, unhealthy coverage, denominator retention, and deterministic identity;
7. later read-only adapter that reconstructs the trusted persistence binding from PostgreSQL;
8. later auditable follow-on membership/coverage projection;
9. later presentation surface showing verified hits, misses, unverified grades, and missing seals together.

No database migration or scheduled writer is authorized by this V0 protocol.
