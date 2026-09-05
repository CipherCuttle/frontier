from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.application.acquisition import AcquisitionResult
from frontier.application.acquisition_state import SourceFetchState
from frontier.domain.source import SourceContract

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
CycleObserver = Callable[[PollCycleResult], None]


class AcquisitionRunner(Protocol):
    async def acquire(self, source_id: str) -> AcquisitionResult: ...


class WorkerRepository(Protocol):
    def upsert_source(self, source: SourceContract) -> None: ...
    def get_source_fetch_state(self, source_id: str) -> SourceFetchState | None: ...


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

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.completed_at - self.started_at).total_seconds())


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
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self._registry = registry
        self._repository = repository
        self._service = service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._idle_seconds = idle_seconds

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
        schedules = self._schedules(started_at)
        acquired: list[AcquisitionResult] = []
        skipped = [schedule.source_id for schedule in schedules if not schedule.due]
        due = [schedule for schedule in schedules if schedule.due]
        due.sort(
            key=lambda schedule: (
                schedule.due_at or datetime.min.replace(tzinfo=UTC),
                schedule.source_id,
            )
        )
        for schedule in due:
            acquired.append(await self._service.acquire(schedule.source_id))
        return PollCycleResult(
            started_at=started_at,
            completed_at=self._clock(),
            acquired=tuple(acquired),
            skipped_not_due=tuple(skipped),
            schedules=schedules,
        )

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

    async def run_forever(self, observer: CycleObserver | None = None) -> None:
        while True:
            cycle = await self.run_once()
            if observer is not None:
                observer(cycle)
            await self._sleep(self.seconds_until_next_cycle())
