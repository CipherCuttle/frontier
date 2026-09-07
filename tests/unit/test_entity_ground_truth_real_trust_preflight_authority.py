from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from frontier.domain.entity_ground_truth_protocol_v2 import (
    ENTITY_QUALITY_STATUS,
    PROMOTION_STATUS,
)

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_real_trust_preflight_authority.json"
)
VALIDATOR_PATH = ROOT / "src/frontier/domain/entity_ground_truth_protocol_v2.py"

EXPECTED_PARENT = "bd2e910ebdc908b1002efbefda8fe030686cea99"
EXPECTED_VALIDATOR_BLOB = "3a5f383f0cdc84f2f75ca968931d423b56832ee7"
EXPECTED_REVIEWED_HEAD = "d9c155f23e8a6ddbe4eeb71c9b56c5e7331ccc60"


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{name} must be object")
    return cast(dict[str, object], value)


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"{name} must be array")
    return cast(list[object], value)


def _load() -> dict[str, object]:
    raw: object = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    return _object(raw, AUTHORITY_PATH.name)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in cast(dict[object, object], value).items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in cast(list[object], value):
            keys.update(_walk_keys(child))
    return keys


def _assert_true_fields(value: dict[str, object], *names: str) -> None:
    for name in names:
        assert value[name] is True, name


def test_preflight_binds_merged_validator_and_preserves_state() -> None:
    authority = _load()
    lineage = _object(authority["lineage"], "lineage")
    closure = _object(authority["closure_requirements"], "closure_requirements")

    assert authority["schema_version"] == (
        "frontier-entity-ground-truth-real-trust-preflight-authority-v1"
    )
    assert authority["phase_id"] == "ENTITY_GROUND_TRUTH_REAL_TRUST_PREFLIGHT_V0"
    assert authority["authority_state"] == "BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL"
    assert authority["parent_main_commit"] == EXPECTED_PARENT
    assert lineage["offline_validator_merge_commit"] == EXPECTED_PARENT
    assert lineage["offline_validator_source_git_blob_sha1"] == EXPECTED_VALIDATOR_BLOB
    assert _git_blob_sha1(VALIDATOR_PATH) == EXPECTED_VALIDATOR_BLOB
    assert closure["one_bounded_hostile_review"] == (
        f"SPENT_ON_{EXPECTED_REVIEWED_HEAD.upper()}"
    )
    assert closure["critical_high_findings"] == (
        "FIVE_P1_REPAIRED_PENDING_TARGETED_REREVIEW"
    )
    assert ENTITY_QUALITY_STATUS == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert PROMOTION_STATUS == "UNAVAILABLE"


def test_gate_requires_bound_real_material_and_rejects_shortcuts() -> None:
    authority = _load()
    gate = _object(authority["real_trust_material_gate"], "real_trust_material_gate")
    fields = set(_array(gate["required_bundle_fields"], "required_bundle_fields"))

    assert gate["status"] == "BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL"
    assert gate["minimum_distinct_human_adjudicators"] == 2
    assert gate["synthetic_test_material_can_satisfy_gate"] is False
    assert gate["placeholder_or_example_material_can_satisfy_gate"] is False
    assert gate["fingerprint_only_material_can_satisfy_gate"] is False
    assert gate["self_declared_origin_root_ids_can_satisfy_independence"] is False
    assert {
        "identity_attestation_authority",
        "adjudicator_identity_key_bindings",
        "service_sealing_verification_object",
        "durability_publication_verification_object",
        "role_controller_attestations",
        "origin_provenance_manifest",
        "rotation_lineage",
        "validity_state",
        "bundle_digest",
    }.issubset(fields)


def test_subject_attestation_binds_exact_key_and_proof_of_possession() -> None:
    authority = _load()
    binding = _object(authority["identity_key_binding_policy"], "binding")

    assert binding["repository_subject_identifiers"] == "OPAQUE_STABLE_SUBJECT_COMMITMENTS"
    assert binding["identity_attestation_must_bind_role"] == "ADJUDICATOR"
    assert binding["proof_of_possession_signature_scheme"] == "ED25519"
    assert binding["proof_of_possession_domain_separator"] == (
        "FRONTIER_ENTITY_GROUND_TRUTH_ADJUDICATOR_POP_V0"
    )
    assert set(_array(binding["proof_of_possession_message_fields"], "pop_fields")) == {
        "phase_id",
        "subject_commitment",
        "adjudicator_public_key_sha256",
        "identity_attestation_digest",
        "proof_challenge_nonce",
    }
    assert binding["proof_challenge_nonce_minimum_bits"] == 128
    _assert_true_fields(
        binding,
        "externally_verifiable_human_identity_attestation_required",
        "identity_attestation_must_bind_exact_subject_commitment",
        "identity_attestation_must_bind_exact_adjudicator_public_key_bytes",
        "subject_controlled_proof_of_possession_required",
        "proof_of_possession_must_verify_under_bound_adjudicator_key",
        "two_adjudicator_slots_must_resolve_to_distinct_human_subjects",
        "candidate_builder_or_evaluator_identity_may_not_self_attest_independence",
        "frontier_model_or_runtime_may_not_generate_human_identity_attestations",
    )


def test_complete_public_verification_objects_are_required() -> None:
    authority = _load()
    signature = _object(authority["signature_policy"], "signature_policy")
    verification = _object(authority["verification_object_policy"], "verification")

    assert signature["adjudicator_signature_scheme"] == "ED25519"
    assert signature["service_sealing_signature_scheme"] == "ED25519"
    assert signature["durability_signature_scheme"] == "ED25519"
    assert signature["identity_attestation_scheme"] == (
        "EXTERNALLY_DECLARED_AND_OFFLINE_VERIFIABLE_NOT_FIXED_TO_ED25519"
    )
    assert signature["ed25519_public_key_encoding"] == "BASE64URL_NOPAD_32_RAW_BYTES"
    _assert_true_fields(
        signature,
        "complete_public_verification_object_required",
        "fingerprints_are_derived_identifiers_only",
        "fingerprint_only_material_rejected",
        "private_keys_repository_forbidden",
        "test_only_key_ids_forbidden",
    )
    _assert_true_fields(
        verification,
        "adjudicator_verification_object_requires_complete_public_key",
        "service_sealing_verification_object_requires_complete_public_key",
        "durability_publication_verification_object_requires_complete_public_key",
        "identity_attestation_authority_requires_complete_offline_verification_material",
        "identity_attestation_authority_requires_scheme_id",
        "identity_attestation_authority_requires_trust_anchor_or_certificate_chain",
        "unavailable_or_unverifiable_public_material_fails_closed",
        "derived_fingerprint_mismatch_fails_closed",
    )


def test_roles_require_exact_material_and_controller_separation() -> None:
    authority = _load()
    separation = _object(authority["role_separation_policy"], "role_separation")
    roles = set(_array(separation["roles_requiring_distinct_controllers"], "roles"))

    assert roles == {
        "ADJUDICATOR_1",
        "ADJUDICATOR_2",
        "SERVICE_SEALING",
        "DURABILITY_PUBLICATION",
        "IDENTITY_ATTESTATION_AUTHORITY",
    }
    _assert_true_fields(
        separation,
        "key_ids_are_non_authoritative_labels",
        "pairwise_distinct_verification_material_required_across_all_signing_roles",
        "byte_level_key_or_verification_object_reuse_across_roles_forbidden",
        "pairwise_distinct_controller_commitments_required",
        "controller_separation_must_be_externally_attested",
        "identity_attestation_authority_must_be_independent_of_candidate_builder_evaluator_and_frontier_runtime",
        "unknown_controller_or_separation_evidence_fails_closed",
    )


def test_origin_independence_is_derived_from_provenance_graph() -> None:
    authority = _load()
    origin = _object(authority["origin_independence_policy"], "origin_policy")

    assert origin["authoritative_input"] == "CONTENT_ADDRESSED_PROVENANCE_GRAPH"
    _assert_true_fields(
        origin,
        "self_declared_origin_root_ids_are_non_authoritative",
        "per_evidence_content_digest_required",
        "provenance_node_content_addressing_required",
        "verified_parent_edges_required",
        "future_validator_must_derive_terminal_upstream_roots",
        "future_validator_must_traverse_verified_parent_edges",
        "common_upstream_roots_must_collapse_to_one_independent_origin",
        "mirrored_syndicated_or_republished_evidence_cannot_count_as_independent_roots",
        "missing_ambiguous_or_unverified_parentage_fails_closed_for_independence",
        "signed_root_labels_alone_cannot_establish_independence",
    )


def test_digest_coverage_rotation_and_current_head_are_fail_closed() -> None:
    authority = _load()
    addressing = _object(authority["content_addressing_policy"], "addressing")
    rotation = _object(authority["rotation_and_validity_policy"], "rotation")

    assert addressing["canonicalization"] == "RFC8785_JCS"
    assert addressing["digest_algorithm"] == "SHA-256"
    assert addressing["digest_prefix"] == "sha256:"
    assert addressing["domain_separator"] == (
        "FRONTIER_ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0\\u0000"
    )
    assert addressing["digest_coverage"] == (
        "COMPLETE_AUTHORITATIVE_BUNDLE_PAYLOAD_EXCLUDING_BUNDLE_ID_AND_BUNDLE_DIGEST"
    )
    assert addressing["bundle_id_derivation"] == (
        "egt-real-trust-v0:<64-lowercase-hex-from-bundle-digest>"
    )
    _assert_true_fields(
        addressing,
        "all_subject_bindings_keys_verification_objects_controller_attestations_provenance_policies_rotation_and_validity_are_digest_covered",
        "future_validator_must_recompute_digest_and_bundle_id",
        "unknown_or_extra_authoritative_fields_are_digest_covered_not_ignored",
    )

    assert rotation["genesis_sequence"] == 0
    assert rotation["genesis_predecessor_bundle_digest"] is None
    _assert_true_fields(
        rotation,
        "key_rotation_requires_new_material_bundle",
        "non_genesis_requires_predecessor_bundle_digest",
        "predecessor_must_equal_previously_pinned_current_authority_head_digest",
        "sequence_must_increment_by_one",
        "successor_requires_authenticated_supersession_statement",
        "supersession_statement_must_bind_predecessor_and_successor_digests",
        "supersession_must_be_authorized_by_predecessor_service_sealing_and_durability_keys",
        "revocation_state_must_be_content_addressed_and_authenticated",
        "unknown_expiry_or_revocation_state_fails_closed",
        "future_validator_requires_expected_current_authority_head_digest",
        "internally_valid_stale_bundle_must_be_rejected_when_not_current_head",
        "next_material_phase_must_pin_exact_current_bundle_digest_and_validity_state_digest",
    )


def test_preflight_contains_no_private_credential_payload_fields() -> None:
    authority = _load()
    keys = _walk_keys(authority)
    forbidden = {
        "private_key",
        "private_key_material",
        "secret_key",
        "secret",
        "seed",
        "mnemonic",
        "recovery_key",
        "signing_token",
    }
    assert keys.isdisjoint(forbidden)


def test_collection_and_quality_remain_forbidden_after_merge() -> None:
    authority = _load()
    collection = _object(authority["collection_authority"], "collection_authority")
    allowed = _object(authority["authorized_after_merge"], "authorized_after_merge")
    scientific = _object(authority["scientific_state"], "scientific_state")
    next_phase = _object(authority["next_phase_if_merged"], "next_phase_if_merged")

    assert collection and all(value is False for value in collection.values())
    assert allowed["prepare_real_trust_material_bundle_candidate"] is True
    assert allowed["prepare_real_trust_material_validation_tests"] is True
    assert allowed["prepare_offline_real_trust_material_validator"] is True
    assert allowed["real_label_collection"] is False
    assert allowed["candidate_quality_evaluation"] is False
    assert allowed["candidate_promotion"] is False
    assert allowed["production_authority_expansion"] is False

    assert scientific["entity_quality"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert scientific["quality_claim"] is None
    assert scientific["promotion_status"] == "UNAVAILABLE"
    assert next_phase["phase_id"] == "ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0"
