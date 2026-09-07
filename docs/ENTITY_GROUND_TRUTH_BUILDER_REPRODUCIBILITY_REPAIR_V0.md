# ENTITY_GROUND_TRUTH_BUILDER_REPRODUCIBILITY_REPAIR_V0

Status: `FROZEN_REPRODUCIBILITY_REPAIR_AUTHORITY_CANDIDATE`

Parent main: `0d30b076cde0439bbd70f1d9390b6d7c5dff5c03`.

Machine authority: `experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_builder_reproducibility_repair_authority.json` (Git blob `beb7bacaec03688b9267e2cc0096a64d69136290`).

## Why this repair exists

`ENTITY_GROUND_TRUTH_V0` correctly repaired six circularity/independence defects and merged as `3449f642aaaa757cf93585a63f997eae059c3463`. During the first post-merge implementation pass, a separate reproducibility defect became visible.

The frozen v1 corpus (`frontier-entity-ground-truth-protocol-corpus-v1`, blob `664a86962b73bd1aae11feea25e41adbfbf5899a`) contains 24 `expected_packet_digest` commitments and states that cases expand from base vectors plus mutations using a "frozen governance builder".

That builder is not present in the merged repository. The corpus also does not itself freeze enough information to reconstruct the exact expanded packets: it lacks the complete packet schema, default receipt payloads, synthetic signature algorithm, default timestamp/sequence rules, nested construction/digest order, and exact mutation application targets.

Commit `955b40d374e7ddc31337f70b89fe4456143adf3f`, which introduced the v1 base-vector/mutation/digest corpus, modified the corpus artifact but did not persist a builder/reference implementation.

Therefore the v1 expected packet digests are historical commitments but are not presently reproducible from a pre-frozen construction rule.

## Fail-closed consequence

Do not invent a builder after freeze and call it v1 conformance.

Do not:
- edit the v1 corpus in place;
- replace or reinterpret its 24 expected packet digests;
- claim the missing builder was reproduced without independent evidence;
- start real label collection;
- emit candidate quality metrics/PASS/FAIL;
- promote the entity candidate;
- grant canonical entity truth;
- add persistence, migrations, workers, API, terminal, source-registry, provenance, or ranking authority.

Entity quality remains exactly:

`INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

## Required repair

Use a versioned v2 protocol freeze rather than mutating v1.

The v2 freeze must bind, before validator conformance is claimed:
1. a deterministic builder/reference specification with its own immutable content identity;
2. the complete expanded synthetic packet schema;
3. synthetic signature/verification algorithms and TEST-ONLY trust roots;
4. deterministic default timestamps and service sequences;
5. exact nested construction, digest, receipt, and signature ordering;
6. exact ordered mutation semantics;
7. a versioned hostile corpus with expected packet digests generated from that frozen builder;
8. independent CI recomputation of every expected digest;
9. the existing 24 attack categories unless a reviewed replacement is strictly stronger;
10. all existing non-escalation boundaries.

## Authority after this repair merges

Only preparation of the v2 builder/specification candidate, v2 synthetic corpus candidate, and v2 reproducibility tests is allowed.

This repair does not itself authorize runtime validator conformance, real labels, candidate-quality evaluation, or promotion.

## Closure

`AUTHORIZE_REPAIR -> ONE BOUNDED HOSTILE REVIEW -> FIX CRITICAL/HIGH -> ONE TARGETED REREVIEW IFF NEEDED -> FULL CI -> MERGE`

After closure, proceed directly to the versioned v2 protocol freeze.
