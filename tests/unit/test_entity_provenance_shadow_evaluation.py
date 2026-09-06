from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.domain.canonical_json import CanonicalValue
from frontier.domain.digests import sha256_digest
from frontier.domain.entity_provenance_bridge import KnownObservationRelation
from frontier.domain.entity_provenance_shadow_evaluation import (
    ENTITY_QUALITY_STATUS,
    FROZEN_SOURCE_REGISTRY_DIGEST,
    PROMOTION_STATUS,
    PROVENANCE_QUALITY_STATUS,
    ShadowIntegrityStatus,
    evaluate_entity_provenance_shadow,
)
from frontier.domain.observation import (
    ArtifactPayload,
    DocumentPayload,
    Observation,
    ObservationCandidate,
    ObservationKind,
)
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "fixtures/entity_provenance/shadow_evaluation_corpus_v0.json"
BRIDGE_CORPUS_PATH = ROOT / "fixtures/entity_provenance/bridge_corpus_v0.json"
EXPECTED_REPORTS_PATH = (
    ROOT / "fixtures/entity_provenance/shadow_evaluation_expected_reports_v0.json"
)
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


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{name} must be integer")
    return value


def _time(value: object, name: str) -> datetime:
    result = datetime.fromisoformat(_string(value, name).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise AssertionError(f"{name} must be timezone-aware")
    return result


def _canonical(value: object) -> CanonicalValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, list):
        return [_canonical(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        raw = cast(dict[object, object], value)
        result: dict[str, CanonicalValue] = {}
        for key, item in raw.items():
            if not isinstance(key, str):
                raise AssertionError("canonical metadata key must be string")
            result[key] = _canonical(item)
        return result
    raise AssertionError(f"unsupported fixture canonical type: {type(value).__name__}")


def _metadata(value: object) -> dict[str, CanonicalValue]:
    canonical = _canonical(value)
    if not isinstance(canonical, dict):
        raise AssertionError("source_metadata must be object")
    return canonical


def _load(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _object(raw, path.name)


def _case_map(document: dict[str, object], *, key: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in _array(document["cases"], "cases"):
        case = _object(value, "case")
        case_id = _string(case[key], f"case.{key}")
        assert case_id not in result
        result[case_id] = case
    return result


def _observation(document: dict[str, object], *, fixture_key: str) -> Observation:
    observed_at = _time(document["observed_at"], "observed_at")
    payload_document = _object(document["payload"], "payload")
    metadata = _metadata(payload_document.get("source_metadata", {}))
    kind = ObservationKind(_string(document["kind"], "kind"))

    if kind is ObservationKind.ARTIFACT:
        payload = ArtifactPayload(
            artifact_type=_string(payload_document["artifact_type"], "artifact_type"),
            name=_string(payload_document["name"], "name"),
            version=_optional_string(payload_document.get("version"), "version"),
            canonical_url=_optional_string(payload_document.get("canonical_url"), "canonical_url"),
            artifact_digest=None,
            source_metadata=metadata,
        )
    elif kind is ObservationKind.DOCUMENT:
        payload = DocumentPayload(
            canonical_url=_optional_string(payload_document.get("canonical_url"), "canonical_url"),
            title=_optional_string(payload_document.get("title"), "title"),
            excerpt=None,
            language=None,
            source_metadata=metadata,
        )
    else:
        raise AssertionError("shadow corpus does not authorize METRIC cases")

    source_published = document.get("source_published_at")
    candidate = ObservationCandidate(
        source_id=_string(document["source_id"], "source_id"),
        source_item_key=_string(document["source_item_key"], "source_item_key"),
        kind=kind,
        payload=payload,
        retrieved_at=observed_at,
        fetch_digest=sha256_digest(fixture_key.encode()),
        source_published_at=None
        if source_published is None
        else _time(source_published, "source_published_at"),
        effective_at=None,
    )
    return Observation(candidate=candidate, observed_at=observed_at)


def _relations(
    raw_relations: list[object],
    *,
    observations: tuple[Observation, ...],
) -> tuple[KnownObservationRelation, ...]:
    result: list[KnownObservationRelation] = []
    if not observations and raw_relations:
        raise AssertionError("relations require observations")
    for value in raw_relations:
        raw = _object(value, "relation")
        raw_from_index = raw.get("from_observation_index")
        from_index = (
            len(observations) - 1
            if raw_from_index is None
            else _integer(raw_from_index, "relation.from_observation_index")
        )
        if not 0 <= from_index < len(observations):
            raise AssertionError("relation.from_observation_index outside fixture")
        authority = RelationAuthority(_string(raw["authority"], "relation.authority"))
        result.append(
            KnownObservationRelation(
                relation=ObservationRelation(
                    relation_type=RelationType(
                        _string(raw["relation_type"], "relation.relation_type")
                    ),
                    from_observation_id=observations[from_index].observation_id,
                    authority=authority,
                    evidence={},
                    target_external_ref=_string(
                        raw["target_external_ref"], "relation.target_external_ref"
                    ),
                    algorithm_version="fixture-inferred-v0"
                    if authority is RelationAuthority.INFERRED
                    else None,
                ),
                known_at=_time(raw["known_at"], "relation.known_at"),
            )
        )
    return tuple(result)


def _resolve_case(
    case: dict[str, object],
    bridge_cases: dict[str, dict[str, object]],
) -> tuple[
    tuple[Observation, ...],
    tuple[KnownObservationRelation, ...],
    tuple[tuple[int, int], ...],
    datetime,
]:
    case_id = _string(case["id"], "case.id")
    raw_input = _object(case["input"], f"{case_id}.input")
    bridge_ref = raw_input.get("bridge_case_ref")

    if bridge_ref is not None:
        bridge_case = bridge_cases[_string(bridge_ref, "bridge_case_ref")]
        documents = [_object(bridge_case["left"], "left")]
        if "right" in bridge_case:
            documents.append(_object(bridge_case["right"], "right"))
        relation_values = _array(bridge_case.get("relations", []), "relations")
    else:
        documents = [
            _object(value, "inline observation")
            for value in _array(raw_input.get("observations", []), "input.observations")
        ]
        relation_values = _array(raw_input.get("relations", []), "input.relations")

    observations = tuple(
        _observation(document, fixture_key=f"{case_id}:{index}")
        for index, document in enumerate(documents)
    )
    relations = _relations(relation_values, observations=observations)

    pairs: list[tuple[int, int]] = []
    for value in _array(case.get("evaluation_pairs", []), "evaluation_pairs"):
        pair = _array(value, "evaluation pair")
        assert len(pair) == 2
        pairs.append((_integer(pair[0], "pair.left"), _integer(pair[1], "pair.right")))

    return observations, relations, tuple(pairs), _time(case["as_of"], "case.as_of")


def _expand_coverage(
    document: dict[str, object], report_case: dict[str, object]
) -> dict[str, dict[str, int]]:
    expansion = _object(document["coverage_expansion"], "coverage_expansion")
    fields = [
        _string(value, "tuple field")
        for value in _array(expansion["tuple_fields"], "tuple_fields")
    ]
    absent = [
        _integer(value, "absent tuple value")
        for value in _array(expansion["absent_source_tuple"], "absent_source_tuple")
    ]
    assert len(fields) == len(absent)

    profiles = _object(document["coverage_profiles"], "coverage_profiles")
    profile_name = _string(report_case["source_coverage_profile"], "source_coverage_profile")
    profile = _object(profiles[profile_name], f"coverage profile {profile_name}")
    source_order = [
        _string(value, "source") for value in _array(document["source_order"], "source_order")
    ]
    assert source_order == EXPECTED_SOURCES

    result: dict[str, dict[str, int]] = {}
    for source in source_order:
        raw_tuple = profile.get(source)
        values = (
            absent
            if raw_tuple is None
            else [
                _integer(value, f"{source} coverage")
                for value in _array(raw_tuple, f"{source} coverage")
            ]
        )
        assert len(values) == len(fields)
        result[source] = dict(zip(fields, values, strict=True))
    return result


def _expected_report_body(
    case: dict[str, object],
    expected_reports: dict[str, object],
    report_case: dict[str, object],
) -> dict[str, object]:
    projection = _object(expected_reports["report_projection"], "report_projection")
    fixed_fields = _object(projection["fixed_fields"], "fixed_fields")
    expected = _object(case["expected"], "case.expected")

    report: dict[str, object] = {
        "schema_version": _string(projection["schema_version"], "report schema"),
        **fixed_fields,
    }
    for field_value in _array(projection["case_fields"], "case_fields"):
        field = _string(field_value, "case field")
        report[field] = case[field]
    for field_value in _array(projection["expected_fields"], "expected_fields"):
        field = _string(field_value, "expected field")
        report[field] = expected[field]

    coverage = _expand_coverage(expected_reports, report_case)
    report["source_coverage"] = coverage
    report["ignored_future_observation_by_source"] = {
        source: values["ignored_future_observation_count"] for source, values in coverage.items()
    }
    report["drift_reasons"] = expected.get("drift_reasons", [])
    return report


def _run_case(
    case: dict[str, object],
    bridge_cases: dict[str, dict[str, object]],
):
    observations, relations, pairs, as_of = _resolve_case(case, bridge_cases)
    return evaluate_entity_provenance_shadow(
        observations,
        relations=relations,
        evaluation_pairs=pairs,
        as_of=as_of,
        source_registry_digest=_string(case["source_registry_digest"], "source_registry_digest"),
        entity_candidate=_string(case["entity_candidate"], "entity_candidate"),
        provenance_candidate=_string(case["provenance_candidate"], "provenance_candidate"),
    )


def test_frozen_24_case_shadow_reports_match_exact_body_and_digest() -> None:
    corpus = _load(CORPUS_PATH)
    expected_reports = _load(EXPECTED_REPORTS_PATH)
    bridge_corpus = _load(BRIDGE_CORPUS_PATH)
    cases = _case_map(corpus, key="id")
    report_cases = _case_map(expected_reports, key="case_id")
    bridge_cases = _case_map(bridge_corpus, key="id")

    assert set(cases) == EXPECTED_CASE_IDS
    assert set(report_cases) == EXPECTED_CASE_IDS

    for case_id in sorted(EXPECTED_CASE_IDS):
        report = _run_case(cases[case_id], bridge_cases)
        expected_body = _expected_report_body(
            cases[case_id], expected_reports, report_cases[case_id]
        )
        assert report.report_body == expected_body, case_id
        assert report.report_digest == report_cases[case_id]["report_digest"], case_id
        assert report.to_canonical()["report_digest"] == report.report_digest, case_id


def test_registry_drift_fails_closed_before_any_quality_counting() -> None:
    corpus = _load(CORPUS_PATH)
    bridge_cases = _case_map(_load(BRIDGE_CORPUS_PATH), key="id")
    case = _case_map(corpus, key="id")["EPSE-019"]
    report = _run_case(case, bridge_cases)

    assert report.integrity_status is ShadowIntegrityStatus.INVALID_DRIFT
    assert report.drift_reasons == ("source-registry-digest-mismatch",)
    assert report.pit_eligible_observation_count == 0
    assert report.native_id_signal_count == 0
    assert report.entity_decision == "NO_EVALUATION"
    assert report.provenance_decision == "NO_EVALUATION"
    assert all(
        row["total_pit_eligible_observations"] == 0
        for row in report.source_coverage.values()
    )


def test_candidate_identity_drift_also_fails_closed_before_bridge_counting() -> None:
    bridge_cases = _case_map(_load(BRIDGE_CORPUS_PATH), key="id")
    raw = bridge_cases["BRV-001"]
    observations = (
        _observation(_object(raw["left"], "left"), fixture_key="candidate-drift:left"),
        _observation(_object(raw["right"], "right"), fixture_key="candidate-drift:right"),
    )
    report = evaluate_entity_provenance_shadow(
        observations,
        evaluation_pairs=((0, 1),),
        as_of=_time(raw["as_of"], "as_of"),
        source_registry_digest=FROZEN_SOURCE_REGISTRY_DIGEST,
        entity_candidate="not-the-frozen-candidate",
    )

    assert report.integrity_status is ShadowIntegrityStatus.INVALID_DRIFT
    assert report.drift_reasons == ("entity-candidate-mismatch",)
    assert report.pit_eligible_observation_count == 0
    assert report.entity_decision == "NO_EVALUATION"


def test_replay_is_byte_identical_after_input_order_reversal() -> None:
    corpus = _load(CORPUS_PATH)
    bridge_cases = _case_map(_load(BRIDGE_CORPUS_PATH), key="id")
    case = _case_map(corpus, key="id")["EPSE-020"]
    observations, relations, pairs, as_of = _resolve_case(case, bridge_cases)
    assert len(observations) == 2

    first = evaluate_entity_provenance_shadow(
        observations,
        relations=relations,
        evaluation_pairs=pairs,
        as_of=as_of,
        source_registry_digest=FROZEN_SOURCE_REGISTRY_DIGEST,
    )
    second = evaluate_entity_provenance_shadow(
        tuple(reversed(observations)),
        relations=tuple(reversed(relations)),
        evaluation_pairs=pairs,
        as_of=as_of,
        source_registry_digest=FROZEN_SOURCE_REGISTRY_DIGEST,
    )
    assert first.canonical_bytes == second.canonical_bytes
    assert first.report_digest == second.report_digest


def test_scientific_quality_and_promotion_authority_never_escalate() -> None:
    corpus = _load(CORPUS_PATH)
    bridge_cases = _case_map(_load(BRIDGE_CORPUS_PATH), key="id")
    cases = _case_map(corpus, key="id")

    for case_id in sorted(EXPECTED_CASE_IDS):
        report = _run_case(cases[case_id], bridge_cases)
        assert report.entity_quality_status == ENTITY_QUALITY_STATUS, case_id
        assert report.provenance_quality_status == PROVENANCE_QUALITY_STATUS, case_id
        assert report.promotion_status == PROMOTION_STATUS, case_id
        assert report.quality_pass_fail_claim is None, case_id
        assert report.forbidden_inference_claims == (), case_id
        assert report.direct_derivation_evidence_count == 0, case_id
        assert report.provenance_decision != "DIRECT_DERIVATIVE", case_id
