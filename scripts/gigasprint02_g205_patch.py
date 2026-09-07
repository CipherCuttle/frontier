from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement target, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(start_marker) != 1:
        raise RuntimeError(f"{path}: expected one start marker")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    file.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def patch_orchestration() -> None:
    path = "src/frontier/application/experiment_orchestration.py"
    replace_once(
        path,
        '''@dataclass(frozen=True, slots=True)
class ConfirmatoryDecision:
    """Outcome of the four confirmatory binding-correctness gates."""

    allowed: bool
    reason: str
    receipt: CandidateFreezeReceipt | None = None


''',
        '''@dataclass(frozen=True, slots=True)
class ConfirmatoryDecision:
    """Outcome of the confirmatory binding-correctness precheck."""

    allowed: bool
    reason: str
    receipt: CandidateFreezeReceipt | None = None


@dataclass(frozen=True, slots=True)
class ConfirmatoryClaimResult:
    """Atomic persistence verdict for a CONFIRMATORY attempt claim."""

    claimed: bool
    skipped: bool
    reason: str | None = None


''',
    )
    replace_once(
        path,
        '''    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool: ...
    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool: ...
''',
        '''    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool: ...
    def claim_confirmatory(
        self,
        attempt_id: str,
        *,
        expected_receipt_id: str | None,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
        deny_reason: str | None = None,
    ) -> ConfirmatoryClaimResult: ...
    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool: ...
''',
    )
    replace_between(
        path,
        "        self._attempts.record_attempt(pending)\n",
        "\n    def _execute_boundary(\n",
        '''        self._attempts.record_attempt(pending)
        lease_expires_at = at + timedelta(seconds=self._lease_seconds)
        freeze_receipt: CandidateFreezeReceipt | None = None
        if self._run_class == RUN_CLASS_CONFIRMATORY:
            binding = None if self._freeze_binding is None else self._freeze_binding.latest_binding()
            decision = evaluate_confirmatory_gates(
                binding, as_of=boundary, canonical_context=self._canonical_context
            )
            expected_receipt_id = None if binding is None else binding.receipt.receipt_id
            claim = self._attempts.claim_confirmatory(
                pending.attempt_id,
                expected_receipt_id=expected_receipt_id,
                owner=self._worker_id,
                lease_expires_at=lease_expires_at,
                now=at,
                deny_reason=None if decision.allowed else decision.reason,
            )
            if claim.skipped:
                detail = claim.reason or "confirmatory claim denied"
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
                    attempt=_with_status(
                        pending, ExperimentAttemptStatus.SKIPPED, detail=detail
                    ),
                    detail=detail,
                )
            if not claim.claimed:
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.DEFERRED_ACTIVE_OWNER,
                    attempt=pending,
                    detail=claim.reason or "attempt claimed concurrently by another worker",
                )
            if not decision.allowed or decision.receipt is None:
                raise RuntimeError(
                    "confirmatory DB claim succeeded without an allowed application binding"
                )
            freeze_receipt = decision.receipt
        else:
            if not self._attempts.claim(
                pending.attempt_id,
                owner=self._worker_id,
                lease_expires_at=lease_expires_at,
                now=at,
            ):
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.DEFERRED_ACTIVE_OWNER,
                    attempt=_with_status(
                        pending,
                        ExperimentAttemptStatus.RUNNING,
                        lease_owner=self._worker_id,
                        lease_expires_at=lease_expires_at,
                    ),
                    detail="attempt claimed concurrently by another worker",
                )
        attempt = _with_status(
            pending,
            ExperimentAttemptStatus.RUNNING,
            lease_owner=self._worker_id,
            lease_expires_at=lease_expires_at,
            heartbeat_at=at,
        )
        return self._execute_boundary(
            attempt, boundary, freeze_receipt=freeze_receipt
        )
''',
    )
    replace_once(
        path,
        '''    def _execute_boundary(
        self, attempt: ExperimentRunAttempt, boundary: datetime
    ) -> ExperimentCycleResult:
''',
        '''    def _execute_boundary(
        self,
        attempt: ExperimentRunAttempt,
        boundary: datetime,
        *,
        freeze_receipt: CandidateFreezeReceipt | None,
    ) -> ExperimentCycleResult:
''',
    )
    replace_between(
        path,
        "        freeze_receipt: CandidateFreezeReceipt | None = None\n        if self._run_class == RUN_CLASS_CONFIRMATORY:\n",
        "        try:\n            run = self._run_paired_experiment(attempt, boundary, freeze_receipt)\n",
        '''        if self._run_class == RUN_CLASS_CONFIRMATORY:
            if freeze_receipt is None:
                raise RuntimeError("CONFIRMATORY execution requires an atomically claimed freeze")
            if self._drift_sentry is not None:
                drift_report = self._drift_sentry.check(freeze_receipt, now=self._clock())
                if drift_report.status is DriftStatus.DRIFTED:
                    detail = "DRIFTED: " + "; ".join(drift_report.reasons)
                    self._attempts.finish(
                        attempt.attempt_id,
                        owner=self._worker_id,
                        status=ExperimentAttemptStatus.SKIPPED,
                        detail=detail,
                        at=self._clock(),
                    )
                    return ExperimentCycleResult(
                        boundary=boundary,
                        action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
                        attempt=_with_status(
                            attempt, ExperimentAttemptStatus.SKIPPED, detail=detail
                        ),
                        detail=detail,
                    )
''',
    )


def patch_postgres_attempts() -> None:
    path = "src/frontier/adapters/postgres/experiment_attempts.py"
    replace_once(
        path,
        '''from frontier.application.experiment_orchestration import (
    LEASE_EXPIRED_DETAIL,
    FreezeBinding,
    ShadowRunPersistence,
)
''',
        '''from frontier.application.experiment_orchestration import (
    LEASE_EXPIRED_DETAIL,
    ConfirmatoryClaimResult,
    FreezeBinding,
    ShadowRunPersistence,
)
from frontier.application.freeze_publication import require_confirmatory_boundary
''',
    )
    marker = "    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool:\n"
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: heartbeat insertion marker missing")
    method = '''    def claim_confirmatory(
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
                SELECT r.status, r.durable_freeze_at, p.publication_committer_at
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
            publication_committer_at = cast(datetime | None, authority[2])
            if publication_committer_at is None:
                return skip("bound freeze receipt has no verified Git publication")
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

'''
    file.write_text(text.replace(marker, method + marker), encoding="utf-8")


def patch_unit_fake() -> None:
    path = "tests/unit/test_experiment_orchestration.py"
    replace_once(
        path,
        '''    ConfirmatoryDecision,
    ExperimentAttemptRepository,
''',
        '''    ConfirmatoryClaimResult,
    ConfirmatoryDecision,
    ExperimentAttemptRepository,
''',
    )
    marker = "    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool:\n"
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: fake heartbeat insertion marker missing")
    method = '''    def claim_confirmatory(
        self,
        attempt_id: str,
        *,
        expected_receipt_id: str | None,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
        deny_reason: str | None = None,
    ) -> ConfirmatoryClaimResult:
        attempt = self.attempts.get(attempt_id)
        if attempt is None:
            return ConfirmatoryClaimResult(False, False, "experiment attempt does not exist")
        if deny_reason is not None or expected_receipt_id is None:
            reason = deny_reason or "no candidate freeze receipt is bound"
            if attempt.status is not ExperimentAttemptStatus.PENDING:
                return ConfirmatoryClaimResult(False, False, "attempt is not claimable")
            self.set_attempt(
                ExperimentRunAttempt(
                    experiment_id=attempt.experiment_id,
                    as_of=attempt.as_of,
                    attempt_no=attempt.attempt_no,
                    status=ExperimentAttemptStatus.SKIPPED,
                    detail=reason,
                    schema_version=attempt.schema_version,
                )
            )
            return ConfirmatoryClaimResult(False, True, reason)
        claimed = self.claim(
            attempt_id,
            owner=owner,
            lease_expires_at=lease_expires_at,
            now=now,
        )
        return ConfirmatoryClaimResult(
            claimed,
            False,
            None if claimed else "attempt is not claimable by this owner",
        )

'''
    file.write_text(text.replace(marker, method + marker), encoding="utf-8")


def write_postgres_tests() -> None:
    path = ROOT / "tests/integration/test_confirmatory_claim_postgres.py"
    path.write_text(
        '''# ruff: noqa: E402
"""G2-05/D014: atomic DB authority for CONFIRMATORY attempt claims."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import PostgresCandidateFreezeRepository
from frontier.adapters.postgres.experiment_attempts import PostgresExperimentAttemptRepository
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.application.freeze_publication import (
    RANKING_WINDOW_SECONDS,
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID
from frontier.domain.candidate_freeze import FreezeInputs, build_candidate_freeze_receipt
from frontier.domain.digests import Digest
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _receipt(seed: str):
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + seed * 64),
            preregistration_config_digest=Digest("sha256:" + "a" * 64),
            implementation_commit=seed * 40,
            implementation_tree_digest=("b" if seed != "b" else "c") * 40,
            dependency_lock_digest=Digest("sha256:" + "d" * 64),
            source_registry_digest=Digest("sha256:" + "e" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=datetime.now(UTC) - timedelta(minutes=5),
    )


def _persist_receipt(conn, seed: str):
    receipt = _receipt(seed)
    PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
    row = conn.execute(
        "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id=%s",
        (receipt.receipt_id,),
    ).fetchone()
    assert row is not None and row[0] is not None
    return receipt, row[0]


def _persist_authority(conn, seed: str):
    receipt, durable = _persist_receipt(conn, seed)
    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    publication_at = durable + timedelta(seconds=1)
    publication = CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit="f" * 40,
        publication_committer_at=publication_at,
    )
    PostgresCandidateFreezePublicationRepository(
        conn, persistence_authorized=True
    ).record_publication(publication)
    return receipt, publication_at


def _pending(repo: PostgresExperimentAttemptRepository, as_of: datetime, attempt_no: int = 1):
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=as_of,
        attempt_no=attempt_no,
        status=ExperimentAttemptStatus.PENDING,
    )
    repo.record_attempt(attempt)
    return attempt


def _claim(repo, attempt, receipt_id: str | None, *, owner: str = "g205-worker", deny=None):
    now = datetime.now(UTC)
    return repo.claim_confirmatory(
        attempt.attempt_id,
        expected_receipt_id=receipt_id,
        owner=owner,
        lease_expires_at=now + timedelta(minutes=2),
        now=now,
        deny_reason=deny,
    )


def test_valid_publication_window_claim_reaches_running() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication_at = _persist_authority(conn, "1")
        repo = PostgresExperimentAttemptRepository(conn)
        attempt = _pending(repo, first_confirmatory_boundary(publication_at))
        result = _claim(repo, attempt, receipt.receipt_id)
        stored = repo.latest_attempt(PEF_EXPERIMENT_ID, attempt.as_of)
    assert result.claimed and not result.skipped and result.reason is None
    assert stored is not None and stored.status is ExperimentAttemptStatus.RUNNING


@pytest.mark.parametrize("position", ["BEFORE", "END"])
def test_outside_fixed_window_is_atomically_skipped(position: str) -> None:
    assert DB_URL is not None
    seed = "2" if position == "BEFORE" else "3"
    with psycopg.connect(DB_URL) as conn:
        receipt, publication_at = _persist_authority(conn, seed)
        start = first_confirmatory_boundary(publication_at)
        as_of = start - timedelta(seconds=300) if position == "BEFORE" else start + timedelta(seconds=RANKING_WINDOW_SECONDS)
        repo = PostgresExperimentAttemptRepository(conn)
        attempt = _pending(repo, as_of)
        result = _claim(repo, attempt, receipt.receipt_id)
        stored = repo.latest_attempt(PEF_EXPERIMENT_ID, as_of)
    assert not result.claimed and result.skipped
    assert result.reason is not None and "outside the fixed preregistered ranking window" in result.reason
    assert stored is not None and stored.status is ExperimentAttemptStatus.SKIPPED


def test_missing_publication_and_wrong_receipt_never_reach_running() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, durable = _persist_receipt(conn, "4")
        as_of = first_confirmatory_boundary(durable + timedelta(seconds=1))
        repo = PostgresExperimentAttemptRepository(conn)
        missing_publication = _pending(repo, as_of)
        first = _claim(repo, missing_publication, receipt.receipt_id)
        wrong = _pending(repo, as_of + timedelta(seconds=300))
        second = _claim(repo, wrong, "freezereceipt_" + "0" * 64)
    assert first.skipped and not first.claimed
    assert first.reason == "bound freeze receipt has no verified Git publication"
    assert second.skipped and not second.claimed
    assert second.reason == "bound candidate freeze receipt is not present in canonical DB"


def test_application_denial_can_only_make_claim_more_restrictive() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication_at = _persist_authority(conn, "5")
        as_of = first_confirmatory_boundary(publication_at)
        repo = PostgresExperimentAttemptRepository(conn)
        attempt = _pending(repo, as_of)
        result = _claim(
            repo,
            attempt,
            receipt.receipt_id,
            deny="run is not executing in the canonical DB context",
        )
        stored = repo.latest_attempt(PEF_EXPERIMENT_ID, as_of)
    assert result.skipped and not result.claimed
    assert stored is not None and stored.status is ExperimentAttemptStatus.SKIPPED


def test_two_workers_racing_same_boundary_yield_exactly_one_claim() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication_at = _persist_authority(conn, "6")
        as_of = first_confirmatory_boundary(publication_at)
        attempt = _pending(PostgresExperimentAttemptRepository(conn), as_of)
    barrier = Barrier(2)

    def race(owner: str):
        assert DB_URL is not None
        with psycopg.connect(DB_URL) as worker_conn:
            repo = PostgresExperimentAttemptRepository(worker_conn)
            now = datetime.now(UTC)
            barrier.wait()
            return repo.claim_confirmatory(
                attempt.attempt_id,
                expected_receipt_id=receipt.receipt_id,
                owner=owner,
                lease_expires_at=now + timedelta(minutes=2),
                now=now,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(race, ("worker-a", "worker-b")))
    assert sum(result.claimed for result in results) == 1
    assert sum(result.skipped for result in results) == 0
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            "SELECT status, COUNT(*) OVER () FROM experiment_run_attempts "
            "WHERE experiment_id=%s AND as_of=%s",
            (PEF_EXPERIMENT_ID, as_of),
        ).fetchone()
    assert row is not None and row[0] == "RUNNING" and row[1] == 1
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_orchestration()
    patch_postgres_attempts()
    patch_unit_fake()
    write_postgres_tests()
    files = [
        "src/frontier/application/experiment_orchestration.py",
        "src/frontier/adapters/postgres/experiment_attempts.py",
        "tests/unit/test_experiment_orchestration.py",
        "tests/integration/test_confirmatory_claim_postgres.py",
    ]
    subprocess.run(["uv", "run", "ruff", "format", *files], cwd=ROOT, check=True)
    subprocess.run(["uv", "run", "ruff", "check", "--fix", *files], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
