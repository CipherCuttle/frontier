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

The v2 protocol and offline validator prove deterministic construction and semantic
validation of the frozen synthetic protocol. They do not establish any real human,
identity, origin, sealing, durability, or material-rotation trust root.

Real collection therefore remains fail-closed until externally supplied trust material is
frozen in a separate phase.

`TEST_ONLY_*` keys, public fixture secrets, placeholders, generated identities, model
assertions, self-declared origin-root IDs, fingerprint-only key references, and example
certificates can never satisfy this gate.

## Hostile-review repair invariants

The bounded hostile review on candidate `d9c155f23e8a6ddbe4eeb71c9b56c5e7331ccc60`
found five P1 defects. This repaired authority freezes all five closures prospectively for
`ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`.

### 1. Subject-to-key binding and proof of possession

The authoritative adjudicator object is a combined
`adjudicator_identity_key_binding`, not independent subject and key lists.

For each adjudicator, the external human-identity attestation must bind:

- the exact opaque subject commitment;
- the exact complete adjudicator public-key bytes;
- the `ADJUDICATOR` role;
- the attestation issuer and verification material;
- validity/revocation evidence.

Each subject must also provide a proof-of-possession signature under that exact bound
adjudicator key. The proof is domain-separated as
`FRONTIER_ENTITY_GROUND_TRUTH_ADJUDICATOR_POP_V0` and binds the phase ID, subject
commitment, SHA-256 digest of the exact public key, identity-attestation digest, and a
fresh challenge nonce of at least 128 bits.

Two real humans plus two keys are insufficient if one actor controls both keys. Distinct
human identity, exact key binding, and proof of possession must all verify.

### 2. Complete public verification material

Fingerprints are derived identifiers only. They can never substitute for verification
material.

Every ED25519 signing role must provide the complete 32-byte raw public key encoded as
base64url without padding. The material bundle must also include the complete public
verification object, trust anchor, or certificate chain necessary to verify the declared
external identity-attestation scheme offline.

An unavailable key, unverifiable external reference, fingerprint-only object, or derived
fingerprint mismatch fails closed.

`ED25519` is frozen only for adjudicator, service-sealing, durability-publication, and
adjudicator proof-of-possession signatures. The external human identity-attestation
scheme is not forced to use ED25519; it must declare its scheme and include complete
offline verification material.

### 3. Pairwise key and controller separation

Key IDs are labels, not proof of separation.

The next material validator must compare exact verification material and reject byte-level
key or verification-object reuse across all signing/trust roles.

Controller commitments must be externally attested and pairwise distinct across:

- adjudicator 1;
- adjudicator 2;
- service sealing;
- durability publication;
- identity-attestation authority.

Unknown controller identity or unknown separation fails closed. Candidate code, the
builder, evaluator, Frontier model/runtime, or repository self-assertion cannot establish
controller independence.

### 4. Derived origin independence

Signed or named `origin_root_id` values are non-authoritative.

The real material bundle must carry a content-addressed provenance graph. Every decisive
evidence object must bind to content-addressed provenance nodes and verified parent edges.

The future validator must independently traverse parent relations including mirror,
syndication, republication, derivation, and canonical-source links until terminal upstream
roots are derived. Evidence sharing a terminal upstream root collapses to one independent
origin.

Mirrored, syndicated, or republished copies cannot manufacture independent roots.
Missing, ambiguous, or unverified parentage fails closed for independence.

This repairs the boundary without modifying the already-merged synthetic v2 validator;
real collection remains unauthorized.

### 5. Complete digest coverage and anti-rollback rotation

The future real-trust bundle uses:

- canonicalization: `RFC8785_JCS`;
- digest: `SHA-256`, rendered as `sha256:<lowercase-hex>`;
- domain separator:
  `FRONTIER_ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0\u0000`;
- digest coverage: the complete authoritative bundle payload except the derived
  `bundle_id` and `bundle_digest`;
- bundle ID: derived from the recomputed bundle digest.

Subject bindings, complete verification objects, controller attestations, provenance,
expiry/revocation policy, rotation, and validity state are all digest-covered. Unknown or
additional authoritative fields are covered rather than silently ignored.

Every non-genesis bundle must bind the exact previously pinned current-head digest and
increment lineage sequence by one. A successor requires an authenticated supersession
statement binding predecessor and successor digests, authorized under the predecessor
service-sealing and durability keys.

A later material authority must pin the exact current bundle digest and validity-state
digest. Offline validation requires that expected current-head commitment; an internally
valid but stale bundle must be rejected. Unknown expiry or revocation state fails closed.

## Secret hygiene

Only public verification material and non-secret evidence may enter Git, including public
keys/certificates, derived fingerprints, opaque subject commitments, public identity
attestations, public proof-of-possession signatures, provenance manifests, and public
rotation/revocation/validity receipts.

Private keys, seeds, recovery material, signing tokens, service secrets, and equivalent
credential material are forbidden from the repository.

## Authority after merge

This preflight may authorize only preparation of:

- `ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`;
- an immutable real-trust material bundle candidate built from externally supplied
  non-placeholder public material;
- offline validation tests for that material;
- a pure offline validator for the frozen trust-material invariants.

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

That phase must freeze actual non-placeholder public verification material, subject-to-key
identity attestations, subject-controlled proofs of possession, role-controller
attestations, and content-addressed provenance material supplied from outside Frontier.

Frontier may validate and content-bind that material. It may not invent, synthesize, or
self-attest it.

Even after a real-trust material bundle is frozen, real label collection remains a
separate later authority decision.

## Closure discipline

`AUTHORIZE -> FULL CI -> ONE bounded hostile review -> fix Critical/High -> ONE targeted re-review iff required -> READY_FOR_MERGE`

The bounded hostile review is spent. After this five-P1 repair, full CI is required and
exactly one targeted re-review may test only those five closures and non-escalation.

No merge without explicit repository-owner authorization.
