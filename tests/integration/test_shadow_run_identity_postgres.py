# ruff: noqa: E402
"""PostgreSQL regressions for experiment-scoped shadow-run identity."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.advanced_intelligence import PostgresShadowRunRepository
from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _hex64(*, first: str | None = None) -> str:
    value = uuid4().hex + uuid4().hex
    return value if first is None else first + value[1:]


def _boundary() -> datetime:
    offset = int(uuid4().hex[:8], 16) % 1_000_000
    return datetime(2040, 1, 1, tzinfo=UTC) + timedelta(seconds=offset)


def _insert_run(
    conn: object,
    *,
    run_id: str,
    experiment_id: str,
    as_of: datetime,
    run_class: str,
) -> None:
    with conn.transaction(), conn.cursor():  # type: ignore[attr-defined]
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                """
                INSERT INTO shadow_experiment_runs (
                    run_id, experiment_id, candidate_id, schema_version,
                    algorithm_version, configuration_digest, authority_state,
                    status, as_of, control_snapshot_id, control_receipt_id,
                    candidate_artifact_id, candidate_output_digest,
                    coverage_state, episode_universe_digest, run_digest,
                    failure_reason, run_class, run_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    run_id,
                    experiment_id,
                    "fixture-candidate",
                    "fixture-shadow-v0",
                    "fixture-algorithm-v0",
                    "sha256:" + _hex64(),
                    "EXPERIMENTAL_SHADOW",
                    "RAN",
                    as_of,
                    "snapshot_" + _hex64(),
                    "receipt_" + _hex64(),
                    "artifact_" + _hex64(),
                    "sha256:" + _hex64(),
                    "OK",
                    "sha256:" + _hex64(),
                    "sha256:" + _hex64(),
                    None,
                    run_class,
                    Jsonb({"fixture": run_id, "experiment_id": experiment_id}),
                ),
            )


def test_lookup_is_scoped_to_pef_experiment_not_run_id_ordering() -> None:
    assert DB_URL is not None
    boundary = _boundary()
    pef_run_id = "shadowrun_" + _hex64(first="0")
    foreign_run_id = "shadowrun_" + _hex64(first="f")

    with psycopg.connect(DB_URL) as conn:
        _insert_run(
            conn,
            run_id=foreign_run_id,
            experiment_id="fixture-successor-experiment",
            as_of=boundary,
            run_class="DEV",
        )
        _insert_run(
            conn,
            run_id=pef_run_id,
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            run_class="DEV",
        )

        retained = PostgresShadowRunRepository(conn).latest_run_id_and_class_for_as_of(boundary)

    assert retained == (pef_run_id, "DEV", "RAN")


def test_boundary_identity_is_unique_per_experiment_and_run_class() -> None:
    assert DB_URL is not None
    boundary = _boundary()
    dev_run_id = "shadowrun_" + _hex64(first="0")
    duplicate_dev_run_id = "shadowrun_" + _hex64(first="1")
    confirmatory_run_id = "shadowrun_" + _hex64(first="f")

    with psycopg.connect(DB_URL) as conn:
        _insert_run(
            conn,
            run_id=dev_run_id,
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            run_class="DEV",
        )

        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_run(
                conn,
                run_id=duplicate_dev_run_id,
                experiment_id=PEF_EXPERIMENT_ID,
                as_of=boundary,
                run_class="DEV",
            )

        # DEV and CONFIRMATORY remain distinct evidence classes and may coexist.
        _insert_run(
            conn,
            run_id=confirmatory_run_id,
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            run_class="CONFIRMATORY",
        )

        retained = PostgresShadowRunRepository(conn).latest_run_id_and_class_for_as_of(boundary)

    # Explicit fail-closed precedence: DEV wins if both classes exist, rather
    # than a content-derived run_id deciding which authority class is observed.
    assert retained == (dev_run_id, "DEV", "RAN")
