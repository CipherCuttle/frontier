from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from frontier.domain.digests import sha256_digest
from frontier.domain.observation import (
    DocumentPayload,
    MetricPayload,
    ObservationCandidate,
    ObservationKind,
)


def candidate() -> ObservationCandidate:
    return ObservationCandidate(
        source_id="fixture.hostile_document",
        source_item_key="item-1",
        kind=ObservationKind.DOCUMENT,
        payload=DocumentPayload(
            canonical_url="https://example.invalid/1",
            title="hello",
            excerpt="world",
        ),
        retrieved_at=datetime(2026, 9, 5, tzinfo=UTC),
        fetch_digest=sha256_digest(b"body"),
        source_published_at=datetime(2026, 9, 4, tzinfo=UTC),
    )


def test_operational_metadata_does_not_change_observation_identity() -> None:
    first = candidate()
    later = replace(
        first,
        retrieved_at=first.retrieved_at + timedelta(hours=1),
        fetch_digest=sha256_digest(b"transport-representation-changed"),
    )
    assert later.observation_id == first.observation_id
    assert later.content_digest == first.content_digest


def test_semantic_change_changes_observation_identity() -> None:
    first = candidate()
    changed_payload = replace(first, payload=replace(first.payload, title="changed"))
    source_published_at = first.source_published_at
    assert source_published_at is not None
    changed_time = replace(
        first,
        source_published_at=source_published_at + timedelta(seconds=1),
    )
    assert changed_payload.observation_id != first.observation_id
    assert changed_time.observation_id != first.observation_id


def test_metric_measurement_time_is_semantic() -> None:
    p1 = MetricPayload.from_decimal(
        metric_name="downloads",
        value=Decimal("42"),
        unit="count",
        measurement_at=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
    )
    p2 = replace(p1, measurement_at=datetime(2026, 9, 5, 12, 5, tzinfo=UTC))
    base = candidate()
    m1 = replace(base, kind=ObservationKind.METRIC, payload=p1)
    m2 = replace(base, kind=ObservationKind.METRIC, payload=p2)
    assert m1.observation_id != m2.observation_id
