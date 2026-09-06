# ENTITY_GROUND_TRUTH_V0

Status: FROZEN_ENTITY_GROUND_TRUTH_AUTHORITY_CANDIDATE

Parent main: `fbf69ecd9f0bf810011e71e8dd2c1627e0b02011`.

This phase exists because `ENTITY_PROVENANCE_SHADOW_EVALUATION_V0` closed successfully while still returning:

`entity_quality_status = INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

The current entity candidate is `transparent-entity-hybrid-v0`. Its entity decision surface can consume provider-native identifiers, canonical target continuity, entity type/name, and explicit `ALIAS_OF` / `RENAMED_FROM` evidence. Reusing those same Frontier signals as the correctness oracle would be circular.

## Objective

Freeze a genuinely candidate-disjoint entity ground-truth protocol before any ground-truth tooling or candidate-quality evaluation is implemented.

The protocol must make it possible to obtain future immutable `SAME_ENTITY` / `DIFFERENT_ENTITY` human gold labels without exposing the candidate's output, reasons, or consumed Frontier identity signals to adjudicators.

This authority does **not** claim that independent ground truth already exists. The 24 frozen fixtures are synthetic hostile protocol cases only. They test the rules of the labeling protocol and MUST NOT be counted as real-world candidate quality evidence.

## Lineage

- shadow-evaluation authority merge: `0638aaca0e1025ea256306172712f46b94515bc7`;
- shadow-evaluation implementation merge: `fbf69ecd9f0bf810011e71e8dd2c1627e0b02011`;
- shadow-evaluation corpus blob: `58c91348a6f81f31d99aadf50a1c32fb22ac0882`;
- shadow expected-reports blob: `d0fa4e4ff82eeb70f551e4274eb856b5f5e9f3d4`;
- selected entity candidate: `transparent-entity-hybrid-v0`;
- source registry digest remains `sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee`.

Frozen protocol corpus:

- path: `fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json`;
- schema: `frontier-entity-ground-truth-protocol-corpus-v0`;
- exact Git blob SHA-1: `c922306ce09c5db18c09f9d33f6ce21301252026`;
- case count: 24.

Machine authority:

- `experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_authority.json`.

## Scientific boundary

Ground-truth independence is defined against the candidate's actual evidence surface, not against filenames or process labels.

Adjudicators MUST NOT see:

- candidate entity decision;
- candidate reasons;
- Frontier `native_ids`;
- Frontier `canonical_url`;
- Frontier `entity_name`;
- Frontier `entity_type`;
- Frontier `source_item_key`;
- Frontier `ALIAS_OF` relation evidence;
- Frontier `RENAMED_FROM` relation evidence.

`source_item_key` is redacted conservatively even though it is not itself a decision branch in the selected entity candidate because it may encode a provider-native identity.

A label is not independent merely because a human clicked it. If the human sees the candidate's answer or the candidate's identity inputs, that label is invalid for this program.

## External evidence packets

Adjudicators receive only external evidence packets. Every decisive evidence item must:

1. be candidate-disjoint;
2. have an immutable snapshot digest;
3. identify an origin key and origin group;
4. declare its evidence class and decisive direction;
5. be preserved exactly for later audit.

V0 permits these evidence classes:

- `EXTERNAL_EXPLICIT_IDENTITY_DECLARATION`;
- `EXTERNAL_EXPLICIT_DISTINCTNESS_DECLARATION`;
- `INDEPENDENT_CONTROLLED_RESOURCE_CONTINUITY`;
- `INDEPENDENT_RELEASE_ARTIFACT_CONTINUITY`;
- `INDEPENDENT_AUTHORSHIP_CONTEXT`.

At least two decisive evidence items from at least two distinct origin groups are required for an evaluable gold label. Syndicated, mirrored, copied, or otherwise common-upstream evidence shares one origin group even if it appears at multiple URLs.

If there is only one decisive origin group, the result is `ABSTAIN_INSUFFICIENT_EVIDENCE`.

If decisive independent evidence points in conflicting directions, the result is `ABSTAIN_CONFLICTING_EVIDENCE`.

Missing immutable snapshot identity, evidence derived from candidate-visible fields, or automated/model-created gold labels invalidates the packet.

## Human adjudication

V0 requires two independent primary human adjudicators.

They must:

- be distinct people;
- adjudicate independently;
- remain blind to the candidate output and reasons;
- remain blind to the redacted Frontier identity fields above;
- remain blind to the other adjudicator's label until both submissions are frozen.

Both adjudicators must independently agree on `SAME_ENTITY` or `DIFFERENT_ENTITY` for the label to become evaluable gold.

Any primary abstention produces `ABSTAIN_INSUFFICIENT_EVIDENCE`.

Any disagreement produces `ABSTAIN_DISAGREEMENT`.

V0 deliberately does **not** majority-force disagreements through a tie-break adjudicator. Scientific coverage may fall; label precision must not be inflated by coercing uncertain cases into a binary answer.

Only these are evaluable gold labels:

- `SAME_ENTITY`;
- `DIFFERENT_ENTITY`.

Abstentions and invalid packets remain explicit denominator/coverage facts in any later evaluation.

## Sampling and selection leakage

The protocol distinguishes:

- `EVALUATION_RANDOM` — candidate-blind evaluation sampling;
- `CHALLENGE_ONLY` — adversarial diagnostic cases.

Any pair set intended for later headline quality metrics must be frozen before candidate scoring for that pair set. Candidate predictions or reasons may not influence inclusion in the `EVALUATION_RANDOM` set.

Challenge cases are useful diagnostics but MUST NOT be pooled into headline quality metrics.

A valid challenge label remains diagnostic-only even when the human label itself is high quality.

This authority freezes the anti-leakage rule; it does not yet create a real evaluation sample or real gold label bundle.

## Immutability

Every evidence item requires an immutable snapshot digest.

Every real label bundle must be frozen before candidate scoring against that bundle. Post-freeze mutation creates a new label-bundle identity. Old and new label-bundle identities may not be silently pooled.

A mutable label file is not ground truth evidence.

## No fake quality result

Merge of this authority does not upgrade entity quality.

After authority merge, the entity quality status remains:

`INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

until a real candidate-disjoint human label bundle exists and a later separate quality-evaluation authority explicitly authorizes candidate scoring against it.

This phase MUST NOT emit:

- candidate accuracy;
- candidate precision;
- candidate recall;
- candidate quality PASS/FAIL;
- promotion eligibility;
- canonical entity truth;
- public entity labels.

Zero evaluable labels must produce no quality claim, not an optimistic zero-error result.

## Frozen hostile protocol corpus

The 24 cases attack:

1. valid blinded `SAME_ENTITY` control;
2. valid blinded `DIFFERENT_ENTITY` control;
3. candidate output leakage;
4. candidate reason leakage;
5. native-ID leakage;
6. canonical-URL leakage;
7. entity-name leakage;
8. entity-type leakage;
9. source-item-key leakage;
10. alias/rename relation leakage;
11. a single decisive evidence item;
12. mirrored evidence masquerading as two independent sources;
13. candidate-derived evidence;
14. mutable/unbound evidence without snapshot digest;
15. adjudicator disagreement;
16. adjudicator abstention;
17. the same person occupying both adjudicator slots;
18. one adjudicator seeing the peer label before submission;
19. model-generated/automated gold labels;
20. candidate-aware sampling after scoring;
21. challenge-only labels entering headline metrics;
22. mutable label bundle;
23. conflicting independent evidence directions;
24. zero evaluable labels being converted into a quality claim.

The corpus expected outputs freeze packet status, label status, headline-metric eligibility, required action, and the absence of any quality claim.

## Implementation authority after merge

Merge of this authority may authorize only:

- an offline packet validator;
- an offline deterministic blinding/redaction helper;
- an offline adjudication-receipt validator;
- hostile protocol tests.

It does not authorize Frontier to manufacture real labels. Real labels remain external human work.

It does not authorize:

- candidate quality metrics;
- candidate quality PASS/FAIL;
- promotion;
- canonical entity IDs or truth;
- persistence or migrations;
- worker/scheduler behavior;
- API or terminal exposure;
- source-registry change;
- provenance changes;
- ranking changes.

## Closure discipline

Authority phase:

`AUTHORIZE -> FREEZE PROTOCOL/CORPUS -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if required -> VERIFY -> MERGE -> VERIFY MERGED TREE`

Implementation after authority merge:

`IMPLEMENT VALIDATORS -> TEST -> ONE hostile implementation review -> fix Critical/High -> ONE targeted re-review only if required -> CLOSE`

A later `ENTITY_QUALITY_EVALUATION_V0` authority is allowed only after an immutable real candidate-disjoint label bundle exists. That later phase may define statistical metrics and thresholds. This phase does not.
