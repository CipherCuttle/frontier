# ruff: noqa: E402
"""G2-05/D014: atomic DB authority for CONFIRMATORY attempt claims."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.postgres.advanced_intelligence import PostgresCandidateFreezeRepository
from frontier.adapters.postgres.experiment_attempts import PostgresExperimentAttemptRepository
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.application.experiment_orchestration import ConfirmatoryClaimResult
from frontier.application.freeze_publication import (
    RANKING_WINDOW_SECONDS,
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.domain.advanced_intelligence import (
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

ConnectionT = Connection[tuple[object, ...]]


def _receipt(seed: str) -> CandidateFreezeReceipt:
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + seed * 64),
            preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
            implementation_commit=seed * 40,
            implementation_tree_digest=("b" if seed != "b" else "c") * 40,
            dependency_lock_digest=Digest("sha256:" + "d" * 64),
            source_registry_digest=Digest("sha256:" + "e" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=datetime.now(UTC) - timedelta(minutes=5),
    )


def _persist_receipt(conn: ConnectionT, seed: str) -> tuple[CandidateFreezeReceipt, datetime]:
    receipt = _receipt(seed)
    PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
    row = conn.execute(
        "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id=%s",
        (receipt.receipt_id,),
    ).fetchone()
    assert row is not None and row[0] is not None
    return receipt, cast(datetime, row[0])


def _persist_authority(conn: ConnectionT, seed: str) -> tuple[CandidateFreezeReceipt, datetime]:
    receipt, durable = _persist_receipt(conn, seed)
    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    publication_at = durable + timedelta(days=int(seed), seconds=1)
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
    ).record_fixture_publication(publication)
    return receipt, publication_at


def _pending(
    repo: PostgresExperimentAttemptRepository,
    as_of: datetime,
    attempt_no: int = 1,
) -> ExperimentRunAttempt:
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=as_of,
        attempt_no=attempt_no,
        status=ExperimentAttemptStatus.PENDING,
    )
    repo.record_attempt(attempt)
    return attempt


def _claim(
    repo: PostgresExperimentAttemptRepository,
    attempt: ExperimentRunAttempt,
    receipt_id: str | None,
    *,
    owner: str = "g205-worker",
    deny: str | None = None,
) -> ConfirmatoryClaimResult:
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
        as_of = (
            start - timedelta(seconds=300)
            if position == "BEFORE"
            else start + timedelta(seconds=RANKING_WINDOW_SECONDS)
        )
        repo = PostgresExperimentAttemptRepository(conn)
        attempt = _pending(repo, as_of)
        result = _claim(repo, attempt, receipt.receipt_id)
        stored = repo.latest_attempt(PEF_EXPERIMENT_ID, as_of)
    assert not result.claimed and result.skipped
    assert (
        result.reason is not None
        and "outside the fixed preregistered ranking window" in result.reason
    )
    assert stored is not None and stored.status is ExperimentAttemptStatus.SKIPPED


def test_missing_publication_and_wrong_receipt_never_reach_running() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, durable = _persist_receipt(conn, "4")
        as_of = first_confirmatory_boundary(durable + timedelta(days=4, seconds=1))
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
