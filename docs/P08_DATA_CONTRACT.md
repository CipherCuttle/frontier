# P08 Canonical Data Contract and PR-01 Boundary

Status: READY_FOR_IMPLEMENTATION_AFTER_PR00_MERGE

PR-01 establishes what FRONTIER observed, from where, when it knew it, how each collection occurrence happened, whether the source was healthy, and whether the same evidence can be reproduced. It does not establish what is trending.

## 1. Authority layers

`FetchArtifact` (hostile/transient) -> `ObservationCandidate` -> durable canonical `Observation` -> versioned Derived Projection -> disposable Public Read Model.

Raw fetch bytes are not canonical evidence by default.

## 2. Stable vs operational identity

Canonical evidence IDs are deterministic. Operational run/job/trace IDs may be nondeterministic and must not influence observation identity, content identity, clustering identity, ranking, or deterministic receipts.

Canonical digest algorithm: SHA-256.
Digest text format: `sha256:` followed by exactly 64 lowercase hexadecimal characters.

## 3. `frontier-canonical-json-v1`

Canonical JSON is normative because IDs and receipts hash its exact UTF-8 bytes.

Allowed canonical scalar/container domain:
- `null`;
- boolean;
- arbitrary-precision signed integer;
- Unicode string;
- array;
- object with string keys.

Forbidden in the generic canonical representation:
- binary floating point;
- NaN or Infinity;
- implementation-specific datetime/Decimal objects;
- duplicate object keys after Unicode normalization.

Normalization rules:
1. Strings and object keys are Unicode NFC normalized before serialization.
2. Output is UTF-8 with no BOM.
3. No insignificant whitespace is emitted; separators are exactly `,` and `:`.
4. Object keys are sorted lexicographically by Unicode code-point sequence after NFC normalization.
5. JSON strings emit Unicode characters directly except characters that JSON requires escaping (`"`, `\\`, and U+0000-U+001F); required escapes use standard JSON escapes.
6. Integers use base-10 with no leading `+`, no leading zero except `0`, and no `-0`.
7. Domain decimal values must be converted before canonical JSON to a canonical decimal string: no exponent, no leading `+`, no unnecessary leading zero, no trailing fractional zero, and zero serializes as `"0"`. If measurement scale/precision is semantically meaningful it must be represented separately, not inferred from trailing zeros.
8. Datetimes must be converted before canonical JSON to UTC strings exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ` with six fractional digits. Naive datetimes and leap-second text are rejected at the canonical boundary.
9. Arrays preserve order unless the schema explicitly declares the field set-like. PR-01 set-like arrays: `signal_roles` only; it is sorted ascending after normalization. No implementation may guess that another array is set-like.
10. Optional fields that participate in canonical identity are always present and use explicit `null` when absent. Omission is allowed only for fields explicitly declared noncanonical/operational by schema.

PR-01 must commit golden canonicalization vectors and property tests; any implementation that produces different bytes is nonconforming.

## 4. Source identity

`source_id` is a stable namespaced identifier matching `^[a-z0-9][a-z0-9._-]{1,63}$`.

`source_item_key` is the provider-native stable item identity where available. It must be non-empty and bounded. Where the provider has no stable ID, the adapter defines a deterministic fallback and versions that fallback behavior.

## 5. Observation kinds

Initial exact enum:
- `DOCUMENT`
- `ARTIFACT`
- `METRIC`

Provider names must not become observation kinds.

## 6. Observation semantic identity

The exact identity material for `observation-v1` is:

```json
{
  "canonicalization_version": "frontier-canonical-json-v1",
  "effective_at": null,
  "kind": "DOCUMENT",
  "payload": {},
  "schema_version": "observation-v1",
  "source_id": "example.source",
  "source_item_key": "provider-stable-key",
  "source_published_at": null
}
```

The real values replace the example values; the key set is fixed for V1.

`observation_id = "obs_" + lowercase_hex(SHA256(canonical_json(identity_material)))`.

The following are deliberately excluded from observation identity:
- `observed_at`;
- `retrieved_at`;
- collection run/reason/trigger;
- retry count;
- trace/process/job IDs;
- `fetch_digest`;
- source health.

Consequences:
- identical semantic evidence collected repeatedly has one observation ID;
- a changed canonical payload, changed claimed source/effective time, changed item key, kind, schema version, or canonicalization version creates a new observation ID;
- operational retries do not manufacture evidence.

`content_digest` is SHA-256 over canonical JSON of `{kind, payload, source_published_at, effective_at}` using the same canonicalization version. It is not a substitute for `observation_id`.

For `METRIC`, the measurement time/window must be part of the payload or source item key so equal numeric values at different measurement times remain distinct observations.

## 7. ObservationCandidate and trusted clocks

A source normalizer produces `ObservationCandidate`; it does not choose `observed_at`.

Candidate fields:
- schema/canonicalization version;
- source ID/item key;
- kind/payload;
- optional source-published/effective times;
- trusted-side `retrieved_at`;
- content/fetch digests.

`retrieved_at` is acquisition telemetry stamped when the complete `BoundedFetchResult` crosses into the trusted ingestion boundary. A timestamp claimed by the hostile fetch runtime is not the canonical `retrieved_at`.

`observed_at` is the authoritative FRONTIER knowledge clock and is assigned only on the first successful durable append. In production PostgreSQL, the trusted persistence boundary obtains the database-server timestamp in the same transaction as the INSERT. The timestamp has canonical effect only if that transaction commits.

If an identical `observation_id` already exists, insertion is an idempotent no-op and the existing first `observed_at` is preserved. A retry must never move first-observed time forward or backward.

Historical rule: an observation may influence an `as_of` state iff its committed `observed_at <= as_of`.

Source/effective/retrieval times never grant earlier knowledge than `observed_at`.

Deterministic replay uses the stored historical `observed_at`; replay does not invent a new live observed time.

## 8. Collection causality is occurrence metadata

Collection causality must not alter observation identity. Therefore reason/trigger is represented on the collection occurrence, not as identity-bearing fields on the observation.

Initial collection reasons:
- `SCHEDULED`
- `DISCOVERY`
- `ACTIVE_ENRICHMENT`
- `BACKFILL`

`ACTIVE_ENRICHMENT` requires a non-null causal `trigger_id` when a stable FRONTIER trigger exists. Recovered backlog collection must be representable (`recovered_after_gap`).

PR-01 persists a join `collection_run_observations` so repeated collection of the same observation can preserve every run/reason/trigger context without creating duplicate evidence.

## 9. Fetch seam integrity

`frontier-fetch` has no canonical DB/admin credentials.

`FetchRequest`/`BoundedFetchResult` are language-neutral semantic contracts. The result body is bounded opaque bytes until trusted validation.

Any body/fetch digest received from the hostile fetch role is advisory only. The trusted ingestion side recomputes `fetch_digest = SHA256(exact returned body bytes)` before canonical use. Hostile metadata cannot substitute for trusted recomputation.

Live network behavior is not implemented in PR-01; fixture transport exercises the semantic seam only.

## 10. Observation relations

Initial relation types:
- `CORRECTS`
- `RETRACTS`
- `REFERENCES`

Relation authority:
- `EXPLICIT`
- `INFERRED`

`INFERRED` requires `algorithm_version` and confidence. PR-01 needs only explicit relation behavior.

Relations append new knowledge; they do not mutate an observation.

## 11. Source health

Source health is append-only/time-indexed and has four independent dimensions:
- transport;
- freshness;
- completeness;
- schema validity.

Initial dimension enum:
- `OK`
- `DEGRADED`
- `FAILED`
- `UNKNOWN`

A single healthy boolean is nonconforming.

## 12. Projection receipt minimum identity

Every canonical derived projection receipt must make these values recoverable:
- `receipt_schema_version`;
- `projection_name`;
- `projection_version`;
- schema version;
- algorithm version when applicable;
- ranking-policy version when applicable;
- `configuration_digest`;
- `source_registry_version`;
- `as_of`;
- `generated_at`;
- `input_digest`;
- `output_digest`;
- status.

Only `COMPLETE` projection output may be published as canonical. Failed/partial candidates cannot replace the previous complete snapshot.

## 13. PR-01 PostgreSQL authority

Initial tables:
- `sources`;
- `collection_runs`;
- `collection_run_observations`;
- `observations`;
- `observation_relations`;
- `source_health_observations`;
- `projection_receipts`.

Stable semantic fields belong in typed columns/domain fields; bounded provider-specific metadata may use JSONB. JSONB is not authorization to avoid modeling invariants.

Routine application roles must not UPDATE/DELETE append-only observations. Correction/retraction uses new evidence/relations.

## 14. PR-01 minimum table semantics

`observations` must persist at least: observation ID, schema/canonicalization versions, source ID/item key, kind, canonical payload, source-published/effective times, `observed_at`, trusted `retrieved_at`, content digest, trusted fetch digest, created metadata required for audit.

`collection_runs` must persist at least: operational run ID, source ID, reason, optional trigger, recovered-after-gap flag, start/completion times, run status, received/accepted/rejected/duplicate counts, safe failure code.

`collection_run_observations` maps each accepted/duplicate collection occurrence to the stable observation ID and run ID; repeated runs may point to the same observation.

`observation_relations` enforces exactly one internal observation target or bounded external target.

`source_health_observations` persists the four health dimensions at an `as_of` time.

`projection_receipts` persists the minimum receipt identity above.

## 15. Fail-closed PR-01 conditions

Canonical writes must refuse to start/continue when:
- database schema is incompatible;
- source contract/registry required for the operation is invalid;
- canonical serialization or identity derivation fails;
- canonical payload exceeds frozen bounds;
- trusted time assignment is unavailable;
- migration fails.

Malformed canonical fields are not silently defaulted to empty strings.

## 16. Explicitly prohibited in PR-01

No clusters, trends, entity resolution, embeddings/vector DB, ranking/emergence/confirmation scores, LLM integration, Redis/Kafka/Celery, GraphQL, browser/live network scraping, frontend/product UI.

## 17. PR-01 acceptance gates

PR-01 must prove:
1. framework-independent domain;
2. exact canonical JSON golden vectors;
3. deterministic observation/content digests;
4. 100 identical semantic ingests -> one observation but 100 collection occurrences may be recorded;
5. changed semantic evidence -> new observation;
6. first durable `observed_at` is immutable and controls `as_of`;
7. backfill cannot masquerade as prior FRONTIER knowledge;
8. correction/retraction is append-only;
9. multidimensional health survives persistence/replay;
10. active-enrichment trigger causality is preserved without changing observation identity;
11. real PostgreSQL integration and fail-closed migrations;
12. byte-identical deterministic replay;
13. no unauthorized scope.
