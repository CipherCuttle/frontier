"""PostgreSQL operational persistence for experiment orchestration (WP2).

The ``experiment_run_attempts`` table is the ONLY new operational state model:
it is a mutable lease table (no append-only trigger), while all experiment
evidence stays in the append-only run/artifact tables. Idempotency is
guaranteed by the UNIQUE (experiment_id, as_of, attempt_no) constraint plus a
pre-check; the lease conditions mirror the table CHECK constraints exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from frontier.adapters.postgres.advanced_intelligence import PostgresShadowRunRepository
from frontier.application.experiment_orchestration import (
    LEASE_EXPIRED_DETAIL,
    FreezeBinding,
    ShadowRunPersistence,
)
from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID, ShadowExperimentRun
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeStatus,
    RegistryEntryDigest,
)
from frontier.domain.digests import Digest
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt

RUN_CLASSES: tuple[str, ...] = ("DEV", "CONFIRMATORY")


def _row_to_attempt(
    experiment_id: str,
    as_of: datetime,
    attempt_no: int,
    status_value: str,
    detail: str | None,
    lease_owner: str | None,
    lease_expires_at: datetime | None,
    heartbeat_at: datetime | None,
) -> ExperimentRunAttempt:
    return ExperimentRunAttempt(
        experiment_id=experiment_id,
        as_of=as_of,
        attempt_no=attempt_no,
        status=ExperimentAttemptStatus(status_value),
        detail=detail,
        lease_owner=lease_owner,
        lease_expires_at=lease_expires_at,
        heartbeat_at=heartbeat_at,
    )


class PostgresExperimentAttemptRepository:
    """Mutable lease-table operations for experiment run attempts."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def latest_attempt(self, experiment_id: str, as_of: datetime) -> ExperimentRunAttempt | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT experiment_id, as_of, attempt_no, status, detail,
                       lease_owner, lease_expires_at, heartbeat_at
                FROM experiment_run_attempts
                WHERE experiment_id = %s AND as_of = %s
                ORDER BY attempt_no DESC
                LIMIT 1
                """,
                (experiment_id, as_of),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_attempt(
            cast(str, row[0]),
            cast(datetime, row[1]),
            int(cast(int, row[2])),
            cast(str, row[3]),
            cast(str | None, row[4]),
            cast(str | None, row[5]),
            cast(datetime | None, row[6]),
            cast(datetime | None, row[7]),
        )

    def record_attempt(self, attempt: ExperimentRunAttempt) -> bool:
        """Insert one PENDING attempt; re-recording the identical attempt is a no-op."""
        if attempt.status is not ExperimentAttemptStatus.PENDING:
            raise ValueError("only PENDING attempts may be recorded as new")
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO experiment_run_attempts (
                    attempt_id, experiment_id, as_of, attempt_no, status,
                    attempt_digest, lease_owner, lease_expires_at,
                    heartbeat_at, detail
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (experiment_id, as_of, attempt_no) DO NOTHING
                RETURNING attempt_id
                """,
                (
                    attempt.attempt_id,
                    attempt.experiment_id,
                    attempt.as_of,
                    attempt.attempt_no,
                    attempt.status.value,
                    attempt.attempt_digest,
                    attempt.lease_owner,
                    attempt.lease_expires_at,
                    attempt.heartbeat_at,
                    attempt.detail,
                ),
            )
            inserted = cur.fetchone()
            if inserted is not None:
                return True
            cur.execute(
                "SELECT attempt_digest FROM experiment_run_attempts WHERE attempt_id = %s",
                (attempt.attempt_id,),
            )
            existing = cur.fetchone()
        if existing is None:
            raise RuntimeError("experiment attempt conflict without existing row")
        if cast(str, existing[0]) != attempt.attempt_digest:
            raise RuntimeError("experiment attempt identity conflict with different digest")
        return False

    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Claim a PENDING attempt (or adopt our own unexpired RUNNING lease)."""
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT experiment_id, as_of, attempt_no, detail
                FROM experiment_run_attempts
                WHERE attempt_id = %s
                """,
                (attempt_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            running = ExperimentRunAttempt(
                experiment_id=cast(str, row[0]),
                as_of=cast(datetime, row[1]),
                attempt_no=int(cast(int, row[2])),
                status=ExperimentAttemptStatus.RUNNING,
                detail=cast(str | None, row[3]),
                lease_owner=owner,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
            )
            cur.execute(
                """
                UPDATE experiment_run_attempts
                SET status = 'RUNNING', lease_owner = %s, lease_expires_at = %s,
                    heartbeat_at = %s, attempt_digest = %s
                WHERE attempt_id = %s
                  AND (
                        status = 'PENDING'
                        OR (
                            status = 'RUNNING'
                            AND lease_owner = %s
                            AND lease_expires_at > %s
                        )
                  )
                RETURNING attempt_no
                """,
                (
                    owner,
                    lease_expires_at,
                    now,
                    running.attempt_digest,
                    attempt_id,
                    owner,
                    now,
                ),
            )
            claimed = cur.fetchone()
        return claimed is not None

    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool:
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                UPDATE experiment_run_attempts
                SET heartbeat_at = %s
                WHERE attempt_id = %s AND status = 'RUNNING'
                  AND lease_owner = %s AND lease_expires_at > %s
                RETURNING attempt_no
                """,
                (at, attempt_id, owner, at),
            )
            beat = cur.fetchone()
        return beat is not None

    def finish(
        self,
        attempt_id: str,
        *,
        owner: str,
        status: ExperimentAttemptStatus,
        detail: str | None,
        at: datetime,
    ) -> bool:
        """Record a terminal transition and release the lease."""
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                "SELECT experiment_id, as_of, attempt_no FROM experiment_run_attempts "
                "WHERE attempt_id = %s",
                (attempt_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            finished = ExperimentRunAttempt(
                experiment_id=cast(str, row[0]),
                as_of=cast(datetime, row[1]),
                attempt_no=int(cast(int, row[2])),
                status=status,
                detail=detail,
            )
            cur.execute(
                """
                UPDATE experiment_run_attempts
                SET status = %s, detail = %s, attempt_digest = %s,
                    lease_owner = NULL, heartbeat_at = %s
                WHERE attempt_id = %s AND status = 'RUNNING' AND lease_owner = %s
                RETURNING attempt_no
                """,
                (
                    status.value,
                    detail,
                    finished.attempt_digest,
                    at,
                    attempt_id,
                    owner,
                ),
            )
            finished_row = cur.fetchone()
        return finished_row is not None

    def expire_stale(
        self, *, now: datetime, detail: str = LEASE_EXPIRED_DETAIL
    ) -> tuple[ExperimentRunAttempt, ...]:
        """Expire every RUNNING attempt whose lease has elapsed (any owner)."""
        expired: list[ExperimentRunAttempt] = []
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT attempt_id, experiment_id, as_of, attempt_no, detail,
                       lease_expires_at, heartbeat_at
                FROM experiment_run_attempts
                WHERE status = 'RUNNING' AND lease_expires_at <= %s
                FOR UPDATE
                """,
                (now,),
            )
            rows = cur.fetchall()
            for row in rows:
                base = _row_to_attempt(
                    cast(str, row[1]),
                    cast(datetime, row[2]),
                    int(cast(int, row[3])),
                    ExperimentAttemptStatus.EXPIRED.value,
                    detail,
                    None,
                    cast(datetime | None, row[5]),
                    cast(datetime | None, row[6]),
                )
                cur.execute(
                    """
                    UPDATE experiment_run_attempts
                    SET status = 'EXPIRED', detail = %s, attempt_digest = %s,
                        lease_owner = NULL
                    WHERE attempt_id = %s AND status = 'RUNNING'
                    RETURNING attempt_no
                    """,
                    (detail, base.attempt_digest, cast(str, row[0])),
                )
                if cur.fetchone() is not None:
                    expired.append(base)
        return tuple(expired)


class PostgresFreezeBindingResolver:
    """Resolves the latest candidate freeze binding from the canonical DB."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def latest_binding(self) -> FreezeBinding | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT status, drift_reasons, preregistration_digest,
                       preregistration_config_digest, implementation_commit,
                       implementation_tree_digest, dependency_lock_digest,
                       source_registry_digest, registry_entry_digests,
                       receipt_digest, frozen_at, verified_at,
                       original_receipt_digest, durable_freeze_at
                FROM candidate_freeze_receipts
                WHERE experiment_id = %s
                ORDER BY frozen_at DESC, receipt_id DESC
                LIMIT 1
                """,
                (PEF_EXPERIMENT_ID,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        entries: tuple[RegistryEntryDigest, ...] | None = None
        if row[8] is not None:
            raw_entries = cast(list[dict[str, object]], row[8])
            entries = tuple(
                RegistryEntryDigest(
                    path=cast(str, entry["path"]),
                    digest=Digest(cast(str, entry["digest"])),
                )
                for entry in raw_entries
            )
        receipt = CandidateFreezeReceipt(
            frozen_at=cast(datetime, row[10]),
            status=FreezeStatus(cast(str, row[0])),
            drift_reasons=tuple(cast(list[str], row[1])),
            preregistration_digest=Digest(cast(str, row[2])),
            preregistration_config_digest=(None if row[3] is None else Digest(cast(str, row[3]))),
            implementation_commit=cast(str | None, row[4]),
            implementation_tree_digest=cast(str | None, row[5]),
            dependency_lock_digest=None if row[6] is None else Digest(cast(str, row[6])),
            source_registry_digest=None if row[7] is None else Digest(cast(str, row[7])),
            registry_entry_digests=entries,
            verified_at=None if row[11] is None else cast(datetime, row[11]),
            original_receipt_digest=None if row[12] is None else Digest(cast(str, row[12])),
        )
        if receipt.receipt_digest.value != cast(str, row[9]):
            raise RuntimeError("freeze receipt row does not bind its stored digest")
        return FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None if row[13] is None else cast(datetime, row[13]),
        )


class PostgresShadowRunPersister(ShadowRunPersistence):
    """Idempotent append-only persistence for completed paired shadow runs."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection
        self._runs = PostgresShadowRunRepository(connection)

    def persist(self, run: ShadowExperimentRun, *, run_class: str) -> str:
        if run_class not in RUN_CLASSES:
            raise ValueError("shadow run run_class must be DEV or CONFIRMATORY")
        # Content-derived run_id: re-inserting the identical run is a no-op.
        self._runs.record_run(run, run_class=run_class)
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT run_class FROM shadow_experiment_runs WHERE run_id = %s",
                (run.run_id,),
            )
            row = cur.fetchone()
        if row is None or cast(str, row[0]) != run_class:
            raise RuntimeError("shadow run class conflict with retained row")
        return run.run_id

    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None:
        return self._runs.latest_run_id_and_class_for_as_of(as_of)


__all__ = [
    "PostgresExperimentAttemptRepository",
    "PostgresFreezeBindingResolver",
    "PostgresShadowRunPersister",
]
