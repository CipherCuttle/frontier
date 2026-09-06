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

EXPECTED_PARENT = "6e43ca0d588785c9d19a33a6dcdcd26944e43700"
EXPECTED_BRIDGE_AUTHORITY = "0027ffcba7ab0d62be8101424ba8e5ecc09cb28c"
EXPECTED_LAB_MERGE = "23cf10e0d65883c7b82356cf1bd18d9c56215604"
EXPECTED_LAB_CORPUS = "sha256:04ac150abe4356ef06a6fda75429d5873d8dd519e79e29f5c5e2853f4432a386"
EXPECTED_BRIDGE_CORPUS = "sha256:34d1c75a7999f0338ae81add88e358d444f0bbd58d59696c08bb7ae0fbaf209f"
EXPECTED_EVAL_CORPUS = "sha256:a210e838abb856f5472dc68503aae088599ba85e2de6a99840525fcd92c42892"
EXPECTED_REGISTRY = "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
EXPECTED_CASE_IDS = {f"EPSE-{i:03d}" for i in range(1, 19)}

PERMITTED_IMPLEMENTATION_AUTHORITY = {
    "deterministic_shadow_report",
    "hostile_shadow_tests",
    "offline_shadow_evaluator",
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


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_shadow_evaluation_authority_binds_exact_lineage() -> None:
    authority = _load(AUTHORITY_PATH)
    assert (
        authority["schema_version"]
        == "frontier-entity-provenance-shadow-evaluation-authority-v0"
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


def test_shadow_evaluation_corpus_is_exact_frozen_18_case_authority() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)

    evaluation_corpus = _as_object(authority["evaluation_corpus"], "evaluation_corpus")
    assert evaluation_corpus == {
        "case_count": 18,
        "digest": EXPECTED_EVAL_CORPUS,
        "path": "fixtures/entity_provenance/shadow_evaluation_corpus_v0.json",
    }
    assert corpus["schema_version"] == "frontier-entity-provenance-shadow-evaluation-corpus-v0"
    cases = _as_list(corpus["cases"], "cases")
    assert len(cases) == 18
    case_ids = {_as_string(_as_object(case, "case")["id"], "case.id") for case in cases}
    assert case_ids == EXPECTED_CASE_IDS
    assert len(case_ids) == len(cases)
    assert _digest(corpus) == EXPECTED_EVAL_CORPUS


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
    for relation in ("REFERENCES", "CORRECTS", "RETRACTS"):
        assert relation in quality_rule


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
