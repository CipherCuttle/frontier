"""Pure offline ENTITY_GROUND_TRUTH_PROTOCOL_V2 expansion and validation."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

PHASE_ID: Final = "ENTITY_GROUND_TRUTH_PROTOCOL_V2_OFFLINE_VALIDATOR"
PROTOCOL_ID: Final = "ENTITY_GROUND_TRUTH_PROTOCOL_V2"
PACKET_SCHEMA_VERSION: Final = "frontier-entity-ground-truth-expanded-packet-v2"
ENTITY_QUALITY_STATUS: Final = "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
PROMOTION_STATUS: Final = "UNAVAILABLE"
TEST_CRYPTO_STATUS: Final = "TEST_ONLY_NOT_A_REAL_SIGNATURE_SCHEME"

JsonObject = dict[str, Any]


class ProtocolV2DefinitionError(ValueError):
    """Raised when frozen v2 declarative inputs drift or are malformed."""


class PacketStatus(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class LabelStatus(StrEnum):
    ADJUDICATED_SAME_ENTITY = "ADJUDICATED_SAME_ENTITY"
    ADJUDICATED_DIFFERENT_ENTITY = "ADJUDICATED_DIFFERENT_ENTITY"
    ABSTAIN_INSUFFICIENT_EVIDENCE = "ABSTAIN_INSUFFICIENT_EVIDENCE"
    ABSTAIN_DISAGREEMENT = "ABSTAIN_DISAGREEMENT"
    ABSTAIN_CONFLICTING_EVIDENCE = "ABSTAIN_CONFLICTING_EVIDENCE"
    NO_EVALUABLE_LABEL = "NO_EVALUABLE_LABEL"
    INVALID_PACKET = "INVALID_PACKET"


@dataclass(frozen=True, slots=True)
class PacketValidation:
    packet_status: PacketStatus
    label_status: LabelStatus
    required_action: str
    headline_metric_eligible: bool
    quality_claim: None = None
    forbidden_claims: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CorpusCaseRun:
    case_id: str
    packet_digest: str
    expected_packet_digest: str
    digest_matches: bool
    validation: PacketValidation


def canonical_protocol_bytes(value: object) -> bytes:
    """Serialize exactly as frozen by the v2 builder specification."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def protocol_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_protocol_bytes(value)).hexdigest()


def _test_mac(key_material: str, payload_digest: str) -> str:
    raw = f"{key_material}:{payload_digest}".encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _signed(payload: JsonObject, key: dict[str, str]) -> JsonObject:
    payload_digest = protocol_digest(payload)
    return {
        "payload": payload,
        "digest": payload_digest,
        "key_id": key["key_id"],
        "test_mac": _test_mac(key["key_material"], payload_digest),
    }


def _durability_bound(
    payload: JsonObject,
    durable_at: str,
    sequence_no: int,
    key: dict[str, str],
) -> JsonObject:
    payload_digest = protocol_digest(payload)
    receipt_payload: JsonObject = {
        "bound_digest": payload_digest,
        "durable_at": durable_at,
        "sequence_no": sequence_no,
        "service": "TEST_ONLY_DURABILITY_SERVICE_V2",
    }
    return {
        "payload": payload,
        "digest": payload_digest,
        "durability_receipt": _signed(receipt_payload, key),
    }


def _definition_parts(
    builder: JsonObject,
    schema: JsonObject,
    corpus: JsonObject,
) -> tuple[JsonObject, str]:
    spec = cast(JsonObject, builder.get("spec_payload"))
    stored_spec_digest = builder.get("spec_payload_digest")
    if not isinstance(stored_spec_digest, str):
        raise ProtocolV2DefinitionError("builder spec payload digest is missing")
    if protocol_digest(spec) != stored_spec_digest:
        raise ProtocolV2DefinitionError("builder spec payload digest mismatch")
    if corpus.get("builder_spec_payload_digest") != stored_spec_digest:
        raise ProtocolV2DefinitionError("corpus builder spec binding mismatch")

    schema_digest = protocol_digest(schema)
    if corpus.get("packet_schema_digest") != schema_digest:
        raise ProtocolV2DefinitionError("corpus packet schema binding mismatch")

    if spec.get("protocol_id") != PROTOCOL_ID or spec.get("synthetic_only") is not True:
        raise ProtocolV2DefinitionError("builder protocol identity drift")
    if corpus.get("synthetic_only") is not True:
        raise ProtocolV2DefinitionError("corpus must remain synthetic-only")

    signal_classes = spec.get("candidate_signal_classes_order")
    candidate_boundary = corpus.get("candidate_signal_boundary")
    if not isinstance(signal_classes, list) or not all(
        isinstance(value, str) for value in signal_classes
    ):
        raise ProtocolV2DefinitionError("candidate signal class definition drift")
    if not isinstance(candidate_boundary, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in candidate_boundary.items()
    ):
        raise ProtocolV2DefinitionError("candidate signal boundary definition drift")
    if set(candidate_boundary) != set(cast(list[str], signal_classes)):
        raise ProtocolV2DefinitionError("candidate signal boundary coverage drift")

    crypto = cast(JsonObject, spec.get("test_mac"))
    if crypto.get("security_status") != TEST_CRYPTO_STATUS:
        raise ProtocolV2DefinitionError("test crypto security status drift")
    if crypto.get("real_label_authority") is not False:
        raise ProtocolV2DefinitionError("test crypto cannot authorize real labels")
    keys = cast(dict[str, dict[str, str]], crypto.get("keys"))
    if not keys:
        raise ProtocolV2DefinitionError("test crypto keys are missing")
    if any(not key.get("key_id", "").startswith("TEST_ONLY_") for key in keys.values()):
        raise ProtocolV2DefinitionError("non-test key id entered synthetic protocol")

    non_escalation = cast(JsonObject, spec.get("non_escalation"))
    if non_escalation.get("entity_quality") != ENTITY_QUALITY_STATUS:
        raise ProtocolV2DefinitionError("entity quality state drift")
    if non_escalation.get("real_label_collection_authorized") is not False:
        raise ProtocolV2DefinitionError("real label collection authority leaked")
    if non_escalation.get("candidate_quality_pass_fail_authorized") is not False:
        raise ProtocolV2DefinitionError("candidate quality authority leaked")
    if non_escalation.get("candidate_promotion_authorized") is not False:
        raise ProtocolV2DefinitionError("promotion authority leaked")
    return spec, schema_digest


def expand_v2_case(
    case: JsonObject,
    *,
    corpus: JsonObject,
    builder: JsonObject,
    schema: JsonObject,
) -> JsonObject:
    """Expand one frozen synthetic v2 case without reading external state."""

    spec, schema_digest = _definition_parts(builder, schema, corpus)
    base_vectors = cast(dict[str, JsonObject], corpus["base_vectors"])
    base_vector_name = cast(str, case["base_vector"])
    base = copy.deepcopy(base_vectors[base_vector_name])
    evidence_map = cast(dict[str, JsonObject], copy.deepcopy(base["evidence"]))
    boundary = cast(dict[str, str], copy.deepcopy(corpus["candidate_signal_boundary"]))
    signal_classes = list(cast(list[str], spec["candidate_signal_classes_order"]))
    boundary_payload: JsonObject = {
        "signals": boundary,
        "signal_classes": signal_classes,
    }
    boundary_digest = protocol_digest(boundary_payload)

    times = cast(dict[str, str], spec["fixed_times"])
    sequences_fixed = cast(dict[str, int], spec["fixed_sequences"])
    test_mac_spec = cast(JsonObject, spec["test_mac"])
    keys = cast(dict[str, dict[str, str]], test_mac_spec["keys"])

    sample_role = cast(str, base["sample_role"])
    sample_durable_at = times["sample_durable_at"]
    labels = list(cast(list[str], base["labels"]))
    pair_id = cast(str, base["pair_id"])
    default_assessment = cast(str, base["default_assessment"])
    subject_ids = [
        "human-subject-synthetic-A",
        "human-subject-synthetic-B",
    ]
    origins = ["HUMAN", "HUMAN"]
    sequences = [
        sequences_fixed["submission_0"],
        sequences_fixed["submission_1"],
    ]
    submitted_ats = [
        times["submission_0_at"],
        times["submission_1_at"],
    ]
    assessments_mode = "DEFAULT"
    empty_adjudication = False
    leaks: list[str] = []

    mutations = cast(list[JsonObject], case["mutations"])
    for mutation in mutations:
        op = cast(str, mutation["op"])
        if op == "DROP_EVIDENCE":
            evidence_map.pop(cast(str, mutation["evidence_id"]), None)
        elif op == "LEAK_SIGNAL":
            leaks.extend(cast(list[str], mutation["signal_classes"]))
        elif op == "SHARE_ORIGIN_ROOT":
            source_id = cast(str, mutation["source_evidence_id"])
            target_id = cast(str, mutation["target_evidence_id"])
            evidence_map[target_id]["origin_root_id"] = evidence_map[source_id]["origin_root_id"]
        elif op == "ADD_CANDIDATE_DEPENDENCY":
            evidence_id = cast(str, mutation["evidence_id"])
            dependencies = cast(
                list[str], evidence_map[evidence_id]["candidate_dependency_digests"]
            )
            dependencies.append(boundary_digest)
        elif op == "REMOVE_RAW_SNAPSHOT_DIGEST":
            evidence_id = cast(str, mutation["evidence_id"])
            evidence_map[evidence_id]["force_null_raw_snapshot_digest"] = True
        elif op == "SET_LABEL":
            index = cast(int, mutation["adjudicator_index"])
            labels[index] = cast(str, mutation["label"])
        elif op == "SET_SUBJECT_EQUAL":
            source_index = cast(int, mutation["source_index"])
            target_index = cast(int, mutation["target_index"])
            subject_ids[target_index] = subject_ids[source_index]
        elif op == "SET_SUBMISSION_ORIGIN":
            index = cast(int, mutation["adjudicator_index"])
            origins[index] = cast(str, mutation["origin"])
        elif op == "SET_SUBMISSION_SEQUENCE":
            index = cast(int, mutation["adjudicator_index"])
            sequences[index] = cast(int, mutation["sequence_no"])
            submitted_ats[index] = cast(str, mutation["submitted_at"])
        elif op == "SET_SAMPLE_DURABLE_AT":
            sample_durable_at = cast(str, mutation["durable_at"])
        elif op == "SET_SAMPLE_ROLE":
            sample_role = cast(str, mutation["sample_role"])
        elif op == "SET_CONFLICTING_ASSESSMENTS":
            assessments_mode = "CONFLICTING"
            labels = [
                "ABSTAIN_CONFLICTING_EVIDENCE",
                "ABSTAIN_CONFLICTING_EVIDENCE",
            ]
        elif op == "EMPTY_ADJUDICATION":
            evidence_map = {}
            empty_adjudication = True
            labels = []
        elif op == "MUTATE_LABEL_BUNDLE_AFTER_DIGEST":
            pass
        else:
            raise ProtocolV2DefinitionError(f"unknown frozen mutation: {op}")

    case_id = cast(str, case["id"])
    sample_payload: JsonObject = {
        "schema_version": "frontier-entity-ground-truth-sample-manifest-v2",
        "manifest_id": f"SAMPLE-MANIFEST-{case_id}",
        "case_id": case_id,
        "pair_id": pair_id,
        "sample_role": sample_role,
        "selected_at": times["sample_selected_at"],
        "durable_at": sample_durable_at,
        "first_candidate_score_at": times["first_candidate_score_at"],
        "candidate_aware_selection": False,
        "synthetic_only": True,
    }
    sample_manifest = _durability_bound(
        sample_payload,
        sample_durable_at,
        sequences_fixed["sample_durability"],
        keys["durability"],
    )

    evidence_out: list[JsonObject] = []
    rendered_items: list[dict[str, str]] = []
    for evidence_id in sorted(evidence_map):
        evidence = evidence_map[evidence_id]
        raw_snapshot = cast(JsonObject, copy.deepcopy(evidence["raw_snapshot"]))
        raw_snapshot_digest: str | None = protocol_digest(raw_snapshot)
        if evidence.get("force_null_raw_snapshot_digest"):
            raw_snapshot_digest = None

        origin_payload: JsonObject = {
            "schema_version": "frontier-entity-ground-truth-origin-receipt-v2",
            "evidence_id": evidence_id,
            "origin_root_id": cast(str, evidence["origin_root_id"]),
            "captured_at": cast(str, raw_snapshot["captured_at"]),
            "service": "TEST_ONLY_ORIGIN_CAPTURE_SERVICE_V2",
            "synthetic_only": True,
        }
        evidence_out.append(
            {
                "evidence_id": evidence_id,
                "raw_snapshot": raw_snapshot,
                "raw_snapshot_digest": raw_snapshot_digest,
                "candidate_dependency_digests": list(
                    cast(list[str], evidence["candidate_dependency_digests"])
                ),
                "origin_receipt": _signed(origin_payload, keys["origin"]),
            }
        )
        rendered_fields = cast(dict[str, str], evidence["rendered_fields"])
        rendered_items.append(
            {
                "evidence_id": evidence_id,
                "title": rendered_fields["title"],
                "excerpt": rendered_fields["excerpt"],
            }
        )

    if leaks and rendered_items:
        for signal_class in leaks:
            rendered_items[0]["excerpt"] += f"\nLEAK::{signal_class}={boundary[signal_class]}"

    rendered_digest = protocol_digest(rendered_items)
    rendered_text = json.dumps(
        rendered_items,
        sort_keys=True,
        ensure_ascii=False,
    )
    matched_signal_classes = [
        signal_class
        for signal_class in signal_classes
        if str(boundary[signal_class]) in rendered_text
    ]
    redaction_payload: JsonObject = {
        "schema_version": "frontier-entity-ground-truth-redaction-receipt-v2",
        "candidate_signal_boundary_digest": boundary_digest,
        "rendered_view_digest": rendered_digest,
        "scanned_signal_classes": signal_classes,
        "matched_signal_classes": matched_signal_classes,
        "direction_neutral_fields_only": True,
        "issued_at": times["identity_issued_at"],
        "sequence_no": sequences_fixed["redaction_receipt"],
        "service": "TEST_ONLY_REDACTION_SERVICE_V2",
        "synthetic_only": True,
    }
    rendered_view: JsonObject = {
        "items": rendered_items,
        "digest": rendered_digest,
        "redaction_receipt": _signed(
            redaction_payload,
            keys["redaction"],
        ),
    }

    identity_receipts: list[JsonObject] = []
    submissions: list[JsonObject] = []
    if not empty_adjudication:
        for index in range(2):
            identity_payload: JsonObject = {
                "schema_version": "frontier-entity-ground-truth-identity-receipt-v2",
                "subject_id": subject_ids[index],
                "verified_unique_person": True,
                "human": True,
                "issued_at": times["identity_issued_at"],
                "verifier": "TEST_ONLY_UNIQUE_PERSON_VERIFIER_V2",
                "synthetic_only": True,
            }
            identity_receipts.append(_signed(identity_payload, keys["identity"]))

        for index in range(2):
            if assessments_mode == "CONFLICTING":
                assessments: list[JsonObject] = [
                    {
                        "evidence_id": evidence_id,
                        "assessment": (
                            "SUPPORTS_SAME" if evidence_id == "E1" else "SUPPORTS_DIFFERENT"
                        ),
                    }
                    for evidence_id in sorted(evidence_map)
                ]
            else:
                assessments = [
                    {
                        "evidence_id": evidence_id,
                        "assessment": default_assessment,
                    }
                    for evidence_id in sorted(evidence_map)
                ]

            submission_payload: JsonObject = {
                "schema_version": "frontier-entity-ground-truth-sealed-submission-v2",
                "submission_id": f"{case_id}-SUB-{index + 1}",
                "subject_id": subject_ids[index],
                "origin": origins[index],
                "sequence_no": sequences[index],
                "submitted_at": submitted_ats[index],
                "label": labels[index],
                "assessments": assessments,
                "peer_label_visible": False,
                "synthetic_only": True,
            }
            submissions.append(_signed(submission_payload, keys["submission"]))

    unseal_payload: JsonObject = {
        "schema_version": "frontier-entity-ground-truth-unseal-receipt-v2",
        "case_id": case_id,
        "sequence_no": sequences_fixed["unseal"],
        "unsealed_at": times["unseal_at"],
        "submission_digests": [submission["digest"] for submission in submissions],
        "service": "TEST_ONLY_SEALED_SUBMISSION_SERVICE_V2",
        "synthetic_only": True,
    }
    unseal_receipt = _signed(unseal_payload, keys["submission"])

    bundle_payload: JsonObject = {
        "schema_version": "frontier-entity-ground-truth-label-bundle-v2",
        "version": "synthetic-v2.0.0",
        "predecessor_digest": None,
        "case_id": case_id,
        "sample_manifest_digest": sample_manifest["digest"],
        "submission_digests": [submission["digest"] for submission in submissions],
        "unseal_receipt_digest": unseal_receipt["digest"],
        "labels": [submission["payload"]["label"] for submission in submissions],
        "durable_at": times["bundle_durable_at"],
        "synthetic_only": True,
    }
    label_bundle = _durability_bound(
        bundle_payload,
        times["bundle_durable_at"],
        sequences_fixed["bundle_durability"],
        keys["durability"],
    )

    for mutation in mutations:
        if mutation["op"] == "MUTATE_LABEL_BUNDLE_AFTER_DIGEST":
            cast(JsonObject, label_bundle["payload"])["version"] = "synthetic-v2.0.0-mutated"

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "case_id": case_id,
        "synthetic_only": True,
        "builder_spec_payload_digest": corpus["builder_spec_payload_digest"],
        "packet_schema_digest": schema_digest,
        "internal_candidate_signal_boundary": {
            "payload": boundary_payload,
            "digest": boundary_digest,
        },
        "sample_manifest": sample_manifest,
        "evidence": evidence_out,
        "rendered_adjudication_view": rendered_view,
        "adjudication": {
            "identity_receipts": identity_receipts,
            "submissions": submissions,
            "unseal_receipt": unseal_receipt,
        },
        "label_bundle": label_bundle,
        "non_escalation": cast(JsonObject, copy.deepcopy(spec["non_escalation"])),
    }


def _signed_valid(value: object, key: dict[str, str]) -> bool:
    if not isinstance(value, dict):
        return False
    obj = cast(JsonObject, value)
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return False
    payload_obj = cast(JsonObject, payload)
    digest = protocol_digest(payload_obj)
    return (
        obj.get("digest") == digest
        and obj.get("key_id") == key["key_id"]
        and obj.get("test_mac") == _test_mac(key["key_material"], digest)
    )


def _durability_valid(value: object, key: dict[str, str]) -> bool:
    if not isinstance(value, dict):
        return False
    obj = cast(JsonObject, value)
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return False
    payload_obj = cast(JsonObject, payload)
    digest = protocol_digest(payload_obj)
    receipt = obj.get("durability_receipt")
    if obj.get("digest") != digest or not _signed_valid(receipt, key):
        return False
    receipt_obj = cast(JsonObject, receipt)
    receipt_payload = cast(JsonObject, receipt_obj["payload"])
    return receipt_payload.get("bound_digest") == digest and receipt_payload.get(
        "durable_at"
    ) == payload_obj.get("durable_at")


def _reject(action: str, *violations: str) -> PacketValidation:
    return PacketValidation(
        packet_status=PacketStatus.REJECT,
        label_status=LabelStatus.INVALID_PACKET,
        required_action=action,
        headline_metric_eligible=False,
        violations=tuple(violations),
    )


def validate_v2_packet(
    packet: JsonObject,
    *,
    builder: JsonObject,
    schema: JsonObject,
    corpus: JsonObject,
) -> PacketValidation:
    """Validate bindings and derive the v2 adjudication outcome from packet content."""

    spec, schema_digest = _definition_parts(builder, schema, corpus)
    test_mac_spec = cast(JsonObject, spec["test_mac"])
    keys = cast(dict[str, dict[str, str]], test_mac_spec["keys"])

    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        return _reject("REJECT_PROTOCOL_DRIFT", "packet-schema-version")
    if packet.get("protocol_id") != PROTOCOL_ID or packet.get("synthetic_only") is not True:
        return _reject("REJECT_PROTOCOL_DRIFT", "protocol-identity")
    if packet.get("builder_spec_payload_digest") != builder["spec_payload_digest"]:
        return _reject("REJECT_PROTOCOL_DRIFT", "builder-binding")
    if packet.get("packet_schema_digest") != schema_digest:
        return _reject("REJECT_PROTOCOL_DRIFT", "schema-binding")
    if packet.get("non_escalation") != spec["non_escalation"]:
        return _reject("REJECT_PROTOCOL_DRIFT", "non-escalation-drift")

    case_id = packet.get("case_id")
    if not isinstance(case_id, str):
        return _reject("REJECT_PROTOCOL_DRIFT", "case-id")

    boundary_obj = packet.get("internal_candidate_signal_boundary")
    if not isinstance(boundary_obj, dict):
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-shape")
    boundary = cast(JsonObject, boundary_obj)
    boundary_payload = boundary.get("payload")
    if not isinstance(boundary_payload, dict):
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-payload")
    boundary_payload_obj = cast(JsonObject, boundary_payload)
    if boundary.get("digest") != protocol_digest(boundary_payload_obj):
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-digest")
    signals = boundary_payload_obj.get("signals")
    signal_classes = boundary_payload_obj.get("signal_classes")
    if not isinstance(signals, dict) or not isinstance(signal_classes, list):
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-content")
    signals_obj = cast(dict[str, str], signals)
    signal_class_list = cast(list[str], signal_classes)
    frozen_signals = cast(dict[str, str], corpus["candidate_signal_boundary"])
    if signal_class_list != cast(list[str], spec["candidate_signal_classes_order"]):
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-order")
    if signals_obj != frozen_signals:
        return _reject("REJECT_PROTOCOL_DRIFT", "candidate-boundary-values")
    boundary_digest = cast(str, boundary["digest"])

    sample_manifest_obj = packet.get("sample_manifest")
    if not _durability_valid(sample_manifest_obj, keys["durability"]):
        return _reject("REJECT_SELECTION_LEAK", "sample-manifest-binding")
    sample_manifest = cast(JsonObject, sample_manifest_obj)
    sample_payload = cast(JsonObject, sample_manifest["payload"])
    if sample_payload.get("case_id") != case_id:
        return _reject("REJECT_SELECTION_LEAK", "sample-case-binding")
    sample_role = sample_payload.get("sample_role")
    if sample_role not in {"EVALUATION_RANDOM", "CHALLENGE_ONLY"}:
        return _reject("REJECT_SELECTION_LEAK", "sample-role")
    if sample_payload.get("candidate_aware_selection") is not False:
        return _reject("REJECT_SELECTION_LEAK", "candidate-aware-selection")
    if sample_role == "EVALUATION_RANDOM":
        durable_at = sample_payload.get("durable_at")
        first_score = sample_payload.get("first_candidate_score_at")
        if not isinstance(durable_at, str) or not isinstance(first_score, str):
            return _reject("REJECT_SELECTION_LEAK", "sample-time-shape")
        if durable_at >= first_score:
            return _reject("REJECT_SELECTION_LEAK", "sample-not-durable-before-scoring")

    evidence_obj = packet.get("evidence")
    if not isinstance(evidence_obj, list):
        return _reject("REJECT_PROTOCOL_DRIFT", "evidence-shape")
    evidence = cast(list[JsonObject], evidence_obj)
    verified_origin_roots: list[str] = []
    evidence_ids: list[str] = []
    origin_root_by_evidence_id: dict[str, str] = {}
    for item in evidence:
        evidence_id = item.get("evidence_id")
        raw_snapshot = item.get("raw_snapshot")
        raw_digest = item.get("raw_snapshot_digest")
        if not isinstance(evidence_id, str):
            return _reject("REJECT_UNBOUND_EVIDENCE", "evidence-id-shape")
        if evidence_id in origin_root_by_evidence_id:
            return _reject("REJECT_UNBOUND_EVIDENCE", "duplicate-evidence-id")
        if not isinstance(raw_snapshot, dict) or not isinstance(raw_digest, str):
            return _reject("REJECT_UNBOUND_EVIDENCE", "raw-snapshot-unbound")
        if protocol_digest(cast(JsonObject, raw_snapshot)) != raw_digest:
            return _reject("REJECT_UNBOUND_EVIDENCE", "raw-snapshot-digest")
        dependencies = item.get("candidate_dependency_digests")
        if not isinstance(dependencies, list):
            return _reject(
                "REJECT_NONINDEPENDENT_EVIDENCE",
                "candidate-dependency-shape",
            )
        if boundary_digest in cast(list[str], dependencies):
            return _reject(
                "REJECT_NONINDEPENDENT_EVIDENCE",
                "candidate-derived-evidence",
            )

        origin_receipt = item.get("origin_receipt")
        if not _signed_valid(origin_receipt, keys["origin"]):
            return _reject("REJECT_UNBOUND_EVIDENCE", "origin-receipt-binding")
        receipt = cast(JsonObject, origin_receipt)
        origin_payload = cast(JsonObject, receipt["payload"])
        if origin_payload.get("evidence_id") != evidence_id:
            return _reject("REJECT_UNBOUND_EVIDENCE", "origin-evidence-binding")
        if origin_payload.get("captured_at") != cast(JsonObject, raw_snapshot).get("captured_at"):
            return _reject("REJECT_UNBOUND_EVIDENCE", "origin-capture-binding")
        origin_root = origin_payload.get("origin_root_id")
        if not isinstance(origin_root, str):
            return _reject("REJECT_UNBOUND_EVIDENCE", "origin-root-shape")
        evidence_ids.append(evidence_id)
        verified_origin_roots.append(origin_root)
        origin_root_by_evidence_id[evidence_id] = origin_root

    rendered_obj = packet.get("rendered_adjudication_view")
    if not isinstance(rendered_obj, dict):
        return _reject("REJECT_PROTOCOL_DRIFT", "rendered-view-shape")
    rendered = cast(JsonObject, rendered_obj)
    items = rendered.get("items")
    if not isinstance(items, list):
        return _reject("REJECT_PROTOCOL_DRIFT", "rendered-items-shape")
    rendered_items = cast(list[JsonObject], items)
    if any(set(item) != {"evidence_id", "title", "excerpt"} for item in rendered_items):
        return _reject("REJECT_PROTOCOL_DRIFT", "direction-neutral-view-shape")
    if [item.get("evidence_id") for item in rendered_items] != evidence_ids:
        return _reject("REJECT_PROTOCOL_DRIFT", "rendered-evidence-binding")
    rendered_digest = protocol_digest(rendered_items)
    if rendered.get("digest") != rendered_digest:
        return _reject("REJECT_PROTOCOL_DRIFT", "rendered-view-digest")
    redaction_receipt = rendered.get("redaction_receipt")
    if not _signed_valid(redaction_receipt, keys["redaction"]):
        return _reject("REJECT_PROTOCOL_DRIFT", "redaction-receipt-binding")
    redaction = cast(JsonObject, redaction_receipt)
    redaction_payload = cast(JsonObject, redaction["payload"])
    if redaction_payload.get("candidate_signal_boundary_digest") != boundary_digest:
        return _reject("REJECT_PROTOCOL_DRIFT", "redaction-boundary-binding")
    if redaction_payload.get("rendered_view_digest") != rendered_digest:
        return _reject("REJECT_PROTOCOL_DRIFT", "redaction-view-binding")
    if redaction_payload.get("direction_neutral_fields_only") is not True:
        return _reject("REJECT_PROTOCOL_DRIFT", "direction-neutrality-claim")

    rendered_text = json.dumps(rendered_items, sort_keys=True, ensure_ascii=False)
    matched = [
        signal_class
        for signal_class in signal_class_list
        if frozen_signals[signal_class] in rendered_text
    ]
    if redaction_payload.get("scanned_signal_classes") != signal_class_list:
        return _reject("REJECT_PROTOCOL_DRIFT", "redaction-scan-boundary")
    if redaction_payload.get("matched_signal_classes") != matched:
        return _reject("REJECT_PROTOCOL_DRIFT", "redaction-match-receipt")
    if matched:
        if any(name in {"candidate_output", "candidate_reason"} for name in matched):
            return _reject("REJECT_CANDIDATE_LEAK", *matched)
        return _reject("REJECT_FEATURE_LEAK", *matched)

    adjudication_obj = packet.get("adjudication")
    if not isinstance(adjudication_obj, dict):
        return _reject("REJECT_PROTOCOL_DRIFT", "adjudication-shape")
    adjudication = cast(JsonObject, adjudication_obj)
    identities_obj = adjudication.get("identity_receipts")
    submissions_obj = adjudication.get("submissions")
    unseal_receipt = adjudication.get("unseal_receipt")
    if not isinstance(identities_obj, list) or not isinstance(submissions_obj, list):
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "adjudication-list-shape")
    identities = cast(list[JsonObject], identities_obj)
    submissions = cast(list[JsonObject], submissions_obj)
    if not _signed_valid(unseal_receipt, keys["submission"]):
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "unseal-binding")
    unseal = cast(JsonObject, unseal_receipt)
    unseal_payload = cast(JsonObject, unseal["payload"])
    if unseal_payload.get("case_id") != case_id:
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "unseal-case-binding")
    submission_digests = [submission.get("digest") for submission in submissions]
    if unseal_payload.get("submission_digests") != submission_digests:
        return _reject(
            "REJECT_ADJUDICATOR_NONINDEPENDENCE",
            "unseal-submission-binding",
        )

    label_bundle_obj = packet.get("label_bundle")
    if not _durability_valid(label_bundle_obj, keys["durability"]):
        return _reject("REJECT_MUTABLE_LABEL", "label-bundle-binding")
    label_bundle = cast(JsonObject, label_bundle_obj)
    bundle_payload = cast(JsonObject, label_bundle["payload"])
    if bundle_payload.get("case_id") != case_id:
        return _reject("REJECT_MUTABLE_LABEL", "bundle-case-binding")
    if bundle_payload.get("sample_manifest_digest") != sample_manifest.get("digest"):
        return _reject("REJECT_MUTABLE_LABEL", "bundle-sample-binding")
    if bundle_payload.get("submission_digests") != submission_digests:
        return _reject("REJECT_MUTABLE_LABEL", "bundle-submission-binding")
    if bundle_payload.get("unseal_receipt_digest") != unseal.get("digest"):
        return _reject("REJECT_MUTABLE_LABEL", "bundle-unseal-binding")

    if not identities and not submissions:
        if evidence:
            return _reject(
                "REJECT_ADJUDICATOR_NONINDEPENDENCE",
                "labels-empty-with-evidence",
            )
        if bundle_payload.get("labels") != []:
            return _reject("REJECT_MUTABLE_LABEL", "empty-bundle-labels")
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.NO_EVALUABLE_LABEL,
            required_action="NO_QUALITY_CLAIM",
            headline_metric_eligible=False,
        )

    if len(identities) != 2 or len(submissions) != 2:
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "adjudicator-count")

    identity_subjects: list[str] = []
    for receipt in identities:
        if not _signed_valid(receipt, keys["identity"]):
            return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "identity-binding")
        identity_payload = cast(JsonObject, receipt["payload"])
        if (
            identity_payload.get("verified_unique_person") is not True
            or identity_payload.get("human") is not True
        ):
            return _reject(
                "REJECT_ADJUDICATOR_NONINDEPENDENCE",
                "identity-not-verified-human",
            )
        subject_id = identity_payload.get("subject_id")
        if not isinstance(subject_id, str):
            return _reject(
                "REJECT_ADJUDICATOR_NONINDEPENDENCE",
                "identity-subject-shape",
            )
        identity_subjects.append(subject_id)
    if len(set(identity_subjects)) != 2:
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "duplicate-human-subject")

    unseal_sequence = unseal_payload.get("sequence_no")
    unsealed_at = unseal_payload.get("unsealed_at")
    if not isinstance(unseal_sequence, int) or not isinstance(unsealed_at, str):
        return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "unseal-order-shape")

    labels: list[str] = []
    submission_subjects: list[str] = []
    assessment_maps: list[dict[str, str]] = []
    evidence_id_set = set(evidence_ids)
    for submission in submissions:
        if not _signed_valid(submission, keys["submission"]):
            return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "submission-binding")
        payload = cast(JsonObject, submission["payload"])
        if payload.get("origin") != "HUMAN":
            return _reject("REJECT_NONHUMAN_GROUND_TRUTH", "submission-origin")
        if payload.get("peer_label_visible") is not False:
            return _reject("REJECT_ADJUDICATOR_NONINDEPENDENCE", "peer-label-visible")
        sequence_no = payload.get("sequence_no")
        submitted_at = payload.get("submitted_at")
        if (
            not isinstance(sequence_no, int)
            or not isinstance(submitted_at, str)
            or sequence_no >= unseal_sequence
            or submitted_at >= unsealed_at
        ):
            return _reject(
                "REJECT_ADJUDICATOR_NONINDEPENDENCE",
                "submission-after-unseal",
            )
        subject_id = payload.get("subject_id")
        label = payload.get("label")
        assessments_obj = payload.get("assessments")
        if not isinstance(subject_id, str) or not isinstance(label, str):
            return _reject(
                "REJECT_ADJUDICATOR_NONINDEPENDENCE",
                "submission-content-shape",
            )
        if not isinstance(assessments_obj, list):
            return _reject("REJECT_PROTOCOL_DRIFT", "assessment-list-shape")
        assessment_map: dict[str, str] = {}
        for assessment in assessments_obj:
            if not isinstance(assessment, dict):
                return _reject("REJECT_PROTOCOL_DRIFT", "assessment-item-shape")
            assessment_obj = cast(JsonObject, assessment)
            assessment_evidence_id = assessment_obj.get("evidence_id")
            assessment_direction = assessment_obj.get("assessment")
            if (
                not isinstance(assessment_evidence_id, str)
                or assessment_evidence_id not in evidence_id_set
                or assessment_evidence_id in assessment_map
            ):
                return _reject("REJECT_PROTOCOL_DRIFT", "assessment-evidence-binding")
            if assessment_direction not in {"SUPPORTS_SAME", "SUPPORTS_DIFFERENT"}:
                return _reject("REJECT_PROTOCOL_DRIFT", "assessment-direction")
            assessment_map[assessment_evidence_id] = cast(str, assessment_direction)
        if set(assessment_map) != evidence_id_set:
            return _reject("REJECT_PROTOCOL_DRIFT", "assessment-evidence-coverage")
        submission_subjects.append(subject_id)
        labels.append(label)
        assessment_maps.append(assessment_map)

    if set(submission_subjects) != set(identity_subjects):
        return _reject(
            "REJECT_ADJUDICATOR_NONINDEPENDENCE",
            "submission-identity-binding",
        )
    if bundle_payload.get("labels") != labels:
        return _reject("REJECT_MUTABLE_LABEL", "bundle-label-binding")

    if len(set(verified_origin_roots)) < 2:
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.ABSTAIN_INSUFFICIENT_EVIDENCE,
            required_action="ABSTAIN",
            headline_metric_eligible=False,
            violations=("insufficient-independent-origin-roots",),
        )

    assessment_directions = {
        direction for assessment_map in assessment_maps for direction in assessment_map.values()
    }
    if assessment_directions == {"SUPPORTS_SAME", "SUPPORTS_DIFFERENT"}:
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.ABSTAIN_CONFLICTING_EVIDENCE,
            required_action="ABSTAIN",
            headline_metric_eligible=False,
        )

    if any(label == "ABSTAIN_CONFLICTING_EVIDENCE" for label in labels):
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.ABSTAIN_CONFLICTING_EVIDENCE,
            required_action="ABSTAIN",
            headline_metric_eligible=False,
        )
    if any(label == "ABSTAIN_INSUFFICIENT_EVIDENCE" for label in labels):
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.ABSTAIN_INSUFFICIENT_EVIDENCE,
            required_action="ABSTAIN",
            headline_metric_eligible=False,
        )
    if labels[0] != labels[1]:
        return PacketValidation(
            packet_status=PacketStatus.ACCEPT,
            label_status=LabelStatus.ABSTAIN_DISAGREEMENT,
            required_action="ABSTAIN",
            headline_metric_eligible=False,
        )

    if labels[0] == "SAME_ENTITY":
        label_status = LabelStatus.ADJUDICATED_SAME_ENTITY
        required_assessment = "SUPPORTS_SAME"
    elif labels[0] == "DIFFERENT_ENTITY":
        label_status = LabelStatus.ADJUDICATED_DIFFERENT_ENTITY
        required_assessment = "SUPPORTS_DIFFERENT"
    else:
        return _reject("REJECT_PROTOCOL_DRIFT", "unknown-adjudication-label")
    if assessment_directions != {required_assessment}:
        return _reject("REJECT_PROTOCOL_DRIFT", "label-assessment-inconsistency")

    headline = sample_role == "EVALUATION_RANDOM"
    return PacketValidation(
        packet_status=PacketStatus.ACCEPT,
        label_status=label_status,
        required_action="ACCEPT_LABEL" if headline else "ACCEPT_DIAGNOSTIC_ONLY",
        headline_metric_eligible=headline,
    )


def execute_v2_corpus(
    *,
    corpus: JsonObject,
    builder: JsonObject,
    schema: JsonObject,
) -> tuple[CorpusCaseRun, ...]:
    """Expand and semantically validate every frozen v2 synthetic case."""

    _definition_parts(builder, schema, corpus)
    cases = cast(list[JsonObject], corpus.get("cases"))
    declared_count = corpus.get("case_count")
    if not isinstance(declared_count, int) or declared_count != len(cases):
        raise ProtocolV2DefinitionError("corpus case count mismatch")

    runs: list[CorpusCaseRun] = []
    for case in cases:
        packet = expand_v2_case(
            case,
            corpus=corpus,
            builder=builder,
            schema=schema,
        )
        packet_digest = protocol_digest(packet)
        expected_digest = cast(str, case["expected_packet_digest"])
        runs.append(
            CorpusCaseRun(
                case_id=cast(str, case["id"]),
                packet_digest=packet_digest,
                expected_packet_digest=expected_digest,
                digest_matches=packet_digest == expected_digest,
                validation=validate_v2_packet(
                    packet,
                    builder=builder,
                    schema=schema,
                    corpus=corpus,
                ),
            )
        )
    return tuple(runs)
