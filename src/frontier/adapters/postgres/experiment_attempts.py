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
    ConfirmatoryClaimResult,
    FreezeBinding,
    ShadowRunPersistence,
)
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    require_confirmatory_boundary,
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

    def claim_confirmatory(
        self,
        attempt_id: str,
        *,
        expected_receipt_id: str | None,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
        deny_reason: str | None = None,
    ) -> ConfirmatoryClaimResult:
        """Atomically authorize and claim one CONFIRMATORY boundary.

        Scientific time authority is read from the persisted freeze publication
        in the SAME transaction that changes PENDING -> RUNNING. ``now`` is
        only the lease clock. Caller-side prechecks can deny but cannot grant
        confirmatory authority.
        """
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT experiment_id, as_of, attempt_no, detail, status,
                       lease_owner, lease_expires_at
                FROM experiment_run_attempts
                WHERE attempt_id = %s
                FOR UPDATE
                """,
                (attempt_id,),
            )
            row = cur.fetchone()
            if row is None:
                return ConfirmatoryClaimResult(False, False, "experiment attempt does not exist")
            experiment_id = cast(str, row[0])
            as_of = cast(datetime, row[1])
            attempt_no = int(cast(int, row[2]))
            detail = cast(str | None, row[3])
            status = ExperimentAttemptStatus(cast(str, row[4]))
            current_owner = cast(str | None, row[5])
            current_expiry = cast(datetime | None, row[6])
            adoptable = status is ExperimentAttemptStatus.PENDING or (
                status is ExperimentAttemptStatus.RUNNING
                and current_owner == owner
                and current_expiry is not None
                and current_expiry > now
            )
            if not adoptable:
                return ConfirmatoryClaimResult(
                    False, False, "attempt is not claimable by this owner"
                )

            def skip(reason: str) -> ConfirmatoryClaimResult:
                skipped = ExperimentRunAttempt(
                    experiment_id=experiment_id,
                    as_of=as_of,
                    attempt_no=attempt_no,
                    status=ExperimentAttemptStatus.SKIPPED,
                    detail=reason,
                )
                cur.execute(
                    """
                    UPDATE experiment_run_attempts
                    SET status = 'SKIPPED', detail = %s, attempt_digest = %s,
                        lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = %s
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
                    (reason, skipped.attempt_digest, now, attempt_id, owner, now),
                )
                return ConfirmatoryClaimResult(False, cur.fetchone() is not None, reason)

            if deny_reason is not None:
                return skip(deny_reason)
            if expected_receipt_id is None:
                return skip("no candidate freeze receipt is bound")
            if experiment_id != PEF_EXPERIMENT_ID:
                return skip("confirmatory claim is not for the PEF_V0 experiment")

            cur.execute(
                """
                SELECT r.status, r.durable_freeze_at, r.receipt_digest,
                       r.implementation_commit, r.implementation_tree_digest,
                       p.freeze_receipt_digest, p.implementation_commit,
                       p.implementation_tree_digest, p.publication_commit,
                       p.publication_committer_at, p.publication_digest,
                       p.publication_json
                FROM candidate_freeze_receipts r
                LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
                WHERE r.receipt_id = %s AND r.experiment_id = %s
                """,
                (expected_receipt_id, PEF_EXPERIMENT_ID),
            )
            authority = cur.fetchone()
            if authority is None:
                return skip("bound candidate freeze receipt is not present in canonical DB")
            if FreezeStatus(cast(str, authority[0])) is not FreezeStatus.FROZEN:
                return skip("bound candidate freeze receipt is not FROZEN")
            durable_freeze_at = cast(datetime | None, authority[1])
            if durable_freeze_at is None:
                return skip("bound freeze receipt has durable_freeze_at NULL (not durable)")
            if authority[9] is None:
                return skip("bound freeze receipt has no verified Git publication")
            try:
                publication = CandidateFreezePublication(
                    freeze_receipt_id=expected_receipt_id,
                    freeze_receipt_digest=Digest(cast(str, authority[5])),
                    implementation_commit=cast(str, authority[6]),
                    implementation_tree_digest=cast(str, authority[7]),
                    publication_commit=cast(str, authority[8]),
                    publication_committer_at=cast(datetime, authority[9]),
                )
            except TypeError, ValueError:
                return skip("bound Git publication identity is invalid")
            if (
                str(publication.freeze_receipt_digest) != cast(str, authority[2])
                or publication.implementation_commit != cast(str, authority[3])
                or publication.implementation_tree_digest != cast(str, authority[4])
            ):
                return skip("bound Git publication identity does not match freeze receipt")
            if str(publication.publication_digest) != cast(str, authority[10]):
                return skip("bound Git publication digest mismatch")
            if publication.to_canonical() != cast(dict[str, object], authority[11]):
                return skip("bound Git publication canonical payload mismatch")
            publication_committer_at = publication.publication_committer_at
            if publication_committer_at < durable_freeze_at:
                return skip("Git publication precedes canonical DB durability")
            try:
                require_confirmatory_boundary(
                    as_of=as_of,
                    publication_committer_at=publication_committer_at,
                )
            except ValueError as error:
                return skip(str(error))

            running = ExperimentRunAttempt(
                experiment_id=experiment_id,
                as_of=as_of,
                attempt_no=attempt_no,
                status=ExperimentAttemptStatus.RUNNING,
                detail=detail,
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
            return ConfirmatoryClaimResult(cur.fetchone() is not None, False, None)

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
                SELECT r.status, r.drift_reasons, r.preregistration_digest,
                       r.preregistration_config_digest, r.implementation_commit,
                       r.implementation_tree_digest, r.dependency_lock_digest,
                       r.source_registry_digest, r.registry_entry_digests,
                       r.receipt_digest, r.frozen_at, r.verified_at,
                       r.original_receipt_digest, r.durable_freeze_at,
                       p.freeze_receipt_digest, p.implementation_commit,
                       p.implementation_tree_digest, p.publication_commit,
                       p.publication_committer_at, p.publication_digest,
                       p.publication_json
                FROM candidate_freeze_receipts r
                LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
                WHERE r.experiment_id = %s
                ORDER BY r.frozen_at DESC, r.receipt_id DESC
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
        publication_commit: str | None = None
        publication_committer_at: datetime | None = None
        if row[18] is not None:
            try:
                publication = CandidateFreezePublication(
                    freeze_receipt_id=receipt.receipt_id,
                    freeze_receipt_digest=Digest(cast(str, row[14])),
                    implementation_commit=cast(str, row[15]),
                    implementation_tree_digest=cast(str, row[16]),
                    publication_commit=cast(str, row[17]),
                    publication_committer_at=cast(datetime, row[18]),
                )
            except (TypeError, ValueError) as error:
                raise RuntimeError("freeze publication row is invalid") from error
            if publication.freeze_receipt_digest != receipt.receipt_digest:
                raise RuntimeError("freeze publication row does not bind freeze receipt digest")
            if publication.implementation_commit != receipt.implementation_commit:
                raise RuntimeError("freeze publication row does not bind implementation commit")
            if publication.implementation_tree_digest != receipt.implementation_tree_digest:
                raise RuntimeError("freeze publication row does not bind implementation tree")
            if str(publication.publication_digest) != cast(str, row[19]):
                raise RuntimeError("freeze publication row does not bind its stored digest")
            if publication.to_canonical() != cast(dict[str, object], row[20]):
                raise RuntimeError("freeze publication row does not bind its canonical payload")
            publication_commit = publication.publication_commit
            publication_committer_at = publication.publication_committer_at
        return FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None if row[13] is None else cast(datetime, row[13]),
            publication_commit=publication_commit,
            publication_committer_at=publication_committer_at,
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
