from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.application.acquisition import AcquisitionResult
from frontier.application.acquisition_state import SourceFetchState
from frontier.application.experiment_orchestration import (
    ExperimentCycleResult,
    ExperimentOrchestrator,
)
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.source import SourceContract

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


class AcquisitionRunner(Protocol):
    async def acquire(self, source_id: str) -> AcquisitionResult: ...


class WorkerRepository(Protocol):
    def upsert_source(self, source: SourceContract) -> None: ...
    def get_source_fetch_state(self, source_id: str) -> SourceFetchState | None: ...


class WorkerLease(Protocol):
    """Singleton cycle lease backed by a Postgres advisory lock (WP9)."""

    def acquire(self, *, owner: str) -> bool: ...
    def release(self, *, owner: str) -> None: ...


class WorkerHeartbeatStore(Protocol):
    """Mutable worker-liveness surface (WP1 ``worker_heartbeats`` table)."""

    def upsert_heartbeat(
        self,
        *,
        worker_id: str,
        role: str,
        beat_at: datetime,
        metrics: dict[str, object],
    ) -> None: ...


class WorkerOpsProbe(Protocol):
    """Cheap read-only enrichment of heartbeat metrics (WP9)."""

    def probe_metrics(self) -> dict[str, object]: ...


class WorkerLeaseHeldError(RuntimeError):
    """A second worker detected the singleton lease already held."""

    ERROR_CODE = "WORKER_LEASE_HELD"


WORKER_ROLE = "ACQUISITION+EXPERIMENT"
_SHUTDOWN_POLL_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0
_MAX_BACKOFF_SHIFT = 6

_LOG = logging.getLogger(__name__)


class CadenceSlo(StrEnum):
    UNKNOWN = "UNKNOWN"
    OK = "OK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"


@dataclass(frozen=True, slots=True)
class SourceSchedule:
    source_id: str
    due: bool
    due_at: datetime | None
    last_success_at: datetime | None
    next_retry_at: datetime | None
    consecutive_failures: int
    cadence_slo: CadenceSlo
    lateness_seconds: float | None


@dataclass(frozen=True, slots=True)
class PollCycleResult:
    started_at: datetime
    completed_at: datetime
    acquired: tuple[AcquisitionResult, ...]
    skipped_not_due: tuple[str, ...]
    schedules: tuple[SourceSchedule, ...]
    experiment: ExperimentCycleResult | None = None
    errors: tuple[tuple[str, str], ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.completed_at - self.started_at).total_seconds())


CycleObserver = Callable[[PollCycleResult], None]


class AcquisitionWorker:
    def __init__(
        self,
        *,
        registry: SourceRegistry,
        repository: WorkerRepository,
        service: AcquisitionRunner,
        clock: Clock | None = None,
        sleep: Sleep | None = None,
        idle_seconds: float = 30.0,
        experiment_orchestrator: ExperimentOrchestrator | None = None,
        worker_id: str = "frontier-worker",
        lease: WorkerLease | None = None,
        heartbeat_store: WorkerHeartbeatStore | None = None,
        ops_probe: WorkerOpsProbe | None = None,
        is_transient_connection_error: Callable[[Exception], bool] | None = None,
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        if not worker_id:
            raise ValueError("worker_id must be non-empty")
        self._registry = registry
        self._repository = repository
        self._service = service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._idle_seconds = idle_seconds
        self._experiment_orchestrator = experiment_orchestrator
        self._worker_id = worker_id
        self._lease = lease
        self._heartbeat_store = heartbeat_store
        self._ops_probe = ops_probe
        self._is_transient_connection_error = is_transient_connection_error

    @staticmethod
    def _cadence_slo(
        source: RegisteredSource, state: SourceFetchState | None, now: datetime
    ) -> CadenceSlo:
        if state is None or state.last_success_at is None:
            return CadenceSlo.UNKNOWN
        age_seconds = max(0.0, (now - state.last_success_at).total_seconds())
        interval = float(source.poll_interval_seconds)
        if age_seconds <= interval:
            return CadenceSlo.OK
        if age_seconds <= interval * 2:
            return CadenceSlo.AT_RISK
        return CadenceSlo.BREACHED

    @classmethod
    def _schedule(
        cls, source: RegisteredSource, state: SourceFetchState | None, now: datetime
    ) -> SourceSchedule:
        regular_due_at = (
            state.last_success_at + timedelta(seconds=source.poll_interval_seconds)
            if state is not None and state.last_success_at is not None
            else None
        )
        due_at = (
            state.next_retry_at
            if state is not None and state.next_retry_at is not None
            else regular_due_at
        )
        due = due_at is None or due_at <= now
        lateness = None if due_at is None else max(0.0, (now - due_at).total_seconds())
        return SourceSchedule(
            source_id=source.contract.source_id,
            due=due,
            due_at=due_at,
            last_success_at=state.last_success_at if state is not None else None,
            next_retry_at=state.next_retry_at if state is not None else None,
            consecutive_failures=state.consecutive_failures if state is not None else 0,
            cadence_slo=cls._cadence_slo(source, state, now),
            lateness_seconds=lateness,
        )

    def _schedules(self, now: datetime) -> tuple[SourceSchedule, ...]:
        schedules: list[SourceSchedule] = []
        for source_id in sorted(self._registry.sources):
            source = self._registry.require(source_id)
            self._repository.upsert_source(source.contract)
            state = self._repository.get_source_fetch_state(source_id)
            schedules.append(self._schedule(source, state, now))
        return tuple(schedules)

    async def run_once(self) -> PollCycleResult:
        started_at = self._clock()
        if self._lease is not None and not self._lease.acquire(owner=self._worker_id):
            raise WorkerLeaseHeldError(
                f"singleton worker lease already held (worker_id={self._worker_id})"
            )
        try:
            cycle = await self._execute_cycle(started_at)
        finally:
            if self._lease is not None:
                try:
                    self._lease.release(owner=self._worker_id)
                except Exception as error:  # never mask a cycle failure
                    _LOG.warning("worker lease release failed: %s: %s", type(error).__name__, error)
        return cycle

    async def _execute_cycle(self, started_at: datetime) -> PollCycleResult:
        schedules = self._schedules(started_at)
        acquired: list[AcquisitionResult] = []
        isolated_errors: list[tuple[str, str]] = []
        skipped = [schedule.source_id for schedule in schedules if not schedule.due]
        due = [schedule for schedule in schedules if schedule.due]
        due.sort(
            key=lambda schedule: (
                schedule.due_at or datetime.min.replace(tzinfo=UTC),
                schedule.source_id,
            )
        )
        for schedule in due:
            try:
                acquired.append(await self._service.acquire(schedule.source_id))
            except WorkerLeaseHeldError:
                raise
            except Exception as error:
                if (
                    self._is_transient_connection_error is not None
                    and self._is_transient_connection_error(error)
                ):
                    raise
                # Per-source error isolation: one malformed/failing item must
                # never kill the cycle. The failure is surfaced in the cycle
                # result and the heartbeat; the remaining sources proceed.
                detail = f"{type(error).__name__}: {error}"
                isolated_errors.append((schedule.source_id, detail))
                _LOG.error("acquisition failed for %s: %s", schedule.source_id, detail)
        experiment: ExperimentCycleResult | None = None
        if self._experiment_orchestrator is not None:
            # Single-process model: the acquisition worker also drives the
            # prospective experiment orchestrator once per cycle. The
            # orchestrator is synchronous (DB-bound) and runs off the event
            # loop; it already implements its own attempt-lease lifecycle.
            experiment = await asyncio.to_thread(
                self._experiment_orchestrator.run_cycle, now=started_at
            )
        cycle = PollCycleResult(
            started_at=started_at,
            completed_at=self._clock(),
            acquired=tuple(acquired),
            skipped_not_due=tuple(skipped),
            schedules=schedules,
            experiment=experiment,
            errors=tuple(isolated_errors),
        )
        self._record_heartbeat(cycle)
        return cycle

    def _record_heartbeat(self, cycle: PollCycleResult) -> None:
        if self._heartbeat_store is None:
            return
        try:
            self._heartbeat_store.upsert_heartbeat(
                worker_id=self._worker_id,
                role=WORKER_ROLE,
                beat_at=cycle.completed_at,
                metrics=self._heartbeat_metrics(cycle),
            )
        except Exception as error:
            # Liveness is best-effort: a failed heartbeat must never fail the
            # acquisition cycle itself (the next cycle will retry the upsert).
            _LOG.error("worker heartbeat upsert failed: %s: %s", type(error).__name__, error)

    def _heartbeat_metrics(self, cycle: PollCycleResult) -> dict[str, object]:
        now = cycle.completed_at
        metrics: dict[str, object] = {
            "cycle_duration_ms": round(cycle.duration_seconds * 1000, 3),
            "acquired_sources": len(cycle.acquired),
            "skipped_not_due": len(cycle.skipped_not_due),
            "isolated_errors": [
                {"source_id": source_id, "error": error} for source_id, error in cycle.errors
            ],
            "inserted_total": sum(result.inserted for result in cycle.acquired),
            "duplicates_total": sum(result.duplicates for result in cycle.acquired),
            "rejected_total": sum(result.rejected for result in cycle.acquired),
            "failed_sources": sorted(
                result.source_id
                for result in cycle.acquired
                if result.status is CollectionRunStatus.FAILED
            ),
            "retry_backlog": {
                schedule.source_id: _isoformat(schedule.next_retry_at)
                for schedule in cycle.schedules
                if schedule.next_retry_at is not None and schedule.next_retry_at > now
            },
            "cadence_slo": {
                schedule.source_id: schedule.cadence_slo.value for schedule in cycle.schedules
            },
        }
        if cycle.experiment is not None:
            metrics["experiment"] = {
                "action": cycle.experiment.action.value,
                "boundary": _isoformat(cycle.experiment.boundary),
                "attempt_status": (
                    None
                    if cycle.experiment.attempt is None
                    else cycle.experiment.attempt.status.value
                ),
                "run_id": cycle.experiment.run_id,
            }
        else:
            metrics["experiment"] = None
        if self._ops_probe is not None:
            try:
                metrics.update(self._ops_probe.probe_metrics())
            except Exception as error:
                metrics["probe_error"] = f"{type(error).__name__}: {error}"
        return metrics

    def seconds_until_next_cycle(self) -> float:
        now = self._clock()
        schedules = self._schedules(now)
        future_due = [
            (schedule.due_at - now).total_seconds()
            for schedule in schedules
            if schedule.due_at is not None and schedule.due_at > now
        ]
        if any(schedule.due for schedule in schedules) or not future_due:
            return self._idle_seconds
        return max(0.001, min(self._idle_seconds, min(future_due)))

    async def run_forever(
        self,
        observer: CycleObserver | None = None,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        """Poll until a shutdown flag fires (WP9 graceful stop).

        Transient failures (e.g. a dropped Postgres connection) are logged and
        retried with bounded exponential backoff; the loop never dies from a
        single failed cycle. ``WorkerLeaseHeldError`` propagates: a second
        worker must exit non-zero instead of polling forever.
        """
        consecutive_failures = 0
        while True:
            if should_stop is not None and should_stop():
                return
            try:
                cycle = await self.run_once()
            except WorkerLeaseHeldError:
                raise
            except Exception as error:
                consecutive_failures += 1
                _LOG.error(
                    "worker cycle failed (%d consecutive): %s: %s",
                    consecutive_failures,
                    type(error).__name__,
                    error,
                )
                if should_stop is not None and should_stop():
                    return
                await self._sleep(self._retry_backoff(consecutive_failures))
                continue
            consecutive_failures = 0
            if observer is not None:
                observer(cycle)
            remaining = self.seconds_until_next_cycle()
            # Sleep in bounded chunks so a SIGTERM/SIGINT shutdown flag is
            # honored promptly instead of only after the full idle interval.
            while remaining > 0:
                if should_stop is not None and should_stop():
                    return
                chunk = min(remaining, _SHUTDOWN_POLL_SECONDS)
                await self._sleep(chunk)
                remaining -= chunk

    def _retry_backoff(self, consecutive_failures: int) -> float:
        return min(
            _MAX_BACKOFF_SECONDS,
            self._idle_seconds * (2 ** min(consecutive_failures, _MAX_BACKOFF_SHIFT)),
        )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
