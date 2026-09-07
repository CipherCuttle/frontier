# ENTITY_GROUND_TRUTH_PROTOCOL_V2_OFFLINE_VALIDATOR

Status: `IMPLEMENTATION_CANDIDATE`

Parent main: `a0b419b8e7eda254834295a78edf95447d538689`

Authority source: `ENTITY_GROUND_TRUTH_PROTOCOL_V2` as frozen by PR #27.

## Objective

Implement only the pure offline/in-memory v2 packet expander and semantic validator authorized by the frozen protocol.

This phase does not collect real labels and does not evaluate the quality of `transparent-entity-hybrid-v0`.

## Implementation boundary

The implementation lives only in the domain layer and consumes already-frozen declarative inputs supplied by the caller:

- v2 builder specification;
- v2 complete packet schema;
- v2 24-case synthetic hostile corpus.

It performs no file-system discovery, network access, database access, persistence, migrations, worker scheduling, API routing, terminal rendering, source-registry mutation, ranking mutation, or candidate promotion.

## Two independent responsibilities

### Deterministic expansion

`expand_v2_case(...)` implements the prospectively frozen construction semantics:

- canonical JSON and SHA-256 binding;
- frozen mutation ordering;
- sample-manifest durability receipt;
- candidate-signal boundary;
- evidence snapshot and origin receipts;
- rendered adjudication view and redaction receipt;
- two synthetic identity receipts and sealed submissions;
- authoritative unseal receipt;
- immutable synthetic label bundle;
- final complete packet digest.

The pre-existing independent reproducibility test from the freeze phase remains unchanged and continues to reconstruct the same 24 packets separately. The runtime implementation therefore cannot redefine the expected hashes.

### Semantic validation

`validate_v2_packet(...)` does not consume the corpus `expected` outcome fields. It recomputes and checks:

- builder/schema/non-escalation bindings;
- sample freeze before first candidate scoring;
- raw evidence snapshot binding;
- candidate-derived evidence exclusion;
- origin-root verification and mirror collapse;
- candidate-signal leakage in the adjudication view;
- direction-neutral rendered fields;
- redaction receipt consistency;
- distinct verified human subjects;
- sealed submission integrity and pre-unseal ordering;
- non-human submission exclusion;
- unseal/submission binding;
- label-bundle immutability and durability binding;
- disagreement, abstention, conflict, challenge-only and zero-label behavior.

## Acceptance criteria

The implementation candidate must satisfy all of the following on one exact head:

1. all 24 runtime-expanded packet digests exactly match the frozen commitments;
2. the semantic validator independently derives all 24 frozen expected outcomes;
3. tampering with corpus `expected` outcome assertions cannot change expansion;
4. non-escalation drift fails closed;
5. synthetic test crypto can never be interpreted as real trust authority;
6. the full repository verification, ops-recovery and ops-capacity workflows pass.

## Scientific state

Entity quality remains exactly:

`INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

Promotion remains:

`UNAVAILABLE`

No candidate accuracy, precision, recall, quality PASS/FAIL, real gold label, canonical entity truth, or promotion claim is authorized by this phase.

## Explicitly forbidden

- real label collection;
- real trust-root or service-key creation;
- candidate quality scoring or PASS/FAIL;
- candidate promotion;
- canonical entity truth;
- production provenance truth;
- persistence or migrations;
- workers or schedulers;
- API or terminal exposure;
- source-registry changes;
- ranking changes.

## Closure discipline

`IMPLEMENT -> FULL CI -> ONE independent hostile review -> fix Critical/High -> ONE targeted re-review iff required -> READY_FOR_MERGE`

A review waiver, if ever needed, must be explicit and phase-local. No prior waiver carries forward automatically.
