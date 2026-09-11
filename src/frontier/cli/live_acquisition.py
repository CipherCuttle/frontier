from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.acquisition.fetcher import SecureHttpFetcher
from frontier.adapters.acquisition.live_compat import LiveSourceCompatibilityFetcher
from frontier.adapters.postgres.live_operations import (
    LiveBaselineProjection,
    PostgresLiveAcquisitionStore,
    PostgresLiveBaselineProjector,
    database_clock,
)
from frontier.adapters.postgres.readiness import (
    DatabaseReadinessError,
    verify_database_readiness,
)
from frontier.adapters.postgres.worker_ops import (
    PostgresWorkerHeartbeatStore,
    PostgresWorkerLease,
    PostgresWorkerOpsProbe,
)
from frontier.application.acquisition import AcquisitionService
from frontier.application.worker import AcquisitionWorker, PollCycleResult
from frontier.domain.collection import CollectionRunStatus

LIVE_WORKER_ROLE = "ACQUISITION"
_MAX_RECONNECT_FAILURES = 5
_SHUTDOWN_POLL_SECONDS = 1.0


def require_direct_session_database_url(database_url: str) -> str:
    """Reject transaction-pooler URLs for the session-lock live runtime."""
    try:
        params = conninfo_to_dict(database_url)
    except psycopg.ProgrammingError as error:
        raise ValueError(
            "live acquisition database URL is not valid Postgres connection info"
        ) from error
    host_value = params.get("host")
    if not isinstance(host_value, str) or not host_value or "," in host_value:
        raise ValueError("live acquisition requires one explicit direct database host")
    normalized = host_value.strip().lower()
    if "-pooler" in normalized:
        raise ValueError(
            "live acquisition forbids transaction-pooler hosts; use a direct/session endpoint"
        )
    return normalized


def is_transient_database_error(error: BaseException) -> bool:
    if isinstance(error, psycopg.OperationalError):
        return True
    return isinstance(error, DatabaseReadinessError) and isinstance(
        error.__cause__, psycopg.OperationalError
    )


def cycle_has_failure(cycle: PollCycleResult) -> bool:
    return bool(cycle.errors) or any(
        result.status is CollectionRunStatus.FAILED for result in cycle.acquired
    )


class ShutdownRequest:
    def __init__(self) -> None:
        self.stop = False

    def __call__(self) -> bool:
        return self.stop


def _install_signal_handlers(shutdown: ShutdownRequest) -> None:
    def handler(signum: int, frame: object) -> None:
        shutdown.stop = True

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _timestamp(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _heartbeat_metrics(
    cycle: PollCycleResult,
    projection: LiveBaselineProjection,
    probe: PostgresWorkerOpsProbe,
) -> dict[str, object]:
    metrics: dict[str, object] = {
        "authority": "ACQUISITION_ONLY",
        "experiment": None,
        "cycle_duration_ms": round(cycle.duration_seconds * 1000, 3),
        "acquired_sources": len(cycle.acquired),
        "inserted_total": sum(result.inserted for result in cycle.acquired),
        "duplicates_total": sum(result.duplicates for result in cycle.acquired),
        "rejected_total": sum(result.rejected for result in cycle.acquired),
        "failed_sources": sorted(
            result.source_id
            for result in cycle.acquired
            if result.status is CollectionRunStatus.FAILED
        ),
        "isolated_errors": [
            {"source_id": source_id, "error": error} for source_id, error in cycle.errors
        ],
        "baseline": {
            "boundary": projection.boundary.isoformat(),
            "published": projection.published,
            "snapshot_id": projection.snapshot_id,
        },
        "cadence_slo": {
            schedule.source_id: schedule.cadence_slo.value for schedule in cycle.schedules
        },
        "retry_backlog": {
            schedule.source_id: _timestamp(schedule.next_retry_at)
            for schedule in cycle.schedules
            if schedule.next_retry_at is not None
        },
    }
    metrics.update(probe.probe_metrics())
    return metrics


def _cycle_payload(
    cycle: PollCycleResult,
    projection: LiveBaselineProjection,
    *,
    worker_id: str,
) -> dict[str, object]:
    return {
        "authority": "ACQUISITION_ONLY",
        "worker_id": worker_id,
        "started_at": cycle.started_at.isoformat(),
        "completed_at": cycle.completed_at.isoformat(),
        "baseline_boundary": projection.boundary.isoformat(),
        "baseline_published": projection.published,
        "baseline_snapshot_id": projection.snapshot_id,
        "acquired": [
            {
                "source_id": result.source_id,
                "status": result.status.value,
                "inserted": result.inserted,
                "duplicates": result.duplicates,
                "rejected": result.rejected,
                "failure_code": result.failure_code,
            }
            for result in cycle.acquired
        ],
        "skipped_not_due": list(cycle.skipped_not_due),
        "errors": [{"source_id": source_id, "error": error} for source_id, error in cycle.errors],
        "experiment": None,
    }


async def _run_connected(
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    config_root: Path,
    worker_id: str,
    idle_seconds: float,
    once: bool,
    shutdown: ShutdownRequest,
    on_successful_cycle: Callable[[], None],
) -> int:
    policy = load_fetch_policy(config_root)
    registry = load_source_registry(config_root)
    store = PostgresLiveAcquisitionStore(connection)
    service = AcquisitionService(
        registry=registry,
        policy=policy,
        fetcher=LiveSourceCompatibilityFetcher(SecureHttpFetcher(policy)),
        repository=store,
    )
    worker = AcquisitionWorker(
        registry=registry,
        repository=store,
        service=service,
        idle_seconds=idle_seconds,
        worker_id=worker_id,
        experiment_orchestrator=None,
        lease=None,
        heartbeat_store=None,
        ops_probe=None,
        is_transient_connection_error=lambda error: isinstance(error, psycopg.OperationalError),
    )
    projector = PostgresLiveBaselineProjector(connection)
    heartbeat = PostgresWorkerHeartbeatStore(connection)
    probe = PostgresWorkerOpsProbe(connection)

    while not shutdown.stop:
        cycle = await worker.run_once()
        now = database_clock(connection)
        projection = projector.publish_current_boundary(
            now=now,
            source_registry_version=registry.source_registry_version,
        )
        heartbeat.upsert_heartbeat(
            worker_id=worker_id,
            role=LIVE_WORKER_ROLE,
            beat_at=now,
            metrics=_heartbeat_metrics(cycle, projection, probe),
        )
        on_successful_cycle()
        print(
            json.dumps(
                _cycle_payload(cycle, projection, worker_id=worker_id),
                sort_keys=True,
            ),
            flush=True,
        )

        if once:
            return 2 if cycle_has_failure(cycle) else 0

        remaining = worker.seconds_until_next_cycle()
        while remaining > 0 and not shutdown.stop:
            chunk = min(remaining, _SHUTDOWN_POLL_SECONDS)
            await asyncio.sleep(chunk)
            remaining -= chunk
    return 0


def run_live_acquisition(
    *,
    database_url: str,
    config_root: Path,
    worker_id: str,
    idle_seconds: float,
    once: bool,
) -> int:
    require_direct_session_database_url(database_url)
    if idle_seconds <= 0:
        raise ValueError("idle_seconds must be positive")

    shutdown = ShutdownRequest()
    _install_signal_handlers(shutdown)
    reconnect_failures = 0

    def reset_reconnect_failures() -> None:
        nonlocal reconnect_failures
        reconnect_failures = 0

    while not shutdown.stop:
        connection: psycopg.Connection[tuple[object, ...]] | None = None
        lease: PostgresWorkerLease | None = None
        lease_acquired = False
        try:
            connection = psycopg.connect(database_url)
            verify_database_readiness(connection)
            lease = PostgresWorkerLease(connection)
            lease_acquired = lease.acquire(owner=worker_id)
            if not lease_acquired:
                print(
                    json.dumps(
                        {"error": "WORKER_LEASE_HELD", "worker_id": worker_id},
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 3

            result = asyncio.run(
                _run_connected(
                    connection,
                    config_root=config_root,
                    worker_id=worker_id,
                    idle_seconds=idle_seconds,
                    once=once,
                    shutdown=shutdown,
                    on_successful_cycle=reset_reconnect_failures,
                )
            )
            return result
        except (psycopg.OperationalError, DatabaseReadinessError) as error:
            if not is_transient_database_error(error):
                raise ValueError(str(error)) from error
            reconnect_failures += 1
            if once or reconnect_failures > _MAX_RECONNECT_FAILURES:
                print(
                    json.dumps(
                        {
                            "error": "LIVE_ACQUISITION_DB_UNREACHABLE",
                            "attempts": reconnect_failures,
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 4
            delay = min(30.0, 2.0**reconnect_failures)
            print(
                json.dumps(
                    {
                        "warning": "LIVE_ACQUISITION_DB_RECONNECT",
                        "attempt": reconnect_failures,
                        "delay_seconds": delay,
                        "error_type": type(error).__name__,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
        finally:
            if lease is not None and lease_acquired and connection is not None:
                with suppress(psycopg.Error, RuntimeError):
                    # A dead connection already releases its session advisory
                    # lock; never mask the reconnect path with cleanup failure.
                    lease.release(owner=worker_id)
            if connection is not None:
                connection.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m frontier.cli.live_acquisition")
    parser.add_argument("--config-root", type=Path, default=Path("."))
    parser.add_argument("--idle-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--worker-id",
        default=os.getenv(
            "FRONTIER_WORKER_ID",
            f"frontier-live-acquisition-{socket.gethostname()}",
        ),
    )
    args = parser.parse_args()
    database_url = os.getenv("FRONTIER_DATABASE_URL_DIRECT")
    if not database_url:
        print(
            json.dumps(
                {
                    "error": "LIVE_ACQUISITION_CONFIGURATION_INVALID",
                    "detail": "FRONTIER_DATABASE_URL_DIRECT is required",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        return run_live_acquisition(
            database_url=database_url,
            config_root=args.config_root,
            worker_id=args.worker_id,
            idle_seconds=args.idle_seconds,
            once=args.once,
        )
    except ValueError as error:
        print(
            json.dumps(
                {
                    "error": "LIVE_ACQUISITION_CONFIGURATION_INVALID",
                    "detail": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
