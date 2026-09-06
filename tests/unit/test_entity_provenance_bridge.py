from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.domain.canonical_json import CanonicalValue
from frontier.domain.digests import sha256_digest
from frontier.domain.entity_provenance_bridge import (
    BRIDGE_SOURCE_REGISTRY,
    EntityBridgeState,
    KnownObservationRelation,
    build_entity_provenance_bridge,
)
from frontier.domain.entity_provenance_lab import EntityDecision, assess_entity
from frontier.domain.observation import (
    ArtifactPayload,
    DocumentPayload,
    Observation,
    ObservationCandidate,
    ObservationKind,
)
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "fixtures/entity_provenance/bridge_corpus_v0.json"
EXPECTED_SOURCES = (
    "arxiv.cs-ai",
    "cisa.kev",
    "gdelt.frontier",
    "github.ml-repos",
    "hf.models",
    "hn.frontpage",
    "pypi.updates",
)


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


def _time(value: object, name: str) -> datetime:
    text = _string(value, name)
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
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


def _load_corpus() -> list[dict[str, object]]:
    raw: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    document = _object(raw, "bridge corpus")
    assert document["schema_version"] == "frontier-entity-provenance-bridge-corpus-v0"
    return [_object(value, "bridge case") for value in _array(document["cases"], "cases")]


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
        raise AssertionError("bridge corpus does not authorize METRIC cases")

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
    raw_case: dict[str, object],
    *,
    left: Observation,
    right: Observation | None,
) -> tuple[KnownObservationRelation, ...]:
    result: list[KnownObservationRelation] = []
    raw_relations = _array(raw_case.get("relations", []), "relations")
    from_observation = right or left
    for value in raw_relations:
        raw = _object(value, "relation")
        authority = RelationAuthority(_string(raw["authority"], "relation.authority"))
        result.append(
            KnownObservationRelation(
                relation=ObservationRelation(
                    relation_type=RelationType(
                        _string(raw["relation_type"], "relation.relation_type")
                    ),
                    from_observation_id=from_observation.observation_id,
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


def _run_case(raw_case: dict[str, object]):
    case_id = _string(raw_case["id"], "case.id")
    left = _observation(_object(raw_case["left"], "left"), fixture_key=f"{case_id}:left")
    right_document = raw_case.get("right")
    right = (
        None
        if right_document is None
        else _observation(_object(right_document, "right"), fixture_key=f"{case_id}:right")
    )
    observations = (left,) if right is None else (left, right)
    as_of = _time(raw_case["as_of"], "as_of")
    relations = _relations(raw_case, left=left, right=right)
    return (
        build_entity_provenance_bridge(observations, relations=relations, as_of=as_of),
        observations,
        as_of,
    )


def test_frozen_18_case_bridge_corpus() -> None:
    cases = _load_corpus()
    assert len(cases) == 18

    for raw_case in cases:
        case_id = _string(raw_case["id"], "case.id")
        expected = _object(raw_case["expected"], f"{case_id}.expected")
        run, observations, as_of = _run_case(raw_case)
        records = {value.observation_id: value for value in run.observations}
        eligible_records = [
            records[value.observation_id] for value in observations if value.observed_at <= as_of
        ]

        if "ignored_future_observations" in expected:
            assert (
                run.coverage.ignored_future_observation_count
                == expected["ignored_future_observations"]
            ), case_id
        if "ignored_future_relations" in expected:
            assert (
                run.coverage.ignored_future_relation_count == expected["ignored_future_relations"]
            ), case_id
        if expected.get("direct_derivation") is False:
            assert run.coverage.direct_derivation_evidence_count == 0, case_id
            assert all(
                value.lab_observation is None or not value.lab_observation.relations
                for value in eligible_records
            ), case_id

        if "malformed_identity_fields" in expected:
            assert (
                sum(value.malformed_identity_fields for value in eligible_records)
                == expected["malformed_identity_fields"]
            ), case_id

        if "entity_supported" in expected:
            expected_supported = expected["entity_supported"]
            actual_supported = [value.entity_supported for value in eligible_records]
            if isinstance(expected_supported, list):
                assert actual_supported == expected_supported, case_id
            else:
                assert actual_supported and all(
                    value is expected_supported for value in actual_supported
                ), case_id

        if "entity_native_id" in expected:
            expected_native = expected["entity_native_id"]
            actual_native = [value.native_id for value in eligible_records]
            assert actual_native and all(value == expected_native for value in actual_native), (
                case_id
            )

        if "entity_native_ids" in expected:
            assert [value.native_id for value in eligible_records] == expected[
                "entity_native_ids"
            ], case_id

        if "entity_type" in expected:
            actual_types = [
                value.entity_type for value in eligible_records if value.entity_supported
            ]
            assert actual_types and all(
                value == expected["entity_type"] for value in actual_types
            ), case_id


def test_selected_entity_candidate_receives_only_frozen_native_identity_signal() -> None:
    cases = {_string(case["id"], "case.id"): case for case in _load_corpus()}

    same_run, _, same_as_of = _run_case(cases["BRV-001"])
    same_lab = [value.lab_observation for value in same_run.observations]
    assert same_lab[0] is not None and same_lab[1] is not None
    same_assessment = assess_entity(
        "transparent-entity-hybrid-v0", same_lab[0], same_lab[1], as_of=same_as_of
    )
    assert same_assessment.decision is EntityDecision.SAME_ENTITY

    different_run, _, different_as_of = _run_case(cases["BRV-004"])
    different_lab = [value.lab_observation for value in different_run.observations]
    assert different_lab[0] is not None and different_lab[1] is not None
    different_assessment = assess_entity(
        "transparent-entity-hybrid-v0",
        different_lab[0],
        different_lab[1],
        as_of=different_as_of,
    )
    assert different_assessment.decision is EntityDecision.DIFFERENT_ENTITY


def test_malformed_native_identity_cannot_fall_back_to_canonical_url() -> None:
    cases = {_string(case["id"], "case.id"): case for case in _load_corpus()}
    run, _, _ = _run_case(cases["BRV-015"])
    assert len(run.observations) == 1
    record = run.observations[0]
    assert record.state is EntityBridgeState.DEGRADED
    assert record.native_id is None
    assert record.lab_observation is not None
    assert record.lab_observation.canonical_url is None
    assert record.lab_observation.native_ids == ()


def test_explicit_null_cisa_metadata_id_fails_closed() -> None:
    observation = _observation(
        {
            "source_id": "cisa.kev",
            "source_item_key": "CVE-2026-9999",
            "observed_at": "2026-09-06T10:00:00Z",
            "kind": "DOCUMENT",
            "payload": {
                "canonical_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                "title": "Null metadata identity",
                "source_metadata": {"cve_id": None},
            },
        },
        fixture_key="cisa-null-cve",
    )
    as_of = datetime.fromisoformat("2026-09-06T12:00:00+00:00")
    run = build_entity_provenance_bridge((observation,), as_of=as_of)
    record = run.observations[0]
    assert record.state is EntityBridgeState.DEGRADED
    assert record.native_id is None
    assert record.malformed_identity_fields == 1
    assert run.coverage.by_source["cisa.kev"].malformed_identity_field_count == 1


def test_future_observation_coverage_is_attributed_per_source() -> None:
    cases = {_string(case["id"], "case.id"): case for case in _load_corpus()}

    pypi_run, _, _ = _run_case(cases["BRV-013"])
    assert pypi_run.coverage.ignored_future_observation_count == 1
    assert pypi_run.coverage.by_source["pypi.updates"].ignored_future_observation_count == 1
    assert pypi_run.coverage.by_source["arxiv.cs-ai"].ignored_future_observation_count == 0

    backfill_run, _, _ = _run_case(cases["BRV-014"])
    assert backfill_run.coverage.ignored_future_observation_count == 1
    assert backfill_run.coverage.by_source["arxiv.cs-ai"].ignored_future_observation_count == 1
    assert backfill_run.coverage.by_source["pypi.updates"].ignored_future_observation_count == 0


def test_bridge_replay_is_byte_identical_independent_of_input_order() -> None:
    cases = {_string(case["id"], "case.id"): case for case in _load_corpus()}
    raw_case = cases["BRV-009"]
    case_id = "BRV-009"
    left = _observation(_object(raw_case["left"], "left"), fixture_key=f"{case_id}:left")
    right = _observation(_object(raw_case["right"], "right"), fixture_key=f"{case_id}:right")
    as_of = _time(raw_case["as_of"], "as_of")
    relations = _relations(raw_case, left=left, right=right)

    first = build_entity_provenance_bridge((left, right), relations=relations, as_of=as_of)
    second = build_entity_provenance_bridge(
        (right, left), relations=tuple(reversed(relations)), as_of=as_of
    )
    assert first.canonical_bytes == second.canonical_bytes


def test_coverage_report_keeps_exact_registry_and_zero_direct_derivation() -> None:
    assert BRIDGE_SOURCE_REGISTRY == EXPECTED_SOURCES
    cases = {_string(case["id"], "case.id"): case for case in _load_corpus()}
    run, _, _ = _run_case(cases["BRV-018"])
    assert tuple(sorted(run.coverage.by_source)) == EXPECTED_SOURCES
    assert run.coverage.direct_derivation_evidence_count == 0
    assert run.coverage.ignored_future_relation_count == 1
