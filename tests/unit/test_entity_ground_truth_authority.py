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
EXPECTED_CORPUS_BLOB = "c922306ce09c5db18c09f9d33f6ce21301252026"
EXPECTED_REGISTRY = "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
EXPECTED_CASE_IDS = {f"EGT-{i:03d}" for i in range(1, 25)}

EXPECTED_REDACTIONS = [
    "native_ids",
    "canonical_url",
    "entity_name",
    "entity_type",
    "source_item_key",
    "ALIAS_OF relation",
    "RENAMED_FROM relation",
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
    assert authority["schema_version"] == "frontier-entity-ground-truth-authority-v0"
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
            "Synthetic hostile protocol cases only; they are not real-world ground-truth labels "
            "and cannot be scored as candidate quality evidence."
        ),
        "path": "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json",
        "schema_version": "frontier-entity-ground-truth-protocol-corpus-v0",
    }
    assert _git_blob_sha1(CORPUS_PATH) == EXPECTED_CORPUS_BLOB
    assert corpus["schema_version"] == "frontier-entity-ground-truth-protocol-corpus-v0"
    assert corpus["phase_id"] == "ENTITY_GROUND_TRUTH_V0"
    assert corpus["case_count"] == 24

    cases = _cases()
    assert set(cases) == EXPECTED_CASE_IDS
    assert {_as_string(case["category"], "category") for case in cases.values()} == (
        EXPECTED_CATEGORIES
    )

    for case_id, case in cases.items():
        expected = _as_object(case["expected"], f"{case_id}.expected")
        assert expected["quality_claim"] is None, case_id
        assert expected["forbidden_claims"] == [], case_id
        assert isinstance(expected["headline_metric_eligible"], bool), case_id
        assert expected["packet_status"] in {"ACCEPT", "REJECT"}, case_id


def test_candidate_feature_surface_is_explicitly_blinded() -> None:
    authority = _load(AUTHORITY_PATH)
    blinding = _as_object(authority["candidate_blinding"], "candidate_blinding")
    assert blinding["candidate_outputs_hidden"] is True
    assert blinding["candidate_reasons_hidden"] is True
    assert blinding["redacted_frontier_fields"] == EXPECTED_REDACTIONS

    for case_id in ("EGT-001", "EGT-002"):
        case = _cases()[case_id]
        input_value = _as_object(case["input"], f"{case_id}.input")
        candidate_blinding = _as_object(
            input_value["candidate_blinding"], f"{case_id}.candidate_blinding"
        )
        assert candidate_blinding and not any(candidate_blinding.values()), case_id


def test_valid_controls_require_human_agreement_and_two_independent_origins() -> None:
    cases = _cases()
    for case_id, expected_label in (
        ("EGT-001", "ADJUDICATED_SAME_ENTITY"),
        ("EGT-002", "ADJUDICATED_DIFFERENT_ENTITY"),
    ):
        case = cases[case_id]
        input_value = _as_object(case["input"], f"{case_id}.input")
        expected = _as_object(case["expected"], f"{case_id}.expected")
        evidence = [
            _as_object(value, "evidence")
            for value in _as_list(input_value["evidence_items"], "evidence_items")
        ]
        adjudicators = [
            _as_object(value, "adjudicator")
            for value in _as_list(input_value["adjudicators"], "adjudicators")
        ]

        assert input_value["label_origin"] == "HUMAN_INDEPENDENT"
        assert input_value["label_bundle_frozen"] is True
        assert input_value["sampling_frozen_before_candidate_scoring"] is True
        assert len(evidence) >= 2
        assert len({_as_string(item["origin_group"], "origin_group") for item in evidence}) >= 2
        assert all(item["candidate_disjoint"] is True for item in evidence)
        assert all(
            _as_string(item["snapshot_digest"], "snapshot_digest").startswith("sha256:")
            for item in evidence
        )
        assert len(adjudicators) == 2
        assert len({_as_string(item["person_key"], "person_key") for item in adjudicators}) == 2
        assert all(item["independent"] is True for item in adjudicators)
        assert all(item["saw_other_label_before_submit"] is False for item in adjudicators)
        assert len({_as_string(item["label"], "label") for item in adjudicators}) == 1
        assert expected["label_status"] == expected_label
        assert expected["headline_metric_eligible"] is True


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
        "offline_packet_validator",
        "offline_blinding_redactor",
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
