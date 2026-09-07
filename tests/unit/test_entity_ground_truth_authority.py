from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT
    / "experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_authority.json"
)
CORPUS_PATH = ROOT / "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json"

EXPECTED_PARENT = "fbf69ecd9f0bf810011e71e8dd2c1627e0b02011"
EXPECTED_SHADOW_AUTHORITY = "0638aaca0e1025ea256306172712f46b94515bc7"
EXPECTED_CORPUS_BLOB = "664a86962b73bd1aae11feea25e41adbfbf5899a"
EXPECTED_REGISTRY = "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
EXPECTED_CASE_IDS = {f"EGT-{i:03d}" for i in range(1, 25)}

EXPECTED_SIGNAL_BOUNDARY = [
    "candidate_output",
    "candidate_reason",
    "native_ids",
    "canonical_url",
    "entity_name",
    "entity_type",
    "source_item_key",
    "ALIAS_OF",
    "RENAMED_FROM",
]

EXPECTED_CATEGORIES = {
    "valid_same_random",
    "valid_different_random",
    "candidate_output_leak",
    "candidate_reason_leak",
    "native_id_leak",
    "canonical_url_leak",
    "entity_name_leak",
    "entity_type_leak",
    "source_item_key_leak",
    "alias_relation_leak",
    "single_decisive_evidence",
    "mirrored_evidence_not_independent",
    "candidate_derived_evidence",
    "missing_snapshot_digest",
    "adjudicator_disagreement",
    "adjudicator_abstention",
    "same_person_double_vote",
    "adjudicator_sees_peer_label",
    "model_generated_label",
    "candidate_aware_sampling",
    "challenge_sample_not_headline",
    "label_bundle_not_frozen",
    "conflicting_evidence_directions",
    "zero_evaluable_labels_no_quality_claim",
}

EXPECTED_MUTATION_OPS = {
    "EGT-003": ["LEAK_SIGNAL"],
    "EGT-004": ["LEAK_SIGNAL"],
    "EGT-005": ["LEAK_SIGNAL"],
    "EGT-006": ["LEAK_SIGNAL"],
    "EGT-007": ["LEAK_SIGNAL"],
    "EGT-008": ["LEAK_SIGNAL"],
    "EGT-009": ["LEAK_SIGNAL"],
    "EGT-010": ["LEAK_SIGNAL"],
    "EGT-011": ["DROP_EVIDENCE"],
    "EGT-012": ["SHARE_ORIGIN_ROOT"],
    "EGT-013": ["ADD_CANDIDATE_DEPENDENCY"],
    "EGT-014": ["REMOVE_RAW_SNAPSHOT_DIGEST"],
    "EGT-015": ["SET_LABEL"],
    "EGT-016": ["SET_LABEL"],
    "EGT-017": ["SET_SUBJECT_EQUAL"],
    "EGT-018": ["SET_SUBMISSION_SEQUENCE"],
    "EGT-019": ["SET_SUBMISSION_ORIGIN"],
    "EGT-020": ["SET_SAMPLE_DURABLE_AT"],
    "EGT-021": ["SET_SAMPLE_ROLE"],
    "EGT-022": ["MUTATE_LABEL_BUNDLE_AFTER_DIGEST"],
    "EGT-023": ["SET_CONFLICTING_ASSESSMENTS"],
    "EGT-024": ["EMPTY_ADJUDICATION"],
}


def _as_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{name} must be object")
    return cast(dict[str, object], value)


def _as_list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"{name} must be list")
    return cast(list[object], value)


def _as_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{name} must be string")
    return value


def _load(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _as_object(raw, path.name)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()


def _cases() -> dict[str, dict[str, object]]:
    corpus = _load(CORPUS_PATH)
    return {
        _as_string(case["id"], "case.id"): case
        for case in (_as_object(value, "case") for value in _as_list(corpus["cases"], "cases"))
    }


def test_entity_ground_truth_authority_binds_exact_lineage() -> None:
    authority = _load(AUTHORITY_PATH)
    assert authority["schema_version"] == "frontier-entity-ground-truth-authority-v1"
    assert authority["phase_id"] == "ENTITY_GROUND_TRUTH_V0"
    assert authority["authority_state"] == "FROZEN_ENTITY_GROUND_TRUTH_AUTHORITY_CANDIDATE"
    assert authority["parent_main_commit"] == EXPECTED_PARENT

    lineage = _as_object(authority["lineage"], "lineage")
    assert lineage == {
        "selected_entity_candidate": "transparent-entity-hybrid-v0",
        "shadow_evaluation_authority_merge_commit": EXPECTED_SHADOW_AUTHORITY,
        "shadow_evaluation_corpus_blob_sha1": "58c91348a6f81f31d99aadf50a1c32fb22ac0882",
        "shadow_evaluation_implementation_merge_commit": EXPECTED_PARENT,
        "shadow_expected_reports_blob_sha1": "d0fa4e4ff82eeb70f551e4274eb856b5f5e9f3d4",
        "source_registry_digest": EXPECTED_REGISTRY,
    }


def test_protocol_corpus_is_exact_24_case_synthetic_authority() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)
    binding = _as_object(authority["protocol_corpus"], "protocol_corpus")

    assert binding == {
        "case_count": 24,
        "git_blob_sha1": EXPECTED_CORPUS_BLOB,
        "note": (
            "Synthetic hostile protocol vectors only. Their test keys/trust roots and expected "
            "outcomes are not real-world entity ground truth and cannot be counted as candidate "
            "quality evidence."
        ),
        "path": "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json",
        "schema_version": "frontier-entity-ground-truth-protocol-corpus-v1",
    }
    assert _git_blob_sha1(CORPUS_PATH) == EXPECTED_CORPUS_BLOB
    assert corpus["schema_version"] == "frontier-entity-ground-truth-protocol-corpus-v1"
    assert corpus["phase_id"] == "ENTITY_GROUND_TRUTH_V0"
    assert corpus["case_count"] == 24

    cases = _cases()
    assert set(cases) == EXPECTED_CASE_IDS
    assert {_as_string(case["category"], "category") for case in cases.values()} == (
        EXPECTED_CATEGORIES
    )

    packet_digests: set[str] = set()
    for case_id, case in cases.items():
        expected = _as_object(case["expected"], f"{case_id}.expected")
        assert expected["quality_claim"] is None, case_id
        assert expected["forbidden_claims"] == [], case_id
        assert isinstance(expected["headline_metric_eligible"], bool), case_id
        assert expected["packet_status"] in {"ACCEPT", "REJECT"}, case_id
        digest = _as_string(case["expected_packet_digest"], f"{case_id}.expected_packet_digest")
        assert digest.startswith("sha256:"), case_id
        assert digest not in packet_digests, case_id
        packet_digests.add(digest)


def test_candidate_disjointness_is_recomputed_over_exact_direction_neutral_view() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)
    blinding = _as_object(authority["candidate_blinding"], "candidate_blinding")

    assert blinding["candidate_outputs_hidden"] is True
    assert blinding["candidate_reasons_hidden"] is True
    assert blinding["internal_candidate_signal_boundary"] == EXPECTED_SIGNAL_BOUNDARY

    rendered_contract = _as_string(blinding["rendered_view_contract"], "rendered_view_contract")
    redaction_contract = _as_string(
        blinding["redaction_receipt_contract"], "redaction_receipt_contract"
    )
    direction_contract = _as_string(blinding["direction_neutrality"], "direction_neutrality")

    assert "content-addressed" in rendered_contract
    assert "recomputes" in rendered_contract
    assert "cannot declare itself candidate-disjoint" in rendered_contract
    assert "content-addressed redaction receipt" in redaction_contract
    assert "independently rescans" in redaction_contract
    assert "decisive_direction" in direction_contract
    assert "MUST NOT" in direction_contract
    assert "sealed authenticated human submission receipts" in direction_contract

    signal_boundary = _as_object(corpus["candidate_signal_boundary"], "candidate_signal_boundary")
    assert set(signal_boundary) == set(EXPECTED_SIGNAL_BOUNDARY)

    base_vectors = _as_object(corpus["base_vectors"], "base_vectors")
    for vector_name in ("VALID_SAME", "VALID_DIFFERENT"):
        vector = _as_object(base_vectors[vector_name], vector_name)
        evidence = _as_object(vector["evidence"], f"{vector_name}.evidence")
        rendered = json.dumps(
            [
                _as_object(_as_object(item, "evidence")["rendered_fields"], "rendered_fields")
                for item in evidence.values()
            ],
            sort_keys=True,
        )
        assert "decisive_direction" not in rendered
        assert "SAME_ENTITY" not in rendered
        assert "DIFFERENT_ENTITY" not in rendered
        for value in signal_boundary.values():
            if isinstance(value, str):
                assert value not in rendered


def test_valid_base_vectors_require_two_candidate_disjoint_independent_inputs() -> None:
    corpus = _load(CORPUS_PATH)
    base_vectors = _as_object(corpus["base_vectors"], "base_vectors")
    cases = _cases()

    assert cases["EGT-001"]["base_vector"] == "VALID_SAME"
    assert cases["EGT-002"]["base_vector"] == "VALID_DIFFERENT"
    assert cases["EGT-001"]["mutations"] == []
    assert cases["EGT-002"]["mutations"] == []

    for vector_name, expected_label in (
        ("VALID_SAME", "SAME_ENTITY"),
        ("VALID_DIFFERENT", "DIFFERENT_ENTITY"),
    ):
        vector = _as_object(base_vectors[vector_name], vector_name)
        evidence = _as_object(vector["evidence"], f"{vector_name}.evidence")
        labels = [_as_string(value, "label") for value in _as_list(vector["labels"], "labels")]

        assert len(evidence) == 2
        assert (
            len(
                {
                    _as_string(_as_object(item, "evidence")["origin_root_seed"], "origin_root_seed")
                    for item in evidence.values()
                }
            )
            == 2
        )
        for item in evidence.values():
            evidence_item = _as_object(item, "evidence")
            raw_payload = _as_object(evidence_item["raw_payload"], "raw_payload")
            assert raw_payload["candidate_dependency_digests"] == []
            assert _as_string(raw_payload["raw_content_digest"], "raw_content_digest").startswith(
                "sha256:"
            )
        assert labels == [expected_label, expected_label]
        assert vector["sample_role"] == "EVALUATION_RANDOM"


def test_hostile_cases_exercise_the_frozen_repair_surfaces() -> None:
    cases = _cases()
    for case_id, expected_ops in EXPECTED_MUTATION_OPS.items():
        mutations = [
            _as_object(value, f"{case_id}.mutation")
            for value in _as_list(cases[case_id]["mutations"], f"{case_id}.mutations")
        ]
        assert [_as_string(value["op"], "mutation.op") for value in mutations] == expected_ops

    leak_signals: list[str] = []
    for case_id in [f"EGT-{i:03d}" for i in range(3, 11)]:
        mutation = _as_object(_as_list(cases[case_id]["mutations"], "mutations")[0], "mutation")
        leak_signals.extend(
            _as_string(value, "signal_class")
            for value in _as_list(mutation["signal_classes"], "signal_classes")
        )
    assert set(leak_signals) == set(EXPECTED_SIGNAL_BOUNDARY)


def test_origin_independence_is_derived_from_verified_provenance_roots() -> None:
    authority = _load(AUTHORITY_PATH)
    evidence = _as_object(authority["evidence_protocol"], "evidence_protocol")

    assert evidence["immutable_snapshot_required"] is True
    assert evidence["minimum_evidence_items"] == 2
    assert evidence["minimum_verified_distinct_origin_roots"] == 2

    origin_rule = _as_string(evidence["origin_independence_rule"], "origin_independence_rule")
    assert "origin_group strings are forbidden" in origin_rule
    assert "signed immutable origin-provenance manifest" in origin_rule
    assert "approved capture-service trust root" in origin_rule
    assert "root_node_digest" in origin_rule
    assert "collapse all evidence sharing the same verified root" in origin_rule
    assert "EGT-012" in _as_string(evidence["synthetic_mirror_attack"], "synthetic_mirror_attack")


def test_adjudicator_identity_peer_blindness_and_bundle_are_cryptographically_bound() -> None:
    authority = _load(AUTHORITY_PATH)
    adjudication = _as_object(authority["adjudication_protocol"], "adjudication_protocol")
    bundle = _as_object(authority["label_bundle_protocol"], "label_bundle_protocol")

    agreement = _as_string(adjudication["agreement_rule"], "agreement_rule")
    identity = _as_string(adjudication["unique_person_proof"], "unique_person_proof")
    peer = _as_string(adjudication["peer_blindness_proof"], "peer_blindness_proof")

    assert "distinct cryptographically verified unique-person subjects" in agreement
    assert "externally signed unique-person attestation" in identity
    assert "two distinct subject digests" in identity
    assert "arbitrary person_key strings" in identity
    assert "immutable service-signed receipt" in peer
    assert "authoritative sequence" in peer
    assert "signed peer-label-unseal receipt" in peer

    assert bundle["identity"] == "bundle_digest = sha256(canonical_json(exact bundle payload))"
    assert bundle["manifest_fields"] == [
        "bundle_version",
        "sample_manifest_digest",
        "submission_receipt_digests",
        "unseal_receipt_digest",
        "predecessor_bundle_digest",
        "created_at",
    ]
    mutation_rule = _as_string(bundle["mutation_rule"], "mutation_rule")
    assert "different bundle digest" in mutation_rule
    assert "Old and new bundle identities cannot be silently pooled or substituted" in mutation_rule
    assert "exactly one immutable bundle digest" in _as_string(
        bundle["later_evaluation_binding"], "later_evaluation_binding"
    )


def test_random_sample_is_content_addressed_and_durable_before_scoring() -> None:
    authority = _load(AUTHORITY_PATH)
    sample = _as_object(authority["sample_protocol"], "sample_protocol")

    freeze = _as_string(sample["evaluation_random_freeze"], "evaluation_random_freeze")
    assert "content-addressed EVALUATION_RANDOM sample manifest" in freeze
    assert "exact pair IDs" in freeze
    assert "seed commitment" in freeze
    assert "signed durability receipt" in freeze
    assert "strictly before the first candidate scoring receipt" in freeze
    assert sample["post_score_selection"] == "INVALID_PACKET / REJECT_SELECTION_LEAK"
    assert "EGT-020" in _as_string(sample["synthetic_attack"], "synthetic_attack")


def test_synthetic_vectors_and_test_trust_roots_cannot_become_real_gold() -> None:
    authority = _load(AUTHORITY_PATH)
    scientific = _as_object(authority["scientific_boundary"], "scientific_boundary")
    trust = _as_object(authority["trust_root_protocol"], "trust_root_protocol")

    assert scientific["synthetic_vectors_are_quality_evidence"] is False
    assert trust["cryptographic_verification_required"] is True
    assert trust["synthetic_keys_authorized_for_real_labels"] is False
    assert trust["synthetic_keys"] == [
        "TEST_ONLY_ENTITY_GROUND_TRUTH_IDENTITY_KEY_V0",
        "TEST_ONLY_SEALED_SUBMISSION_SERVICE_KEY_V0",
        "TEST_ONLY_ORIGIN_CAPTURE_SERVICE_KEY_V0",
        "TEST_ONLY_REDACTION_SERVICE_KEY_V0",
        "TEST_ONLY_DURABILITY_SERVICE_KEY_V0",
    ]
    real_gate = _as_string(trust["real_collection_gate"], "real_collection_gate")
    assert "Before any real label collection" in real_gate
    assert "separately frozen" in real_gate
    assert "may not be substituted after collection begins" in real_gate


def test_feature_and_candidate_leaks_fail_closed() -> None:
    cases = _cases()
    for case_id in [f"EGT-{i:03d}" for i in range(3, 11)]:
        expected = _as_object(cases[case_id]["expected"], f"{case_id}.expected")
        assert expected["packet_status"] == "REJECT", case_id
        assert expected["label_status"] == "INVALID_PACKET", case_id
        assert expected["headline_metric_eligible"] is False, case_id


def test_evidence_nonindependence_and_mutability_do_not_become_gold() -> None:
    cases = _cases()
    for case_id in ("EGT-011", "EGT-012", "EGT-013", "EGT-014", "EGT-023"):
        expected = _as_object(cases[case_id]["expected"], f"{case_id}.expected")
        assert expected["headline_metric_eligible"] is False, case_id
        assert expected["quality_claim"] is None, case_id

    assert _as_object(cases["EGT-011"]["expected"], "EGT-011.expected")["label_status"] == (
        "ABSTAIN_INSUFFICIENT_EVIDENCE"
    )
    assert _as_object(cases["EGT-012"]["expected"], "EGT-012.expected")["label_status"] == (
        "ABSTAIN_INSUFFICIENT_EVIDENCE"
    )
    assert _as_object(cases["EGT-013"]["expected"], "EGT-013.expected")["packet_status"] == (
        "REJECT"
    )
    assert _as_object(cases["EGT-014"]["expected"], "EGT-014.expected")["packet_status"] == (
        "REJECT"
    )
    assert _as_object(cases["EGT-023"]["expected"], "EGT-023.expected")["label_status"] == (
        "ABSTAIN_CONFLICTING_EVIDENCE"
    )


def test_adjudicator_contamination_abstains_or_fails_closed() -> None:
    cases = _cases()
    assert _as_object(cases["EGT-015"]["expected"], "EGT-015.expected")["label_status"] == (
        "ABSTAIN_DISAGREEMENT"
    )
    assert _as_object(cases["EGT-016"]["expected"], "EGT-016.expected")["label_status"] == (
        "ABSTAIN_INSUFFICIENT_EVIDENCE"
    )
    for case_id in ("EGT-017", "EGT-018"):
        expected = _as_object(cases[case_id]["expected"], f"{case_id}.expected")
        assert expected["packet_status"] == "REJECT", case_id
        assert expected["label_status"] == "INVALID_PACKET", case_id


def test_model_gold_and_selection_leak_are_invalid() -> None:
    cases = _cases()
    for case_id in ("EGT-019", "EGT-020", "EGT-022"):
        expected = _as_object(cases[case_id]["expected"], f"{case_id}.expected")
        assert expected["packet_status"] == "REJECT", case_id
        assert expected["label_status"] == "INVALID_PACKET", case_id
        assert expected["headline_metric_eligible"] is False, case_id


def test_challenge_labels_are_diagnostic_only_and_zero_labels_make_no_quality_claim() -> None:
    cases = _cases()
    challenge = _as_object(cases["EGT-021"]["expected"], "EGT-021.expected")
    assert challenge["packet_status"] == "ACCEPT"
    assert challenge["label_status"] == "ADJUDICATED_SAME_ENTITY"
    assert challenge["headline_metric_eligible"] is False
    assert challenge["required_action"] == "ACCEPT_DIAGNOSTIC_ONLY"

    zero = _as_object(cases["EGT-024"]["expected"], "EGT-024.expected")
    assert zero["label_status"] == "NO_EVALUABLE_LABEL"
    assert zero["headline_metric_eligible"] is False
    assert zero["quality_claim"] is None
    assert zero["required_action"] == "NO_QUALITY_CLAIM"


def test_merge_authority_does_not_upgrade_quality_or_grant_runtime_truth() -> None:
    authority = _load(AUTHORITY_PATH)
    scientific = _as_object(authority["scientific_boundary"], "scientific_boundary")
    assert scientific["current_entity_quality_status"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert scientific["quality_status_after_authority_merge"] == (
        "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    )
    assert scientific["quality_evaluation_authorized"] is False
    assert scientific["promotion_authorized"] is False

    implementation = _as_object(
        authority["implementation_authority_on_merge"], "implementation_authority_on_merge"
    )
    permitted = {key for key, value in implementation.items() if value is True}
    assert permitted == {
        "offline_packet_expander_validator",
        "offline_blinding_redaction_validator",
        "offline_adjudication_receipt_validator",
        "protocol_hostile_tests",
    }
    for forbidden in (
        "real_world_label_generation_by_frontier",
        "candidate_quality_metrics",
        "candidate_quality_pass_fail",
        "candidate_promotion",
        "persistence",
        "migration",
        "worker_scheduling",
        "api",
        "terminal",
        "source_registry_change",
        "canonical_entity_authority",
    ):
        assert implementation[forbidden] is False
