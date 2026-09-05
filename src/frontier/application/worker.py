from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from frontier.adapters.acquisition.config import SourceRegistry
from frontier.application.acquisition import AcquisitionResult, AcquisitionService
from frontier.application.ports.repositories import AcquisitionRepository

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PollCycleResult:
    acquired: tuple[AcquisitionResult, ...]
    skipped_not_due: tuple[str, ...]


class AcquisitionWorker:
    def __init__(
        self,
        *,
        registry: SourceRegistry,
        repository: AcquisitionRepository,
        service: AcquisitionService,
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

    async def run_once(self) -> PollCycleResult:
        now = self._clock()
        acquired: list[AcquisitionResult] = []
        skipped: list[str] = []
        for source_id in sorted(self._registry.sources):
            source = self._registry.require(source_id)
            self._repository.upsert_source(source.contract)
            state = self._repository.get_source_fetch_state(source_id)
            if state is not None:
                if state.next_retry_at is not None and state.next_retry_at > now:
                    skipped.append(source_id)
                    continue
                if state.last_success_at is not None:
                    due_at = state.last_success_at + timedelta(seconds=source.poll_interval_seconds)
                    if due_at > now:
                        skipped.append(source_id)
                        continue
            acquired.append(await self._service.acquire(source_id))
        return PollCycleResult(acquired=tuple(acquired), skipped_not_due=tuple(skipped))

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await self._sleep(self._idle_seconds)
