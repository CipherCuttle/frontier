# BASELINE_INTELLIGENCE_V0

Status: FROZEN_EVALUATION_AUTHORITY

Parent authority: `main@7aafe82eb8630188b659666e597febdd17e69ed4`.

This phase establishes the permanent naive prospective intelligence baseline required before any advanced ranking experiment. This authority and `fixtures/baseline_intelligence/corpus_v0.json` must exist before runtime implementation.

## Objective

Produce a deterministic, versioned, point-in-time-safe ranking of episode activity: which episode candidates are moving now according to the simplest transparent activity baseline FRONTIER can compute from evidence it actually knew by `as_of`.

The baseline is a comparator, not a claim of truth, entity identity, causal origin, or independent corroboration.

## Unit of analysis

The ranking unit is an episode candidate derived from `GROUPING_BASELINE_V0` at the same `as_of`.

- multi-observation `EpisodeGroup` => one episode candidate;
- ungrouped observation => singleton episode candidate;
- `AMBIGUOUS` grouping never forces a merge;
- observation identity remains untouched.

Episode IDs are deterministic from grouping algorithm version + sorted canonical observation IDs.

## Knowledge horizon

`observed_at` is the only FRONTIER knowledge clock. An observation may influence a snapshot iff `observed_at <= as_of`.

Source/effective/retrieval/provider timestamps and `generated_at` never grant earlier knowledge. Historical replay must not use observations, relations, collection occurrences, or health observations first known later.

## Prospective activity eligibility

All canonical evidence remains in episode membership, but live activity windows include only observations whose first durable INSERTED collection occurrence is prospectively eligible.

- `SCHEDULED`, `DISCOVERY`, `ACTIVE_ENRICHMENT`: eligible;
- `BACKFILL`: excluded from live activity/rank movement;
- `recovered_after_gap=true`: excluded from live activity/rank movement and counted separately as recovered backlog;
- missing/contradictory insertion causality: fail closed;
- duplicate/repeated collection never creates additional mentions.

## Fixed windows and metrics

Windows are half-open `(start, end]` using `observed_at`.

- `mentions_1h`: `(as_of-1h, as_of]`
- `mentions_6h`: `(as_of-6h, as_of]`
- `mentions_24h`: `(as_of-24h, as_of]`
- `previous_6h`: `(as_of-12h, as_of-6h]`
- `preprevious_6h`: `(as_of-18h, as_of-12h]`

Integer derived metrics:

- `velocity_6h_delta = mentions_6h - previous_6h`
- `acceleration_6h = mentions_6h - (2 * previous_6h) + preprevious_6h`

No binary floating point is authorized in canonical output.

Each episode also reports first/last observed time, non-negative integer `age_seconds`, total evidence count, prospective evidence count, backfill count, recovered-backlog count, sorted contributing source IDs, `source_count`, sorted signal roles, and `source_role_diversity`.

`evidence_root_diversity` MUST be `null` and `confirmation` MUST be `UNAVAILABLE` in V0 because provenance-root independence is not yet authorized.

## Health / coverage

Use the latest source-health observation at or before `as_of` for every enabled source.

Aggregate each dimension deterministically:

1. `FAILED` if any enabled source is FAILED;
2. else `DEGRADED` if any is DEGRADED;
3. else `UNKNOWN` if any is UNKNOWN or missing;
4. else `OK`.

Snapshot fields: `transport_state`, `freshness_state`, `coverage_state` (completeness), `schema_state`.

Ranking metrics are not normalized downward when coverage degrades. Missing input remains explicit uncertainty rather than becoming zero activity.

## Frozen naive ranking policy

Ranking policy version: `naive-episode-activity-v0`.

Sort by this exact tuple:

1. `mentions_1h` descending
2. `mentions_6h` descending
3. `velocity_6h_delta` descending
4. `acceleration_6h` descending
5. `mentions_24h` descending
6. `source_role_diversity` descending
7. `last_observed_at` descending
8. `evidence_count_total` descending
9. `episode_id` ascending

No hidden weights, learned parameters, embeddings, LLM judgments, popularity counters, market prices, or entity priors.

## Correction / retraction

Correction and retraction remain append-only evidence and may remain highly active. The baseline never suppresses activity merely because assertion state changed. Assertion lifecycle and trend activity remain orthogonal.

## Canonical projection

- projection name: `baseline-intelligence`
- projection version: `baseline-intelligence-v0`
- schema version: `baseline-intelligence-snapshot-v0`
- algorithm version: `windowed-episode-metrics-v0`
- ranking policy version: `naive-episode-activity-v0`

Canonical output contains versions, `as_of`, aggregate health state, and ranked episode entries with rank starting at 1. `generated_at` is excluded from canonical output.

## Receipt and retention

P08 projection receipt minimum identity is mandatory.

Only COMPLETE output may be canonical. COMPLETE snapshot payload + receipt must persist atomically. Any serialization/database/receipt failure rolls back the candidate and leaves the previous COMPLETE snapshot as latest publishable state.

Snapshot payloads must be retained prospectively for later advanced-model comparison.

Frozen inputs/config/version/`as_of` must produce byte-identical canonical output and the same receipt identity. Changing only `generated_at` must not change output or receipt ID.

## Frozen adversarial requirements

The corpus covers at least:

- future observation exclusion and historical replay;
- fresh primary emission;
- attention propagation without confirmation inflation;
- syndication/source visibility without provenance-root claims;
- positive/negative velocity and acceleration;
- deterministic tie breaking;
- BACKFILL exclusion;
- recovered backlog exclusion;
- degraded/missing source health remaining explicit;
- old source timestamp first observed now using `observed_at`;
- correction/retraction remaining activity-visible;
- duplicate collection not manufacturing mentions;
- failed candidate publication preserving prior COMPLETE snapshot.

## Explicit exclusions

No provenance-root inference, entity resolution, lifecycle labels, learned ranking, manipulation/reflexivity model, embeddings/vector DB/LLM clustering, public API/read plane, frontend, or D007 branch-protection mutation.

## Closure discipline

`IMPLEMENT -> TEST -> ONE hostile review -> fix Critical/High -> ONE targeted re-review only if required -> VERIFY -> MERGE -> VERIFY MERGED TREE -> MOVE FORWARD`

Closure additionally requires frozen authority/corpus preflight, PIT/replay tests, backfill/backlog/outage tests, atomic PostgreSQL retention proof, and failure-preserves-prior-COMPLETE proof.
