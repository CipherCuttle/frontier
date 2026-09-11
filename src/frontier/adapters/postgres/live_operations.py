from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import psycopg

from frontier.application.intelligence import run_baseline_intelligence
from frontier.domain.digests import Digest

from .intelligence import PostgresBaselineIntelligenceRepository
from .store import PostgresEvidenceStore

_BASELINE_CADENCE_SECONDS = 300
_FAILURE_BACKOFF_SECONDS = (60, 120, 240, 480, 900, 1800, 3600)


def failure_backoff_seconds(consecutive_failures_before: int) -> int:
    """Return bounded cross-cycle backoff for the next failed acquisition.

    ``consecutive_failures_before`` is the persisted failure count before the
    failure being recorded. The first failure waits one minute and sustained
    failures eventually open a one-hour circuit. A successful fetch resets the
    persisted counter through ``PostgresEvidenceStore.record_fetch_success``.
    """
    if consecutive_failures_before < 0:
        raise ValueError("consecutive_failures_before must be non-negative")
    index = min(consecutive_failures_before, len(_FAILURE_BACKOFF_SECONDS) - 1)
    return _FAILURE_BACKOFF_SECONDS[index]


def resolve_failure_retry_at(
    *,
    now: datetime,
    consecutive_failures_before: int,
    proposed_retry_at: datetime | None,
) -> datetime:
    """Combine the circuit floor with any stronger fetcher Retry-After delay."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    circuit_retry_at = now + timedelta(seconds=failure_backoff_seconds(consecutive_failures_before))
    if proposed_retry_at is None:
        return circuit_retry_at
    if proposed_retry_at.tzinfo is None or proposed_retry_at.utcoffset() is None:
        raise ValueError("proposed_retry_at must be timezone-aware")
    return max(circuit_retry_at, proposed_retry_at)


def baseline_boundary_at(now: datetime) -> datetime:
    """Return only the current five-minute UTC boundary; never an older gap."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("baseline boundary clock must be timezone-aware")
    utc_now = now.astimezone(UTC)
    epoch_seconds = int(utc_now.timestamp())
    boundary_seconds = epoch_seconds - (epoch_seconds % _BASELINE_CADENCE_SECONDS)
    return datetime.fromtimestamp(boundary_seconds, tz=UTC)


def database_clock(connection: psycopg.Connection[tuple[object, ...]]) -> datetime:
    """Use the canonical database clock for live operational boundaries."""
    with connection.cursor() as cur:
        cur.execute("SELECT clock_timestamp()")
        row = cur.fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise RuntimeError("database clock unavailable")
    value = row[0]
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("database clock must be timezone-aware")
    return value


class PostgresLiveAcquisitionStore(PostgresEvidenceStore):
    """Canonical evidence store with persistent cross-cycle failure throttling."""

    def record_fetch_failure(
        self,
        source_id: str,
        *,
        next_retry_at: datetime | None,
    ) -> None:
        state = self.get_source_fetch_state(source_id)
        failures_before = 0 if state is None else state.consecutive_failures
        now = database_clock(self._connection)
        resolved = resolve_failure_retry_at(
            now=now,
            consecutive_failures_before=failures_before,
            proposed_retry_at=next_retry_at,
        )
        super().record_fetch_failure(source_id, next_retry_at=resolved)


@dataclass(frozen=True, slots=True)
class LiveBaselineProjection:
    boundary: datetime
    published: bool
    snapshot_id: str


class PostgresLiveBaselineProjector:
    """Publish at most the current boundary and never fill historical gaps."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection
        self._repository = PostgresBaselineIntelligenceRepository(connection)

    def publish_current_boundary(
        self,
        *,
        now: datetime,
        source_registry_version: Digest,
    ) -> LiveBaselineProjection:
        boundary = baseline_boundary_at(now)
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id
                FROM baseline_intelligence_snapshots
                WHERE as_of = %s
                ORDER BY snapshot_id
                """,
                (boundary,),
            )
            existing = [cast(str, row[0]) for row in cur.fetchall()]
        self._connection.commit()

        if len(existing) > 1:
            raise RuntimeError("ambiguous COMPLETE baseline snapshots at current boundary")
        if existing:
            return LiveBaselineProjection(
                boundary=boundary,
                published=False,
                snapshot_id=existing[0],
            )

        result = run_baseline_intelligence(
            self._repository,
            as_of=boundary,
            generated_at=now,
            source_registry_version=source_registry_version,
        )
        return LiveBaselineProjection(
            boundary=boundary,
            published=True,
            snapshot_id=result.snapshot.snapshot_id,
        )


__all__ = [
    "LiveBaselineProjection",
    "PostgresLiveAcquisitionStore",
    "PostgresLiveBaselineProjector",
    "baseline_boundary_at",
    "database_clock",
    "failure_backoff_seconds",
    "resolve_failure_retry_at",
]
