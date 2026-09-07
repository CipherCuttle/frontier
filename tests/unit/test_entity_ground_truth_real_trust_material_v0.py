from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from frontier.domain.entity_ground_truth_real_trust_material_v0 import (
    MaterialCandidateStatus,
    candidate_bundle_digest,
    derive_bundle_id,
    material_core_digest,
    object_digest,
    provenance_node_id,
    sha256_digest_bytes,
    validate_real_trust_material_candidate,
    validity_state_digest,
)

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_AUTHORITY_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_real_trust_preflight_authority.json"
)
PROTOCOL_V2_PATH = ROOT / "src/frontier/domain/entity_ground_truth_protocol_v2.py"
EXPECTED_PREFLIGHT_AUTHORITY_BLOB = "955d98348df8622a5336c40762c3cd722f589c8d"
EXPECTED_PROTOCOL_V2_BLOB = "3a5f383f0cdc84f2f75ca968931d423b56832ee7"

JsonObject = dict[str, Any]
JsonList = list[Any]

IDENTITY_MATERIAL = b"external-identity-attestation-authority-material"
IDENTITY_MATERIAL_DIGEST = sha256_digest_bytes(IDENTITY_MATERIAL)
IDENTITY_VALID_FROM = "2026-01-01T00:00:00Z"
IDENTITY_VALID_UNTIL = "2027-01-01T00:00:00Z"
DEFAULT_POP_CHALLENGES = {
    "ADJUDICATOR_1": b"caller-issued-pop-challenge-one",
    "ADJUDICATOR_2": b"caller-issued-pop-challenge-two",
}


def _obj(value: object) -> JsonObject:
    assert isinstance(value, dict)
    return cast(JsonObject, value)


def _list(value: object) -> JsonList:
    assert isinstance(value, list)
    return cast(JsonList, value)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _commitment(label: str) -> str:
    return sha256_digest_bytes(label.encode("ascii"))


class FakeOfflineBackend:
    def __init__(self, *, external_ok: bool = True, ed25519_ok: bool = True) -> None:
        self.external_ok = external_ok
        self.ed25519_ok = ed25519_ok

    def verify_ed25519(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        return self.ed25519_ok and len(public_key) == 32 and bool(message) and len(signature) == 64

    def verify_external_attestation(
        self,
        *,
        kind: str,
        verification_material: bytes,
        payload: dict[str, Any],
        proof: dict[str, Any],
        as_of: datetime,
    ) -> bool:
        return (
            self.external_ok
            and bool(kind)
            and bool(verification_material)
            and bool(payload)
            and proof == {"ok": True}
            and as_of.tzinfo is not None
        )


def _identity_binding(index: int, controller: str) -> JsonObject:
    role = f"ADJUDICATOR_{index}"
    subject = _commitment(f"human-subject-{index}")
    public_key = bytes([64 + index]) * 32
    public_key_digest = sha256_digest_bytes(public_key)
    attestation: JsonObject = {
        "payload": {
            "role": "ADJUDICATOR",
            "issuer_verification_material_sha256": IDENTITY_MATERIAL_DIGEST,
            "subject_commitment": subject,
            "adjudicator_public_key_sha256": public_key_digest,
            "valid_from": IDENTITY_VALID_FROM,
            "valid_until": IDENTITY_VALID_UNTIL,
            "revocation_state": "ACTIVE",
            "revocation_sequence": 0,
        },
        "proof": {"ok": True},
    }
    binding: JsonObject = {
        "role": role,
        "subject_commitment": subject,
        "public_key_b64u": _b64u(public_key),
        "public_key_sha256": public_key_digest,
        "controller_commitment": controller,
        "identity_attestation": attestation,
        "identity_attestation_digest": object_digest(attestation),
        "proof_challenge_nonce_b64u": _b64u(DEFAULT_POP_CHALLENGES[role]),
        "proof_of_possession_signature_b64u": _b64u(bytes([90 + index]) * 64),
    }
    return binding


def _verification_object(role: str, key_byte: int, controller: str) -> JsonObject:
    public_key = bytes([key_byte]) * 32
    return {
        "role": role,
        "public_key_b64u": _b64u(public_key),
        "public_key_sha256": sha256_digest_bytes(public_key),
        "controller_commitment": controller,
    }


def _controller_attestation(
    role: str,
    controller: str,
    verification_material_sha256: str,
    index: int,
) -> JsonObject:
    material = f"controller-attestation-material-{index}".encode("ascii")
    attestation: JsonObject = {
        "payload": {
            "role": role,
            "controller_commitment": controller,
            "verification_material_sha256": verification_material_sha256,
        },
        "proof": {"ok": True},
    }
    return {
        "role": role,
        "controller_commitment": controller,
        "verification_material_b64u": _b64u(material),
        "verification_material_sha256": sha256_digest_bytes(material),
        "attestation": attestation,
        "attestation_digest": object_digest(attestation),
    }


def _root_node(label: str, index: int, *, upstream_label: str | None = None) -> JsonObject:
    content_digest = _commitment(label)
    equivalence = _commitment(upstream_label or f"upstream-{label}")
    verification_material = f"root-verification-material-{index}".encode("ascii")
    attestation: JsonObject = {
        "payload": {
            "content_digest": content_digest,
            "upstream_equivalence_commitment": equivalence,
            "terminal_upstream": True,
        },
        "proof": {"ok": True},
    }
    node: JsonObject = {
        "node_id": "",
        "content_digest": content_digest,
        "parents": [],
        "upstream_equivalence_commitment": equivalence,
        "root_verification_material_b64u": _b64u(verification_material),
        "root_verification_material_sha256": sha256_digest_bytes(verification_material),
        "root_attestation": attestation,
        "root_attestation_digest": object_digest(attestation),
    }
    node["node_id"] = provenance_node_id(node)
    return node


def _child_node(label: str, parent_node_id: str) -> JsonObject:
    content_digest = _commitment(label)
    verification_material = b"provenance-edge-verification-material"
    attestation: JsonObject = {
        "payload": {
            "child_content_digest": content_digest,
            "parent_node_id": parent_node_id,
            "relation": "MIRROR_OF",
        },
        "proof": {"ok": True},
    }
    edge: JsonObject = {
        "parent_node_id": parent_node_id,
        "relation": "MIRROR_OF",
        "verification_material_b64u": _b64u(verification_material),
        "verification_material_sha256": sha256_digest_bytes(verification_material),
        "attestation": attestation,
        "attestation_digest": object_digest(attestation),
    }
    node: JsonObject = {
        "node_id": "",
        "content_digest": content_digest,
        "parents": [edge],
        "upstream_equivalence_commitment": None,
        "root_verification_material_b64u": None,
        "root_verification_material_sha256": None,
        "root_attestation": None,
        "root_attestation_digest": None,
    }
    node["node_id"] = provenance_node_id(node)
    return node


def _provenance_manifest() -> JsonObject:
    root_a = _root_node("origin-a", 1)
    root_b = _root_node("origin-b", 2)
    child = _child_node("mirror-a", str(root_a["node_id"]))
    nodes = [root_a, root_b, child]
    bindings: list[JsonObject] = [
        {"evidence_id": "evidence-a", "node_id": child["node_id"]},
        {"evidence_id": "evidence-b", "node_id": root_b["node_id"]},
    ]
    return {
        "nodes": nodes,
        "evidence_bindings": bindings,
        "manifest_digest": object_digest({"nodes": nodes, "evidence_bindings": bindings}),
    }


def _candidate() -> JsonObject:
    controllers = {
        "ADJUDICATOR_1": _commitment("controller-adjudicator-1"),
        "ADJUDICATOR_2": _commitment("controller-adjudicator-2"),
        "SERVICE_SEALING": _commitment("controller-service"),
        "DURABILITY_PUBLICATION": _commitment("controller-durability"),
        "IDENTITY_ATTESTATION_AUTHORITY": _commitment("controller-identity-authority"),
    }
    identity_authority: JsonObject = {
        "scheme_id": "EXTERNAL_OFFLINE_IDENTITY_SCHEME_V1",
        "verification_material_b64u": _b64u(IDENTITY_MATERIAL),
        "verification_material_sha256": IDENTITY_MATERIAL_DIGEST,
        "controller_commitment": controllers["IDENTITY_ATTESTATION_AUTHORITY"],
    }
    valid_from = "2026-01-01T00:00:00Z"
    valid_until = "2027-01-01T00:00:00Z"
    validity_state: JsonObject = {
        "state": "ACTIVE",
        "sequence": 0,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "state_digest": "",
        "material_core_digest": "",
        "service_sealing_signature_b64u": _b64u(b"S" * 64),
        "durability_signature_b64u": _b64u(b"D" * 64),
    }
    validity_state["state_digest"] = validity_state_digest(validity_state)
    adjudicator_bindings = [
        _identity_binding(1, controllers["ADJUDICATOR_1"]),
        _identity_binding(2, controllers["ADJUDICATOR_2"]),
    ]
    service_object = _verification_object(
        "SERVICE_SEALING",
        67,
        controllers["SERVICE_SEALING"],
    )
    durability_object = _verification_object(
        "DURABILITY_PUBLICATION",
        68,
        controllers["DURABILITY_PUBLICATION"],
    )
    verification_digests = {
        "ADJUDICATOR_1": str(adjudicator_bindings[0]["public_key_sha256"]),
        "ADJUDICATOR_2": str(adjudicator_bindings[1]["public_key_sha256"]),
        "SERVICE_SEALING": str(service_object["public_key_sha256"]),
        "DURABILITY_PUBLICATION": str(durability_object["public_key_sha256"]),
        "IDENTITY_ATTESTATION_AUTHORITY": str(
            identity_authority["verification_material_sha256"]
        ),
    }
    controller_attestations = [
        _controller_attestation(
            role,
            controllers[role],
            verification_digests[role],
            index,
        )
        for index, role in enumerate(
            [
                "ADJUDICATOR_1",
                "ADJUDICATOR_2",
                "SERVICE_SEALING",
                "DURABILITY_PUBLICATION",
                "IDENTITY_ATTESTATION_AUTHORITY",
            ],
            start=1,
        )
    ]
    bundle: JsonObject = {
        "schema_version": "frontier-entity-ground-truth-real-trust-material-v0",
        "bundle_id": "",
        "created_at": "2026-09-07T11:00:00Z",
        "identity_attestation_authority": identity_authority,
        "adjudicator_identity_key_bindings": adjudicator_bindings,
        "service_sealing_verification_object": service_object,
        "durability_publication_verification_object": durability_object,
        "role_controller_attestations": controller_attestations,
        "origin_provenance_manifest": _provenance_manifest(),
        "revocation_policy": {
            "unknown_state_fails_closed": True,
            "authenticated_validity_state_required": True,
        },
        "expiry_policy": {
            "valid_from": valid_from,
            "valid_until": valid_until,
            "unknown_expiry_fails_closed": True,
        },
        "rotation_lineage": {
            "sequence": 0,
            "predecessor_bundle_digest": None,
            "supersession_statement": None,
        },
        "validity_state": validity_state,
        "bundle_digest": "",
    }
    validity_state["material_core_digest"] = material_core_digest(bundle)
    digest = candidate_bundle_digest(bundle)
    bundle["bundle_digest"] = digest
    bundle["bundle_id"] = derive_bundle_id(digest)
    return bundle


def _refresh_bundle_identity(bundle: JsonObject) -> str:
    state = _obj(bundle["validity_state"])
    state["state_digest"] = validity_state_digest(state)
    state["material_core_digest"] = material_core_digest(bundle)
    digest = candidate_bundle_digest(bundle)
    bundle["bundle_digest"] = digest
    bundle["bundle_id"] = derive_bundle_id(digest)
    return digest


def _validate(
    bundle: JsonObject,
    *,
    expected_current_authority_head_digest: str | None = None,
    expected_pop_challenges: dict[str, bytes] | None = None,
    backend: FakeOfflineBackend | None = None,
    as_of: datetime | None = None,
):
    digest = str(bundle["bundle_digest"])
    return validate_real_trust_material_candidate(
        bundle,
        expected_current_authority_head_digest=(
            digest
            if expected_current_authority_head_digest is None
            else expected_current_authority_head_digest
        ),
        expected_pop_challenges=(
            dict(DEFAULT_POP_CHALLENGES)
            if expected_pop_challenges is None
            else expected_pop_challenges
        ),
        backend=FakeOfflineBackend() if backend is None else backend,
        as_of=datetime(2026, 9, 7, 12, 0, tzinfo=UTC) if as_of is None else as_of,
    )


def test_validator_is_bound_to_merged_preflight_authority() -> None:
    authority = json.loads(PREFLIGHT_AUTHORITY_PATH.read_text(encoding="utf-8"))

    assert _git_blob_sha1(PREFLIGHT_AUTHORITY_PATH) == EXPECTED_PREFLIGHT_AUTHORITY_BLOB
    assert _git_blob_sha1(PROTOCOL_V2_PATH) == EXPECTED_PROTOCOL_V2_BLOB
    assert authority["schema_version"] == (
        "frontier-entity-ground-truth-real-trust-preflight-authority-v1"
    )
    assert authority["authorized_after_merge"]["prepare_offline_real_trust_material_validator"]
    assert authority["authorized_after_merge"]["prepare_real_trust_material_validation_tests"]
    assert authority["collection_authority"]["real_label_collection"] is False
    assert authority["scientific_state"]["entity_quality"] == (
        "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    )
    assert authority["scientific_state"]["promotion_status"] == "UNAVAILABLE"


def test_candidate_accept_never_grants_real_authority() -> None:
    result = _validate(_candidate())

    assert result.status is MaterialCandidateStatus.ACCEPT_CANDIDATE
    assert result.real_trust_authority is False
    assert result.real_label_collection_authorized is False
    assert result.candidate_quality_evaluation_authorized is False
    assert result.promotion_authorized is False
    assert result.entity_quality == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert result.promotion_status == "UNAVAILABLE"
    assert len(result.derived_origin_roots) == 2


def test_test_only_placeholder_or_example_material_is_rejected() -> None:
    candidate = _candidate()
    _obj(candidate["identity_attestation_authority"])["scheme_id"] = "TEST_ONLY_IDENTITY_SCHEME"
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "synthetic-placeholder-or-example-material" in result.violations


def test_secret_material_field_is_rejected_before_other_validation() -> None:
    candidate = _candidate()
    _obj(candidate["identity_attestation_authority"])["private_key"] = "do-not-commit"
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "secret-material-present" in result.violations


def test_fingerprint_without_complete_public_key_is_rejected() -> None:
    candidate = _candidate()
    _obj(candidate["service_sealing_verification_object"]).pop("public_key_b64u")
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "service-or-durability-verification-object" in result.violations


def test_duplicate_human_subject_cannot_masquerade_as_two_adjudicators() -> None:
    candidate = _candidate()
    bindings = _list(candidate["adjudicator_identity_key_bindings"])
    first = _obj(bindings[0])
    second = _obj(bindings[1])
    second["subject_commitment"] = first["subject_commitment"]
    attestation = _obj(second["identity_attestation"])
    _obj(attestation["payload"])["subject_commitment"] = first["subject_commitment"]
    second["identity_attestation_digest"] = object_digest(attestation)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_replayed_pop_fails_without_matching_caller_issued_challenge() -> None:
    candidate = _candidate()
    replay_context = {
        "ADJUDICATOR_1": b"new-fresh-challenge-for-one",
        "ADJUDICATOR_2": DEFAULT_POP_CHALLENGES["ADJUDICATOR_2"],
    }

    result = _validate(candidate, expected_pop_challenges=replay_context)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_duplicate_caller_pop_challenges_fail_closed() -> None:
    candidate = _candidate()
    duplicated = b"same-caller-issued-challenge"

    result = _validate(
        candidate,
        expected_pop_challenges={
            "ADJUDICATOR_1": duplicated,
            "ADJUDICATOR_2": duplicated,
        },
    )

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_expired_human_identity_attestation_is_rejected() -> None:
    candidate = _candidate()
    binding = _obj(_list(candidate["adjudicator_identity_key_bindings"])[0])
    attestation = _obj(binding["identity_attestation"])
    _obj(attestation["payload"])["valid_until"] = "2026-01-02T00:00:00Z"
    binding["identity_attestation_digest"] = object_digest(attestation)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_revoked_human_identity_attestation_is_rejected() -> None:
    candidate = _candidate()
    binding = _obj(_list(candidate["adjudicator_identity_key_bindings"])[0])
    attestation = _obj(binding["identity_attestation"])
    _obj(attestation["payload"])["revocation_state"] = "REVOKED"
    binding["identity_attestation_digest"] = object_digest(attestation)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_controller_reuse_across_roles_is_rejected() -> None:
    candidate = _candidate()
    service = _obj(candidate["service_sealing_verification_object"])
    durability = _obj(candidate["durability_publication_verification_object"])
    attestations = _list(candidate["role_controller_attestations"])
    durability["controller_commitment"] = service["controller_commitment"]
    durability_attestation = next(
        item for item in map(_obj, attestations) if item["role"] == "DURABILITY_PUBLICATION"
    )
    durability_attestation["controller_commitment"] = service["controller_commitment"]
    attestation = _obj(durability_attestation["attestation"])
    _obj(attestation["payload"])["controller_commitment"] = service["controller_commitment"]
    durability_attestation["attestation_digest"] = object_digest(attestation)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "controller-reuse-across-roles" in result.violations


def test_mirrored_evidence_collapses_to_one_origin_and_fails_closed() -> None:
    candidate = _candidate()
    manifest = _obj(candidate["origin_provenance_manifest"])
    nodes = _list(manifest["nodes"])
    bindings = _list(manifest["evidence_bindings"])
    root_a = _obj(nodes[0])
    child = _obj(nodes[2])
    bindings[:] = [
        {"evidence_id": "evidence-a", "node_id": root_a["node_id"]},
        {"evidence_id": "evidence-b", "node_id": child["node_id"]},
    ]
    manifest["manifest_digest"] = object_digest({"nodes": nodes, "evidence_bindings": bindings})
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "origin-provenance-independence" in result.violations


def test_re_attested_same_upstream_equivalence_collapses_to_one_origin() -> None:
    candidate = _candidate()
    manifest = _obj(candidate["origin_provenance_manifest"])
    nodes = _list(manifest["nodes"])
    root_a = _obj(nodes[0])
    root_b = _obj(nodes[1])
    root_b["upstream_equivalence_commitment"] = root_a["upstream_equivalence_commitment"]
    attestation = _obj(root_b["root_attestation"])
    payload = _obj(attestation["payload"])
    payload["upstream_equivalence_commitment"] = root_a["upstream_equivalence_commitment"]
    root_b["root_attestation_digest"] = object_digest(attestation)
    old_root_b_id = str(root_b["node_id"])
    root_b["node_id"] = provenance_node_id(root_b)
    bindings = _list(manifest["evidence_bindings"])
    for raw_binding in bindings:
        binding = _obj(raw_binding)
        if binding["node_id"] == old_root_b_id:
            binding["node_id"] = root_b["node_id"]
    manifest["manifest_digest"] = object_digest({"nodes": nodes, "evidence_bindings": bindings})
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "origin-provenance-independence" in result.violations


def test_missing_provenance_parent_fails_closed() -> None:
    candidate = _candidate()
    manifest = _obj(candidate["origin_provenance_manifest"])
    nodes = _list(manifest["nodes"])
    child = _obj(nodes[2])
    edge = _obj(_list(child["parents"])[0])
    missing_parent = _commitment("missing-parent")
    edge["parent_node_id"] = missing_parent
    attestation = _obj(edge["attestation"])
    _obj(attestation["payload"])["parent_node_id"] = missing_parent
    edge["attestation_digest"] = object_digest(attestation)
    child["node_id"] = provenance_node_id(child)
    bindings = _list(manifest["evidence_bindings"])
    for raw_binding in bindings:
        binding = _obj(raw_binding)
        if binding["evidence_id"] == "evidence-a":
            binding["node_id"] = child["node_id"]
    manifest["manifest_digest"] = object_digest({"nodes": nodes, "evidence_bindings": bindings})
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "origin-provenance-independence" in result.violations


def test_bundle_content_drift_under_old_digest_is_rejected() -> None:
    candidate = _candidate()
    candidate["created_at"] = "2026-09-08T11:00:00Z"

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "bundle-digest" in result.violations


def test_unpinned_or_stale_current_head_is_rejected() -> None:
    result = _validate(
        _candidate(),
        expected_current_authority_head_digest="sha256:" + "0" * 64,
    )

    assert result.status is MaterialCandidateStatus.REJECT
    assert "stale-or-unpinned-current-head" in result.violations


def test_non_genesis_rotation_is_rejected_fail_closed_in_v0() -> None:
    candidate = _candidate()
    candidate["rotation_lineage"] = {
        "sequence": 1,
        "predecessor_bundle_digest": "sha256:" + "1" * 64,
        "supersession_statement": {"opaque": "present"},
    }
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "non-genesis-rotation-fails-closed" in result.violations


def test_expired_candidate_is_rejected() -> None:
    result = _validate(_candidate(), as_of=datetime(2028, 1, 1, tzinfo=UTC))

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_external_verification_failure_is_rejected() -> None:
    result = _validate(_candidate(), backend=FakeOfflineBackend(external_ok=False))

    assert result.status is MaterialCandidateStatus.REJECT
    assert "adjudicator-identity-key-binding-or-pop" in result.violations


def test_naive_as_of_is_rejected() -> None:
    result = _validate(_candidate(), as_of=datetime(2026, 9, 7, 12, 0))

    assert result.status is MaterialCandidateStatus.REJECT
    assert "as-of-must-be-timezone-aware" in result.violations


def test_non_ascii_material_is_rejected_by_frozen_jcs_safe_subset() -> None:
    candidate = _candidate()
    _obj(candidate["identity_attestation_authority"])["scheme_id"] = "EXTERNAL_ÅUTHORITY"

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "bundle-jcs-safe-subset" in result.violations


def test_controller_attestation_cannot_be_replayed_onto_different_role_key() -> None:
    candidate = _candidate()
    service = _obj(candidate["service_sealing_verification_object"])
    new_key = b"Z" * 32
    service["public_key_b64u"] = _b64u(new_key)
    service["public_key_sha256"] = sha256_digest_bytes(new_key)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "controller-attestation" in result.violations


def test_signing_verification_material_reuse_is_rejected() -> None:
    candidate = _candidate()
    service = _obj(candidate["service_sealing_verification_object"])
    durability = _obj(candidate["durability_publication_verification_object"])
    attestations = _list(candidate["role_controller_attestations"])
    durability["public_key_b64u"] = service["public_key_b64u"]
    durability["public_key_sha256"] = service["public_key_sha256"]
    durability_attestation = next(
        item for item in map(_obj, attestations) if item["role"] == "DURABILITY_PUBLICATION"
    )
    attestation = _obj(durability_attestation["attestation"])
    _obj(attestation["payload"])["verification_material_sha256"] = service[
        "public_key_sha256"
    ]
    durability_attestation["attestation_digest"] = object_digest(attestation)
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "verification-material-reuse-across-roles" in result.violations


def test_provenance_cycle_fails_closed() -> None:
    candidate = _candidate()
    manifest = _obj(candidate["origin_provenance_manifest"])
    nodes = _list(manifest["nodes"])
    root_a = _obj(nodes[0])
    child = _obj(nodes[2])
    root_a["parents"] = child["parents"]
    root_a["upstream_equivalence_commitment"] = None
    root_a["root_verification_material_b64u"] = None
    root_a["root_verification_material_sha256"] = None
    root_a["root_attestation"] = None
    root_a["root_attestation_digest"] = None
    root_a["node_id"] = provenance_node_id(root_a)
    manifest["manifest_digest"] = object_digest(
        {"nodes": nodes, "evidence_bindings": manifest["evidence_bindings"]}
    )
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "origin-provenance-independence" in result.violations


def test_validity_authorization_signature_shape_is_required() -> None:
    candidate = _candidate()
    state = _obj(candidate["validity_state"])
    state["service_sealing_signature_b64u"] = _b64u(b"too-short")
    _refresh_bundle_identity(candidate)

    result = _validate(candidate)

    assert result.status is MaterialCandidateStatus.REJECT
    assert "expiry-revocation-or-validity-state" in result.violations
