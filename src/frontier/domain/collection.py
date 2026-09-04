from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CollectionReason(StrEnum):
    SCHEDULED = "SCHEDULED"
    DISCOVERY = "DISCOVERY"
    ACTIVE_ENRICHMENT = "ACTIVE_ENRICHMENT"
    BACKFILL = "BACKFILL"


class CollectionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class OccurrenceStatus(StrEnum):
    INSERTED = "INSERTED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True)
class CollectionRun:
    run_id: UUID
    source_id: str
    reason: CollectionReason
    started_at: datetime
    trigger_id: str | None = None
    recovered_after_gap: bool = False

    def __post_init__(self) -> None:
        if self.reason is CollectionReason.ACTIVE_ENRICHMENT and not self.trigger_id:
            raise ValueError("ACTIVE_ENRICHMENT requires trigger_id")
