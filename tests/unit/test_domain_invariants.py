from datetime import datetime, timezone
from uuid import uuid4

import pytest

from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

UTC = timezone.utc


def test_active_enrichment_requires_trigger() -> None:
    with pytest.raises(ValueError):
        CollectionRun(
            run_id=uuid4(),
            source_id="fixture.hostile_document",
            reason=CollectionReason.ACTIVE_ENRICHMENT,
            started_at=datetime.now(UTC),
        )


def test_source_roles_are_set_like_and_sorted() -> None:
    source = SourceContract(
        source_id="fixture.hostile_document",
        display_name="fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION, SignalRole.ATTENTION, SignalRole.PRIMARY_EMISSION),
        transport=SourceTransport.FIXTURE,
    )
    assert source.to_canonical()["signal_roles"] == ["ATTENTION", "PRIMARY_EMISSION"]


def test_relation_requires_exactly_one_target_and_algorithm_for_inference() -> None:
    with pytest.raises(ValueError):
        ObservationRelation(
            relation_type=RelationType.REFERENCES,
            from_observation_id="obs_" + "a" * 64,
            authority=RelationAuthority.EXPLICIT,
            evidence={},
        )
    with pytest.raises(ValueError):
        ObservationRelation(
            relation_type=RelationType.REFERENCES,
            from_observation_id="obs_" + "a" * 64,
            target_external_ref="https://example.invalid",
            authority=RelationAuthority.INFERRED,
            evidence={},
        )


def test_health_dimensions_are_independent() -> None:
    health = SourceHealthObservation(
        source_id="fixture.hostile_document",
        as_of=datetime.now(UTC),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.DEGRADED,
        schema=HealthValue.OK,
        details={"pagination_complete": False},
    )
    assert health.transport is HealthValue.OK
    assert health.completeness is HealthValue.DEGRADED
