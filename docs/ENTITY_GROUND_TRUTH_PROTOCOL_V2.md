# ENTITY_GROUND_TRUTH_PROTOCOL_V2

Status: `FROZEN_PROTOCOL_V2_CANDIDATE`

Parent main: `bee2b5a74a7d4df630c72330ea6c576571ffa305`

Machine authority: `experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_protocol_v2_authority.json`

Authority Git blob: `b4e2593481eafc4ce1718263574a1bf26a116001`

## Purpose

This phase repairs the reproducibility defect identified after `ENTITY_GROUND_TRUTH_V0` without rewriting or reinterpreting v1.

The v1 authority and v1 hostile corpus remain immutable historical artifacts. Their expected packet digests are not retroactively fitted to a newly invented builder.

Instead, v2 prospectively freezes the complete construction contract before any runtime validator is allowed to claim conformance.

## Frozen v2 artifacts

- Builder specification: `entity_ground_truth_protocol_builder_v2.json`
  - Git blob: `fca9669c08396de9bb49a218e26a59e47fb87c8e`
  - canonical spec payload digest: `sha256:443135bdcd0702ddae1ef224db243ce376e8ab1c2ffd57f1d3b50498f15cbe95`
- Expanded packet schema: `entity_ground_truth_expanded_packet_v2.schema.json`
  - Git blob: `8ed77a799070dd9e4720069c09a16bb4437e34b2`
  - canonical JSON digest: `sha256:c6fb80c8b5a46a18c2fc631243130fcd41456bcb1754b097d90576f27e1822e1`
- Hostile corpus: `fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v2.json`
  - Git blob: `e61330b6ac94ccb52817fbe4078f63bfcd242732`
  - 24 synthetic hostile cases
- Independent recomputation test: `tests/unit/test_entity_ground_truth_protocol_v2_reproducibility.py`
  - Git blob: `ee03950d85d2258e0ee515a71c0ad9ce73b45529`

## What is now prospectively frozen

The v2 builder fixes:

1. canonical JSON serialization and SHA-256 rules;
2. exact candidate-signal classes and ordering;
3. deterministic timestamps and authoritative sequence numbers;
4. complete packet construction order;
5. synthetic evidence snapshot and origin-receipt construction;
6. rendered adjudication-view and redaction-receipt construction;
7. unique-person identity receipt and sealed-submission construction;
8. authoritative unseal receipt construction;
9. immutable label-bundle construction;
10. exact PRE_DERIVATION and POST_BUNDLE_DIGEST mutation semantics;
11. the complete expanded packet schema;
12. all 24 expected complete-packet digests before runtime validator implementation.

The CI test independently reconstructs every packet using only the frozen builder specification, packet schema and corpus and requires `24/24` exact digest matches.

## Synthetic cryptography boundary

The v2 fixture MAC is intentionally named:

`TEST_ONLY_SHA256_KEYED_CONCAT_V2`

Its status is explicitly:

`TEST_ONLY_NOT_A_REAL_SIGNATURE_SCHEME`

The fixture key material is public test data. Every key id begins with `TEST_ONLY_`. None of these identities, roots, receipts, labels or signatures can authorize real-world ground truth.

Real collection still requires a separately frozen real trust-root and service-key authority.

## Scientific state

Nothing in this freeze establishes candidate quality.

Entity quality remains exactly:

`INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

Promotion remains:

`UNAVAILABLE`

No accuracy, precision, recall, PASS, FAIL or canonical entity-truth claim is authorized.

## Authority after merge

After this freeze merges, the next phase may implement only pure offline/in-memory components that consume these frozen artifacts:

- `offline_packet_expander_validator`
- `offline_blinding_redaction_validator`
- `offline_adjudication_receipt_validator`
- protocol hostile tests

The implementation must reproduce all 24 committed v2 packet digests exactly.

It may not add real label collection, candidate-quality scoring, promotion, persistence, migrations, workers/schedulers, API, terminal, source-registry changes, production provenance truth or ranking changes.

## Closure discipline

`FREEZE -> FULL CI -> ONE BOUNDED HOSTILE REVIEW -> FIX CRITICAL/HIGH -> ONE TARGETED REREVIEW IFF NEEDED -> READY_FOR_MERGE`

An explicit repository-owner waiver must be separately recorded if independent review is externally unavailable; such a waiver is phase-local and does not alter the default policy.
