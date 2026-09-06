# ENTITY_PROVENANCE_BRIDGE_V0

Status: FROZEN_BRIDGE_AUTHORITY_CANDIDATE

Parent authority: `main@23cf10e0d65883c7b82356cf1bd18d9c56215604`.

Promotion rule: merge of this authority PR promotes this document to `FROZEN_BRIDGE_AUTHORITY` and authorizes implementation of the bounded bridge defined here. It does **not** authorize entity/provenance truth, persistence, API exposure, terminal exposure, worker scheduling, ranking changes, or candidate promotion.

## Why this phase exists

`ENTITY_PROVENANCE_LAB_V0` closed successfully as an offline falsification lab and selected:

- entity candidate: `transparent-entity-hybrid-v0`;
- provenance candidate: `explicit-reference-v0`.

The lab intentionally used a richer synthetic evidence vocabulary than current canonical FRONTIER relations. Current canonical `ObservationRelation` types are only `CORRECTS`, `RETRACTS`, and `REFERENCES`, with `EXPLICIT` or `INFERRED` authority.

Therefore the next safe step is **not** to turn the lab on in production. It is to freeze and falsify the one-way mapping from existing canonical evidence into experimental entity/provenance lab inputs, and to measure what evidence is actually available without inventing stronger semantics.

## Objective

Implement, after this authority merges, a deterministic point-in-time **canonical -> experimental bridge** that:

1. consumes only already-canonical observations and relations available by `as_of`;
2. emits ephemeral experimental bridge records and coverage diagnostics;
3. exposes evidence gaps explicitly;
4. never upgrades canonical relation semantics;
5. never grants entity, provenance, confirmation, origin, ranking, or truth authority.

This phase answers: **can the selected lab methods be supplied faithfully from current retained FRONTIER evidence?**

It does not answer whether those methods should be promoted.

## Lineage

Frozen lab lineage:

- lab: `ENTITY_PROVENANCE_LAB_V0`;
- lab merge commit: `23cf10e0d65883c7b82356cf1bd18d9c56215604`;
- hostile lab corpus digest: `sha256:04ac150abe4356ef06a6fda75429d5873d8dd519e79e29f5c5e2853f4432a386`;
- selected entity candidate: `transparent-entity-hybrid-v0`;
- selected provenance candidate: `explicit-reference-v0`.

Bridge hostile corpus:

- path: `fixtures/entity_provenance/bridge_corpus_v0.json`;
- case count: 18;
- canonical digest: `sha256:9b9998be5245c7d4481652c588177c6a46ed486dd5b51902630bd36b901686ad`.

Exact source registry remains:

- `arxiv.cs-ai`
- `cisa.kev`
- `gdelt.frontier`
- `github.ml-repos`
- `hf.models`
- `hn.frontpage`
- `pypi.updates`

Registry digest remains `sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee`.

## Authority boundary

This is a derived experimental adapter only.

It MUST NOT:

- mutate canonical observations or relations;
- create canonical entity IDs;
- create canonical provenance-root IDs;
- regroup episodes;
- treat source multiplicity as independence;
- infer confirmation strength;
- infer true origin;
- infer causal ancestry;
- convert `NO_LINK_EVIDENCE` into independence;
- change baseline/PEF ranking;
- write migrations;
- persist bridge output to canonical PostgreSQL;
- add API routes;
- add terminal surfaces;
- schedule worker execution;
- alter the seven-source registry.

The bridge is one-way: canonical evidence may feed experimental bridge records; experimental bridge output must never flow back into canonical identity/evidence by this phase.

## Point-in-time contract

For bridge evaluation at `as_of = T`:

- an observation is eligible only when canonical `observed_at <= T`;
- source/effective/publication timestamps never grant earlier knowledge;
- BACKFILL collected after T is unavailable at T even when its publisher timestamp is old;
- a canonical relation may be inspected only if it was durably known by T;
- a future relation cannot alter an earlier bridge record;
- replay of frozen canonical inputs/config/version/`as_of` must serialize identically.

A bridge implementation that consults current state without reconstructing the historical knowledge horizon is nonconforming.

## Frozen entity-evidence mapping

V0 deliberately supports entity-native identity only where current canonical evidence contains a conservative stable coordinate.

### `pypi.updates`

Eligible observations: `ARTIFACT` with artifact type `python-package-release`.

Experimental entity type: `PACKAGE`.

Native ID:

`pypi:<NFC + casefold of ArtifactPayload.name>`

No punctuation folding or extra package-name equivalence heuristic is authorized in V0.

### `cisa.kev`

Eligible observations: canonical CISA KEV documents.

Experimental entity type: `VULNERABILITY`.

Native ID:

`cve:<source_item_key>`

only when:

- `source_item_key` is a valid CVE identifier; and
- `source_metadata.cve_id`, when present, exactly matches it.

Mismatch or malformed metadata removes that identity signal; it is not coerced.

### `github.ml-repos`

Eligible observations: GitHub repository artifacts.

Experimental entity type: `REPOSITORY`.

Native ID:

`github_repo:<github_repository_id>`

only when `source_metadata.github_repository_id` is a positive JSON integer.

`node_id`, repository slug, owner/name, title, URL, and `fork` boolean do not substitute for the frozen numeric repository identity in V0.

### `hf.models`

Eligible observations: Hugging Face model repository artifacts.

Experimental entity type: `MODEL`.

Native ID:

`hf_model:<source_item_key>`

The V0 bridge does not infer rename continuity if the provider key changes.

### Unsupported entity sources in V0

The bridge emits **no entity-native identity** for:

- `arxiv.cs-ai`;
- `gdelt.frontier`;
- `hn.frontpage`.

This is a deliberate conservative gap, not evidence that no entity exists.

In particular:

- a GDELT discovery URL is not project identity;
- an HN link/title is not project identity;
- an arXiv version/document identifier is not promoted to persistent research-entity identity by this bridge.

Same URL/title alone must never override this unsupported state.

## Frozen provenance-evidence mapping

The selected provenance candidate is `explicit-reference-v0`, but the current canonical relation vocabulary does not contain the lab's explicit derivation relations (`COPY_OF`, `REVISION_OF`, `FORK_OF`).

Therefore V0 freezes **zero direct-derivation bridge authority**.

The following upgrades are forbidden:

- `REFERENCES -> DIRECT_DERIVATIVE`;
- `CORRECTS -> DIRECT_DERIVATIVE`;
- `RETRACTS -> DIRECT_DERIVATIVE`;
- GitHub `fork=true` without an explicit parent target -> `DIRECT_DERIVATIVE`;
- same canonical URL -> `DIRECT_DERIVATIVE`;
- exact text/content mirror -> `DIRECT_DERIVATIVE`;
- earliest FRONTIER observation -> true origin.

The bridge may report that current provenance-direct-evidence coverage is zero. That is a coverage limitation only. It is never factual independence, no-derivation truth, or provenance-root diversity.

A later phase may propose richer explicit provenance evidence, but only under a separate frozen authority. This phase cannot smuggle such schema/source changes into the bridge.

## Malformed evidence behavior

Provider-specific metadata is untrusted as a semantic signal until type-checked against the frozen mapping.

- objects/lists are never stringified into native IDs;
- numeric repository identity is never accepted from a string or object;
- mismatched CISA CVE metadata disables the identity signal;
- missing fields reduce coverage instead of fabricating defaults;
- unsupported source metadata cannot promote a source into a supported entity class.

Malformed identity evidence may yield a degraded/unsupported bridge record, but must never create a stronger positive identity signal.

## Bridge output

Implementation may produce only:

1. ephemeral `BridgeObservation`-equivalent values used by tests/offline diagnostics;
2. an offline coverage report.

Coverage must be reported separately by source and signal family, including at least:

- total PIT-eligible observations;
- entity-bridge supported;
- entity-bridge degraded;
- entity-bridge unsupported;
- native-ID signal count;
- malformed identity-field count;
- direct-derivation evidence count;
- ignored future observation/relation count.

A zero count must remain zero; it cannot be converted into evidence of absence.

## Success / falsification

Bridge implementation closes only if:

- all 18 frozen bridge cases pass;
- deterministic replay is byte-identical for frozen input/config/`as_of`;
- no future observation/relation leaks across the horizon;
- no unsupported source is upgraded to entity authority;
- no canonical relation is upgraded to direct derivation;
- malformed metadata fails closed;
- coverage gaps remain explicit;
- the seven-source registry and canonical data contract remain unchanged;
- one bounded hostile implementation review has no unresolved Critical/High defect after the normal single repair/re-review policy.

A valid bridge may still prove that provenance evaluation is currently underpowered. That is an acceptable scientific result.

## Explicit exclusions

No:

- canonical schema extension;
- migration;
- source normalizer expansion;
- observation-relation enum expansion;
- persistence;
- worker scheduling;
- API;
- terminal;
- public entity/provenance labels;
- prospective candidate evaluation;
- promotion decision;
- PEF/baseline ranking change;
- graph DB/vector DB/LLM.

## Closure discipline

Authority freeze:

`AUTHORIZE -> FREEZE CONTRACT/CORPUS -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if needed -> VERIFY -> MERGE -> VERIFY MERGED TREE`

After authority merges, bridge implementation:

`IMPLEMENT -> TEST -> ONE hostile implementation review -> fix Critical/High -> ONE targeted re-review only if needed -> CLOSE`

Only after bridge closure may a separate `ENTITY_PROVENANCE_SHADOW_EVALUATION` authority be proposed. Provenance evaluation remains blocked unless explicit derivation evidence is separately earned rather than inferred from weaker canonical relations.
