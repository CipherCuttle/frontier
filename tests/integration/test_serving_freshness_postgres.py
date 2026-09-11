# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import datetime
from typing import cast

import pytest

psycopg = pytest.importorskip("psycopg")

from scripts.ops.serving_freshness import ServingFreshnessState, read_serving_freshness

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _liveness_row_counts(database_url: str) -> tuple[int, int]:
    with psycopg.connect(database_url, autocommit=True) as connection:
        baseline_row = connection.execute(
            "SELECT count(*) FROM baseline_intelligence_snapshots"
        ).fetchone()
        heartbeat_row = connection.execute("SELECT count(*) FROM worker_heartbeats").fetchone()
    assert baseline_row is not None
    assert heartbeat_row is not None
    return int(baseline_row[0]), int(heartbeat_row[0])


def test_serving_freshness_probe_is_read_only_and_preserves_existing_evidence() -> None:
    assert DB_URL is not None
    before = _liveness_row_counts(DB_URL)

    status = read_serving_freshness(DB_URL)

    assert status.state in ServingFreshnessState
    assert _liveness_row_counts(DB_URL) == before


def test_serving_freshness_ignores_non_acquisition_worker_heartbeats() -> None:
    assert DB_URL is not None
    worker_id = "serving-freshness-decoy-non-acquisition"
    with psycopg.connect(DB_URL, autocommit=True) as connection:
        expected_row = connection.execute(
            "SELECT max(beat_at) FROM worker_heartbeats WHERE role = 'ACQUISITION'"
        ).fetchone()
        assert expected_row is not None
        expected = cast(datetime | None, expected_row[0])
        connection.execute(
            """
            INSERT INTO worker_heartbeats (worker_id, role, beat_at, metrics)
            VALUES (%s, 'NOT_ACQUISITION', '2999-01-01T00:00:00+00'::timestamptz, '{}'::jsonb)
            ON CONFLICT (worker_id) DO UPDATE SET
                role = EXCLUDED.role,
                beat_at = EXCLUDED.beat_at,
                metrics = EXCLUDED.metrics
            """,
            (worker_id,),
        )

    try:
        status = read_serving_freshness(DB_URL)
        assert status.latest_worker_beat_at == expected
    finally:
        with psycopg.connect(DB_URL, autocommit=True) as connection:
            connection.execute("DELETE FROM worker_heartbeats WHERE worker_id = %s", (worker_id,))
