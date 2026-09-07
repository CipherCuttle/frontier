# ENTITY_GROUND_TRUTH_REAL_TRUST_VALIDATOR_V0

## State

`IMPLEMENTATION_CANDIDATE`

Parent authority:

- merged `main`: `d4a0edf334576998e89e13ba71ee8fd73ff54b77`
- preflight authority blob: `955d98348df8622a5336c40762c3cd722f589c8d`
- bound protocol-v2 validator blob: `3a5f383f0cdc84f2f75ca968931d423b56832ee7`

This phase is an implementation of the authority already granted by
`ENTITY_GROUND_TRUTH_REAL_TRUST_PREFLIGHT_V0` to prepare a pure offline real-trust material
validator and validation tests.

It is **not** `ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0` itself.

## Objective

Provide a deterministic, fail-closed validator for a future externally supplied real-trust
material bundle candidate without creating, synthesizing, self-attesting, or freezing any real
trust material.

The validator exists so the later material-freeze phase can reject malformed, self-declared,
reused, stale, expired, non-independent, or incompletely bound material before any real label
collection is even eligible for separate authorization.

## Authority boundary

This implementation may only validate a supplied candidate.

A result of `ACCEPT_CANDIDATE` means only that the supplied object satisfied this executable
candidate contract under the caller-provided offline verification backend and externally supplied
current-head pin.

It does **not** mean:

- real trust material is frozen;
- synthetic fixture material is real;
- any adjudicator identity is independently established by Frontier;
- label collection is authorized;
- `transparent-entity-hybrid-v0` has been evaluated;
- entity quality is PASS/FAIL;
- promotion is available;
- canonical entity truth exists.

Frozen scientific state remains:

- entity quality: `INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`
- promotion: `UNAVAILABLE`

## Exact implementation scope

1. `src/frontier/domain/entity_ground_truth_real_trust_material_v0.py`
2. `tests/unit/test_entity_ground_truth_real_trust_material_v0.py`
3. `docs/ENTITY_GROUND_TRUTH_REAL_TRUST_VALIDATOR_V0.md`

No persistence, migration, worker, scheduler, API, terminal, source-registry, ranking, production
provenance-truth, label-collection, or candidate-evaluation change is authorized.

## Candidate schema

The top-level candidate must contain exactly the preflight-required fields:

- `schema_version`
- `bundle_id`
- `created_at`
- `identity_attestation_authority`
- `adjudicator_identity_key_bindings`
- `service_sealing_verification_object`
- `durability_publication_verification_object`
- `role_controller_attestations`
- `origin_provenance_manifest`
- `revocation_policy`
- `expiry_policy`
- `rotation_lineage`
- `validity_state`
- `bundle_digest`

Unknown top-level fields fail closed rather than being silently ignored.

## Canonicalization and content addressing

The merged authority freezes RFC8785/JCS + SHA-256 and the domain separator
`FRONTIER_ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0\u0000`.

To avoid adding a new serialization dependency or silently diverging from RFC8785, V0 accepts only
a strict JCS-safe subset:

- ASCII object keys and string values;
- booleans, null, arrays, objects;
- integers only within the IEEE-754 exact-integer range;
- no binary floats;
- no non-ASCII strings.

Within that strict subset the existing Frontier canonical JSON serializer is deterministic and
compatible with the required JCS ordering/encoding properties. Inputs outside the subset fail
closed rather than receiving an approximate canonicalization.

`bundle_digest` is recomputed over the complete authoritative payload excluding only `bundle_id`
and `bundle_digest`, with the frozen domain separator. `bundle_id` is derived from that digest.

A second `material_core_digest` is derived inside the validity state so service-sealing and
durability signatures can bind the complete material core without creating a circular signature
inside the full bundle digest. The full bundle digest still covers the authorization signatures.

## Human subject to key binding

Exactly two ordered adjudicator slots are required.

Each slot must provide:

- an opaque SHA-256 subject commitment;
- a complete base64url-no-pad 32-byte ED25519 public key;
- the derived SHA-256 public-key fingerprint;
- an external identity attestation whose payload binds the exact opaque subject commitment and
  exact adjudicator public-key fingerprint to role `ADJUDICATOR`;
- the canonical attestation digest;
- a minimum 128-bit proof challenge nonce;
- an ED25519 proof-of-possession signature over the frozen domain-separated message fields.

The two subject commitments, two public keys, and two controller commitments must all be distinct.

## Offline verification backend

The core validator contains no network calls and does not hard-code an external human identity
scheme.

The caller supplies an `OfflineVerificationBackend` with only two capabilities:

1. ED25519 signature verification;
2. verification of externally specified attestations against complete supplied verification
   material.

This preserves the preflight decision that adjudicator/service/durability/PoP signatures are
ED25519 while the external human identity-attestation mechanism remains scheme-declared and
offline-verifiable rather than falsely forced into ED25519.

The test suite uses a fake backend only to exercise mechanics. Because this validator never grants
real trust authority, a synthetic test fixture can at most produce `ACCEPT_CANDIDATE`; it cannot
satisfy the real-material gate.

## Complete verification objects and role separation

Fingerprints are never accepted in place of complete verification material.

The candidate must carry complete public verification material for:

- ADJUDICATOR_1
- ADJUDICATOR_2
- SERVICE_SEALING
- DURABILITY_PUBLICATION
- IDENTITY_ATTESTATION_AUTHORITY

Verification material must be byte-distinct across all five roles.

Controller commitments must be pairwise distinct across the same five roles. Each external
controller attestation binds both the role/controller commitment and the exact verification
material digest, preventing an attestation for one controller from being replayed onto a different
key or verification object.

## Provenance-derived origin independence

Self-declared `origin_root_id` labels do not exist in this candidate contract.

The provenance manifest is content-addressed. Every node is content-addressed. Every parent edge
is externally verified and binds:

- child content digest;
- parent node digest;
- relation class.

Terminal upstream nodes require an external root attestation binding the content digest to
`terminal_upstream=true`.

The validator traverses verified parent edges, rejects missing parents and cycles, derives terminal
upstream roots, and collapses common upstream roots. A candidate with fewer than two distinct
derived terminal roots fails closed.

## Validity, expiry, genesis, and anti-rollback

V0 accepts only the genesis material lineage:

- sequence `0`;
- predecessor bundle digest `null`;
- supersession statement `null`.

Any non-genesis rotation fails closed. Rotation support must not be improvised inside this phase.

The candidate must be ACTIVE, within its frozen validity interval, and carry service-sealing plus
durability ED25519 signatures over the domain-separated validity authorization message containing:

- `material_core_digest`
- `state_digest`
- sequence

The caller must also provide the independently expected current authority-head digest. If the
candidate digest differs, validation rejects it as stale or unpinned.

Passing the candidate's own digest back as the expected head is sufficient only for mechanical
tests; the later real-material freeze must provide the pin independently and durably.

## Secret hygiene

The validator rejects known secret-bearing field names such as private keys, seeds, mnemonics,
recovery keys, signing tokens, and service secrets. Exact nested schemas further reduce places in
which unexpected data can hide.

This is a fail-closed repository safeguard, not a claim that arbitrary byte strings can be
semantically proven public. The later real-material freeze must still establish that supplied
verification objects are genuinely public material from the external trust providers.

## Required hostile tests

At minimum, tests must prove rejection of:

- synthetic/test/placeholder/example markers;
- known secret-bearing fields;
- fingerprint-only signing roles;
- duplicate human subjects;
- reused signing verification material;
- reused role controllers;
- controller attestations not bound to the exact verification material;
- mirrored evidence falsely counted as independent roots;
- missing or cyclic provenance parents;
- bundle drift under an old digest;
- a self-consistent but non-pinned/stale bundle;
- non-genesis rotation;
- expired or unauthenticated validity state;
- failed external attestation verification;
- naive/as-timezone-ambiguous evaluation timestamps;
- non-ASCII or otherwise unsupported JCS inputs.

## Closure policy

`IMPLEMENT -> FULL CI -> ONE independent hostile review -> fix Critical/High -> ONE targeted re-review only if Critical/High fixes were required -> READY_FOR_MERGE`

Medium/Low findings do not restart the phase unless they undermine this phase objective, violate a
frozen invariant, break fail-closed behavior, or invalidate the evidence.

Do not merge without explicit repository-owner authorization.
