# ENTITY_GROUND_TRUTH_V0

Status: FROZEN_ENTITY_GROUND_TRUTH_AUTHORITY_CANDIDATE

Parent main: `fbf69ecd9f0bf810011e71e8dd2c1627e0b02011`.

This phase exists because `ENTITY_PROVENANCE_SHADOW_EVALUATION_V0` closed successfully while still returning:

`entity_quality_status = INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

The current entity candidate is `transparent-entity-hybrid-v0`. Its entity decision surface can consume provider-native identifiers, canonical target continuity, entity type/name, and explicit `ALIAS_OF` / `RENAMED_FROM` evidence. Reusing those same Frontier signals as the correctness oracle would be circular.

## Objective

Freeze a genuinely candidate-disjoint entity ground-truth protocol before any ground-truth tooling or candidate-quality evaluation is implemented.

The protocol must make it possible to obtain future immutable `SAME_ENTITY` / `DIFFERENT_ENTITY` human gold labels without exposing the candidate's output, reasons, or consumed Frontier identity signals to adjudicators.

This authority does **not** claim that independent ground truth already exists. The 24 frozen fixtures are synthetic hostile protocol vectors only. Their test keys, trust roots, and expected outcomes test the rules of the labeling protocol and MUST NOT be counted as real-world candidate quality evidence.

## Lineage

- shadow-evaluation authority merge: `0638aaca0e1025ea256306172712f46b94515bc7`;
- shadow-evaluation implementation merge: `fbf69ecd9f0bf810011e71e8dd2c1627e0b02011`;
- shadow-evaluation corpus blob: `58c91348a6f81f31d99aadf50a1c32fb22ac0882`;
- shadow expected-reports blob: `d0fa4e4ff82eeb70f551e4274eb856b5f5e9f3d4`;
- selected entity candidate: `transparent-entity-hybrid-v0`;
- source registry digest remains `sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee`.

Frozen protocol corpus:

- path: `fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json`;
- schema: `frontier-entity-ground-truth-protocol-corpus-v1`;
- exact Git blob SHA-1: `664a86962b73bd1aae11feea25e41adbfbf5899a`;
- case count: 24.

Machine authority:

- `experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_authority.json`;
- schema: `frontier-entity-ground-truth-authority-v1`.

## Scientific boundary

Ground-truth independence is defined against the candidate's actual evidence surface, not against filenames, process labels, or packet-supplied booleans.

The exact internal candidate-signal boundary is:

- `candidate_output`;
- `candidate_reason`;
- `native_ids`;
- `canonical_url`;
- `entity_name`;
- `entity_type`;
- `source_item_key`;
- `ALIAS_OF`;
- `RENAMED_FROM`.

`source_item_key` is redacted conservatively even though it is not itself a decision branch in the selected entity candidate because it may encode provider-native identity.

A label is not independent merely because a human clicked it. If the human sees the candidate's answer or the candidate's identity inputs, that label is invalid for this program.

A packet MUST NOT establish candidate-disjointness by asserting `candidate_disjoint=true` or an equivalent status flag. The exact rendered adjudication view must be content-addressed and independently rescanned against the complete candidate-signal boundary.

## External evidence packets and rendered adjudication view

The protocol separates immutable raw evidence from the direction-neutral rendered view shown to adjudicators.

Every evidence item must:

1. bind an immutable raw evidence snapshot with a recomputable content identity;
2. contain no candidate dependency digest;
3. bind a content-addressed rendered view;
4. bind the raw snapshot, exact candidate-signal boundary, and rendered view through a content-addressed redaction receipt;
5. participate in an immutable origin-provenance manifest whose nodes, parent links, and root identity are cryptographically verifiable against an approved capture-service trust root.

The validator, not the packet, recomputes rendered-view and redaction identities and rescans every rendered field against the exact candidate-signal boundary.

Rendered evidence MUST be direction-neutral. It MUST NOT expose:

- `decisive_direction`;
- a preassigned `SAME_ENTITY` / `DIFFERENT_ENTITY` conclusion;
- candidate output or reason;
- any other adjudication-outcome metadata.

Per-item human assessments occur only inside separately sealed authenticated human submission receipts after review.

At least two immutable evidence items from at least two cryptographically verified distinct origin roots are required for an evaluable gold label.

`origin_group` strings or equivalent packet-supplied grouping labels are not evidence of independence. The validator must traverse verified provenance manifests to their `root_node_digest` values and collapse evidence sharing one verified root. Syndicated, mirrored, copied, or otherwise common-upstream evidence therefore remains one root even if it appears under multiple publishers or URLs.

If fewer than two verified distinct roots remain, the result is `ABSTAIN_INSUFFICIENT_EVIDENCE` rather than binary gold.

If sealed human item assessments identify conflicting evidence directions, the result is `ABSTAIN_CONFLICTING_EVIDENCE`.

Missing immutable snapshot identity, candidate-derived evidence, failed provenance verification, failed redaction verification, or leaked candidate signals invalidates the packet.

## Human adjudication

V0 requires exactly two primary human submissions from cryptographically verified distinct unique-person subjects.

Each primary submission must:

- bind an externally signed unique-person attestation;
- validate that attestation against an approved trust root;
- resolve to a subject digest distinct from the other primary adjudicator;
- be an immutable service-signed submission receipt;
- be sealed independently before peer-label unsealing;
- remain blind to the candidate output, reasons, and complete candidate-signal boundary;
- remain blind to the peer label until the required submissions are sealed.

Arbitrary `person_key` strings, self-reported `independent=true`, or self-reported peer-blindness booleans are not identity/blindness proof.

The sealed-submission service assigns authoritative sequence numbers. Every required submission sequence must precede the signed peer-label-unseal receipt. The unseal receipt may reference only already sealed submission receipt digests.

Both distinct verified humans must independently agree on `SAME_ENTITY` or `DIFFERENT_ENTITY` for the label to become evaluable gold.

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

Any pair set intended for later headline quality metrics must be bound to a content-addressed `EVALUATION_RANDOM` sample manifest that freezes the exact pair IDs, selection method, seed commitment, role, and creation time.

A signed durability receipt must bind that exact sample-manifest digest strictly before the first candidate scoring receipt for the same digest. A packet-supplied `sampling_frozen_before_candidate_scoring=true` flag or equivalent assertion is not proof.

Candidate predictions or reasons may not influence inclusion in the `EVALUATION_RANDOM` set. Post-scoring selection is `INVALID_PACKET / REJECT_SELECTION_LEAK`.

Challenge cases are useful diagnostics but MUST NOT be pooled into headline quality metrics.

A valid challenge label remains diagnostic-only even when the human label itself is high quality.

This authority freezes the anti-leakage rule; it does not yet create a real evaluation sample or real gold label bundle.

## Label-bundle identity and immutability

A label bundle is an exact content-addressed object:

`bundle_digest = sha256(canonical_json(exact bundle payload))`

Its manifest binds:

- `bundle_version`;
- `sample_manifest_digest`;
- `submission_receipt_digests`;
- `unseal_receipt_digest`;
- `predecessor_bundle_digest`;
- `created_at`.

A signed durability receipt binds one exact bundle digest/version. Any payload mutation creates a different bundle identity. Old and new bundle identities may not be silently pooled, substituted, or treated as one frozen file.

A future separately authorized quality evaluation must bind exactly one immutable bundle digest.

A mutable label file or a self-reported `label_bundle_frozen=true` flag is not ground-truth evidence.

## Trust roots and real-collection gate

The frozen corpus uses synthetic TEST-ONLY keys/trust roots for protocol attacks. Those keys are not authorized to create real labels.

Before any real label collection begins, a separate authority must freeze the approved real trust-root/key identities for at least:

- unique-person identity attestations;
- sealed submissions and peer-label unseal;
- evidence-origin capture/provenance manifests;
- redaction receipts;
- sample/bundle durability or publication receipts.

Those trust-root identities may not be substituted after real collection begins.

Merge of this authority does not itself authorize real-world label generation.

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

Synthetic vectors are not candidate-quality evidence.

Zero evaluable labels must produce no quality claim, not an optimistic zero-error result.

## Frozen hostile protocol corpus

The 24 deterministic synthetic cases attack:

1. valid blinded `SAME_ENTITY` control;
2. valid blinded `DIFFERENT_ENTITY` control;
3. candidate-output leakage into rendered evidence;
4. candidate-reason leakage into rendered evidence;
5. native-ID leakage;
6. canonical-URL leakage;
7. entity-name leakage;
8. entity-type leakage;
9. source-item-key leakage;
10. alias/rename relation leakage;
11. fewer than two evidence items;
12. multiple publisher leaves sharing one verified origin root;
13. candidate-dependent raw evidence;
14. missing raw snapshot digest;
15. adjudicator disagreement;
16. adjudicator abstention;
17. two submissions resolving to one verified unique-person subject;
18. a submission sealed after peer-label unseal;
19. model-generated/automated label origin;
20. sample-manifest durability occurring after candidate scoring;
21. challenge-only labels entering headline metrics;
22. label-bundle payload mutation after its content digest is frozen;
23. conflicting sealed human item assessments;
24. zero evaluable labels being converted into a quality claim.

Each case deterministically expands from an immutable base vector plus ordered mutation operations. Its `expected_packet_digest` binds the complete expanded packet. Stored status assertions are non-authoritative; identities and expected outcomes must be recomputed by the future bounded validators.

The corpus expected outputs freeze packet status, label status, headline-metric eligibility, required action, and the absence of any candidate-quality claim.

## Implementation authority after merge

Merge of this authority may authorize only:

- `offline_packet_expander_validator`;
- `offline_blinding_redaction_validator`;
- `offline_adjudication_receipt_validator`;
- `protocol_hostile_tests`.

The bounded offline implementation may exercise the synthetic vectors, test-only trust roots, deterministic expansion, cryptographic/trust-root interfaces, redaction verification, provenance-root verification, sample/bundle identity verification, and adjudication-receipt validation required by this authority.

It does not authorize Frontier to manufacture real labels. Real label collection remains separately gated by frozen real trust roots and a durable real sample manifest.

It does not authorize:

- real-world label generation by Frontier/model;
- candidate quality metrics;
- candidate quality PASS/FAIL;
- promotion;
- canonical entity IDs or truth;
- persistence or migrations;
- worker/scheduler behavior;
- API or terminal exposure;
- source-registry change;
- provenance or ranking changes.

## Closure discipline

Authority phase:

`AUTHORIZE -> FREEZE PROTOCOL/CORPUS -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if required -> VERIFY -> MERGE -> VERIFY MERGED TREE`

Implementation after authority merge:

`IMPLEMENT VALIDATORS -> TEST -> ONE hostile implementation review -> fix Critical/High -> ONE targeted re-review only if required -> CLOSE`

A later `ENTITY_QUALITY_EVALUATION_V0` authority is allowed only after an immutable real candidate-disjoint human label bundle exists. That later phase may define statistical metrics and thresholds. This phase does not.
