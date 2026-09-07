from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_protocol_builder_v2.json"
)
SCHEMA_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_expanded_packet_v2.schema.json"
)
CORPUS_PATH = ROOT / "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v2.json"
V1_AUTHORITY_PATH = (
    ROOT
    / "experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_authority.json"
)
V1_CORPUS_PATH = ROOT / "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json"

EXPECTED_V1_AUTHORITY_BLOB = "4aa25903a9f8ee6d016111bbe48483661f327a79"
EXPECTED_V1_CORPUS_BLOB = "664a86962b73bd1aae11feea25e41adbfbf5899a"


def _load(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _test_mac(key_material: str, payload_digest: str) -> str:
    raw = f"{key_material}:{payload_digest}".encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _signed(
    payload: dict[str, Any],
    key: dict[str, str],
) -> dict[str, Any]:
    payload_digest = _digest(payload)
    return {
        "payload": payload,
        "digest": payload_digest,
        "key_id": key["key_id"],
        "test_mac": _test_mac(key["key_material"], payload_digest),
    }


def _durability_bound(
    payload: dict[str, Any],
    durable_at: str,
    sequence_no: int,
    key: dict[str, str],
) -> dict[str, Any]:
    payload_digest = _digest(payload)
    receipt_payload = {
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


def _expand_case(
    case: dict[str, Any],
    corpus: dict[str, Any],
    spec: dict[str, Any],
    schema_digest: str,
) -> dict[str, Any]:
    base_vectors = cast(dict[str, dict[str, Any]], corpus["base_vectors"])
    base_vector_name = cast(str, case["base_vector"])
    base = copy.deepcopy(base_vectors[base_vector_name])
    evidence_map = cast(dict[str, dict[str, Any]], copy.deepcopy(base["evidence"]))
    boundary = cast(dict[str, str], copy.deepcopy(corpus["candidate_signal_boundary"]))
    signal_classes = list(cast(list[str], spec["candidate_signal_classes_order"]))
    boundary_payload = {
        "signals": boundary,
        "signal_classes": signal_classes,
    }
    boundary_digest = _digest(boundary_payload)

    times = cast(dict[str, str], spec["fixed_times"])
    sequences_fixed = cast(dict[str, int], spec["fixed_sequences"])
    test_mac_spec = cast(dict[str, Any], spec["test_mac"])
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

    mutations = cast(list[dict[str, Any]], case["mutations"])
    for mutation in mutations:
        op = mutation["op"]
        if op == "DROP_EVIDENCE":
            evidence_map.pop(mutation["evidence_id"], None)
        elif op == "LEAK_SIGNAL":
            leaks.extend(mutation["signal_classes"])
        elif op == "SHARE_ORIGIN_ROOT":
            source_id = mutation["source_evidence_id"]
            target_id = mutation["target_evidence_id"]
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
            labels[mutation["adjudicator_index"]] = mutation["label"]
        elif op == "SET_SUBJECT_EQUAL":
            source_index = mutation["source_index"]
            target_index = mutation["target_index"]
            subject_ids[target_index] = subject_ids[source_index]
        elif op == "SET_SUBMISSION_ORIGIN":
            origins[mutation["adjudicator_index"]] = mutation["origin"]
        elif op == "SET_SUBMISSION_SEQUENCE":
            index = mutation["adjudicator_index"]
            sequences[index] = mutation["sequence_no"]
            submitted_ats[index] = mutation["submitted_at"]
        elif op == "SET_SAMPLE_DURABLE_AT":
            sample_durable_at = mutation["durable_at"]
        elif op == "SET_SAMPLE_ROLE":
            sample_role = mutation["sample_role"]
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
            raise AssertionError(f"unknown mutation {op}")

    case_id = case["id"]
    sample_payload = {
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

    evidence_out: list[dict[str, Any]] = []
    rendered_items: list[dict[str, str]] = []
    for evidence_id in sorted(evidence_map):
        evidence = evidence_map[evidence_id]
        raw_snapshot = cast(dict[str, Any], copy.deepcopy(evidence["raw_snapshot"]))
        raw_snapshot_digest: str | None = _digest(raw_snapshot)
        if evidence.get("force_null_raw_snapshot_digest"):
            raw_snapshot_digest = None

        origin_payload = {
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

    rendered_digest = _digest(rendered_items)
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
    redaction_payload = {
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
    rendered_view = {
        "items": rendered_items,
        "digest": rendered_digest,
        "redaction_receipt": _signed(
            redaction_payload,
            keys["redaction"],
        ),
    }

    identity_receipts: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    if not empty_adjudication:
        for index in range(2):
            identity_payload = {
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
                assessments: list[dict[str, Any]] = [
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

            submission_payload = {
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

    unseal_payload = {
        "schema_version": "frontier-entity-ground-truth-unseal-receipt-v2",
        "case_id": case_id,
        "sequence_no": sequences_fixed["unseal"],
        "unsealed_at": times["unseal_at"],
        "submission_digests": [submission["digest"] for submission in submissions],
        "service": "TEST_ONLY_SEALED_SUBMISSION_SERVICE_V2",
        "synthetic_only": True,
    }
    unseal_receipt = _signed(unseal_payload, keys["submission"])

    bundle_payload = {
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
            label_bundle["payload"]["version"] = "synthetic-v2.0.0-mutated"

    return {
        "schema_version": "frontier-entity-ground-truth-expanded-packet-v2",
        "protocol_id": "ENTITY_GROUND_TRUTH_PROTOCOL_V2",
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
        "non_escalation": cast(dict[str, Any], copy.deepcopy(spec["non_escalation"])),
    }


def test_v2_builder_and_schema_are_content_addressed() -> None:
    builder = _load(BUILDER_PATH)
    schema = _load(SCHEMA_PATH)
    corpus = _load(CORPUS_PATH)

    spec_payload = builder["spec_payload"]
    assert _digest(spec_payload) == builder["spec_payload_digest"]
    assert builder["spec_payload_digest"] == (corpus["builder_spec_payload_digest"])
    assert _digest(schema) == corpus["packet_schema_digest"]


def test_v1_artifacts_remain_byte_identical() -> None:
    assert _git_blob_sha1(V1_AUTHORITY_PATH) == EXPECTED_V1_AUTHORITY_BLOB
    assert _git_blob_sha1(V1_CORPUS_PATH) == EXPECTED_V1_CORPUS_BLOB


def test_v2_corpus_preserves_24_attack_categories_and_non_escalation() -> None:
    corpus = _load(CORPUS_PATH)
    assert corpus["case_count"] == 24
    assert len(corpus["cases"]) == 24
    cases = cast(list[dict[str, Any]], corpus["cases"])
    assert len({cast(str, case["category"]) for case in cases}) == 24
    assert corpus["synthetic_only"] is True

    scientific = corpus["scientific_contract"]
    assert scientific["quality_state"] == ("INSUFFICIENT_INDEPENDENT_GROUND_TRUTH")
    forbidden = [
        "runtime_validator_conformance_authorized",
        "real_label_collection_authorized",
        "candidate_quality_evaluation_authorized",
        "candidate_promotion_authorized",
        "canonical_entity_truth_authorized",
    ]
    assert all(scientific[name] is False for name in forbidden)


def test_every_v2_expected_packet_digest_recomputes_independently() -> None:
    builder = _load(BUILDER_PATH)
    schema = _load(SCHEMA_PATH)
    corpus = _load(CORPUS_PATH)
    spec = builder["spec_payload"]
    schema_digest = _digest(schema)

    recomputed: dict[str, str] = {}
    cases = cast(list[dict[str, Any]], corpus["cases"])
    for case in cases:
        packet = _expand_case(case, corpus, spec, schema_digest)
        packet_digest = _digest(packet)
        assert packet_digest == cast(str, case["expected_packet_digest"])
        recomputed[cast(str, case["id"])] = packet_digest

    assert len(recomputed) == corpus["case_count"]
    assert len(set(recomputed.values())) == corpus["case_count"]


def test_test_only_crypto_cannot_be_mistaken_for_real_authority() -> None:
    builder = _load(BUILDER_PATH)
    spec = builder["spec_payload"]
    crypto = spec["test_mac"]

    assert crypto["security_status"] == ("TEST_ONLY_NOT_A_REAL_SIGNATURE_SCHEME")
    assert crypto["real_label_authority"] is False
    for key in crypto["keys"].values():
        assert key["key_id"].startswith("TEST_ONLY_")

    assert spec["non_escalation"]["entity_quality"] == ("INSUFFICIENT_INDEPENDENT_GROUND_TRUTH")
    assert spec["non_escalation"]["real_label_collection_authorized"] is False
