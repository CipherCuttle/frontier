from __future__ import annotations

from datetime import UTC, datetime

from frontier.domain.digests import sha256_digest
from frontier.domain.entity_provenance_shadow_evaluation import (
    FROZEN_SOURCE_REGISTRY_DIGEST,
    ShadowIntegrityStatus,
    evaluate_entity_provenance_shadow,
)
from frontier.domain.observation import (
    ArtifactPayload,
    Observation,
    ObservationCandidate,
    ObservationKind,
)


def _candidate() -> ObservationCandidate:
    return ObservationCandidate(
        source_id="pypi.updates",
        source_item_key="pit-alias-demo:1.0.0",
        kind=ObservationKind.ARTIFACT,
        payload=ArtifactPayload(
            artifact_type="package",
            name="pit-alias-demo",
            version="1.0.0",
            canonical_url=None,
            artifact_digest=None,
            source_metadata={},
        ),
        retrieved_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC),
        fetch_digest=sha256_digest(b"pit-alias-demo"),
        source_published_at=None,
        effective_at=None,
    )


def test_future_pair_member_with_same_observation_id_is_not_evaluable() -> None:
    candidate = _candidate()
    eligible = Observation(
        candidate=candidate,
        observed_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC),
    )
    future = Observation(
        candidate=candidate,
        observed_at=datetime(2026, 9, 6, 13, 0, tzinfo=UTC),
    )
    assert eligible.observation_id == future.observation_id

    report = evaluate_entity_provenance_shadow(
        (eligible, future),
        evaluation_pairs=((0, 1),),
        as_of=datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
        source_registry_digest=FROZEN_SOURCE_REGISTRY_DIGEST,
    )

    assert report.integrity_status is ShadowIntegrityStatus.COMPLETE_DIAGNOSTIC
    assert report.pit_eligible_observation_count == 1
    assert report.ignored_future_observation_count == 1
    assert report.ignored_future_observation_by_source["pypi.updates"] == 1
    assert report.entity_decision == "NOT_EVALUABLE"
    assert report.provenance_decision == "NOT_EVALUABLE"
    assert report.direct_derivation_evidence_count == 0


def test_duplicate_eligible_observation_ids_cannot_become_semantic_self_pair() -> None:
    candidate = _candidate()
    first = Observation(
        candidate=candidate,
        observed_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC),
    )
    second = Observation(
        candidate=candidate,
        observed_at=datetime(2026, 9, 6, 10, 0, tzinfo=UTC),
    )
    assert first.observation_id == second.observation_id

    report = evaluate_entity_provenance_shadow(
        (first, second),
        evaluation_pairs=((0, 1),),
        as_of=datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
        source_registry_digest=FROZEN_SOURCE_REGISTRY_DIGEST,
    )

    assert report.integrity_status is ShadowIntegrityStatus.COMPLETE_DIAGNOSTIC
    assert report.pit_eligible_observation_count == 2
    assert report.ignored_future_observation_count == 0
    assert report.entity_decision == "NOT_EVALUABLE"
    assert report.provenance_decision == "NOT_EVALUABLE"
    assert report.direct_derivation_evidence_count == 0
