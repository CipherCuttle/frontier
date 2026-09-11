# ruff: noqa: E402
from __future__ import annotations

import os

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
