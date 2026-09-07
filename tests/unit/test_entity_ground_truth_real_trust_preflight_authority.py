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
    ROOT
    / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_real_trust_preflight_authority.json"
)
VALIDATOR_PATH = ROOT / "src/frontier/domain/entity_ground_truth_protocol_v2.py"

EXPECTED_PARENT = "bd2e910ebdc908b1002efbefda8fe030686cea99"
EXPECTED_VALIDATOR_BLOB = "3a5f383f0cdc84f2f75ca968931d423b56832ee7"


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


def test_preflight_binds_the_merged_v2_validator_without_escalating_state() -> None:
    authority = _load()
    lineage = _object(authority["lineage"], "lineage")

    assert authority["schema_version"] == (
        "frontier-entity-ground-truth-real-trust-preflight-authority-v0"
    )
    assert authority["phase_id"] == "ENTITY_GROUND_TRUTH_REAL_TRUST_PREFLIGHT_V0"
    assert authority["authority_state"] == "BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL"
    assert authority["parent_main_commit"] == EXPECTED_PARENT
    assert lineage["offline_validator_merge_commit"] == EXPECTED_PARENT
    assert lineage["offline_validator_source_git_blob_sha1"] == EXPECTED_VALIDATOR_BLOB
    assert _git_blob_sha1(VALIDATOR_PATH) == EXPECTED_VALIDATOR_BLOB

    assert ENTITY_QUALITY_STATUS == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert PROMOTION_STATUS == "UNAVAILABLE"


def test_real_trust_gate_is_explicit_and_cannot_be_satisfied_by_synthetic_material() -> None:
    authority = _load()
    gate = _object(authority["real_trust_material_gate"], "real_trust_material_gate")
    required_fields = set(_array(gate["required_bundle_fields"], "required_bundle_fields"))

    assert gate["status"] == "BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL"
    assert gate["minimum_distinct_human_adjudicators"] == 2
    assert gate["private_key_material_in_repository_forbidden"] is True
    assert gate["synthetic_test_material_can_satisfy_gate"] is False
    assert gate["placeholder_or_example_material_can_satisfy_gate"] is False
    assert gate["candidate_or_frontier_generated_identity_assertions_can_satisfy_gate"] is False
    assert {
        "identity_attestation_authority",
        "adjudicator_subjects",
        "adjudicator_public_keys",
        "service_sealing_public_key",
        "durability_publication_public_key",
        "origin_verification_roots",
        "revocation_policy",
        "expiry_policy",
        "role_separation_assertions",
        "bundle_digest",
    }.issubset(required_fields)


def test_real_trust_crypto_and_role_separation_are_frozen_fail_closed() -> None:
    authority = _load()
    crypto = _object(authority["cryptographic_policy"], "cryptographic_policy")
    identity = _object(authority["identity_policy"], "identity_policy")
    separation = _object(authority["role_separation"], "role_separation")

    assert crypto["adjudicator_signature_scheme"] == "ED25519"
    assert crypto["service_sealing_signature_scheme"] == "ED25519"
    assert crypto["durability_signature_scheme"] == "ED25519"
    assert crypto["private_keys_repository_forbidden"] is True
    assert crypto["public_keys_or_fingerprints_only_in_repository"] is True
    assert crypto["key_ids_unique_across_roles"] is True
    assert crypto["test_only_key_ids_forbidden"] is True
    assert crypto["key_rotation_requires_new_material_bundle"] is True

    assert identity["repository_subject_identifiers"] == "OPAQUE_STABLE_SUBJECT_COMMITMENTS"
    assert identity["real_names_required_in_repository"] is False
    assert identity["externally_verifiable_human_identity_attestation_required"] is True
    assert identity["two_adjudicator_slots_must_resolve_to_distinct_human_subjects"] is True

    assert separation and all(value is True for value in separation.values())


def test_preflight_contains_no_private_credential_payload_fields() -> None:
    authority = _load()
    keys = _walk_keys(authority)

    forbidden_payload_keys = {
        "private_key",
        "private_key_material",
        "secret_key",
        "secret",
        "seed",
        "mnemonic",
        "recovery_key",
        "signing_token",
    }
    assert keys.isdisjoint(forbidden_payload_keys)


def test_collection_and_quality_remain_forbidden_after_preflight_merge() -> None:
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
