# GROUPING SCALABILITY V1 — Candidate Authority

Status: CANDIDATE_AUTHORITY / PRE-IMPLEMENTATION

Parent authority: `GROUPING_BASELINE_V0`.

Incident trigger: PEF_V0 confirmatory execution on 2026-09-08 demonstrated that the V0 requirement to assess every unordered pair and explicitly materialize every `AMBIGUOUS` pair is not sustainable for a growing prospective evidence universe. This authority exists to repair scalability without granting stronger epistemic claims.

## Objective

Produce the same episode-membership decisions that `guarded-hybrid-v0` would produce for eligible observations, while removing the requirement to enumerate every non-grouped pair in the projection artifact.

V1 is a grouping/deduplication projection only. It does not grant entity, provenance-root, confirmation, causal-origin, truth, importance, or ranking authority.

## Frozen epistemic semantics

The pair-level concepts remain exactly:

- `GROUP`: sufficient evidence to connect the pair under the frozen guarded-hybrid rules;
- `NO_GROUP`: explicit negative evidence under those rules;
- `AMBIGUOUS`: insufficient evidence; not a negative and not evidence of independence.

V1 MUST NOT reinterpret an omitted pair as `NO_GROUP`. A pair not explicitly represented in the compact projection remains queryable under deterministic pair semantics and defaults to no stronger epistemic state than `AMBIGUOUS` unless an explicit V1 negative rule applies.

## Membership-compatibility contract

For any bounded input universe on which V0 can complete, V1 MUST produce exactly the same:

- eligible observation set at the same `as_of`;
- `GROUP` pair relation;
- episode/group membership partition;
- singleton/ungrouped observation set.

Group IDs MUST be deterministic from the V1 algorithm version plus sorted member observation IDs. Group IDs are therefore versioned identities and are not required to equal V0 group IDs.

The V0 frozen pair corpus and all 11 retained successful PEF_V0 baseline boundaries (`15:00` through `15:50` UTC on 2026-09-08) are mandatory membership-equivalence evidence before V1 may be frozen for a new confirmatory experiment.

Any mismatch in `GROUP` relation or episode membership is a Critical failure unless separately authorized as a deliberate semantic change before implementation.

## Pair-decision compatibility

V1 SHALL retain the existing `assess_pair` decision rules as the reference pair semantics unless a later authority explicitly changes them.

The scalable projection does not have to persist or canonicalize every `AMBIGUOUS`/`NO_GROUP` pair. It MUST provide a deterministic diagnostic path capable of evaluating a requested eligible pair with the frozen pair rules.

This distinction is intentional:

- pair semantics remain available;
- projection membership is computed from the complete `GROUP` relation;
- exhaustive unknown-pair enumeration is no longer part of the projection artifact or its digest.

## GROUP-complete candidate generation

The implementation MUST NOT compare every unordered pair.

It MUST use deterministic candidate generation that is *GROUP-complete*: every pair that the reference `assess_pair` would classify `GROUP` must be generated or handled by an equivalent direct grouping rule.

Permitted deterministic candidate families are limited to necessary conditions already present in the guarded-hybrid rules:

1. explicit eligible `CORRECTS` / `RETRACTS` relations with `authority=EXPLICIT`;
2. equal canonical URL within the existing far-window semantics;
3. equal semantic text within the existing time semantics;
4. equal normalized substantive title within the existing time semantics;
5. title-token similarity candidates capable of proving completeness for Jaccard `>= 0.80` under the existing time semantics;
6. direct bucket/component rules that are mathematically equivalent to the corresponding pairwise GROUP clique (for example homogeneous same-URL ATTENTION buckets), provided equivalence is proved.

Candidate generation may emit false candidates for later exact assessment. It MUST NOT omit a true GROUP pair.

Approximate nearest-neighbor search, probabilistic blocking, embeddings, LLMs, learned blocking, nondeterministic hashing, or recall-tuned heuristics are forbidden.

## Group construction

The existing conservative clique rule remains the semantic reference: observations may share one episode component only when every cross-member pair required by the V0 merge rule is `GROUP`.

V1 may implement this more efficiently, but it MUST prove partition equivalence against the reference implementation on bounded corpora.

No transitive relaxation is authorized. A-B GROUP and B-C GROUP do not permit A-C to be assumed GROUP.

## Compact ambiguity representation

V1 projection schema MUST NOT include an exhaustive `ambiguous_pairs` array.

Instead it SHALL contain, at minimum:

- algorithm/projection/schema version;
- `as_of`;
- deterministic groups;
- deterministic ungrouped observation IDs;
- the eligible observation count;
- deterministic candidate-pair count;
- deterministic GROUP-pair count or an equivalent compact membership diagnostic;
- a pair-semantics version identifying the diagnostic `GROUP/NO_GROUP/AMBIGUOUS` rules;
- an explicit statement that omitted pairs carry no negative/independence meaning;
- deterministic input and output digests.

Optional bounded diagnostics MAY retain a capped/sampled set of ambiguous examples only if sampling/capping is deterministic and the artifact clearly states that the examples are non-exhaustive. Such diagnostics cannot influence grouping.

## Receipt/digest contract

V1 receipts MUST be deterministic without expanding an O(n²) canonical object graph.

Canonical hashing may be streamed/chunked or computed from compact deterministic structures. It MUST bind all inputs that can affect membership, including:

- sorted eligible observation identities and grouping-relevant fields/digests;
- eligible explicit relations;
- algorithm/configuration versions;
- groups and ungrouped IDs;
- candidate-generation identity.

Digest implementation is not authority to omit membership-relevant input.

Replay of the same input/configuration MUST reproduce the exact receipt and compact projection bytes/digests.

## Point-in-time contract

V0 point-in-time rules remain binding:

- only observations with `observed_at <= as_of` may enter;
- only relations durably known by `as_of` may enter;
- future observations/relations may not alter historical replay;
- source publication/effective time cannot manufacture earlier FRONTIER knowledge.

## Scale gates — frozen before implementation

The implementation MUST pass all of these on the project’s supported Python runtime with measurement artifacts retained:

1. **Incident-shape gate:** 2,425 same-day low-overlap observations; complete successfully with peak RSS <= 512 MiB and wall time <= 30 s.
2. **Sparse 10k gate:** 10,000 same-day low-overlap observations; peak RSS <= 768 MiB and wall time <= 60 s.
3. **Sparse 25k gate:** 25,000 same-day low-overlap observations; peak RSS <= 1,024 MiB and wall time <= 180 s.
4. **Dense-equivalence gate:** at least one 5,000-observation high-collision corpus exercising same-URL and exact-title/semantic grouping without pairwise output explosion; peak RSS <= 1,024 MiB and wall time <= 180 s.

A benchmark that skips receipt generation is insufficient. The measured path MUST include projection construction and the exact receipt/input-output digest path intended for production.

If the dense gate cannot preserve reference membership within these bounds, the implementation is not eligible for confirmatory freeze; the authority must be revisited instead of silently weakening semantics.

## Required falsification/equivalence evidence

Before candidate freeze or use as a control universe, V1 requires:

- V0 frozen grouping corpus: exact pair decision compatibility;
- V0 grouping selection corpus: exact membership compatibility;
- all 11 retained successful PEF_V0 boundaries: exact episode-membership partition compatibility;
- randomized/property comparison against exhaustive V0 for bounded universes;
- explicit relation before/after-`as_of` tests;
- punctuation/confusable/version-split hostile cases;
- a candidate-generation omission attack proving a missing true GROUP pair fails the suite;
- a false-merge attack proving precision remains fail-closed;
- deterministic replay and receipt identity;
- the four frozen scale gates above.

## Operational constraints for successor confirmatory use

If a session-level PostgreSQL advisory lock remains the singleton mechanism:

- the database endpoint MUST be a direct/session endpoint, not a transaction-pooled `-pooler` endpoint;
- preflight MUST fail closed when a known transaction-pooled endpoint is configured;
- local cached lease ownership MUST never substitute for a real database lock acquisition after an unlock/connection failure;
- transient PostgreSQL reconnect causes MUST be logged;
- resource limits MUST be derived from measured V1 production-path peaks and must not use prolonged `MemoryHigh` throttling as a substitute for liveness.

## Authority boundaries

This authority DOES NOT:

- resume or modify PEF_V0;
- authorize backfill or pooling of PEF_V0 evidence with a successor;
- change the seven-source registry;
- change PEF ranking logic;
- change evaluation thresholds or promotion criteria;
- grant public ranking authority;
- authorize entity/provenance/confirmation semantics;
- authorize embeddings, vector search, or LLM grouping.

PEF_V0 remains a retained aborted confirmatory run. Any successor advanced-ranking experiment that binds V1 grouping requires a new preregistration, implementation/freeze identity, publication, and fresh prospective window.

## Closure discipline

`AUTHORIZE -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if required -> IMPLEMENT -> TEST/EQUIVALENCE/SCALE -> candidate freeze under separate experiment authority`
