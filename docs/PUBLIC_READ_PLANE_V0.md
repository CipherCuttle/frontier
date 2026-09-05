# PUBLIC_READ_PLANE_V0

Status: FROZEN_AUTHORITY_BEFORE_RUNTIME

Parent authority: `main@91000cb3be809b85599a5b2109988322231f8449`.

This phase implements the disposable public-read boundary promoted by `docs/ROADMAP.md`. It does not create new intelligence authority. `BASELINE_INTELLIGENCE_V0` remains the sole ranking/episode-activity authority exposed by this phase.

## 1. Objective

Expose auditable derived intelligence and canonical evidence through a read-only FastAPI boundary so the later terminal can consume stable generated OpenAPI/TypeScript contracts without gaining canonical mutation authority.

The phase must provide:
- FastAPI transport only;
- deterministic OpenAPI output and generated TypeScript client/types derived from it;
- read-only access to the latest or explicitly selected retained COMPLETE baseline snapshot;
- API-ready RADAR/NOW/TRENDING **baseline substrate views** with no new ranking;
- episode/evidence/provenance drill-down;
- aggregate and per-source health visibility at the selected snapshot horizon;
- explicit snapshot/receipt/version/`as_of` binding on every intelligence response;
- measured healthy-condition p95 read latency against the P03 `<250ms` candidate.

## 2. Explicit non-authority

`PUBLIC_READ_PLANE_V0` MUST NOT:
- write, update, delete, truncate, publish or recompute canonical observations, relations, health, grouping projections, baseline snapshots or receipts;
- run grouping or baseline-intelligence processors;
- change baseline rank or create a second ranking score;
- infer provenance roots, factual independence, entity identity, lifecycle labels, consequence, confidence or confirmation;
- promote source count or source-role diversity into independent-confirmation language;
- render upstream HTML;
- add GraphQL, Redis, Kafka, Celery, embeddings, vector DBs, LLM inference or frontend UI.

The public read model is disposable. Canonical authority remains PostgreSQL canonical evidence + versioned projection receipts/snapshots.

## 3. Transport identity

Frozen transport identifiers:
- API version: `public-read-api-v0`
- response schema family: `public-read-response-v0`
- baseline view policy: `baseline-read-views-v0`
- generated TypeScript client namespace: `FrontierPublicReadV0`

FastAPI-generated OpenAPI is the Python/TypeScript transport authority per ADR-0008. Manually duplicated TypeScript DTO definitions are prohibited.

The application/domain layers remain framework-independent. FastAPI/Pydantic types belong only in the transport adapter.

## 4. Snapshot selection

Every intelligence/read-model request resolves exactly one retained baseline snapshot.

Selection rules:
1. If `snapshot_id` is supplied, resolve that exact snapshot.
2. Otherwise select the latest retained baseline snapshot ordered by `as_of DESC, snapshot_id DESC`.
3. The snapshot is publishable only when its joined projection receipt is `COMPLETE` and matches the frozen baseline projection identity.
4. Snapshot row `receipt_id` and `output_digest` must equal the joined receipt.
5. Re-canonicalizing `snapshot_json` with `frontier-canonical-json-v1` must reproduce `output_digest`; mismatch fails closed.
6. Stored snapshot version/algorithm/ranking/as-of fields must agree with the payload and receipt; mismatch fails closed.
7. FAILED receipts and orphan/mismatched rows are never served.

No request may select a future/unpublished candidate.

## 5. Audit binding

Every intelligence/view/episode/health response includes an immutable `snapshot` binding containing:
- `snapshot_id`;
- `receipt_id`;
- `receipt_schema_version`;
- `projection_name`;
- `projection_version`;
- `schema_version`;
- `algorithm_version`;
- `ranking_policy_version`;
- `configuration_digest`;
- `source_registry_version`;
- `as_of`;
- `input_digest`;
- `output_digest`.

`generated_at` is receipt audit metadata but not response identity; it may be exposed separately as receipt metadata and must not be used to choose/rank items.

## 6. Baseline substrate views

These are presentation/read slices over the frozen baseline. They are **not** the richer semantic lifecycle labels described in P07 and they do not claim consequence, confirmation or establishment.

All views preserve the original `BaselineEpisode.rank`; filtering never renumbers or reranks.

Frozen view rules:
- `RADAR`: every episode in baseline rank order.
- `NOW`: episodes with `mentions_1h > 0`, preserving baseline rank order.
- `TRENDING`: episodes with `velocity_6h_delta > 0`, preserving baseline rank order.

Every view response declares `view_policy_version="baseline-read-views-v0"` and `semantic_scope="BASELINE_SUBSTRATE"`.

A later phase may replace these presentation slices only through new explicit intelligence authority. Transport code must not silently alter them.

## 7. Pagination and deterministic ordering

View endpoints accept:
- `limit`: default 50, minimum 1, maximum 100;
- `offset`: default 0, minimum 0.

Filtering is applied before pagination. Ordering is baseline rank ascending. Ties are impossible because rank is already total and deterministic.

Responses include `total`, `limit`, `offset` and `items`.

## 8. Evidence drill-down

Episode drill-down returns the selected baseline episode plus canonical evidence for exactly the episode's `observation_ids`.

Observation evidence may expose:
- observation identity/schema/canonicalization version;
- source ID/item key/kind;
- canonical payload JSON;
- source-published/effective/observed/retrieved timestamps;
- content/fetch digests;
- collection occurrence reason/trigger/recovered-after-gap/status;
- explicit/inferred observation relations and their authority metadata.

Rules:
- every returned observation must have `observed_at <= selected snapshot.as_of`;
- episode drill-down may not inject observations outside the selected episode;
- relation rows may reference external/internal targets, but do not establish provenance-root independence;
- upstream HTML is returned only as inert canonical data if it is already canonical evidence; the API never renders it as HTML.

A direct observation endpoint may return canonical evidence at or before the selected snapshot horizon, but does not imply that observation belongs to a baseline episode unless the response says so.

## 9. Health read model

The selected baseline snapshot's aggregate states are authoritative for interpretation:
- transport;
- freshness;
- coverage/completeness;
- schema.

Per-source health is the latest recorded health observation at or before the selected snapshot `as_of` for each source with such a record. It is informational evidence bound to that horizon, not a reconstructed claim about historical registry membership beyond what the receipt's `source_registry_version` proves.

Missing per-source health remains missing/UNKNOWN; it must never be converted to healthy or zero activity.

## 10. HTTP surface

Frozen V0 application endpoints:
- `GET /v0/meta`
- `GET /v0/radar`
- `GET /v0/now`
- `GET /v0/trending`
- `GET /v0/episodes/{episode_id}`
- `GET /v0/observations/{observation_id}`
- `GET /v0/health`
- FastAPI OpenAPI JSON GET endpoint.

No canonical mutation endpoint is authorized. The generated OpenAPI document must contain no POST, PUT, PATCH or DELETE operation.

`/v0/meta` is transport metadata only and may be served without a baseline snapshot. Intelligence endpoints fail explicitly if no valid COMPLETE snapshot exists.

## 11. Read-only PostgreSQL boundary

The PostgreSQL public-read adapter:
- exposes SELECT-only repository methods;
- owns/uses a database session configured `default_transaction_read_only=on` before serving requests;
- does not import or call canonical write repositories;
- has no method that accepts a canonical candidate/projection for persistence;
- must fail closed if read-only session establishment cannot be verified.

Production deployment should use a least-privilege read credential in addition to session read-only mode. Credential provisioning itself is operational deployment scope, not authority to weaken the in-process/DB-session read-only invariant.

## 12. Error semantics

Frozen error codes:
- `NO_COMPLETE_SNAPSHOT` -> 503 when implicit latest selection has no publishable snapshot;
- `SNAPSHOT_NOT_FOUND` -> 404 for explicit unknown/nonpublishable snapshot;
- `SNAPSHOT_INTEGRITY_FAILURE` -> 503 on binding/digest/version corruption;
- `EPISODE_NOT_FOUND` -> 404 within selected snapshot;
- `OBSERVATION_NOT_FOUND` -> 404 at selected horizon.

Errors must not expose DSNs, SQL, stack traces or secrets.

## 13. Deterministic generated contracts

Repository-generated artifacts:
- `contracts/public/openapi_v0.json` from `FastAPI.openapi()` with deterministic JSON serialization;
- `clients/typescript/src/generated/public_read_v0.ts` generated from the OpenAPI document by a repository codegen script.

Verification regenerates both artifacts and fails on drift. The TypeScript file is generated output, not a manually maintained source of API truth.

## 14. Latency evaluation

P03's materialized-read candidate is p95 server latency `<250ms` under healthy conditions.

V0 evaluates the candidate on real PostgreSQL integration using a warmed local/CI database and the FastAPI test transport over a representative retained snapshot. The measurement must be reported by tests. The candidate passes V0 when measured p95 is `<250ms` in the verified CI environment; this does not claim an internet/user-perceived SLO.

No ranking, caching or correctness invariant may be weakened to hit the target.

## 15. Frozen hostile corpus

`fixtures/public_read_plane/corpus_v0.json` freezes adversarial scenarios before runtime implementation. The runtime must satisfy them without modifying expected semantics after evaluation begins.

Required scenario families include:
- FAILED receipt not publishable;
- snapshot/receipt/output digest mismatch fails closed;
- latest COMPLETE deterministic selection;
- RADAR preserves rank;
- NOW filters only by `mentions_1h > 0` and preserves rank;
- TRENDING filters only by `velocity_6h_delta > 0` and preserves rank;
- degraded/missing coverage remains visible;
- source diversity never becomes confirmation;
- episode drill-down cannot escape membership;
- future evidence excluded at selected horizon;
- mutation methods absent from OpenAPI;
- DB session rejects writes;
- generated OpenAPI/TypeScript artifacts deterministic;
- no COMPLETE snapshot produces explicit unavailable response.

## 16. Acceptance gates

`PUBLIC_READ_PLANE_V0` may close only when all are true:
1. frozen authority + hostile corpus predate runtime implementation;
2. FastAPI transport is isolated from domain authority;
3. exact snapshot/receipt/digest/version binding is verified;
4. only COMPLETE baseline snapshots are served;
5. RADAR/NOW/TRENDING preserve frozen baseline rank and frozen filter semantics;
6. evidence drill-down is horizon- and membership-safe;
7. aggregate/per-source health remains explicit and non-optimistic;
8. public DB session is verified read-only and write attempts fail;
9. OpenAPI contains no mutation operation;
10. generated TypeScript contract is reproducible from OpenAPI;
11. Ruff, Pyright, architecture checks, all frozen preflights and pytest pass;
12. healthy CI p95 is measured and `<250ms`;
13. exactly one hostile closure review is performed; Critical/High findings receive one bounded repair and one targeted re-review only if required;
14. exact merged tree verifies before roadmap promotion.

D007 (`main` unprotected) remains separate operational governance debt and is not silently closed by this phase.
