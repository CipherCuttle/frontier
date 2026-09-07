# ruff: noqa: E402
"""Postgres integration tests for the WP9 worker lifecycle.

Requires a migrated FRONTIER_TEST_DATABASE_URL. Covered: advisory singleton
lease exclusivity across connections, heartbeat rows (first write + upsert),
a full worker cycle writing liveness without partial rows, the read-only ops
status snapshot, and stale attempt lease expiry on restart (WP2 adopt/expire).
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
)
from frontier.adapters.postgres.worker_ops import (
    PostgresWorkerHeartbeatStore,
    PostgresWorkerLease,
    PostgresWorkerOpsProbe,
    build_ops_status,
)
from frontier.application.acquisition import AcquisitionResult
from frontier.application.worker import (
    WORKER_ROLE,
    AcquisitionWorker,
    PollCycleResult,
    WorkerLeaseHeldError,
)
from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import sha256_digest
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

ConnectionT = Connection[tuple[object, ...]]


def _source(source_id: str) -> RegisteredSource:
    return RegisteredSource(
        contract=SourceContract(
            source_id=source_id,
            display_name=source_id,
            acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
            signal_roles=(SignalRole.PRIMARY_EMISSION,),
            transport=SourceTransport.REST,
        ),
        endpoint_url=f"https://{source_id}.example/api",
        fallback_urls=(),
        fallback_semantics=None,
        accepted_content_types=("application/json",),
        policy_profile="structured-public-v0",
        authentication="NONE",
        credential_ref=None,
        poll_interval_seconds=60,
        finite_window=True,
        etag_support="UNKNOWN",
        last_modified_support="UNKNOWN",
        raw_contract={},
    )


class _NoopRunner:
    async def acquire(self, source_id: str) -> AcquisitionResult:
        return AcquisitionResult(
            run_id=uuid4(),
            source_id=source_id,
            status=CollectionRunStatus.SUCCESS,
            inserted=0,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=None,
        )


def _connect() -> ConnectionT:
    import psycopg

    conn: ConnectionT = psycopg.connect(DB_URL)  # type: ignore[arg-type]
    return conn


def test_advisory_lease_is_exclusive_across_connections() -> None:
    conn_a = _connect()
    conn_b = _connect()
    try:
        lease_a = PostgresWorkerLease(conn_a)
        lease_b = PostgresWorkerLease(conn_b)
        assert lease_a.acquire(owner="worker-a") is True
        # A second worker must detect the held singleton lease.
        assert lease_b.acquire(owner="worker-b") is False
        # Re-acquire by the owner while still holding it is idempotent.
        assert lease_a.acquire(owner="worker-a") is True
        lease_a.release(owner="worker-a")
        # After release the lease is available again.
        assert lease_b.acquire(owner="worker-b") is True
        lease_b.release(owner="worker-b")
    finally:
        conn_a.close()
        conn_b.close()


def test_heartbeat_upsert_writes_single_mutable_row() -> None:
    conn = _connect()
    try:
        store = PostgresWorkerHeartbeatStore(conn)
        worker_id = f"worker.{uuid4().hex}"
        first_at = datetime.now(UTC) - timedelta(seconds=30)
        store.upsert_heartbeat(
            worker_id=worker_id,
            role=WORKER_ROLE,
            beat_at=first_at,
            metrics={"cycle_duration_ms": 1.0},
        )
        second_at = datetime.now(UTC)
        store.upsert_heartbeat(
            worker_id=worker_id,
            role=WORKER_ROLE,
            beat_at=second_at,
            metrics={"cycle_duration_ms": 2.0},
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), max(beat_at) FROM worker_heartbeats WHERE worker_id = %s",
                (worker_id,),
            )
            row = cur.fetchone()
            assert row is not None
            count, beat_at = row
            assert count == 1  # upsert, never accumulate
            assert beat_at == second_at
            cur.execute("SELECT metrics FROM worker_heartbeats WHERE worker_id = %s", (worker_id,))
            metrics_row = cur.fetchone()
            assert metrics_row is not None
            assert metrics_row[0] == {"cycle_duration_ms": 2.0}
    finally:
        conn.close()


def test_worker_cycle_writes_heartbeat_and_no_partial_rows() -> None:
    conn = _connect()
    worker_id = f"worker.{uuid4().hex}"
    source_id = f"fixture.worker_lifecycle.{uuid4().hex}"
    try:
        store = PostgresEvidenceStore(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM collection_runs")
            runs_before = int(cur.fetchone()[0])  # type: ignore[index]
        worker = AcquisitionWorker(
            registry=SourceRegistry(
                sources={source_id: _source(source_id)},
                source_registry_version=sha256_digest(source_id.encode()),
            ),
            repository=store,
            service=_NoopRunner(),
            clock=lambda: datetime.now(UTC),
            worker_id=worker_id,
            lease=PostgresWorkerLease(conn),
            heartbeat_store=PostgresWorkerHeartbeatStore(conn),
            ops_probe=PostgresWorkerOpsProbe(conn),
        )
        cycle = _run_cycle(worker.run_once())
        assert cycle.errors == ()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, metrics FROM worker_heartbeats WHERE worker_id = %s",
                (worker_id,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == WORKER_ROLE
            cur.execute("SELECT count(*) FROM collection_runs")
            runs_after = int(cur.fetchone()[0])  # type: ignore[operator,index]
        # The noop runner creates no runs: no partial cycle rows were written.
        assert runs_after == runs_before
        _ = cycle
    finally:
        conn.close()


def test_second_worker_rejected_mid_cycle_leaves_state_consistent() -> None:
    conn = _connect()
    conn_b = _connect()
    worker_id = f"worker.{uuid4().hex}"
    try:
        store = PostgresEvidenceStore(conn)
        lease_b = PostgresWorkerLease(conn_b)
        # Simulate a second live worker holding the singleton lease.
        assert lease_b.acquire(owner="worker-b") is True
        worker = AcquisitionWorker(
            registry=SourceRegistry(
                sources={},
                source_registry_version=sha256_digest(b"second-worker"),
            ),
            repository=store,
            service=_NoopRunner(),
            clock=lambda: datetime.now(UTC),
            worker_id=worker_id,
            lease=PostgresWorkerLease(conn),
            heartbeat_store=PostgresWorkerHeartbeatStore(conn),
        )
        with pytest.raises(WorkerLeaseHeldError):
            _run(worker.run_once())
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM worker_heartbeats WHERE worker_id = %s",
                (worker_id,),
            )
            assert int(cur.fetchone()[0]) == 0  # type: ignore[index]
    finally:
        conn.close()
        conn_b.close()


def test_ops_status_snapshot_is_read_only_and_complete() -> None:
    conn = _connect()
    worker_id = f"worker.{uuid4().hex}"
    source_id = f"fixture.worker_lifecycle.{uuid4().hex}"
    try:
        store = PostgresEvidenceStore(conn)
        worker = AcquisitionWorker(
            registry=SourceRegistry(
                sources={source_id: _source(source_id)},
                source_registry_version=sha256_digest(source_id.encode()),
            ),
            repository=store,
            service=_NoopRunner(),
            clock=lambda: datetime.now(UTC),
            worker_id=worker_id,
            lease=PostgresWorkerLease(conn),
            heartbeat_store=PostgresWorkerHeartbeatStore(conn),
            ops_probe=PostgresWorkerOpsProbe(conn),
        )
        _run(worker.run_once())
        registry = SourceRegistry(
            sources={source_id: _source(source_id)},
            source_registry_version=sha256_digest(source_id.encode()),
        )
        status = build_ops_status(conn, registry, now=datetime.now(UTC))
        assert status["drift_state"] in {"OK", "DRIFTED", "NOT_DURABLE", "UNBOUND"}
        heartbeat = cast(dict[str, object], status["heartbeat"])
        assert heartbeat["worker_id"] == worker_id
        assert heartbeat["role"] == WORKER_ROLE
        assert isinstance(heartbeat["age_seconds"], float)
        source_rows = cast(list[dict[str, object]], status["sources"])
        entry = next(row for row in source_rows if row["source_id"] == source_id)
        assert entry["freshness"] in {"FRESH", "DEGRADED", "STALE", "UNKNOWN"}
        counts = cast(dict[str, int], status["artifact_counts"])
        assert all(isinstance(value, int) for value in counts.values())
        attempt_counts = cast(dict[str, int], status["attempt_state_counts"])
        assert all(
            isinstance(status_value, str) and isinstance(amount, int)
            for status_value, amount in attempt_counts.items()
        )
        _ = worker_id, source_id
    finally:
        conn.close()


def test_stale_attempt_lease_expired_on_restart() -> None:
    conn = _connect()
    try:
        attempts = PostgresExperimentAttemptRepository(conn)
        now = datetime.now(UTC)
        as_of = datetime.fromtimestamp(
            (int(now.timestamp()) // 300) * 300 - (int(uuid4().hex[:8], 16) % 24_000) * 300,
            tz=UTC,
        )
        pending = ExperimentRunAttempt(
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=as_of,
            attempt_no=1,
            status=ExperimentAttemptStatus.PENDING,
        )
        attempts.record_attempt(pending)
        stale_lease = now - timedelta(days=1)
        assert attempts.claim(
            pending.attempt_id,
            owner="crashed-worker",
            lease_expires_at=stale_lease,
            now=now,
        )
        expired = attempts.expire_stale(now=now)
        assert any(row.attempt_no == 1 for row in expired)
        latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, as_of)
        assert latest is not None
        assert latest.status is ExperimentAttemptStatus.EXPIRED
        assert latest.lease_owner is None
    finally:
        conn.close()


def _run(awaitable: object) -> object:
    return asyncio.run(awaitable)  # type: ignore[arg-type]


def _run_cycle(awaitable: object) -> PollCycleResult:
    return asyncio.run(awaitable)  # type: ignore[arg-type,return-value]
