from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "fixtures/entity_provenance/shadow_evaluation_corpus_v0.json"
EXPECTED_REPORTS_PATH = (
    ROOT / "fixtures/entity_provenance/shadow_evaluation_expected_reports_v0.json"
)
AUTHORITY_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/shadow_evaluation_authority.json"
)

EXPECTED_CORPUS_BLOB = "58c91348a6f81f31d99aadf50a1c32fb22ac0882"
EXPECTED_REPORTS_BLOB = "d0fa4e4ff82eeb70f551e4274eb856b5f5e9f3d4"
EXPECTED_CASE_IDS = {f"EPSE-{index:03d}" for index in range(1, 25)}
EXPECTED_SOURCES = [
    "arxiv.cs-ai",
    "cisa.kev",
    "gdelt.frontier",
    "github.ml-repos",
    "hf.models",
    "hn.frontpage",
    "pypi.updates",
]


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{name} must be object")
    return cast(dict[str, object], value)


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"{name} must be array")
    return cast(list[object], value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{name} must be string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{name} must be integer")
    return value


def _load(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _object(raw, path.name)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _case_map(document: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in _array(document["cases"], "cases"):
        case = _object(value, "case")
        case_id = _string(case["id"], "case.id") if "id" in case else _string(
            case["case_id"], "case.case_id"
        )
        assert case_id not in result
        result[case_id] = case
    return result


def _expand_coverage(
    report_document: dict[str, object],
    report_case: dict[str, object],
) -> dict[str, dict[str, int]]:
    expansion = _object(report_document["coverage_expansion"], "coverage_expansion")
    fields = [_string(value, "tuple field") for value in _array(expansion["tuple_fields"], "tuple_fields")]
    absent = [_integer(value, "absent tuple value") for value in _array(expansion["absent_source_tuple"], "absent_source_tuple")]
    assert len(fields) == len(absent)

    profiles = _object(report_document["coverage_profiles"], "coverage_profiles")
    profile_name = _string(report_case["source_coverage_profile"], "source_coverage_profile")
    profile = _object(profiles[profile_name], f"coverage profile {profile_name}")

    source_order = [_string(value, "source") for value in _array(report_document["source_order"], "source_order")]
    assert source_order == EXPECTED_SOURCES

    result: dict[str, dict[str, int]] = {}
    for source in source_order:
        raw_tuple = profile.get(source)
        values = (
            absent
            if raw_tuple is None
            else [_integer(value, f"{source} coverage") for value in _array(raw_tuple, source)]
        )
        assert len(values) == len(fields)
        result[source] = dict(zip(fields, values, strict=True))
    return result


def _project_report_body(
    corpus_case: dict[str, object],
    report_document: dict[str, object],
    report_case: dict[str, object],
) -> dict[str, object]:
    projection = _object(report_document["report_projection"], "report_projection")
    fixed_fields = _object(projection["fixed_fields"], "fixed_fields")
    expected = _object(corpus_case["expected"], "case.expected")

    report: dict[str, object] = {
        "schema_version": _string(projection["schema_version"], "report schema"),
        **fixed_fields,
    }
    for field_value in _array(projection["case_fields"], "case_fields"):
        field = _string(field_value, "case field")
        report[field] = corpus_case[field]
    for field_value in _array(projection["expected_fields"], "expected_fields"):
        field = _string(field_value, "expected field")
        report[field] = expected[field]

    coverage = _expand_coverage(report_document, report_case)
    report["source_coverage"] = coverage
    report["ignored_future_observation_by_source"] = {
        source: values["ignored_future_observation_count"]
        for source, values in coverage.items()
    }
    report["drift_reasons"] = expected.get("drift_reasons", [])
    return report


def test_expected_report_artifact_is_exactly_bound_by_machine_authority() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)
    expected_reports = _load(EXPECTED_REPORTS_PATH)

    assert _git_blob_sha1(CORPUS_PATH) == EXPECTED_CORPUS_BLOB
    assert _git_blob_sha1(EXPECTED_REPORTS_PATH) == EXPECTED_REPORTS_BLOB

    binding = _object(authority["expected_reports"], "authority.expected_reports")
    assert binding == {
        "case_count": 24,
        "git_blob_sha1": EXPECTED_REPORTS_BLOB,
        "path": "fixtures/entity_provenance/shadow_evaluation_expected_reports_v0.json",
        "report_schema_version": "frontier-entity-provenance-shadow-evaluation-report-v0",
        "schema_version": "frontier-entity-provenance-shadow-evaluation-expected-reports-v0",
    }
    assert expected_reports["schema_version"] == binding["schema_version"]
    assert corpus["schema_version"] == "frontier-entity-provenance-shadow-evaluation-corpus-v1"


def test_all_24_cases_resolve_to_concrete_seven_source_coverage_and_exact_digests() -> None:
    corpus = _load(CORPUS_PATH)
    expected_reports = _load(EXPECTED_REPORTS_PATH)
    corpus_cases = _case_map(corpus)
    report_cases = _case_map(expected_reports)

    assert set(corpus_cases) == EXPECTED_CASE_IDS
    assert set(report_cases) == EXPECTED_CASE_IDS

    for case_id in sorted(EXPECTED_CASE_IDS):
        corpus_case = corpus_cases[case_id]
        report_case = report_cases[case_id]
        expected = _object(corpus_case["expected"], f"{case_id}.expected")
        report_body = _project_report_body(corpus_case, expected_reports, report_case)
        coverage = _object(report_body["source_coverage"], f"{case_id}.source_coverage")

        assert set(coverage) == set(EXPECTED_SOURCES), case_id
        assert all(isinstance(coverage[source], dict) for source in EXPECTED_SOURCES), case_id

        total = sum(
            _integer(_object(coverage[source], source)["total_pit_eligible_observations"], "total")
            for source in EXPECTED_SOURCES
        )
        native = sum(
            _integer(_object(coverage[source], source)["native_id_signal_count"], "native")
            for source in EXPECTED_SOURCES
        )
        malformed = sum(
            _integer(_object(coverage[source], source)["malformed_identity_field_count"], "malformed")
            for source in EXPECTED_SOURCES
        )
        ignored_future = sum(
            _integer(_object(coverage[source], source)["ignored_future_observation_count"], "future")
            for source in EXPECTED_SOURCES
        )

        assert total == expected["pit_eligible_observation_count"], case_id
        assert native == expected["native_id_signal_count"], case_id
        assert malformed == expected["malformed_identity_field_count"], case_id
        assert ignored_future == expected["ignored_future_observation_count"], case_id

        frozen_digest = _string(report_case["report_digest"], f"{case_id}.report_digest")
        assert frozen_digest.startswith("sha256:") and len(frozen_digest) == 71, case_id
        assert _canonical_sha256(report_body) == frozen_digest, case_id


def test_report_digest_rule_is_non_circular_and_replay_case_is_exact() -> None:
    expected_reports = _load(EXPECTED_REPORTS_PATH)
    projection = _object(expected_reports["report_projection"], "report_projection")
    rule = _string(projection["report_digest_rule"], "report_digest_rule")
    assert "report_digest is outside report_body" in rule

    corpus_cases = _case_map(_load(CORPUS_PATH))
    report_cases = _case_map(expected_reports)
    replay_body = _project_report_body(corpus_cases["EPSE-020"], expected_reports, report_cases["EPSE-020"])
    original_body = _project_report_body(corpus_cases["EPSE-001"], expected_reports, report_cases["EPSE-001"])
    assert replay_body == original_body
    assert report_cases["EPSE-020"]["report_digest"] == report_cases["EPSE-001"]["report_digest"]


def test_source_multiplicity_and_zero_derivation_coverage_are_explicitly_non_authoritative() -> None:
    corpus_cases = _case_map(_load(CORPUS_PATH))
    expected_reports = _load(EXPECTED_REPORTS_PATH)
    report_cases = _case_map(expected_reports)
    case = report_cases["EPSE-024"]

    assertions = " ".join(
        _string(value, "mandatory negative assertion")
        for value in _array(case["mandatory_negative_assertions"], "mandatory_negative_assertions")
    ).casefold()
    assert "source multiplicity" in assertions
    assert "factual independence" in assertions
    assert "direct_derivation_evidence_count=0" in assertions
    assert "no derivation" in assertions

    body = _project_report_body(corpus_cases["EPSE-024"], expected_reports, case)
    coverage = _object(body["source_coverage"], "EPSE-024.source_coverage")
    represented_sources = [
        source
        for source in EXPECTED_SOURCES
        if _integer(_object(coverage[source], source)["total_pit_eligible_observations"], "total") > 0
    ]
    assert represented_sources == ["hf.models", "pypi.updates"]
    assert body["direct_derivation_evidence_count"] == 0
    assert body["forbidden_inference_claims"] == []
    assert body["provenance_quality_status"] == "BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE"
    assert body["promotion_status"] == "UNAVAILABLE"
