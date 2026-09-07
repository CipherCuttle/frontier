# ENTITY_GROUND_TRUTH_REAL_TRUST_VALIDATOR_V0

## State

`IMPLEMENTATION_CANDIDATE / BROAD_REVIEW_SPENT / TARGETED_REREVIEW_SPENT / FINAL_P1_REPAIRED_PENDING_FULL_CI`

Parent authority:

- merged `main`: `d4a0edf334576998e89e13ba71ee8fd73ff54b77`
- preflight authority blob: `955d98348df8622a5336c40762c3cd722f589c8d`
- bound protocol-v2 validator blob: `3a5f383f0cdc84f2f75ca968931d423b56832ee7`

This phase implements the authority already granted by
`ENTITY_GROUND_TRUTH_REAL_TRUST_PREFLIGHT_V0` to prepare a pure offline real-trust material
validator and hostile validation tests. It is **not** `ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`
itself and does not create, freeze, or authorize real trust material.

## Authority boundary

`ACCEPT_CANDIDATE` means only that a supplied candidate satisfied this executable mechanical
contract under caller-provided offline verification, caller-provided fresh PoP challenges,
caller-provided expected upstream-equivalence mappings, and an independently supplied current-head
pin.

It never grants:

- real-trust authority;
- real label collection;
- candidate quality evaluation or PASS/FAIL;
- promotion;
- canonical entity truth;
- persistence, API, workers, terminal, registry, ranking, or production provenance authority.

Frozen scientific state remains:

- entity quality: `INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`
- promotion: `UNAVAILABLE`

## Exact implementation scope

1. `src/frontier/domain/entity_ground_truth_real_trust_material_v0.py`
2. `tests/unit/test_entity_ground_truth_real_trust_material_v0.py`
3. `docs/ENTITY_GROUND_TRUTH_REAL_TRUST_VALIDATOR_V0.md`

No other repository surface is authorized by this phase.

## Canonicalization and content addressing

The validator preserves the frozen RFC8785/JCS + SHA-256 contract and accepts only the existing
strict JCS-safe subset. `bundle_digest` is recomputed over the complete authoritative payload
excluding only `bundle_id` and `bundle_digest`, and `bundle_id` is derived from that digest.

A separate `material_core_digest` binds the complete material core for service-sealing and
durability authorization without creating a circular signature inside the full bundle digest.

## Human identity and fresh proof of possession

Exactly two ordered adjudicator slots are required. Each identity attestation must bind:

- role `ADJUDICATOR`;
- opaque subject commitment;
- adjudicator public-key fingerprint derived from the complete supplied public key;
- the exact identity-authority verification-material digest acting as issuer identity;
- authenticated `valid_from` and `valid_until` timestamps;
- authenticated revocation state `ACTIVE`;
- a non-negative authenticated revocation sequence.

The validator passes `as_of` into the injected offline external-attestation verifier and also
mechanically requires `valid_from <= as_of < valid_until`. Unknown, expired, or revoked identity
state fails closed.

Proof of possession does not trust a candidate-chosen nonce as freshness evidence. The caller must
provide exactly one fresh challenge for each adjudicator role. Each challenge must be at least 128
bits and the two challenges must differ. The candidate-carried nonce must exactly equal the
independently caller-supplied role challenge before the ED25519 PoP is accepted. Replaying a valid
old PoP under a new caller challenge therefore fails closed.

The caller is responsible for issuing fresh unpredictable challenges and for not reusing them
across real material-freeze attempts. Frontier does not manufacture freshness by accepting a nonce
merely because the candidate contains it.

## Complete verification objects and role separation

Fingerprints are never accepted in place of complete verification material. Verification bytes
and externally attested controller commitments remain pairwise separated across:

- `ADJUDICATOR_1`
- `ADJUDICATOR_2`
- `SERVICE_SEALING`
- `DURABILITY_PUBLICATION`
- `IDENTITY_ATTESTATION_AUTHORITY`

Controller attestations continue to bind the exact role, controller commitment, and verification
material digest.

## Provenance-derived origin independence

The provenance manifest remains content-addressed and every parent edge/root assertion remains
externally verified. Terminal roots carry an externally attested `upstream_equivalence_commitment`
bound inside the root attestation.

A signed candidate-carried equivalence commitment is **not authoritative by itself**. The caller
must independently provide the complete expected mapping
`content_digest -> upstream_equivalence_commitment` for every terminal root. The validator requires:

- every mapping key and value to be a valid SHA-256 digest;
- exact coverage of the terminal-root content-digest set, with no missing or extra mapping entries;
- each candidate terminal equivalence commitment to exactly equal the caller's expected value for
  that content digest;
- every verified root attestation to bind that same content digest and equivalence commitment;
- traversal to derive root identity from the caller-provided mapping, not from node ID or from an
  unanchored candidate-selected equivalence value.

Therefore two different node IDs, proofs, verification objects, or re-attestations for identical
terminal content cannot manufacture multiple origins by choosing conflicting equivalence
commitments. Common upstreams collapse to one caller-anchored equivalence identity before the
minimum-two-origin threshold is evaluated.

Non-terminal nodes must not carry a terminal equivalence commitment. Missing parents, cycles,
malformed attestations, duplicate evidence IDs, ambiguous/unmapped terminal roots, or fewer than
two distinct derived upstream equivalence commitments fail closed.

The test harness may derive the expected mapping from a positive synthetic fixture only as **test
mechanics**. Production and later real-material callers must supply it independently; deriving the
expected mapping from the candidate under validation would defeat this control.

## Validity, expiry, genesis, and anti-rollback

V0 continues to accept only genesis lineage. The material bundle itself must be ACTIVE and inside
its authenticated validity interval, with service and durability signatures over the frozen
validity-authorization message. The caller must provide the independently expected current-head
digest; an internally valid but stale bundle is rejected.

## Secret and synthetic-material hygiene

Known private/signing/recovery fields remain forbidden, as do `TEST_ONLY_*`, `PLACEHOLDER_*`, and
`EXAMPLE_*` markers. Synthetic fixtures may exercise mechanics but can never become real trust.

## Broad hostile review and bounded repair

The one broad hostile review was spent on exact head
`465f379813310edac7a0157f7987cbe4b31cc403` and found three P1 blockers:

1. candidate-controlled PoP nonce allowed replay without a fresh external challenge;
2. human identity attestations lacked authenticated validity/revocation enforcement at `as_of`;
3. terminal independence counted node IDs, allowing re-attestation of one upstream to manufacture
   multiple apparent roots.

The bounded repair required caller-issued PoP challenges, identity validity/revocation evidence
with `as_of` verification, and externally attested upstream-equivalence commitments used as the
derived root identity.

## Targeted re-review and final bounded repair

The single targeted re-review was spent on exact green head
`b5ecda48faf6d576740235b83742a5a6fccab002`, restricted to the three broad-review P1 closures.
It confirmed no new Critical/High blocker for the PoP-freshness or identity-validity repairs, but
found one remaining P1 inside the original provenance-equivalence closure: identical terminal
content could still be re-attested with two different signed candidate-selected equivalence
commitments and be counted as two origins.

The final bounded repair closes that exact residual defect by requiring the independently
caller-supplied `content_digest -> upstream_equivalence_commitment` mapping described above and by
adding a hostile regression that reproduces conflicting re-attestation for identical terminal
content. No second targeted re-review is authorized; final closure requires fresh exact-head full
CI plus persisted review/repair evidence.

## Required hostile regression coverage

The focused suite must prove rejection of at least:

- replayed PoP under a different caller-issued challenge;
- duplicate caller challenges;
- expired human identity attestation;
- revoked human identity attestation;
- two differently attested terminal nodes sharing one upstream-equivalence commitment;
- identical terminal content re-attested under conflicting equivalence commitments when the
  independent caller mapping binds that content to one canonical equivalence identity;
- synthetic/test/placeholder/example material;
- known secret-bearing fields;
- fingerprint-only signing roles;
- duplicate human subjects;
- reused signing verification material or controllers;
- controller attestation replay onto a different role key;
- mirrored evidence, missing parents, and provenance cycles;
- bundle drift or a stale/unpinned current head;
- non-genesis rotation;
- invalid bundle validity signatures;
- failed external attestation verification;
- naive timestamps and unsupported JCS inputs.

## Closure policy

`IMPLEMENT -> FULL CI -> ONE independent hostile review -> fix Critical/High -> ONE targeted re-review only if Critical/High fixes were required -> final Critical/High closure repair if needed -> FULL CI -> READY_FOR_MERGE`

The broad review and the one targeted re-review are both spent. Do not run another review. The
remaining closure gate is fresh exact-head full CI and evidence synchronization for the final
bounded repair.

Do not merge without explicit repository-owner authorization.
