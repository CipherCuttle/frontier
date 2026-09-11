# ruff: noqa: E402
from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

from scripts.ops.serving_freshness import ServingFreshnessState, read_serving_freshness

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_serving_freshness_probe_is_read_only_and_fails_closed_without_liveness_evidence() -> None:
    assert DB_URL is not None

    status = read_serving_freshness(DB_URL)

    assert status.state is ServingFreshnessState.STALE
    assert status.latest_baseline_as_of is None
    assert status.latest_worker_beat_at is None
    assert status.reasons == ("NO_BASELINE_SNAPSHOT", "NO_WORKER_HEARTBEAT")

    with psycopg.connect(DB_URL, autocommit=True) as connection:
        row = connection.execute("SELECT count(*) FROM baseline_intelligence_snapshots").fetchone()
        assert row is not None
        assert int(row[0]) == 0
        heartbeat_row = connection.execute("SELECT count(*) FROM worker_heartbeats").fetchone()
        assert heartbeat_row is not None
        assert int(heartbeat_row[0]) == 0
