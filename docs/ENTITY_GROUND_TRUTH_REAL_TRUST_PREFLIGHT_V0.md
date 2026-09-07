# ENTITY_GROUND_TRUTH_REAL_TRUST_PREFLIGHT_V0

Status: `GOVERNANCE_CANDIDATE`

Parent main: `bd2e910ebdc908b1002efbefda8fe030686cea99`

Authority source:
`experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_real_trust_preflight_authority.json`

## Objective

Freeze the fail-closed prerequisites for **real** human entity-ground-truth trust material
after `ENTITY_GROUND_TRUTH_PROTOCOL_V2_OFFLINE_VALIDATOR`.

This phase does **not** create credentials, collect labels, evaluate
`transparent-entity-hybrid-v0`, or change any production authority.

The merged v2 validator remains synthetic-only. Its source is bound here at Git blob
`3a5f383f0cdc84f2f75ca968931d423b56832ee7`.

## Why this phase exists

The v2 protocol and offline validator prove that Frontier can construct and validate the
frozen synthetic protocol without post-hoc fitting. They do not establish any real human,
origin, sealing, or durability trust root.

Real collection must therefore fail closed until actual externally supplied trust material
exists and is frozen separately.

`TEST_ONLY_*` keys, public fixture secrets, placeholder identities, generated identities,
model assertions, and example certificates can never satisfy this gate.

## Real-trust material requirements

The next material bundle must contain immutable, content-addressed public commitments for:

- an externally verifiable human-identity attestation authority;
- exactly two distinct human adjudicator subject commitments at minimum;
- a distinct public verification key for each adjudicator;
- a service-sealing public verification key;
- a durability-publication public verification key;
- real origin-verification roots used to establish source independence;
- explicit key-expiry and revocation policy;
- explicit role-separation assertions;
- a canonical bundle digest.

Human names are not required in Git. Repository-visible subject identifiers should be
opaque stable commitments. The identity evidence behind those commitments must remain
externally verifiable.

## Cryptographic boundary

The preflight freezes `ED25519` as the signature scheme for adjudicator, service-sealing,
and durability signatures in the next real-trust material phase.

Only public verification material, fingerprints, certificate/attestation commitments, and
non-secret metadata may be committed.

Private keys, seeds, recovery material, signing tokens, service secrets, or equivalent
credential material are forbidden from the repository.

Role separation is mandatory:

- the two adjudicator keys must be distinct;
- adjudicator keys must be distinct from the service-sealing key;
- the service-sealing key must be distinct from the durability key;
- test-only key identifiers are forbidden;
- key rotation requires a new immutable material bundle.

## Identity boundary

Frontier cannot prove human distinctness by self-assertion.

The next phase must bind each adjudicator slot to an externally verifiable human identity
attestation and prove that the two slots resolve to distinct subjects.

Candidate code, Frontier runtime/model output, or an evaluator cannot self-attest this
independence.

## Authority after merge

This preflight may authorize only preparation of:

- `ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`;
- an immutable real-trust material bundle candidate;
- offline validation tests for that material;
- a pure offline validator for role separation, key identity, expiry, revocation, and
  content addressing.

It does **not** authorize:

- real label collection;
- candidate accuracy/precision/recall;
- candidate quality PASS/FAIL;
- promotion;
- canonical entity truth;
- persistence or migrations;
- workers or schedulers;
- API or terminal exposure;
- source-registry changes;
- production provenance truth;
- ranking changes.

## Scientific state

Entity quality remains exactly:

`INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

Promotion remains:

`UNAVAILABLE`

No quality claim is authorized.

## Required next phase

`ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`

That phase must freeze actual non-placeholder public verification material and opaque
subject attestations supplied from outside Frontier. Frontier may validate and content-bind
that material, but it may not invent or synthesize it.

Even after the real-trust material bundle is frozen, real label collection remains a
separate later authority decision.

## Closure discipline

`AUTHORIZE -> FULL CI -> ONE bounded hostile review -> fix Critical/High -> ONE targeted re-review iff required -> READY_FOR_MERGE`

No merge without explicit repository-owner authorization.
