"""Unit tests for WP9 worker lifecycle: heartbeat, lease, shutdown, isolation.

These tests exercise the lifecycle machinery with injected fakes only (no real
signals, no Postgres): the shutdown path is simulated through the injected
``should_stop`` flag, the singleton lease through a fake advisory-lock gateway,
and the DB liveness surfaces through fake stores.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.application.acquisition import AcquisitionResult
from frontier.application.experiment_orchestration import (
    ExperimentCycleAction,
    ExperimentOrchestrator,
    derive_experiment_boundary,
)
from frontier.application.worker import WORKER_ROLE, AcquisitionWorker, WorkerLeaseHeldError
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.intelligence import BaselineObservationInput
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


class MemoryWorkerRepository:
    def __init__(self) -> None:
        self.upserted: list[str] = []

    def upsert_source(self, source: SourceContract) -> None:
        self.upserted.append(source.source_id)

    def get_source_fetch_state(self, source_id: str) -> None:
        return None


class OkRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def acquire(self, source_id: str) -> AcquisitionResult:
        self.calls.append(source_id)
        return AcquisitionResult(
            run_id=uuid4(),
            source_id=source_id,
            status=CollectionRunStatus.SUCCESS,
            inserted=1,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=None,
        )


class FlakyRunner(OkRunner):
    """Acquire runner that raises for designated sources (malformed items)."""

    def __init__(self, raise_for: set[str]) -> None:
        super().__init__()
        self.raise_for = raise_for

    async def acquire(self, source_id: str) -> AcquisitionResult:
        self.calls.append(source_id)
        if source_id in self.raise_for:
            raise ValueError(f"malformed item in {source_id}")
        return AcquisitionResult(
            run_id=uuid4(),
            source_id=source_id,
            status=CollectionRunStatus.SUCCESS,
            inserted=1,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=None,
        )


class ExplodingRunner:
    async def acquire(self, source_id: str) -> AcquisitionResult:
        raise RuntimeError("boom")


@dataclass
class FakeLease:
    held_by_other: bool = False
    acquire_calls: int = 0
    last_owner: str | None = None
    released: bool = False

    def acquire(self, *, owner: str) -> bool:
        self.acquire_calls += 1
        self.last_owner = owner
        return not self.held_by_other

    def release(self, *, owner: str) -> None:
        assert owner == self.last_owner
        self.released = True


@dataclass
class FakeHeartbeatStore:
    calls: list[dict[str, object]]

    def __init__(self) -> None:
        self.calls = []

    def upsert_heartbeat(
        self,
        *,
        worker_id: str,
        role: str,
        beat_at: datetime,
        metrics: dict[str, object],
    ) -> None:
        self.calls.append(
            {
                "worker_id": worker_id,
                "role": role,
                "beat_at": beat_at,
                "metrics": dict(metrics),
            }
        )


class FakeProbe:
    def probe_metrics(self) -> dict[str, object]:
        return {"latest_baseline_as_of": "2026-09-05T19:55:00+00:00"}


def registered_source(source_id: str, poll_interval_seconds: int = 60) -> RegisteredSource:
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
        poll_interval_seconds=poll_interval_seconds,
        finite_window=True,
        etag_support="UNKNOWN",
        last_modified_support="UNKNOWN",
        raw_contract={},
    )


def registry(*source_ids: str) -> SourceRegistry:
    return SourceRegistry(
        sources={source_id: registered_source(source_id) for source_id in source_ids},
        source_registry_version=sha256_digest(b"worker-lifecycle-test"),
    )


def build_worker(
    sources: SourceRegistry,
    runner: OkRunner | ExplodingRunner,
    *,
    lease: FakeLease | None = None,
    heartbeat: FakeHeartbeatStore | None = None,
    probe: FakeProbe | None = None,
    orchestrator: ExperimentOrchestrator | None = None,
    sleep: object = None,
    idle_seconds: float = 30.0,
) -> AcquisitionWorker:
    kwargs: dict[str, object] = {}
    if lease is not None:
        kwargs["lease"] = lease
    if heartbeat is not None:
        kwargs["heartbeat_store"] = heartbeat
    if probe is not None:
        kwargs["ops_probe"] = probe
    if orchestrator is not None:
        kwargs["experiment_orchestrator"] = orchestrator
    if sleep is not None:
        kwargs["sleep"] = sleep
    return AcquisitionWorker(
        registry=sources,
        repository=MemoryWorkerRepository(),  # type: ignore[arg-type]
        service=runner,  # type: ignore[arg-type]
        clock=lambda: NOW,
        idle_seconds=idle_seconds,
        worker_id="worker-a",
        **kwargs,  # type: ignore[arg-type]
    )


def test_heartbeat_upserted_each_cycle_with_metrics() -> None:
    heartbeat = FakeHeartbeatStore()
    worker = build_worker(
        registry("source.alpha"), OkRunner(), heartbeat=heartbeat, probe=FakeProbe()
    )
    cycle = asyncio.run(worker.run_once())
    assert len(heartbeat.calls) == 1
    beat = heartbeat.calls[0]
    assert beat["worker_id"] == "worker-a"
    assert beat["role"] == WORKER_ROLE == "ACQUISITION+EXPERIMENT"
    assert beat["beat_at"] == NOW
    metrics = beat["metrics"]
    assert isinstance(metrics, dict)
    assert "cycle_duration_ms" in metrics
    assert metrics["acquired_sources"] == 1
    assert metrics["cadence_slo"] == {"source.alpha": "UNKNOWN"}
    assert metrics["retry_backlog"] == {}
    assert metrics["experiment"] is None
    assert metrics["latest_baseline_as_of"] == "2026-09-05T19:55:00+00:00"
    assert cycle.errors == ()


def test_lease_acquired_and_released_per_cycle() -> None:
    lease = FakeLease()
    worker = build_worker(registry("source.alpha"), OkRunner(), lease=lease)
    asyncio.run(worker.run_once())
    assert lease.acquire_calls == 1
    assert lease.last_owner == "worker-a"
    assert lease.released is True


def test_second_worker_detects_lease_held_and_raises() -> None:
    lease = FakeLease(held_by_other=True)
    worker = build_worker(registry("source.alpha"), OkRunner(), lease=lease)
    raised = False
    try:
        asyncio.run(worker.run_once())
    except WorkerLeaseHeldError as error:
        raised = True
        assert error.ERROR_CODE == "WORKER_LEASE_HELD"
    assert raised


def test_lease_released_even_when_cycle_fails() -> None:
    lease = FakeLease()
    worker = build_worker(registry("source.alpha"), ExplodingRunner(), lease=lease)
    with contextlib.suppress(RuntimeError):
        asyncio.run(worker.run_once())
    assert lease.released is True


def test_per_source_error_isolation_keeps_cycle_alive() -> None:
    runner = FlakyRunner({"source.bad"})
    heartbeat = FakeHeartbeatStore()
    worker = build_worker(registry("source.bad", "source.good"), runner, heartbeat=heartbeat)
    cycle = asyncio.run(worker.run_once())
    # Both sources attempted; the malformed one is isolated, not fatal.
    assert sorted(runner.calls) == ["source.bad", "source.good"]
    assert cycle.errors == (("source.bad", "ValueError: malformed item in source.bad"),)
    assert len(heartbeat.calls) == 1
    metrics = cast("dict[str, object]", heartbeat.calls[0]["metrics"])
    assert metrics["isolated_errors"] == [
        {"source_id": "source.bad", "error": "ValueError: malformed item in source.bad"}
    ]


def test_transient_connection_error_propagates_for_reconnect() -> None:
    lease = FakeLease()
    worker = AcquisitionWorker(
        registry=registry("source.alpha"),
        repository=MemoryWorkerRepository(),  # type: ignore[arg-type]
        service=ExplodingRunner(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        worker_id="worker-a",
        lease=lease,
        is_transient_connection_error=lambda error: isinstance(error, RuntimeError),
    )
    try:
        asyncio.run(worker.run_once())
    except RuntimeError:
        pass
    else:
        raise AssertionError("transient connection error must propagate")
    # The cycle lease was still released so reconnect can re-acquire it.
    assert lease.released is True


def test_run_forever_shutdown_flag_exits_cleanly() -> None:
    lease = FakeLease()
    heartbeat = FakeHeartbeatStore()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    worker = build_worker(
        registry("source.alpha"), OkRunner(), lease=lease, heartbeat=heartbeat, sleep=fake_sleep
    )

    asyncio.run(worker.run_forever(None, should_stop=lambda: len(heartbeat.calls) >= 1))
    assert len(heartbeat.calls) == 1
    assert lease.acquire_calls == 1
    assert lease.released is True
    assert sleeps == []  # never slept past the first cycle


def test_run_forever_survives_failed_cycle_with_bounded_backoff() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    class BrokenRepository:
        # Cycle-level failure (not per-source isolated): the schedule scan
        # itself fails, exercising the reconnect/backoff path.
        def upsert_source(self, source: SourceContract) -> None:
            raise RuntimeError("database connection lost")

        def get_source_fetch_state(self, source_id: str) -> None:
            return None

    worker = AcquisitionWorker(
        registry=registry("source.alpha"),
        repository=BrokenRepository(),  # type: ignore[arg-type]
        service=OkRunner(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        sleep=fake_sleep,
        idle_seconds=0.1,
        worker_id="worker-a",
    )
    cycles = {"n": 0}
    original_run_once = worker.run_once

    async def counting_run_once() -> object:
        cycles["n"] += 1
        return await original_run_once()

    worker.run_once = counting_run_once  # type: ignore[method-assign]

    def stop_after_two_failures() -> bool:
        return cycles["n"] >= 2

    asyncio.run(worker.run_forever(None, should_stop=stop_after_two_failures))
    assert cycles["n"] == 2
    assert sleeps == [0.2]  # idle 0.1 * 2**1: bounded exponential backoff


class RecordingAttemptRepository:
    """Minimal in-memory WP2 attempt lifecycle for boundary uniqueness."""

    def __init__(self) -> None:
        self.rows: dict[str, ExperimentRunAttempt] = {}
        self.recorded = 0

    def latest_attempt(self, experiment_id: str, as_of: datetime) -> ExperimentRunAttempt | None:
        matching = [
            row
            for row in self.rows.values()
            if row.experiment_id == experiment_id and row.as_of == as_of
        ]
        if not matching:
            return None
        return max(matching, key=lambda row: row.attempt_no)

    def record_attempt(self, attempt: ExperimentRunAttempt) -> bool:
        self.recorded += 1
        self.rows[attempt.attempt_id] = attempt
        return True

    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool:
        row = self.rows[attempt_id]
        self.rows[attempt_id] = replace(
            row,
            status=ExperimentAttemptStatus.RUNNING,
            lease_owner=owner,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now,
        )
        return True

    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool:
        return True

    def finish(
        self,
        attempt_id: str,
        *,
        owner: str,
        status: ExperimentAttemptStatus,
        detail: str | None,
        at: datetime,
    ) -> bool:
        row = self.rows[attempt_id]
        self.rows[attempt_id] = replace(
            row,
            status=status,
            detail=detail,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=at,
        )
        return True

    def expire_stale(
        self, *, now: datetime, detail: str = "lease expired"
    ) -> tuple[ExperimentRunAttempt, ...]:
        return ()


class OneShotPersistence:
    """First boundary consult returns a completed DEV run; counts consultations."""

    RUN_ID = "shadowrun_" + "a" * 64

    def __init__(self) -> None:
        self.consulted: list[datetime] = []

    def persist(self, run: object, *, run_class: str) -> str:
        raise AssertionError("completed boundary must not re-execute the engine")

    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None:
        self.consulted.append(as_of)
        return (self.RUN_ID, "DEV", "RAN")


class UnusedBaselineRepository:
    """Never reached when a boundary is already complete."""

    def list_baseline_observations_as_of(
        self, as_of: datetime
    ) -> tuple[BaselineObservationInput, ...]:
        raise AssertionError("completed boundary must not re-read the baseline repository")

    def list_grouping_relations_as_of(self, as_of: datetime) -> tuple[()]:
        raise AssertionError("completed boundary must not re-read the baseline repository")

    def list_enabled_source_ids(self) -> tuple[()]:
        raise AssertionError("completed boundary must not re-read the baseline repository")

    def list_latest_health_as_of(self, as_of: datetime) -> tuple[()]:
        raise AssertionError("completed boundary must not re-read the baseline repository")


def _orchestrator(
    attempts: RecordingAttemptRepository, persistence: OneShotPersistence
) -> ExperimentOrchestrator:
    return ExperimentOrchestrator(
        attempts=attempts,  # type: ignore[arg-type]
        baseline_repository=UnusedBaselineRepository(),  # type: ignore[arg-type]
        persistence=persistence,  # type: ignore[arg-type]
        source_registry_version=Digest(sha256_digest(b"lifecycle-test").value),
        run_class="DEV",
        worker_id="worker-a",
        clock=lambda: NOW,
    )


def test_duplicate_cycle_invocation_cannot_double_execute_boundary() -> None:
    """Regression (WP9): a duplicate cycle cannot double-execute a boundary.

    The worker drives the orchestrator twice against an unchanged clock; the
    attempt-lifecycle uniqueness short-circuits the second cycle into
    ALREADY_COMPLETE without touching the paired-experiment engine again.
    """
    attempts = RecordingAttemptRepository()
    persistence = OneShotPersistence()
    orchestrator = _orchestrator(attempts, persistence)
    heartbeat = FakeHeartbeatStore()
    worker = build_worker(
        registry("source.alpha"), OkRunner(), heartbeat=heartbeat, orchestrator=orchestrator
    )
    first = asyncio.run(worker.run_once())
    second = asyncio.run(worker.run_once())
    assert first.experiment is not None and second.experiment is not None
    assert first.experiment.action is ExperimentCycleAction.ALREADY_COMPLETE
    assert second.experiment.action is ExperimentCycleAction.ALREADY_COMPLETE
    # The paired-experiment engine was consulted exactly once for the boundary.
    assert persistence.consulted == [derive_experiment_boundary(NOW)]
    assert attempts.recorded == 1
    # And every cycle still beats the heartbeat.
    assert len(heartbeat.calls) == 2


def test_cli_worker_composition_wires_experiment_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (H-01): the shipped CLI worker composition builds the WP2
    orchestrator from the canonical PG repositories and passes it to the
    AcquisitionWorker (it is never None in production wiring)."""
    import psycopg

    import frontier.adapters.postgres as postgres_pkg
    import frontier.adapters.postgres.experiment_attempts as attempts_mod
    import frontier.adapters.postgres.intelligence as intelligence_mod
    import frontier.adapters.postgres.readiness as readiness_mod
    import frontier.adapters.postgres.worker_ops as worker_ops_mod
    import frontier.cli.main as cli_main
    from frontier.cli.main import _build_worker_components  # pyright: ignore[reportPrivateUsage]

    class _FakeConn:
        def close(self) -> None: ...

    def _fake_connect(url: str) -> _FakeConn:
        return _FakeConn()

    def _no_policy(root: Path) -> None:
        return None

    registry = SourceRegistry(sources={}, source_registry_version=sha256_digest(b"cli-worker-test"))

    def _registry(root: Path) -> SourceRegistry:
        return registry

    def _no_fetcher(policy: object) -> None:
        return None

    def _no_op(*args: object, **kwargs: object) -> None:
        return None

    def _stub(*args: object, **kwargs: object) -> object:
        return object()

    monkeypatch.setattr(psycopg, "connect", _fake_connect)
    monkeypatch.setattr(cli_main, "load_fetch_policy", _no_policy)
    monkeypatch.setattr(cli_main, "load_source_registry", _registry)
    monkeypatch.setattr(cli_main, "SecureHttpFetcher", _no_fetcher)
    monkeypatch.setattr(cli_main, "AcquisitionService", _stub)
    monkeypatch.setattr(readiness_mod, "verify_database_readiness", _no_op)
    monkeypatch.setattr(postgres_pkg, "PostgresEvidenceStore", _stub, raising=False)
    monkeypatch.setattr(worker_ops_mod, "PostgresWorkerLease", _stub)
    monkeypatch.setattr(worker_ops_mod, "PostgresWorkerHeartbeatStore", _stub)
    monkeypatch.setattr(worker_ops_mod, "PostgresWorkerOpsProbe", _stub)
    monkeypatch.setattr(attempts_mod, "PostgresExperimentAttemptRepository", _stub)
    monkeypatch.setattr(attempts_mod, "PostgresFreezeBindingResolver", _stub)
    monkeypatch.setattr(attempts_mod, "PostgresShadowRunPersister", _stub)
    monkeypatch.setattr(intelligence_mod, "PostgresBaselineIntelligenceRepository", _stub)

    _conn, worker = _build_worker_components(
        "postgresql://fake.invalid/frontier",
        Path("."),
        worker_id="frontier-worker",
        idle_seconds=30.0,
    )
    orchestrator = worker._experiment_orchestrator  # pyright: ignore[reportPrivateUsage]
    assert orchestrator is not None
    assert isinstance(orchestrator, ExperimentOrchestrator)
    assert orchestrator._run_class == "DEV"  # pyright: ignore[reportPrivateUsage]
    # dev run-class default; confirmatory stays gated
    assert orchestrator._canonical_context is False  # pyright: ignore[reportPrivateUsage]


def test_run_forever_with_orchestrator_writes_experiment_metrics() -> None:
    attempts = RecordingAttemptRepository()
    persistence = OneShotPersistence()
    heartbeat = FakeHeartbeatStore()

    async def fake_sleep(seconds: float) -> None:
        return None

    worker = build_worker(
        registry("source.alpha"),
        OkRunner(),
        heartbeat=heartbeat,
        orchestrator=_orchestrator(attempts, persistence),
        sleep=fake_sleep,
    )
    asyncio.run(worker.run_forever(None, should_stop=lambda: len(heartbeat.calls) >= 1))
    metrics = cast("dict[str, object]", heartbeat.calls[0]["metrics"])
    assert metrics["experiment"] == {
        "action": "ALREADY_COMPLETE",
        "boundary": derive_experiment_boundary(NOW).isoformat(),
        "attempt_status": "DONE",
        "run_id": OneShotPersistence.RUN_ID,
    }
