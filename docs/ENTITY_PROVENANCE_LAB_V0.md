# ENTITY_PROVENANCE_LAB_V0

Status: EXPERIMENTAL_LAB_AUTHORITY_CANDIDATE

Parent authority: `main@db9a56e4be66085def287682fa94bbe599bb58f5`.

## Objective

Test whether simple, deterministic, transparent methods can produce useful **entity-link**
and **provenance-link hypotheses** over retained FRONTIER evidence without changing episode
grouping, factual confirmation, provenance-root independence, public ranking, or any canonical
truth surface.

This is an offline falsification lab. It creates no production runtime authority.

## Authority boundary

The frozen `GROUPING_BASELINE_V0` remains the only authority that decides whether observations
belong to one FRONTIER episode. This lab does not mutate grouping inputs, grouping decisions,
episode IDs, observations, relations, baseline snapshots, source registry state, PEF ranking,
or public read semantics.

The following concepts remain distinct:

- observation — one source emission durably observed by FRONTIER;
- episode — a reversible grouping interpretation;
- entity — a hypothesized persistent project/product/artifact/research object identity;
- provenance relation — a hypothesized derivation/link relationship between emissions;
- provenance root / factual independence — **not available** in this lab.

A `SAME_ENTITY` lab decision is a hypothesis that two observations refer to the same persistent
object. It is not canonical entity identity.

A `DIRECT_DERIVATIVE` lab decision is permitted only where explicit point-in-time evidence
supports a specific derivation relation. It is not a claim that the referenced item is the true
or ultimate origin.

`NO_LINK_EVIDENCE` means only that this lab has no qualifying evidence of a provenance link.
It must never be interpreted as independent corroboration.

## Epistemic non-escalation

This lab MUST NOT emit or derive:

- factual confirmation or confirmation counts;
- factual confidence / truth probability;
- provenance-root counts;
- independent-source counts presented as independence;
- true-origin identity;
- causal ancestry beyond an explicit qualifying relation;
- authoritative entity identity;
- manipulation verdicts;
- public/canonical ranking authority.

Unknown or insufficient evidence remains explicit rather than being forced into a positive claim.

## Point-in-time rule

For a case evaluated at `as_of = T`:

- observation evidence must have `observed_at <= T`;
- a relation may influence the decision only if it was durably known by FRONTIER by T;
- when a fixture relation has `created_at`, it is eligible only when `created_at <= T`;
- future relations must not retroactively establish entity or provenance hypotheses;
- publisher/effective timestamps do not substitute for FRONTIER knowledge time.

## Frozen hostile corpus

`fixtures/entity_provenance/corpus_v0.json` is the V0 labeled authority for candidate selection.

Entity labels:

- `SAME_ENTITY`
- `DIFFERENT_ENTITY`
- `AMBIGUOUS`

Provenance labels:

- `DIRECT_DERIVATIVE`
- `SHARED_UPSTREAM_POSSIBLE`
- `NO_LINK_EVIDENCE`

`SHARED_UPSTREAM_POSSIBLE` is deliberately weaker than a derivation claim: exact substantive
mirrors may suggest a common upstream, but without explicit ancestry the lab must not invent one.

The corpus includes mirrors, explicit copying, revisions, forks, package versions, repository
renames, stable provider-native identifiers, namespace collisions, Unicode confusables,
punctuation-sensitive aliases, CVE identity, discovery links, DOI identity, same-name collisions,
and a future-relation leakage trap.

## Candidate families

Entity candidates are frozen to:

1. `explicit-native-id-v0`
2. `canonical-entity-target-v0`
3. `artifact-coordinate-v0`
4. `transparent-entity-hybrid-v0`

Provenance candidates are frozen to:

1. `explicit-reference-v0`
2. `exact-content-common-upstream-v0`
3. `transparent-provenance-hybrid-v0`

No embeddings, vector database, graph database, LLM, learned classifier, remote mutable model,
or paid model API is authorized.

## Selection rule

### Entity

1. reject any candidate that emits `SAME_ENTITY` for a frozen `DIFFERENT_ENTITY` or `AMBIGUOUS` case;
2. require `SAME_ENTITY` precision `>= 1.000000`;
3. among survivors maximize `SAME_ENTITY` recall;
4. then minimize forced `DIFFERENT_ENTITY` outcomes on expected `AMBIGUOUS` cases;
5. then prefer lower complexity.

### Provenance

1. reject any candidate that emits `DIRECT_DERIVATIVE` unless the frozen expected label is `DIRECT_DERIVATIVE`;
2. require `DIRECT_DERIVATIVE` precision `>= 1.000000`;
3. among survivors maximize `DIRECT_DERIVATIVE` recall;
4. preserve `NO_LINK_EVIDENCE` where ancestry is unsupported;
5. then prefer lower complexity.

The labels, thresholds, and candidate set may not be weakened after runtime results are visible to
rescue a candidate.

## Required falsifiers

The lab fails or remains experimental if any selected candidate:

- leaks future relations into an earlier `as_of`;
- changes output across deterministic replay;
- treats source multiplicity as factual independence;
- treats earliest-observed evidence as true origin;
- collapses episode grouping into entity identity;
- collapses `NO_LINK_EVIDENCE` into independent confirmation;
- makes an ungrounded `DIRECT_DERIVATIVE` claim;
- creates a false `SAME_ENTITY` on a frozen negative/ambiguous case.

## Output authority

All outputs are offline experimental hypotheses only.

They are not persisted to canonical PostgreSQL by this phase, are not exposed through the public
or experimental API by this phase, and are not rendered in the terminal by this phase.

Operationalization, persistence, prospective evaluation, API exposure, or promotion requires a
separate bounded authority change after this lab is closed.

## Completion discipline

`PREREGISTER -> FREEZE HOSTILE CORPUS -> IMPLEMENT -> TEST -> ONE HOSTILE REVIEW -> repair Critical/High -> ONE targeted re-review only if needed -> CLOSE`

This lab must remain mergeable independently of `GIGASPRINT_01`; it intentionally adds no migration,
readiness, opportunity/outcome, freeze-persistence, source-registry, API, terminal, or operations changes.
