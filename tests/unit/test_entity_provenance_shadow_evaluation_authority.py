from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/shadow_evaluation_authority.json"
)
CORPUS_PATH = ROOT / "fixtures/entity_provenance/shadow_evaluation_corpus_v0.json"
BRIDGE_CORPUS_PATH = ROOT / "fixtures/entity_provenance/bridge_corpus_v0.json"

EXPECTED_PARENT = "6e43ca0d588785c9d19a33a6dcdcd26944e43700"
EXPECTED_BRIDGE_AUTHORITY = "0027ffcba7ab0d62be8101424ba8e5ecc09cb28c"
EXPECTED_LAB_MERGE = "23cf10e0d65883c7b82356cf1bd18d9c56215604"
EXPECTED_LAB_CORPUS = "sha256:04ac150abe4356ef06a6fda75429d5873d8dd519e79e29f5c5e2853f4432a386"
EXPECTED_BRIDGE_CORPUS = "sha256:34d1c75a7999f0338ae81add88e358d444f0bbd58d59696c08bb7ae0fbaf209f"
EXPECTED_EVAL_CORPUS_BLOB = "58c91348a6f81f31d99aadf50a1c32fb22ac0882"
EXPECTED_REGISTRY = "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
EXPECTED_CASE_IDS = {f"EPSE-{i:03d}" for i in range(1, 25)}

PERMITTED_IMPLEMENTATION_AUTHORITY = {
    "deterministic_shadow_report",
    "hostile_shadow_tests",
    "offline_shadow_evaluator",
}

REQUIRED_EXPECTED_FIELDS = {
    "integrity_status",
    "entity_decision",
    "provenance_decision",
    "pit_eligible_observation_count",
    "native_id_signal_count",
    "malformed_identity_field_count",
    "ignored_future_observation_count",
    "ignored_future_relation_count",
    "eligible_weak_relation_count",
    "direct_derivation_evidence_count",
    "source_coverage",
    "entity_quality_status",
    "provenance_quality_status",
    "promotion_status",
    "forbidden_inference_claims",
    "quality_pass_fail_claim",
}

LAUNDERING_CATEGORIES = {
    "references_not_derivation",
    "corrects_not_derivation",
    "retracts_not_derivation",
    "github_fork_boolean_single_no_parent",
    "shared_url_cannot_override_unsupported",
    "mirrored_text_not_derivation",
    "earliest_observation_not_origin",
    "github_fork_boolean_not_derivation",
    "shared_url_supported_sources_not_provenance",
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


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324 - Git object identity, not security


def test_shadow_evaluation_authority_binds_exact_lineage() -> None:
    authority = _load(AUTHORITY_PATH)
    assert (
        authority["schema_version"] == "frontier-entity-provenance-shadow-evaluation-authority-v0"
    )
    assert authority["phase_id"] == "ENTITY_PROVENANCE_SHADOW_EVALUATION_V0"
    assert authority["authority_state"] == "FROZEN_SHADOW_EVALUATION_AUTHORITY_CANDIDATE"
    assert authority["parent_main_commit"] == EXPECTED_PARENT

    lineage = _as_object(authority["lineage"], "lineage")
    assert lineage == {
        "bridge_authority_merge_commit": EXPECTED_BRIDGE_AUTHORITY,
        "bridge_corpus_digest": EXPECTED_BRIDGE_CORPUS,
        "bridge_implementation_merge_commit": EXPECTED_PARENT,
        "lab_corpus_digest": EXPECTED_LAB_CORPUS,
        "lab_merge_commit": EXPECTED_LAB_MERGE,
        "selected_entity_candidate": "transparent-entity-hybrid-v0",
        "selected_provenance_candidate": "explicit-reference-v0",
    }


def test_shadow_evaluation_corpus_is_exact_executable_24_case_authority() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)
    bridge_corpus = _load(BRIDGE_CORPUS_PATH)

    evaluation_corpus = _as_object(authority["evaluation_corpus"], "evaluation_corpus")
    assert evaluation_corpus == {
        "case_count": 24,
        "git_blob_sha1": EXPECTED_EVAL_CORPUS_BLOB,
        "path": "fixtures/entity_provenance/shadow_evaluation_corpus_v0.json",
        "schema_version": "frontier-entity-provenance-shadow-evaluation-corpus-v1",
    }
    assert _git_blob_sha1(CORPUS_PATH) == EXPECTED_EVAL_CORPUS_BLOB
    assert corpus["schema_version"] == "frontier-entity-provenance-shadow-evaluation-corpus-v1"
    assert _canonical_digest(bridge_corpus) == EXPECTED_BRIDGE_CORPUS

    bridge_cases = {
        _as_string(_as_object(value, "bridge case")["id"], "bridge case id"): _as_object(
            value, "bridge case"
        )
        for value in _as_list(bridge_corpus["cases"], "bridge cases")
    }
    cases = [_as_object(value, "evaluation case") for value in _as_list(corpus["cases"], "cases")]
    assert len(cases) == 24
    assert {_as_string(case["id"], "case.id") for case in cases} == EXPECTED_CASE_IDS

    for case in cases:
        case_id = _as_string(case["id"], "case.id")
        assert (
            _as_string(case["entity_candidate"], "entity_candidate")
            == "transparent-entity-hybrid-v0"
        )
        assert (
            _as_string(case["provenance_candidate"], "provenance_candidate")
            == "explicit-reference-v0"
        )
        assert isinstance(case["as_of"], str)
        assert isinstance(case["evaluation_pairs"], list)

        input_value = _as_object(case["input"], f"{case_id}.input")
        bridge_ref = input_value.get("bridge_case_ref")
        if bridge_ref is not None:
            ref = _as_string(bridge_ref, "bridge_case_ref")
            assert ref in bridge_cases, case_id
            assert case["as_of"] == bridge_cases[ref]["as_of"], case_id
        else:
            assert isinstance(input_value.get("observations"), list), case_id
            assert isinstance(input_value.get("relations"), list), case_id
            assert input_value["observations"], case_id

        expected = _as_object(case["expected"], f"{case_id}.expected")
        assert REQUIRED_EXPECTED_FIELDS <= set(expected), case_id
        assert expected["direct_derivation_evidence_count"] == 0, case_id
        assert expected["entity_quality_status"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH", case_id
        assert expected["provenance_quality_status"] == "BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE", (
            case_id
        )
        assert expected["promotion_status"] == "UNAVAILABLE", case_id
        assert expected["forbidden_inference_claims"] == [], case_id
        assert expected["quality_pass_fail_claim"] is None, case_id
        assert expected["entity_decision"] in {
            "SAME_ENTITY",
            "DIFFERENT_ENTITY",
            "AMBIGUOUS",
            "NOT_EVALUABLE",
            "NO_EVALUATION",
        }, case_id
        assert expected["provenance_decision"] in {
            "NO_LINK_EVIDENCE",
            "NOT_EVALUABLE",
            "NO_EVALUATION",
        }, case_id


def test_registry_drift_case_fails_before_quality_counting() -> None:
    corpus = _load(CORPUS_PATH)
    cases = {
        _as_string(case["id"], "case.id"): case
        for case in (_as_object(value, "case") for value in _as_list(corpus["cases"], "cases"))
    }
    drift = cases["EPSE-019"]
    assert drift["source_registry_digest"] != EXPECTED_REGISTRY
    expected = _as_object(drift["expected"], "EPSE-019.expected")
    assert expected["integrity_status"] == "INVALID_DRIFT"
    assert expected["pit_eligible_observation_count"] == 0
    assert expected["entity_decision"] == "NO_EVALUATION"
    assert expected["provenance_decision"] == "NO_EVALUATION"


def test_replay_case_requires_byte_identical_report_and_digest() -> None:
    corpus = _load(CORPUS_PATH)
    cases = {
        _as_string(case["id"], "case.id"): case
        for case in (_as_object(value, "case") for value in _as_list(corpus["cases"], "cases"))
    }
    replay = cases["EPSE-020"]
    permutations = _as_list(replay["replay_permutations"], "replay_permutations")
    assert len(permutations) >= 2
    expected = _as_object(replay["expected"], "EPSE-020.expected")
    assert expected["replay_requirement"] == "BYTE_IDENTICAL_CANONICAL_REPORT_AND_DIGEST"


def test_frozen_corpus_covers_every_forbidden_provenance_laundering_path() -> None:
    corpus = _load(CORPUS_PATH)
    cases = [_as_object(value, "case") for value in _as_list(corpus["cases"], "cases")]
    categories = {_as_string(case["category"], "category") for case in cases}
    assert LAUNDERING_CATEGORIES <= categories

    laundering_text = " ".join(
        _as_string(value, "forbidden signal")
        for case in cases
        for value in _as_list(case.get("forbidden_signals", []), "forbidden_signals")
    ).casefold()
    for signal in (
        "references",
        "corrects",
        "retracts",
        "mirrored text",
        "earliest observed_at",
        "fork boolean",
        "shared url",
        "independence",
        "true origin",
    ):
        assert signal in laundering_text


def test_entity_quality_cannot_self_validate_from_bridge_signals() -> None:
    authority = _load(AUTHORITY_PATH)
    protocol = _as_object(authority["evaluation_protocol"], "evaluation_protocol")
    entity = _as_object(protocol["entity"], "entity")

    assert entity["candidate"] == "transparent-entity-hybrid-v0"
    assert entity["independent_ground_truth_available"] is False
    assert entity["quality_status"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert entity["promotion_status"] == "UNAVAILABLE"
    quality_rule = _as_string(entity["quality_rule"], "entity.quality_rule")
    assert "cannot independently validate" in quality_rule


def test_provenance_quality_remains_blocked_without_explicit_derivation() -> None:
    authority = _load(AUTHORITY_PATH)
    protocol = _as_object(authority["evaluation_protocol"], "evaluation_protocol")
    provenance = _as_object(protocol["provenance"], "provenance")

    assert provenance["candidate"] == "explicit-reference-v0"
    assert provenance["direct_derivation_evidence_available"] is False
    assert provenance["quality_status"] == "BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE"
    assert provenance["promotion_status"] == "UNAVAILABLE"
    quality_rule = _as_string(provenance["quality_rule"], "provenance.quality_rule")
    for signal in (
        "REFERENCES",
        "CORRECTS",
        "RETRACTS",
        "mirrored text",
        "earliest observation",
        "GitHub fork booleans",
        "shared URLs",
        "source multiplicity",
        "zero coverage",
    ):
        assert signal in quality_rule


def test_authority_grants_only_offline_shadow_diagnostics() -> None:
    authority = _load(AUTHORITY_PATH)
    implementation = _as_object(
        authority["implementation_authority_on_merge"],
        "implementation_authority_on_merge",
    )
    true_keys = {key for key, value in implementation.items() if value is True}
    false_keys = {key for key, value in implementation.items() if value is False}
    assert true_keys == PERMITTED_IMPLEMENTATION_AUTHORITY
    assert false_keys == {
        "api",
        "canonical_schema_change",
        "candidate_promotion",
        "explicit_derivation_evidence_ingestion",
        "migration",
        "persistence",
        "source_registry_change",
        "terminal",
        "worker_scheduling",
    }

    output = _as_object(authority["output_authority"], "output_authority")
    for key in (
        "api_authority",
        "canonical_entity_authority",
        "canonical_provenance_authority",
        "persistence_authority",
        "promotion_authority",
        "ranking_authority",
        "terminal_authority",
    ):
        assert output[key] is False
    assert output["shadow_report"] == "EXPERIMENTAL_DIAGNOSTIC_ONLY"
    assert output["entity_quality_status"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert output["provenance_quality_status"] == "BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE"


def test_protocol_binds_registry_and_required_non_escalating_metrics() -> None:
    authority = _load(AUTHORITY_PATH)
    input_authority = _as_object(authority["input_authority"], "input_authority")
    assert input_authority["source_registry_digest"] == EXPECTED_REGISTRY
    assert input_authority["bridge_corpus_digest"] == EXPECTED_BRIDGE_CORPUS

    protocol = _as_object(authority["evaluation_protocol"], "evaluation_protocol")
    statuses = {
        _as_string(value, "integrity status")
        for value in _as_list(protocol["integrity_statuses"], "integrity_statuses")
    }
    assert statuses == {"COMPLETE_DIAGNOSTIC", "INVALID_DRIFT"}

    metrics = {
        _as_string(value, "metric")
        for value in _as_list(protocol["required_metrics"], "required_metrics")
    }
    assert "ignored future observation count globally and per source" in metrics
    assert "direct-derivation evidence count" in metrics
    assert "forbidden inference claims" in metrics
    assert "report digest" in metrics


def test_shadow_evaluation_corpus_grants_no_truth_or_runtime_authority() -> None:
    corpus = _load(CORPUS_PATH)
    corpus_authority = _as_object(corpus["authority"], "authority")
    assert corpus_authority == {
        "canonical_entity_authority": False,
        "canonical_provenance_authority": False,
        "persistence_authority": False,
        "promotion_authority": False,
        "public_authority": False,
        "runtime_authority": False,
    }
