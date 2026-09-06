# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.opportunity import PostgresOpportunityRepository
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import sha256_digest
from frontier.domain.opportunity import (
    BlindingState,
    DomainStratum,
    OpportunityAnchor,
    OpportunityState,
    OutcomeLabel,
    OutcomeResolution,
    advance,
    genesis_transition,
)
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _test_source() -> SourceContract:
    return SourceContract(
        source_id="fixture.opportunity.anchor",
        display_name="Opportunity fixture anchor source",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def _build_anchor(observation_id: str, observed_at: datetime) -> OpportunityAnchor:
    return OpportunityAnchor(
        observation_id=observation_id,
        source_id="fixture.opportunity.anchor",
        as_of=observed_at + timedelta(seconds=300),
        observed_at=observed_at,
        domain_stratum=DomainStratum.SOFTWARE_PACKAGES,
    )


def test_postgres_opportunity_state_is_append_only_and_idempotent() -> None:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Opportunity anchor live</title><link>https://example.com/opportunity</link>
        <comments>https://news.ycombinator.com/item?id=91001</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source = _test_source()

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(source)
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source.source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=retrieved_at,
        )
        evidence.start_collection_run(run)
        observation, inserted = evidence.append_observation(batch.candidates[0], run.run_id)
        assert inserted

        anchor = _build_anchor(observation.observation_id, observation.observed_at)
        repository = PostgresOpportunityRepository(conn)

        # Anchor insert is content-derived and idempotent (re-insert is a no-op).
        repository.record_anchor(anchor)
        repository.record_anchor(anchor)
        assert repository.count_anchors() >= 1
        assert repository.get_anchor_json(anchor.anchor_id) == anchor.to_canonical()

        # The transition log folds into the projection; identical events are no-ops.
        genesis = genesis_transition(anchor, occurred_at=observation.observed_at)
        repository.record_transition(genesis)
        repository.record_transition(genesis)
        assert repository.read_projection(anchor.anchor_id) is OpportunityState.PENDING

        resolution = OutcomeResolution(
            resolution_state=OpportunityState.RESOLVED,
            label=OutcomeLabel.POSITIVE,
            blinding_state=BlindingState.BLINDED,
            decided_at=anchor.resolution_at,
            evidence_digest="sha256:" + "c" * 64,
        )
        terminal = advance(
            anchor,
            OpportunityState.PENDING,
            OpportunityState.RESOLVED,
            reason="blinded automated adjudication resolved POSITIVE",
            occurred_at=anchor.resolution_at,
        )
        repository.record_transition(terminal)
        repository.record_resolution(anchor.anchor_id, resolution)
        repository.record_resolution(anchor.anchor_id, resolution)
        assert repository.read_projection(anchor.anchor_id) is OpportunityState.RESOLVED
        assert repository.get_resolution_json(anchor.anchor_id) == resolution.to_canonical()

        # Replaying the same log in-domain yields the same projection.
        assert repository.list_transitions(anchor.anchor_id) == (genesis, terminal)

        # Append-only: UPDATE/DELETE on the transition log must be rejected.
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE opportunity_transitions SET reason = reason WHERE anchor_id = %s",
                (anchor.anchor_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "DELETE FROM opportunity_anchors WHERE anchor_id = %s",
                (anchor.anchor_id,),
            )

        # outcome_resolutions rejects unblinded adjudications at the DB layer too.
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                INSERT INTO outcome_resolutions (
                    anchor_id, schema_version, resolution_state, label,
                    blinding_state, decided_at, evidence_digest,
                    lane_health_digest, resolution_digest, resolution_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    anchor.anchor_id,
                    "opportunity-outcome-state-v0",
                    "RESOLVED",
                    "NEGATIVE",
                    "OPEN",
                    anchor.resolution_at,
                    "sha256:" + "d" * 64,
                    None,
                    "sha256:" + "e" * 64,
                    "{}",
                ),
            )


def test_postgres_run_attempts_lease_discipline_and_heartbeats() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        as_of = datetime(2026, 9, 5, 12, tzinfo=UTC)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO experiment_run_attempts (
                    attempt_id, experiment_id, as_of, attempt_no, status, attempt_digest
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    "opattempt_" + "f" * 64,
                    "advanced-ranking-pef-v0",
                    as_of,
                    1,
                    "PENDING",
                    "sha256:" + "1" * 64,
                ),
            )
            # RUNNING requires an explicit lease (fail-closed).
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                cur.execute(
                    "UPDATE experiment_run_attempts SET status = 'RUNNING' WHERE attempt_id = %s",
                    ("opattempt_" + "f" * 64,),
                )
            cur.execute(
                """
                UPDATE experiment_run_attempts
                SET status = 'RUNNING', lease_owner = %s,
                    lease_expires_at = %s, heartbeat_at = %s
                WHERE attempt_id = %s
                """,
                (
                    "worker-1",
                    as_of + timedelta(seconds=60),
                    as_of,
                    "opattempt_" + "f" * 64,
                ),
            )
            # A boundary may be retried after EXPIRED via a new attempt_no.
            cur.execute(
                """
                INSERT INTO experiment_run_attempts (
                    attempt_id, experiment_id, as_of, attempt_no, status, attempt_digest
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    "opattempt_" + "0" * 64,
                    "advanced-ranking-pef-v0",
                    as_of,
                    2,
                    "EXPIRED",
                    "sha256:" + "2" * 64,
                ),
            )
            cur.execute("SELECT count(*) FROM experiment_run_attempts WHERE as_of = %s", (as_of,))
            assert cur.fetchone() == (2,)

            # Worker heartbeats are a mutable operational table (upsert).
            cur.execute(
                """
                INSERT INTO worker_heartbeats (worker_id, role, beat_at, metrics)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (worker_id) DO UPDATE
                SET role = EXCLUDED.role, beat_at = EXCLUDED.beat_at,
                    metrics = EXCLUDED.metrics
                """,
                ("worker-1", "boundary-runner", as_of, "{}"),
            )
            cur.execute(
                """
                INSERT INTO worker_heartbeats (worker_id, role, beat_at, metrics)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (worker_id) DO UPDATE
                SET role = EXCLUDED.role, beat_at = EXCLUDED.beat_at,
                    metrics = EXCLUDED.metrics
                """,
                ("worker-1", "ranking-runner", as_of + timedelta(seconds=1), '{"ok": true}'),
            )
            cur.execute(
                "SELECT role, metrics->>'ok' FROM worker_heartbeats WHERE worker_id = 'worker-1'"
            )
            assert cur.fetchone() == ("ranking-runner", "true")


def test_postgres_durable_freeze_at_is_stamped_at_canonical_insert() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt_id = "freezereceipt_" + "9" * 64
        frozen_at = datetime(2026, 9, 5, 10, tzinfo=UTC)
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidate_freeze_receipts (
                    receipt_id, schema_version, candidate_id, experiment_id,
                    algorithm_version, configuration_digest, status,
                    preregistration_path, preregistration_digest,
                    drift_reasons, receipt_digest, frozen_at, receipt_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    receipt_id,
                    "candidate-freeze-receipt-v0",
                    "prospective-primary-emission-freshness-v0",
                    "advanced-ranking-pef-v0",
                    "prospective-primary-emission-freshness-lexicographic-v0",
                    "sha256:" + "2" * 64,
                    "FROZEN",
                    "experiments/advanced_intelligence/pef_v0/preregistration.json",
                    "sha256:" + "3" * 64,
                    "[]",
                    "sha256:" + "4" * 64,
                    frozen_at,
                    "{}",
                ),
            )
            cur.execute(
                """
                SELECT frozen_at, durable_freeze_at
                FROM candidate_freeze_receipts WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
        assert row is not None
        frozen, durable = row
        assert durable is not None
        # durable_freeze_at is the canonical insert-transaction clock, distinct
        # from the receipt creation time and never collapsed with it.
        assert frozen == frozen_at
        assert durable >= frozen_at
        assert durable != frozen_at
