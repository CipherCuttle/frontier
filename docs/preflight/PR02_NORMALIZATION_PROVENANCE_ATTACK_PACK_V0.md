# PR-02 Normalization + Provenance Attack Pack V0

Status: `PREFLIGHT_ONLY`

Runtime implementation authorized: **NO**

This pack attacks the semantic boundary immediately after secure acquisition. A fetch can be transport-safe and syntactically valid while still corrupting FRONTIER if normalization invents identity or provenance.

## Governing rule

Normalization MUST be conservative.

FRONTIER may collapse two representations only when equivalence is justified by protocol semantics or an explicit source-specific rule. Fuzzy similarity, visual similarity, shared content digests, earlier observation time, or shared URLs do not by themselves prove identity or common provenance.

## Standards grounding

- RFC 3986 URI Generic Syntax: URI comparison is purpose-dependent; generic normalization includes scheme/host case normalization, percent-encoding normalization for unreserved characters, and dot-segment handling.
- Unicode UTS #39: confusable detection is a security mechanism. A confusable identifier is not therefore the same identifier.
- FRONTIER canonical text remains NFC under the frozen `frontier-canonical-json-v1` contract.

## Attack classes

### URL over-normalization

Fixtures prove that:
- source-approved tracking parameters may be stripped without creating new evidence;
- semantic query parameters must survive;
- generic URI-equivalent syntax may normalize;
- fragments do not create different network resources;
- normalization policy is not a universal regex that deletes arbitrary query parameters.

### Source identity impersonation

A page calling itself `CISA`, `OpenAI`, or `PyPI` does not acquire that source authority. Registry identity comes from configured source authority and verified acquisition context.

Unicode lookalikes such as Cyrillic/Latin confusables are preserved as distinct raw identifiers and surfaced as risk metadata. They never inherit trust by appearance.

### Mirroring and syndication

Equal content digests can justify a duplicate-content relationship. They do not prove which publisher originated the content.

Explicit source references may establish explicit provenance edges. Without them, lineage stays inferred or unknown.

Propagation is still evidence: multiple syndicated copies may indicate high attention while contributing at most one factual root.

### Content revision

The same source item or URL may change over time.

Changed canonical content creates a new immutable Observation. The prior Observation is not updated or deleted.

A revision relationship is not invented unless source semantics or later inference justify one.

### Corrections and retractions

Correction/retraction chains remain append-only.

`CORRECTS` and `RETRACTS` alter current assertion interpretation, not historical existence. Retraction does not force trend attention to zero.

### Temporal conflict

Source-provided publication time cannot rewrite FRONTIER knowledge history.

`observed_at` remains the knowledge horizon. Contradictory source timestamps are retained as source evidence/anomaly metadata.

### Discovery lineage

A GDELT/HN/search/index/redirect discovery path remains `discovered_via`. It does not become the primary source simply because FRONTIER found the URL there first.

### Ambiguous ancestry

Near-identical documents arriving seconds apart with no explicit references MUST NOT produce a fabricated `root_origin_id`.

FRONTIER may expose an `earliest_observed_origin` while status remains `INFERRED` or `UNKNOWN`.

### Entity confusables

Names that are visually confusable or fuzzily similar become entity-resolution candidates only.

They cannot silently collapse canonical entity identity.

## Permanent kill invariants

PR-02 or later normalization/provenance work fails if it can:

1. remove a semantically meaningful query parameter under generic normalization;
2. inherit source authority from a display label or Unicode lookalike;
3. treat content-digest equality as proof of common origin;
4. treat earliest observation as proof of origin;
5. mutate an existing canonical Observation when fetched content changes;
6. delete prior observations after correction/retraction;
7. let source timestamps rewrite `as_of` knowledge history;
8. promote discovery surfaces into primary authority;
9. turn similarity scores into `EXPLICIT` provenance;
10. auto-merge confusable/fuzzy entity names into canonical identity.

## Corpus

`fixtures/acquisition/normalization_provenance_v0.json`

20 cases:

- `NORM-001..005` URL equivalence / over-normalization
- `NORM-006..007` source impersonation
- `NORM-008` mirror ambiguity
- `NORM-009` syndication
- `NORM-010` same-content provenance ambiguity
- `NORM-011` content revision
- `NORM-012..013` correction/retraction chains
- `NORM-014` conflicting timestamps
- `NORM-015` same URL, changed bytes
- `NORM-016` discovery lineage
- `NORM-017` ambiguous ancestry
- `NORM-018` Unicode entity confusable
- `NORM-019` NFC equivalence
- `NORM-020` fuzzy over-normalization

This pack specifies test authority only. It does not select the future URL-canonicalization, dedupe, provenance-inference, clustering, or entity-resolution algorithms.
