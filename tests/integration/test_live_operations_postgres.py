# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.live_operations import (
    PostgresLiveAcquisitionStore,
    PostgresLiveBaselineProjector,
    baseline_boundary_at,
    database_clock,
)
from frontier.domain.digests import Digest
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _source() -> SourceContract:
    return SourceContract(
        source_id="fixture.live-ops",
        display_name="Live operations fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def test_live_store_persists_cross_cycle_backoff_and_honors_longer_provider_delay() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        store = PostgresLiveAcquisitionStore(conn)
        store.upsert_source(_source())

        before = database_clock(conn)
        store.record_fetch_failure("fixture.live-ops", next_retry_at=None)
        after = database_clock(conn)
        first = store.get_source_fetch_state("fixture.live-ops")
        assert first is not None
        assert first.consecutive_failures == 1
        assert first.next_retry_at is not None
        assert first.next_retry_at >= before + timedelta(seconds=60)
        assert first.next_retry_at <= after + timedelta(seconds=60)

        store.record_fetch_failure("fixture.live-ops", next_retry_at=None)
        second_after = database_clock(conn)
        second = store.get_source_fetch_state("fixture.live-ops")
        assert second is not None
        assert second.consecutive_failures == 2
        assert second.next_retry_at is not None
        assert second.next_retry_at >= second_after + timedelta(seconds=119)
        assert second.next_retry_at <= second_after + timedelta(seconds=120)

        provider_retry = database_clock(conn) + timedelta(hours=2)
        store.record_fetch_failure("fixture.live-ops", next_retry_at=provider_retry)
        third = store.get_source_fetch_state("fixture.live-ops")
        assert third is not None
        assert third.consecutive_failures == 3
        assert third.next_retry_at == provider_retry


def test_live_baseline_projector_publishes_only_current_boundary_and_is_idempotent() -> None:
    assert DB_URL is not None
    source_registry_version = Digest("sha256:" + "7" * 64)
    with psycopg.connect(DB_URL) as conn:
        now = database_clock(conn)
        boundary = baseline_boundary_at(now)
        projector = PostgresLiveBaselineProjector(conn)

        first = projector.publish_current_boundary(
            now=now,
            source_registry_version=source_registry_version,
        )
        assert first.boundary == boundary
        assert first.published is True

        second = projector.publish_current_boundary(
            now=now,
            source_registry_version=source_registry_version,
        )
        assert second.boundary == boundary
        assert second.published is False
        assert second.snapshot_id == first.snapshot_id

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id
                FROM baseline_intelligence_snapshots
                WHERE as_of = %s
                ORDER BY snapshot_id
                """,
                (boundary,),
            )
            rows = cur.fetchall()
        assert rows == [(first.snapshot_id,)]


def test_baseline_boundary_rejects_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        baseline_boundary_at(datetime(2026, 9, 11, 2, 9))
