# ruff: noqa: E402
"""Postgres regression coverage for worker heartbeat liveness semantics."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.acquisition.config import SourceRegistry
from frontier.adapters.postgres.worker_ops import (
    WORKER_HEARTBEAT_STALE_AFTER_SECONDS,
    PostgresWorkerHeartbeatStore,
    build_ops_status,
)
from frontier.domain.digests import sha256_digest

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

ConnectionT = Connection[tuple[object, ...]]


def _connect() -> ConnectionT:
    conn: ConnectionT = psycopg.connect(DB_URL)  # type: ignore[arg-type]
    return conn


def _empty_registry() -> SourceRegistry:
    return SourceRegistry(
        sources={},
        source_registry_version=sha256_digest(b"worker-ops-liveness-test"),
    )


def test_ops_status_counts_only_fresh_heartbeats_as_workers() -> None:
    conn = _connect()
    fresh_worker_id = f"worker.fresh.{uuid4().hex}"
    stale_worker_id = f"worker.stale.{uuid4().hex}"
    now = datetime.now(UTC)
    try:
        before = build_ops_status(conn, _empty_registry(), now=now)
        store = PostgresWorkerHeartbeatStore(conn)
        store.upsert_heartbeat(
            worker_id=stale_worker_id,
            role="ACQUISITION+EXPERIMENT",
            beat_at=now - timedelta(seconds=WORKER_HEARTBEAT_STALE_AFTER_SECONDS + 1),
            metrics={"test": "stale"},
        )
        store.upsert_heartbeat(
            worker_id=fresh_worker_id,
            role="ACQUISITION+EXPERIMENT",
            beat_at=now,
            metrics={"test": "fresh"},
        )

        status = build_ops_status(conn, _empty_registry(), now=now)

        assert status["worker_heartbeat_stale_after_seconds"] == 300.0
        assert status["worker_row_count"] == cast(int, before["worker_row_count"]) + 2
        assert status["worker_count"] == cast(int, before["worker_count"]) + 1
        assert status["stale_worker_count"] == cast(int, before["stale_worker_count"]) + 1
        assert status["worker_count"] + status["stale_worker_count"] == status["worker_row_count"]  # type: ignore[operator]

        latest = cast(dict[str, object], status["heartbeat"])
        assert latest["worker_id"] == fresh_worker_id
        assert latest["freshness"] == "FRESH"
        assert latest["age_seconds"] == 0.0
    finally:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "DELETE FROM worker_heartbeats WHERE worker_id = ANY(%s)",
                ([fresh_worker_id, stale_worker_id],),
            )
        conn.close()
