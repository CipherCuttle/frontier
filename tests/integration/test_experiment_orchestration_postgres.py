# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresFreezeBindingResolver,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.application.experiment_orchestration import (
    ExperimentCycleAction,
    ExperimentOrchestrator,
    evaluate_confirmatory_gates,
)
from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID
from frontier.domain.candidate_freeze import FreezeStatus
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

# Session-unique base boundary (still an exact multiple of 300 s) so repeated
# test sessions never collide on the UNIQUE (experiment_id, as_of) key. The
# offset stays in the past (at most ~83 days back) so this file's synthetic
# runs can never shadow tests that seed "latest" rows far in the future.
_SESSION_OFFSET = (int(uuid4().hex[:8], 16) % 24_000) * 300
BOUNDARY = datetime.fromtimestamp(
    (int(datetime.now(UTC).timestamp()) // 300) * 300 - _SESSION_OFFSET, tz=UTC
)
REGISTRY = Digest("sha256:" + "3" * 64)


ConnectionT = Connection[tuple[object, ...]]


def _setup_evidence(conn: ConnectionT) -> None:
    run_token = uuid4().hex
    source_id = f"fixture.orchestrator.{run_token}"
    retrieved_at = BOUNDARY - timedelta(seconds=1)
    body = b"""<rss version="2.0"><channel>
      <item><title>Orchestrated live item</title><link>https://example.com/orch-live</link>
        <comments>https://news.ycombinator.com/item?id=91001</comments></item>
      <item><title>Orchestrated backfill item</title><link>https://example.com/orch-bf</link>
        <comments>https://news.ycombinator.com/item?id=91002</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)
    source = SourceContract(
        source_id=source_id,
        display_name="Orchestrator fixture emission source",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )
    evidence = PostgresEvidenceStore(conn)
    evidence.upsert_source(source)
    reasons = (CollectionReason.SCHEDULED, CollectionReason.BACKFILL)
    for candidate, reason in zip(candidates, reasons, strict=True):
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=reason,
            started_at=candidate.retrieved_at,
        )
        evidence.start_collection_run(run)
        _, inserted = evidence.append_observation(candidate, run.run_id)
        assert inserted
    evidence.add_source_health(
        SourceHealthObservation(
            source_id=source_id,
            as_of=BOUNDARY,
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.OK,
            schema=HealthValue.OK,
            details={},
        )
    )


def _orchestrator(
    conn: ConnectionT, *, worker_id: str, boundary: datetime
) -> ExperimentOrchestrator:
    return ExperimentOrchestrator(
        attempts=PostgresExperimentAttemptRepository(conn),
        baseline_repository=PostgresBaselineIntelligenceRepository(conn),
        persistence=PostgresShadowRunPersister(conn),
        source_registry_version=REGISTRY,
        canonical_context=True,
        worker_id=worker_id,
        lease_seconds=1.0,
        clock=lambda: boundary,
    )


def _boundary(offset: int) -> datetime:
    """Each test owns a distinct 300s-aligned boundary window."""
    return BOUNDARY + timedelta(seconds=300 * offset)


def test_attempt_uniqueness_is_enforced_at_database_level() -> None:
    assert DB_URL is not None
    boundary = _boundary(0)
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=boundary,
        attempt_no=1,
        status=ExperimentAttemptStatus.PENDING,
    )
    with psycopg.connect(DB_URL) as conn:
        repo = PostgresExperimentAttemptRepository(conn)
        assert repo.record_attempt(attempt) is True
        # Duplicate delivery: identical attempt is an idempotent no-op.
        assert repo.record_attempt(attempt) is False
        with (
            pytest.raises(psycopg.errors.UniqueViolation),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                INSERT INTO experiment_run_attempts (
                    attempt_id, experiment_id, as_of, attempt_no, status,
                    attempt_digest
                ) VALUES (%s, %s, %s, %s, 'PENDING', %s)
                """,
                (
                    attempt.attempt_id,
                    attempt.experiment_id,
                    attempt.as_of,
                    attempt.attempt_no,
                    "sha256:" + "0" * 64,
                ),
            )


def test_lease_expiry_expires_stale_attempt_and_retry_increments_attempt_no() -> None:
    assert DB_URL is not None
    boundary = _boundary(1)
    with psycopg.connect(DB_URL) as conn:
        repo = PostgresExperimentAttemptRepository(conn)
        attempt = ExperimentRunAttempt(
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            attempt_no=1,
            status=ExperimentAttemptStatus.PENDING,
        )
        assert repo.record_attempt(attempt) is True
        assert (
            repo.claim(
                attempt.attempt_id,
                owner="worker.crashed",
                lease_expires_at=boundary + timedelta(seconds=1),
                now=boundary,
            )
            is True
        )
        latest = repo.latest_attempt(PEF_EXPERIMENT_ID, boundary)
        assert latest is not None
        assert latest.status is ExperimentAttemptStatus.RUNNING
        assert latest.lease_owner == "worker.crashed"
        # A fresh worker adopts-or-expires: the stale lease is expired with
        # reason, then the boundary retries with attempt_no incremented.
        expired = repo.expire_stale(now=boundary + timedelta(seconds=2))
        # Only attempts of THIS boundary window are asserted (other sessions
        # may legitimately have their own stale RUNNING attempts swept).
        ours = [attempt for attempt in expired if attempt.as_of == boundary]
        assert len(ours) == 1
        assert ours[0].status is ExperimentAttemptStatus.EXPIRED
        assert ours[0].detail == "lease expired"
        # Expiry releases the lease (CHECK: non-RUNNING rows hold no owner).
        assert ours[0].lease_owner is None
        latest = repo.latest_attempt(PEF_EXPERIMENT_ID, boundary)
        assert latest is not None and latest.status is ExperimentAttemptStatus.EXPIRED
        retry = ExperimentRunAttempt(
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            attempt_no=latest.attempt_no + 1,
            status=ExperimentAttemptStatus.PENDING,
        )
        assert repo.record_attempt(retry) is True
        assert (
            repo.claim(
                retry.attempt_id,
                owner="worker.recovery",
                lease_expires_at=boundary + timedelta(seconds=60),
                now=boundary,
            )
            is True
        )
        latest = repo.latest_attempt(PEF_EXPERIMENT_ID, boundary)
        assert latest is not None and latest.attempt_no == 2


def test_orchestrator_crash_restart_persists_run_once_and_no_duplicate() -> None:
    assert DB_URL is not None
    boundary = _boundary(2)
    with psycopg.connect(DB_URL) as conn:
        _setup_evidence(conn)
        attempts = PostgresExperimentAttemptRepository(conn)
        first = _orchestrator(conn, worker_id="worker.first", boundary=boundary).run_cycle()
        assert first.action is ExperimentCycleAction.RAN
        assert first.run_id is not None
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), max(control_snapshot_id)
                FROM shadow_experiment_runs WHERE run_id = %s
                """,
                (first.run_id,),
            )
            row = cur.fetchone()
            assert row is not None and row[0] == 1
            control_snapshot_id = row[1]
            cur.execute(
                "SELECT count(*) FROM baseline_intelligence_snapshots WHERE snapshot_id = %s",
                (control_snapshot_id,),
            )
            assert cur.fetchone() == (1,)

        # Simulated crash: the DONE attempt is rolled back to a RUNNING
        # attempt with an expired lease, as a crashed process would leave it.
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                UPDATE experiment_run_attempts
                SET status = 'RUNNING', lease_owner = 'worker.crashed',
                    lease_expires_at = %s, detail = NULL
                WHERE experiment_id = %s AND as_of = %s AND attempt_no = 1
                """,
                (boundary - timedelta(seconds=1), PEF_EXPERIMENT_ID, boundary),
            )
        recovered = _orchestrator(conn, worker_id="worker.recovered", boundary=boundary).run_cycle()
        # Crash happened AFTER the run row was persisted: the recovery cycle
        # must NOT re-execute the boundary (no duplicate run row); it adopts
        # the boundary as ALREADY_COMPLETE with an incremented attempt_no.
        assert recovered.action is ExperimentCycleAction.ALREADY_COMPLETE
        assert recovered.run_id == first.run_id
        with conn.cursor() as cur:
            # The deterministic re-execution reproduced the identical
            # content-derived run_id: still exactly one run row.
            cur.execute(
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                (first.run_id,),
            )
            assert cur.fetchone() == (1,)
            cur.execute(
                "SELECT count(*) FROM baseline_intelligence_snapshots WHERE snapshot_id = %s",
                (control_snapshot_id,),
            )
            assert cur.fetchone() == (1,)
        history = attempts.latest_attempt(PEF_EXPERIMENT_ID, boundary)
        assert history is not None and history.status is ExperimentAttemptStatus.DONE
        assert history.attempt_no == 2

        # The completed boundary is never re-executed after this.
        again = _orchestrator(conn, worker_id="worker.again", boundary=boundary).run_cycle()
        assert again.action is ExperimentCycleAction.ALREADY_COMPLETE
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                (first.run_id,),
            )
            assert cur.fetchone() == (1,)


def test_freeze_binding_resolver_reads_durable_freeze_stamp() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        resolver = PostgresFreezeBindingResolver(conn)
        binding = resolver.latest_binding()
        if binding is None:
            # No freeze receipts exist: confirmatory gating fails closed.
            assert (
                evaluate_confirmatory_gates(None, as_of=BOUNDARY, canonical_context=True).allowed
                is False
            )
        else:
            # A binding read from the canonical DB must re-verify its stored
            # digest (checked inside the resolver) and carry the durability
            # stamp column truthfully (may be NULL for legacy rows).
            assert binding.receipt.status in (FreezeStatus.FROZEN, FreezeStatus.DRIFTED)
            assert binding.durable_freeze_at is None or binding.durable_freeze_at.tzinfo is not None
