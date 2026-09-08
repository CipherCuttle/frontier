# EVIDENCE_QUERY_V0

Status: FROZEN_AUTHORITY_BEFORE_RUNTIME

Parent development authority: `dev/post-pef-v0@7430c9a5f5ff84900212412d8c9fbd8a7d5a25ae`.

This phase extends the existing read-only public read plane with a deterministic lexical evidence filter. It creates no canonical intelligence, entity, provenance, confirmation, ranking, experimental, or promotion authority.

## 1. Objective

Add one auditable point-in-time query surface over evidence already bound into one retained COMPLETE baseline snapshot.

The V0 query is a filter, not a relevance ranker:

`COMPLETE BASELINE SNAPSHOT -> EXACT MEMBER OBSERVATIONS AT SNAPSHOT as_of -> DETERMINISTIC LEXICAL FILTER -> ORIGINAL BASELINE RANK ORDER`

The phase must provide:

- `GET /v0/search`;
- required lexical query `q`;
- optional existing `snapshot_id` binding;
- existing bounded `limit` / `offset` pagination;
- exact baseline snapshot/receipt/version/`as_of` binding in every response;
- explicit query policy identity and normalized query tokens;
- matched observation IDs for auditability;
- deterministic generated OpenAPI/TypeScript contracts.

## 2. Explicit non-authority

EVIDENCE_QUERY_V0 MUST NOT:

- write or mutate canonical state;
- create a new score, relevance rank, confidence, importance, confirmation, entity, provenance-root, or truth signal;
- reorder or renumber baseline episodes;
- search evidence outside the selected snapshot's episode membership;
- use evidence observed after the selected snapshot `as_of`;
- use experimental candidate ranking to order results;
- add embeddings, vector search, pgvector, an external vector database, LLM inference, generated summaries, fuzzy entity resolution, synonym expansion, stemming, learned retrieval, or MCP;
- become `AGENT_CONTEXT_PROTOCOL_V0` or `AGENT_RETRIEVAL_EXPERIMENT_V0` by implication.

The existing baseline rank remains the only ordering authority exposed by this surface.

## 3. Frozen identifiers

- query policy: `evidence-query-lexical-filter-v0`
- semantic scope: `BASELINE_SUBSTRATE_QUERY`
- endpoint: `GET /v0/search`
- response schema remains within the generated public-read contract family.

## 4. Snapshot and evidence boundary

Every query resolves exactly one snapshot through the existing `PublicReadService` / public-read repository rules.

Only a retained COMPLETE baseline snapshot may be queried.

For that snapshot:

1. validate baseline episode IDs/ranks with the existing public-read invariants;
2. collect the exact union of `observation_ids` contained by those episodes;
3. load those observations through the existing repository with `observed_at <= snapshot.as_of`;
4. fail closed on duplicate returned observations;
5. fail closed unless the returned observation-ID set equals the exact expected snapshot-member set;
6. never admit a repository row not named by the selected snapshot.

A missing member observation is an integrity failure, not an implicit non-match. An extra observation is an integrity failure, not additional search recall.

## 5. Query normalization

V0 normalization is intentionally small and deterministic:

1. require a string of 1..256 Unicode code points after trimming leading/trailing whitespace;
2. split on Unicode whitespace;
3. `casefold()` each token;
4. remove duplicate tokens while preserving first occurrence order;
5. allow at most 12 resulting tokens.

No Unicode compatibility normalization, confusable folding, stemming, synonym expansion, punctuation rewriting, fuzzy matching, or language-specific tokenization is authorized.

This means visually confusable or compatibility-equivalent strings remain distinct unless ordinary Unicode `casefold()` itself makes them equal.

## 6. Searchable evidence text

For each snapshot-member observation, V0 may search only:

- `source_item_key`;
- `kind`;
- string leaf values recursively contained in canonical `payload`.

V0 MUST NOT treat as lexical content:

- JSON object keys;
- numbers;
- booleans;
- null;
- relation metadata;
- health metadata;
- collection-run metadata;
- digests;
- timestamps;
- source IDs merely because they are source identifiers.

Nested arrays/objects are traversed only to reach string leaf values. No value is coerced to string.

## 7. Match semantics

Matching is case-insensitive substring matching against `casefold()`ed searchable string values.

An episode matches iff **every normalized query token** is present in at least one searchable value across that episode's own member observations. Different tokens may be satisfied by different observations in the same episode.

`matched_observation_ids` contains, in the episode's snapshot membership order, observations that match at least one normalized token.

No token frequency, field weighting, match count, proximity, or other relevance score is computed or exposed.

## 8. Ordering and pagination

Matched episodes remain in original baseline rank ascending.

Filtering occurs before pagination.

The response preserves original `rank`; it never renumbers results from 1..N.

A lower-ranked episode with more lexical occurrences MUST remain below a higher-ranked matching episode.

## 9. Response audit fields

The response must expose at least:

- existing immutable snapshot binding;
- existing aggregate transport/freshness/coverage/schema states;
- `query_policy_version="evidence-query-lexical-filter-v0"`;
- `semantic_scope="BASELINE_SUBSTRATE_QUERY"`;
- original request query `q`;
- normalized query tokens;
- `total`, `limit`, `offset`;
- items containing the unchanged baseline episode and `matched_observation_ids`.

No `score`, `confidence`, `relevance`, `entity`, or inferred semantic label is authorized.

## 10. Transport and persistence

- GET only;
- reuse the existing verified read-only PostgreSQL public-read repository/session;
- no migration;
- no new persisted index or mutable query state;
- no query telemetry may feed canonical signal/ranking;
- generated OpenAPI remains Python/TypeScript transport authority under ADR-0008.

## 11. Frozen hostile corpus

`fixtures/evidence_query/corpus_v0.json` is frozen before runtime implementation and defines the required adversarial families.

Runtime implementation MUST NOT rewrite the expected semantics in that corpus after seeing failures.

## 12. Acceptance gates

EVIDENCE_QUERY_V0 may close only when all are true:

1. this authority and hostile corpus predate runtime implementation;
2. exact snapshot membership and `as_of` confinement are verified;
3. query normalization exactly matches §5;
4. only authorized string values in §6 are searchable;
5. all-token episode matching and matched-observation audit semantics match §7;
6. baseline rank/order is preserved and no relevance score exists;
7. filtering precedes pagination;
8. zero-match is explicit and deterministic;
9. malformed/empty/over-limit queries fail explicitly;
10. public API remains GET-only and DB boundary remains read-only;
11. generated OpenAPI/TypeScript artifacts are deterministic;
12. no migration, source registry, PEF preregistration, PEF ranking, live confirmatory deployment, or canonical `main` change occurs;
13. full applicable repository CI passes;
14. exactly one hostile closure review is performed; Critical/High findings receive one bounded repair and one targeted re-review only if required.

## 13. Non-escalation

Search inclusion means only: lexical content in canonical evidence belonging to the selected baseline snapshot matched the frozen filter.

It does not mean the episode is true, important, confirmed, independently corroborated, entity-resolved, semantically similar, or recommended.
