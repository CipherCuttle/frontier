# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresFeatureVectorRepository,
)
from frontier.application.advanced_features import compute_advanced_features
from frontier.domain.digests import Digest
from frontier.domain.features import FEATURE_ORDER, FEATURE_SCHEMA_VERSION
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    build_baseline_receipt,
    build_baseline_snapshot,
)

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
GENERATED_AT = AS_OF
REGISTRY = Digest("sha256:" + "1" * 64)
SOURCES = ("s.a", "s.ext", "s.pri")


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    *,
    observed_at: datetime,
    source_id: str = "s.a",
    roles: tuple[str, ...] = ("PRIMARY_EMISSION",),
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id=source_id,
            source_item_key=label,
            kind="DOCUMENT",
            observed_at=observed_at,
            canonical_url=f"https://example.test/{label}",
            title=f"Fixture {label} episode title",
            text=None,
            signal_roles=roles,
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


def _healthy() -> tuple[BaselineHealthInput, ...]:
    return tuple(
        BaselineHealthInput(
            source_id=source_id,
            as_of=AS_OF - timedelta(minutes=1),
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.OK,
            schema=HealthValue.OK,
        )
        for source_id in SOURCES
    )


def _projection(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
) -> GroupingProjection:
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    return GroupingProjection(
        as_of=AS_OF,
        groups=tuple(
            EpisodeGroup(group_id=f"grp_{index:064x}", observation_ids=tuple(sorted(group)))
            for index, group in enumerate(grouped, start=1)
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=tuple(
            sorted(
                item.observation_id
                for item in observations
                if item.observation_id not in grouped_ids
            )
        ),
    )


def test_postgres_feature_vectors_persist_and_are_append_only() -> None:
    assert DB_URL is not None
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20), source_id="s.ext"),
        _observation("b", observed_at=AS_OF - timedelta(hours=10), source_id="s.pri"),
        _observation("c", observed_at=AS_OF - timedelta(hours=5), source_id="s.a"),
    ]
    grouped = (tuple(item.observation_id for item in observations),)
    eligible = [item for item in observations if item.observed_at <= AS_OF]
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_healthy(),
        as_of=AS_OF,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_healthy(),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    run = compute_advanced_features(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    batch = run.batch
    assert batch.status.value == "RAN"
    assert len(batch.vectors) >= 1

    with psycopg.connect(DB_URL) as conn:
        repository = PostgresFeatureVectorRepository(conn)
        repository.publish_batch(batch)
        assert repository.count_for_batch(batch.batch_id) == len(batch.vectors)

        first_vector = batch.vectors[0]
        assert repository.latest_vector_id() is not None
        retained = repository.get_vector_json(first_vector.vector_id)
        assert retained == first_vector.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, authority_state, feature_schema_version, vector_digest
                FROM feature_vectors
                WHERE feature_vector_id = %s
                """,
                (first_vector.vector_id,),
            )
            row = cur.fetchone()
        assert row == (
            "RAN",
            "EXPERIMENTAL_SHADOW",
            FEATURE_SCHEMA_VERSION,
            str(first_vector.vector_digest),
        )

        # Re-publishing the identical batch is an append-only no-op.
        repository.publish_batch(batch)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM feature_vectors WHERE batch_id = %s",
                (batch.batch_id,),
            )
            assert cur.fetchone() == (len(batch.vectors),)

        # Append-only guard: mutation of a durable vector must be rejected.
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE feature_vectors SET status = 'FAILED' WHERE feature_vector_id = %s",
                (first_vector.vector_id,),
            )

        # Vector payload carries the full canonical feature list (R7 labelling).
        assert retained is not None
        payload_features = cast(list[object], retained["features"])
        feature_names = [cast(dict[str, object], feature)["name"] for feature in payload_features]
        assert feature_names == list(FEATURE_ORDER)
        assert retained["authority_state"] == "EXPERIMENTAL_SHADOW"
        assert retained["interpretation"]
