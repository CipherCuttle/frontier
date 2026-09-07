"""Pure offline candidate validator for ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0.

This module does not create trust material and never authorizes label collection, candidate
quality claims, promotion, or canonical entity truth. It validates a supplied material-bundle
candidate against the merged preflight contract. External signature/attestation verification is
injected so this domain module remains offline and does not hard-code an identity scheme.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, Protocol, cast

from frontier.domain.canonical_json import CanonicalizationError, canonical_json_bytes

PHASE_ID: Final = "ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0"
SCHEMA_VERSION: Final = "frontier-entity-ground-truth-real-trust-material-v0"
ENTITY_QUALITY_STATUS: Final = "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
PROMOTION_STATUS: Final = "UNAVAILABLE"
BUNDLE_DOMAIN_SEPARATOR: Final = b"FRONTIER_ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0\x00"
POP_DOMAIN_SEPARATOR: Final = "FRONTIER_ENTITY_GROUND_TRUTH_ADJUDICATOR_POP_V0"
MATERIAL_CORE_DOMAIN_SEPARATOR: Final = b"FRONTIER_ENTITY_GROUND_TRUTH_MATERIAL_CORE_V0\x00"
VALIDITY_AUTHORIZATION_DOMAIN_SEPARATOR: Final = (
    b"FRONTIER_ENTITY_GROUND_TRUTH_VALIDITY_AUTHORIZATION_V0\x00"
)
ED25519_PUBLIC_KEY_BYTES: Final = 32
ED25519_SIGNATURE_BYTES: Final = 64
SAFE_INTEGER_MAX: Final = (1 << 53) - 1

JsonObject = dict[str, Any]

_REQUIRED_TOP_LEVEL_FIELDS: Final = {
    "schema_version",
    "bundle_id",
    "created_at",
    "identity_attestation_authority",
    "adjudicator_identity_key_bindings",
    "service_sealing_verification_object",
    "durability_publication_verification_object",
    "role_controller_attestations",
    "origin_provenance_manifest",
    "revocation_policy",
    "expiry_policy",
    "rotation_lineage",
    "validity_state",
    "bundle_digest",
}
_REQUIRED_CONTROLLER_ROLES: Final = {
    "ADJUDICATOR_1",
    "ADJUDICATOR_2",
    "SERVICE_SEALING",
    "DURABILITY_PUBLICATION",
    "IDENTITY_ATTESTATION_AUTHORITY",
}
_PARENT_RELATIONS: Final = {
    "MIRROR_OF",
    "SYNDICATED_FROM",
    "REPUBLISHED_FROM",
    "DERIVED_FROM",
    "CANONICAL_SOURCE",
}
_FORBIDDEN_SECRET_KEYS: Final = {
    "private_key",
    "private_key_material",
    "secret_key",
    "secret",
    "seed",
    "mnemonic",
    "recovery_key",
    "signing_token",
    "service_secret",
}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class MaterialCandidateStatus(StrEnum):
    ACCEPT_CANDIDATE = "ACCEPT_CANDIDATE"
    REJECT = "REJECT"


class OfflineVerificationBackend(Protocol):
    """Verification adapter supplied by the caller; it must perform no network I/O."""

    def verify_ed25519(self, public_key: bytes, message: bytes, signature: bytes) -> bool: ...

    def verify_external_attestation(
        self,
        *,
        kind: str,
        verification_material: bytes,
        payload: JsonObject,
        proof: JsonObject,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class MaterialCandidateValidation:
    status: MaterialCandidateStatus
    required_action: str
    real_trust_authority: bool = False
    real_label_collection_authorized: bool = False
    candidate_quality_evaluation_authorized: bool = False
    promotion_authorized: bool = False
    entity_quality: str = ENTITY_QUALITY_STATUS
    promotion_status: str = PROMOTION_STATUS
    derived_origin_roots: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()


def _reject(*violations: str) -> MaterialCandidateValidation:
    return MaterialCandidateValidation(
        status=MaterialCandidateStatus.REJECT,
        required_action="REPAIR_MATERIAL_CANDIDATE",
        violations=tuple(violations),
    )


def _accept(roots: set[str]) -> MaterialCandidateValidation:
    return MaterialCandidateValidation(
        status=MaterialCandidateStatus.ACCEPT_CANDIDATE,
        required_action="FREEZE_REAL_EXTERNAL_MATERIAL_IN_SEPARATE_AUTHORIZED_PHASE",
        derived_origin_roots=tuple(sorted(roots)),
    )


def _object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return cast(JsonObject, value)


def _array(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def _strict_ascii_jcs_subset(value: object) -> None:
    """Restrict inputs to a subset whose repo canonical JSON equals RFC8785/JCS bytes."""

    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError("integer outside RFC8785 safe subset")
        return
    if isinstance(value, str):
        if not value.isascii():
            raise ValueError("non-ASCII string outside frozen JCS-safe subset")
        return
    if isinstance(value, float):
        raise ValueError("binary float forbidden in frozen JCS-safe subset")
    if isinstance(value, list):
        for item in cast(list[object], value):
            _strict_ascii_jcs_subset(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str) or not key.isascii():
                raise ValueError("non-ASCII or non-string object key")
            _strict_ascii_jcs_subset(item)
        return
    raise ValueError(f"unsupported JCS-safe value: {type(value).__name__}")


def jcs_safe_bytes(value: object) -> bytes:
    _strict_ascii_jcs_subset(value)
    try:
        return canonical_json_bytes(value)
    except CanonicalizationError as exc:
        raise ValueError("candidate is not canonicalizable") from exc


def sha256_digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def object_digest(value: object) -> str:
    return sha256_digest_bytes(jcs_safe_bytes(value))


def bundle_payload(bundle: JsonObject) -> JsonObject:
    return {
        key: value for key, value in bundle.items() if key not in {"bundle_id", "bundle_digest"}
    }


def candidate_bundle_digest(bundle: JsonObject) -> str:
    payload = bundle_payload(bundle)
    return sha256_digest_bytes(BUNDLE_DOMAIN_SEPARATOR + jcs_safe_bytes(payload))


def derive_bundle_id(bundle_digest: str) -> str:
    if not _DIGEST_RE.fullmatch(bundle_digest):
        raise ValueError("invalid bundle digest")
    return "egt-real-trust-v0:" + bundle_digest.removeprefix("sha256:")


def _decode_base64url(value: object, *, exact_bytes: int | None = None) -> bytes | None:
    if not isinstance(value, str) or not value or "=" in value or not value.isascii():
        return None
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except ValueError, binascii.Error:
        return None
    if exact_bytes is not None and len(raw) != exact_bytes:
        return None
    return raw


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return parsed.tzinfo is UTC


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _contains_forbidden_marker(value: object) -> bool:
    if isinstance(value, str):
        upper = value.upper()
        return upper.startswith(("TEST_ONLY_", "PLACEHOLDER_", "EXAMPLE_"))
    if isinstance(value, list):
        return any(_contains_forbidden_marker(item) for item in cast(list[object], value))
    if isinstance(value, dict):
        return any(
            _contains_forbidden_marker(key) or _contains_forbidden_marker(item)
            for key, item in cast(dict[object, object], value).items()
        )
    return False


def _contains_secret_field(value: object) -> bool:
    if isinstance(value, list):
        return any(_contains_secret_field(item) for item in cast(list[object], value))
    if not isinstance(value, dict):
        return False
    for key, item in cast(dict[object, object], value).items():
        if isinstance(key, str) and key.lower() in _FORBIDDEN_SECRET_KEYS:
            return True
        if _contains_secret_field(item):
            return True
    return False


def _verification_object(
    value: object,
    *,
    expected_role: str,
) -> tuple[bytes, str, str] | None:
    obj = _object(value)
    if obj is None or set(obj) != {
        "role",
        "public_key_b64u",
        "public_key_sha256",
        "controller_commitment",
    }:
        return None
    if obj.get("role") != expected_role or not _valid_digest(obj.get("controller_commitment")):
        return None
    public_key = _decode_base64url(
        obj.get("public_key_b64u"),
        exact_bytes=ED25519_PUBLIC_KEY_BYTES,
    )
    fingerprint = obj.get("public_key_sha256")
    if public_key is None or fingerprint != sha256_digest_bytes(public_key):
        return None
    return public_key, cast(str, fingerprint), cast(str, obj["controller_commitment"])


def _identity_authority(value: object) -> tuple[bytes, str, str] | None:
    obj = _object(value)
    if obj is None or set(obj) != {
        "scheme_id",
        "verification_material_b64u",
        "verification_material_sha256",
        "controller_commitment",
    }:
        return None
    scheme_id = obj.get("scheme_id")
    if not isinstance(scheme_id, str) or not scheme_id or not scheme_id.isascii():
        return None
    material = _decode_base64url(obj.get("verification_material_b64u"))
    fingerprint = obj.get("verification_material_sha256")
    controller = obj.get("controller_commitment")
    if (
        material is None
        or fingerprint != sha256_digest_bytes(material)
        or not _valid_digest(controller)
    ):
        return None
    return material, scheme_id, cast(str, controller)


def pop_message(binding: JsonObject) -> bytes:
    payload = {
        "phase_id": PHASE_ID,
        "subject_commitment": binding["subject_commitment"],
        "adjudicator_public_key_sha256": binding["public_key_sha256"],
        "identity_attestation_digest": binding["identity_attestation_digest"],
        "proof_challenge_nonce": binding["proof_challenge_nonce_b64u"],
    }
    return POP_DOMAIN_SEPARATOR.encode("ascii") + jcs_safe_bytes(payload)


def _validate_adjudicators(
    bundle: JsonObject,
    *,
    identity_material: bytes,
    identity_scheme: str,
    backend: OfflineVerificationBackend,
) -> tuple[set[str], set[bytes], dict[str, str]] | None:
    raw = _array(bundle.get("adjudicator_identity_key_bindings"))
    if raw is None or len(raw) != 2:
        return None

    expected_roles = ["ADJUDICATOR_1", "ADJUDICATOR_2"]
    subjects: set[str] = set()
    keys: set[bytes] = set()
    controllers: dict[str, str] = {}
    for raw_binding, expected_role in zip(raw, expected_roles, strict=True):
        binding = _object(raw_binding)
        if binding is None or set(binding) != {
            "role",
            "subject_commitment",
            "public_key_b64u",
            "public_key_sha256",
            "controller_commitment",
            "identity_attestation",
            "identity_attestation_digest",
            "proof_challenge_nonce_b64u",
            "proof_of_possession_signature_b64u",
        }:
            return None
        if binding.get("role") != expected_role:
            return None
        subject = binding.get("subject_commitment")
        controller = binding.get("controller_commitment")
        if not _valid_digest(subject) or not _valid_digest(controller):
            return None
        public_key = _decode_base64url(
            binding.get("public_key_b64u"),
            exact_bytes=ED25519_PUBLIC_KEY_BYTES,
        )
        if public_key is None or binding.get("public_key_sha256") != sha256_digest_bytes(
            public_key
        ):
            return None
        attestation = _object(binding.get("identity_attestation"))
        if attestation is None or set(attestation) != {"payload", "proof"}:
            return None
        payload = _object(attestation.get("payload"))
        proof = _object(attestation.get("proof"))
        if payload is None or proof is None:
            return None
        if payload != {
            "role": "ADJUDICATOR",
            "subject_commitment": subject,
            "adjudicator_public_key_sha256": binding.get("public_key_sha256"),
        }:
            return None
        if binding.get("identity_attestation_digest") != object_digest(attestation):
            return None
        if not backend.verify_external_attestation(
            kind="HUMAN_IDENTITY",
            verification_material=identity_material,
            payload={"scheme_id": identity_scheme, **payload},
            proof=proof,
        ):
            return None
        nonce = _decode_base64url(binding.get("proof_challenge_nonce_b64u"))
        signature = _decode_base64url(
            binding.get("proof_of_possession_signature_b64u"),
            exact_bytes=ED25519_SIGNATURE_BYTES,
        )
        if nonce is None or len(nonce) < 16 or signature is None:
            return None
        if not backend.verify_ed25519(public_key, pop_message(binding), signature):
            return None
        subjects.add(cast(str, subject))
        keys.add(public_key)
        controllers[expected_role] = cast(str, controller)

    if len(subjects) != 2 or len(keys) != 2 or len(set(controllers.values())) != 2:
        return None
    return subjects, keys, controllers


def _validate_controller_attestations(
    bundle: JsonObject,
    *,
    expected_bindings: dict[str, tuple[str, str]],
    backend: OfflineVerificationBackend,
) -> bool:
    raw = _array(bundle.get("role_controller_attestations"))
    if raw is None or len(raw) != len(_REQUIRED_CONTROLLER_ROLES):
        return False
    seen: set[str] = set()
    for item in raw:
        obj = _object(item)
        if obj is None or set(obj) != {
            "role",
            "controller_commitment",
            "verification_material_b64u",
            "verification_material_sha256",
            "attestation",
            "attestation_digest",
        }:
            return False
        role = obj.get("role")
        controller = obj.get("controller_commitment")
        if (
            not isinstance(role, str)
            or role not in _REQUIRED_CONTROLLER_ROLES
            or not _valid_digest(controller)
        ):
            return False
        role_str = role
        expected = expected_bindings.get(role_str)
        if expected is None or role_str in seen or expected[0] != controller:
            return False
        material = _decode_base64url(obj.get("verification_material_b64u"))
        if material is None or obj.get("verification_material_sha256") != sha256_digest_bytes(
            material
        ):
            return False
        attestation = _object(obj.get("attestation"))
        if attestation is None or set(attestation) != {"payload", "proof"}:
            return False
        payload = _object(attestation.get("payload"))
        proof = _object(attestation.get("proof"))
        if (
            payload
            != {
                "role": role_str,
                "controller_commitment": controller,
                "verification_material_sha256": expected[1],
            }
            or proof is None
        ):
            return False
        if obj.get("attestation_digest") != object_digest(attestation):
            return False
        if not backend.verify_external_attestation(
            kind="ROLE_CONTROLLER",
            verification_material=material,
            payload=cast(JsonObject, payload),
            proof=proof,
        ):
            return False
        seen.add(role_str)
    return seen == _REQUIRED_CONTROLLER_ROLES


def provenance_node_id(node: JsonObject) -> str:
    payload = {key: value for key, value in node.items() if key != "node_id"}
    return object_digest(payload)


def _validate_provenance(
    manifest_value: object,
    *,
    backend: OfflineVerificationBackend,
) -> set[str] | None:
    manifest = _object(manifest_value)
    if manifest is None or set(manifest) != {"nodes", "evidence_bindings", "manifest_digest"}:
        return None
    if manifest.get("manifest_digest") != object_digest(
        {"nodes": manifest.get("nodes"), "evidence_bindings": manifest.get("evidence_bindings")}
    ):
        return None
    raw_nodes = _array(manifest.get("nodes"))
    raw_bindings = _array(manifest.get("evidence_bindings"))
    if raw_nodes is None or raw_bindings is None or not raw_nodes or not raw_bindings:
        return None

    nodes: dict[str, JsonObject] = {}
    for raw_node in raw_nodes:
        node = _object(raw_node)
        if node is None or set(node) != {
            "node_id",
            "content_digest",
            "parents",
            "root_verification_material_b64u",
            "root_verification_material_sha256",
            "root_attestation",
            "root_attestation_digest",
        }:
            return None
        node_id = node.get("node_id")
        if not _valid_digest(node_id) or not _valid_digest(node.get("content_digest")):
            return None
        if node_id != provenance_node_id(node) or node_id in nodes:
            return None
        parents = _array(node.get("parents"))
        if parents is None:
            return None
        if not parents:
            root_material = _decode_base64url(node.get("root_verification_material_b64u"))
            if root_material is None or node.get(
                "root_verification_material_sha256"
            ) != sha256_digest_bytes(root_material):
                return None
            root_attestation = _object(node.get("root_attestation"))
            if root_attestation is None or set(root_attestation) != {"payload", "proof"}:
                return None
            root_payload = _object(root_attestation.get("payload"))
            root_proof = _object(root_attestation.get("proof"))
            if (
                root_payload
                != {
                    "content_digest": node.get("content_digest"),
                    "terminal_upstream": True,
                }
                or root_proof is None
            ):
                return None
            if node.get("root_attestation_digest") != object_digest(root_attestation):
                return None
            if not backend.verify_external_attestation(
                kind="PROVENANCE_ROOT",
                verification_material=root_material,
                payload=cast(JsonObject, root_payload),
                proof=root_proof,
            ):
                return None
        elif any(
            node.get(name) is not None
            for name in (
                "root_verification_material_b64u",
                "root_verification_material_sha256",
                "root_attestation",
                "root_attestation_digest",
            )
        ):
            return None
        nodes[cast(str, node_id)] = node

    for child_id, node in nodes.items():
        parents = cast(list[object], node["parents"])
        for raw_edge in parents:
            edge = _object(raw_edge)
            if edge is None or set(edge) != {
                "parent_node_id",
                "relation",
                "verification_material_b64u",
                "verification_material_sha256",
                "attestation",
                "attestation_digest",
            }:
                return None
            parent_id = edge.get("parent_node_id")
            relation = edge.get("relation")
            if (
                not isinstance(parent_id, str)
                or parent_id not in nodes
                or not isinstance(relation, str)
                or relation not in _PARENT_RELATIONS
            ):
                return None
            material = _decode_base64url(edge.get("verification_material_b64u"))
            if material is None or edge.get("verification_material_sha256") != sha256_digest_bytes(
                material
            ):
                return None
            attestation = _object(edge.get("attestation"))
            if attestation is None or set(attestation) != {"payload", "proof"}:
                return None
            payload = _object(attestation.get("payload"))
            proof = _object(attestation.get("proof"))
            if (
                payload
                != {
                    "child_content_digest": node.get("content_digest"),
                    "parent_node_id": parent_id,
                    "relation": relation,
                }
                or proof is None
            ):
                return None
            if edge.get("attestation_digest") != object_digest(attestation):
                return None
            if not backend.verify_external_attestation(
                kind="PROVENANCE_EDGE",
                verification_material=material,
                payload=cast(JsonObject, payload),
                proof=proof,
            ):
                return None

    visiting: set[str] = set()
    memo: dict[str, set[str]] = {}

    def roots(node_id: str) -> set[str] | None:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            return None
        visiting.add(node_id)
        parents = cast(list[object], nodes[node_id]["parents"])
        if not parents:
            result = {node_id}
        else:
            result: set[str] = set()
            for raw_edge in parents:
                edge = cast(JsonObject, raw_edge)
                parent_roots = roots(cast(str, edge["parent_node_id"]))
                if parent_roots is None:
                    return None
                result.update(parent_roots)
        visiting.remove(node_id)
        memo[node_id] = result
        return result

    evidence_ids: set[str] = set()
    all_roots: set[str] = set()
    for raw_binding in raw_bindings:
        binding = _object(raw_binding)
        if binding is None or set(binding) != {"evidence_id", "node_id"}:
            return None
        evidence_id = binding.get("evidence_id")
        node_id = binding.get("node_id")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id
            or not isinstance(node_id, str)
            or node_id not in nodes
        ):
            return None
        if evidence_id in evidence_ids:
            return None
        derived = roots(cast(str, node_id))
        if derived is None:
            return None
        evidence_ids.add(evidence_id)
        all_roots.update(derived)
    if len(all_roots) < 2:
        return None
    return all_roots


def validity_state_digest(value: JsonObject) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key
        not in {
            "state_digest",
            "material_core_digest",
            "service_sealing_signature_b64u",
            "durability_signature_b64u",
        }
    }
    return object_digest(payload)


def material_core_digest(bundle: JsonObject) -> str:
    payload = bundle_payload(bundle)
    state = _object(payload.get("validity_state"))
    if state is None:
        raise ValueError("validity state missing from material core")
    state_copy = {
        key: item
        for key, item in state.items()
        if key
        not in {
            "material_core_digest",
            "service_sealing_signature_b64u",
            "durability_signature_b64u",
        }
    }
    payload = {**payload, "validity_state": state_copy}
    return sha256_digest_bytes(MATERIAL_CORE_DOMAIN_SEPARATOR + jcs_safe_bytes(payload))


def validity_authorization_message(state: JsonObject) -> bytes:
    payload = {
        "material_core_digest": state["material_core_digest"],
        "state_digest": state["state_digest"],
        "sequence": state["sequence"],
    }
    return VALIDITY_AUTHORIZATION_DOMAIN_SEPARATOR + jcs_safe_bytes(payload)


def _validate_time_and_validity(
    bundle: JsonObject,
    *,
    as_of: datetime,
    service_key: bytes,
    durability_key: bytes,
    backend: OfflineVerificationBackend,
) -> bool:
    created_at = bundle.get("created_at")
    expiry = _object(bundle.get("expiry_policy"))
    revocation = _object(bundle.get("revocation_policy"))
    state = _object(bundle.get("validity_state"))
    if not _valid_timestamp(created_at) or expiry is None or revocation is None or state is None:
        return False
    if set(expiry) != {"valid_from", "valid_until", "unknown_expiry_fails_closed"}:
        return False
    if set(revocation) != {"unknown_state_fails_closed", "authenticated_validity_state_required"}:
        return False
    if expiry.get("unknown_expiry_fails_closed") is not True:
        return False
    if revocation != {
        "unknown_state_fails_closed": True,
        "authenticated_validity_state_required": True,
    }:
        return False
    valid_from = expiry.get("valid_from")
    valid_until = expiry.get("valid_until")
    if not _valid_timestamp(valid_from) or not _valid_timestamp(valid_until):
        return False
    if set(state) != {
        "state",
        "sequence",
        "valid_from",
        "valid_until",
        "state_digest",
        "material_core_digest",
        "service_sealing_signature_b64u",
        "durability_signature_b64u",
    }:
        return False
    if state.get("state") != "ACTIVE" or state.get("sequence") != 0:
        return False
    if state.get("valid_from") != valid_from or state.get("valid_until") != valid_until:
        return False
    if state.get("state_digest") != validity_state_digest(state):
        return False
    try:
        expected_core_digest = material_core_digest(bundle)
    except ValueError:
        return False
    if state.get("material_core_digest") != expected_core_digest:
        return False
    service_signature = _decode_base64url(
        state.get("service_sealing_signature_b64u"),
        exact_bytes=ED25519_SIGNATURE_BYTES,
    )
    durability_signature = _decode_base64url(
        state.get("durability_signature_b64u"),
        exact_bytes=ED25519_SIGNATURE_BYTES,
    )
    if service_signature is None or durability_signature is None:
        return False
    authorization_message = validity_authorization_message(state)
    if not backend.verify_ed25519(service_key, authorization_message, service_signature):
        return False
    if not backend.verify_ed25519(
        durability_key,
        authorization_message,
        durability_signature,
    ):
        return False
    start = _timestamp(cast(str, valid_from))
    end = _timestamp(cast(str, valid_until))
    created = _timestamp(cast(str, created_at))
    return start <= created <= as_of.astimezone(UTC) < end


def validate_real_trust_material_candidate(
    bundle: object,
    *,
    expected_current_authority_head_digest: str,
    backend: OfflineVerificationBackend,
    as_of: datetime,
) -> MaterialCandidateValidation:
    """Validate one candidate without granting any scientific or collection authority."""

    obj = _object(bundle)
    if obj is None:
        return _reject("bundle-shape")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        return _reject("as-of-must-be-timezone-aware")
    if set(obj) != _REQUIRED_TOP_LEVEL_FIELDS:
        return _reject("bundle-field-set")
    try:
        jcs_safe_bytes(obj)
    except ValueError:
        return _reject("bundle-jcs-safe-subset")
    if _contains_secret_field(obj):
        return _reject("secret-material-present")
    if _contains_forbidden_marker(obj):
        return _reject("synthetic-placeholder-or-example-material")
    if obj.get("schema_version") != SCHEMA_VERSION:
        return _reject("schema-version")
    if not _valid_digest(expected_current_authority_head_digest):
        return _reject("expected-current-head-shape")

    digest = candidate_bundle_digest(obj)
    if obj.get("bundle_digest") != digest:
        return _reject("bundle-digest")
    if obj.get("bundle_id") != derive_bundle_id(digest):
        return _reject("bundle-id")
    if expected_current_authority_head_digest != digest:
        return _reject("stale-or-unpinned-current-head")

    identity = _identity_authority(obj.get("identity_attestation_authority"))
    if identity is None:
        return _reject("identity-attestation-authority")
    identity_material, identity_scheme, identity_controller = identity

    adjudicators = _validate_adjudicators(
        obj,
        identity_material=identity_material,
        identity_scheme=identity_scheme,
        backend=backend,
    )
    if adjudicators is None:
        return _reject("adjudicator-identity-key-binding-or-pop")
    _, adjudicator_keys, adjudicator_controllers = adjudicators

    service = _verification_object(
        obj.get("service_sealing_verification_object"),
        expected_role="SERVICE_SEALING",
    )
    durability = _verification_object(
        obj.get("durability_publication_verification_object"),
        expected_role="DURABILITY_PUBLICATION",
    )
    if service is None or durability is None:
        return _reject("service-or-durability-verification-object")
    service_key, _, service_controller = service
    durability_key, _, durability_controller = durability
    all_keys = {*adjudicator_keys, service_key, durability_key, identity_material}
    if len(all_keys) != 5:
        return _reject("verification-material-reuse-across-roles")

    adjudicator_bindings = cast(list[JsonObject], obj["adjudicator_identity_key_bindings"])
    expected_bindings = {
        "ADJUDICATOR_1": (
            adjudicator_controllers["ADJUDICATOR_1"],
            cast(str, adjudicator_bindings[0]["public_key_sha256"]),
        ),
        "ADJUDICATOR_2": (
            adjudicator_controllers["ADJUDICATOR_2"],
            cast(str, adjudicator_bindings[1]["public_key_sha256"]),
        ),
        "SERVICE_SEALING": (service_controller, service[1]),
        "DURABILITY_PUBLICATION": (durability_controller, durability[1]),
        "IDENTITY_ATTESTATION_AUTHORITY": (
            identity_controller,
            sha256_digest_bytes(identity_material),
        ),
    }
    if len({controller for controller, _ in expected_bindings.values()}) != 5:
        return _reject("controller-reuse-across-roles")
    if not _validate_controller_attestations(
        obj,
        expected_bindings=expected_bindings,
        backend=backend,
    ):
        return _reject("controller-attestation")

    roots = _validate_provenance(obj.get("origin_provenance_manifest"), backend=backend)
    if roots is None:
        return _reject("origin-provenance-independence")

    rotation = _object(obj.get("rotation_lineage"))
    if rotation != {
        "sequence": 0,
        "predecessor_bundle_digest": None,
        "supersession_statement": None,
    }:
        return _reject("non-genesis-rotation-fails-closed")
    if not _validate_time_and_validity(
        obj,
        as_of=as_of,
        service_key=service_key,
        durability_key=durability_key,
        backend=backend,
    ):
        return _reject("expiry-revocation-or-validity-state")

    return _accept(roots)
