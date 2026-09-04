# P08 Canonical Data Contract and PR-01 Boundary

Status: READY_FOR_IMPLEMENTATION_AFTER_FREEZE

PR-01 establishes what FRONTIER observed, from where, when it knew it, why it collected it, whether the source was healthy, and whether the same evidence can be reproduced. It does not establish what is trending.

Authority layers: transient hostile FetchArtifact -> canonical append-only Observation -> versioned Derived Projection -> disposable Public Read Model.

Stable evidence IDs are deterministic. Operational run/job/trace IDs may be nondeterministic and must not influence canonical intelligence identity/digests.

Canonical digest: SHA-256. Canonical JSON V1: UTF-8, NFC normalization, sorted object keys, semantic array order, set-like collections sorted before serialization, UTC Z timestamps with fixed precision, decimals represented exactly, explicit null where semantic.

Initial canonical evidence substrate:
- SourceContract
- CollectionRun
- Observation
- ObservationRelation
- SourceHealthObservation
- ProjectionReceipt
- language-neutral FetchRequest / BoundedFetchResult seam

Initial observation kinds: DOCUMENT, ARTIFACT, METRIC.

Observation envelope includes source ID/item key, kind/payload, source/effective timestamps where available, trusted `observed_at`, `retrieved_at`, collection context, content/fetch digests, schema/canonicalization versions.

Observation ID is derived from stable semantic source/item/kind/canonical payload identity; `observed_at`, run ID and trace ID do not manufacture new evidence. Changed canonical payload for the same source item becomes a new observation, preserving revisions append-only.

Initial observation relation types: CORRECTS, RETRACTS, REFERENCES. Relation authority: EXPLICIT or INFERRED; inferred requires algorithm version and confidence.

Source health observation dimensions: transport, freshness, completeness, schema; initial health values OK, DEGRADED, FAILED, UNKNOWN.

Initial PostgreSQL tables for PR-01 only: `sources`, `collection_runs`, `observations`, `observation_relations`, `source_health_observations`, `projection_receipts`.

Explicitly prohibited in PR-01: clusters, trends, entities, embeddings/vector DB, ranking/emergence/confirmation scores, LLM integration, Redis/Kafka/Celery, GraphQL, browser/network scraping, frontend/product UI.

PR-01 acceptance gates: pure framework-independent domain; deterministic canonical serialization/IDs; idempotent retries; changed evidence creates new observation; knowledge-horizon `as_of` correctness; backfill semantics; append-only corrections/retractions; multidimensional health; active-enrichment trigger enforcement; real Postgres integration; fail-closed migrations; byte-identical replay; no unauthorized scope.
