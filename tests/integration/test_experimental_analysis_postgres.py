# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresExperimentalAnalysisRepository,
)
from frontier.application.experimental_analysis import produce_experimental_analysis
from frontier.domain.digests import Digest
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
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
REGISTRY = Digest("sha256:" + "3" * 64)
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


def test_postgres_experimental_analysis_persists_and_is_append_only() -> None:
    assert DB_URL is not None
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=2), source_id="s.pri"),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=1),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
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
    run = produce_experimental_analysis(
        observations,
        kind=ExperimentalAnalysisKind.CORROBORATION,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    artifact = run.artifact
    assert artifact.status.value == "DESCRIPTOR"
    assert artifact.authority_state == "EXPERIMENTAL_SHADOW"

    with psycopg.connect(DB_URL) as conn:
        repository = PostgresExperimentalAnalysisRepository(conn)
        repository.record_artifact(artifact, input_digest=run.input_digest)
        assert repository.count_for_kind(ExperimentalAnalysisKind.CORROBORATION) >= 1
        assert (
            repository.latest_analysis_id(kind=ExperimentalAnalysisKind.CORROBORATION) is not None
        )
        retained = repository.get_artifact_json(artifact.analysis_id)
        assert retained == artifact.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT artifact_kind, status, authority_state, output_digest, input_digest
                FROM experimental_analysis_artifacts
                WHERE analysis_id = %s
                """,
                (artifact.analysis_id,),
            )
            row = cur.fetchone()
        assert row == (
            "CORROBORATION",
            "DESCRIPTOR",
            "EXPERIMENTAL_SHADOW",
            str(artifact.analysis_digest),
            str(run.input_digest),
        )

        # Re-recording the identical artifact is an append-only no-op.
        repository.record_artifact(artifact, input_digest=run.input_digest)

        # Append-only guard: mutation of a durable artifact must be rejected.
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                UPDATE experimental_analysis_artifacts SET status = 'HYPOTHESIS'
                WHERE analysis_id = %s
                """,
                (artifact.analysis_id,),
            )

        # Payload carries explicit hypothesis-level labelling (R7).
        assert retained is not None
        assert retained["authority_state"] == "EXPERIMENTAL_SHADOW"
        assert retained["interpretation"]
        payload = cast(dict[str, object], retained["payload"])
        assert payload["semantics"]
