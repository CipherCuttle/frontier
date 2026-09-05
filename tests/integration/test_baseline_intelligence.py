# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.application.intelligence import run_baseline_intelligence
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_postgres_baseline_retains_complete_snapshot_and_rolls_back_conflict() -> None:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Baseline live discussion</title><link>https://example.com/baseline</link>
        <comments>https://news.ycombinator.com/item?id=99001</comments></item>
      <item><title>Baseline backfill discussion</title><link>https://example.com/baseline</link>
        <comments>https://news.ycombinator.com/item?id=99002</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source_id = "fixture.baseline.attention"
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)
    source = SourceContract(
        source_id=source_id,
        display_name="Baseline intelligence attention fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.ATTENTION,),
        transport=SourceTransport.FIXTURE,
    )

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(source)
        observations = []
        reasons = (CollectionReason.SCHEDULED, CollectionReason.BACKFILL)
        for candidate, reason in zip(candidates, reasons, strict=True):
            run = CollectionRun(
                run_id=uuid4(),
                source_id=source_id,
                reason=reason,
                started_at=candidate.retrieved_at,
            )
            evidence.start_collection_run(run)
            observation, inserted = evidence.append_observation(candidate, run.run_id)
            assert inserted
            observations.append(observation)

        as_of = max(item.observed_at for item in observations) + timedelta(seconds=1)
        evidence.add_source_health(
            SourceHealthObservation(
                source_id=source_id,
                as_of=as_of,
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
                details={},
            )
        )

        repository = PostgresBaselineIntelligenceRepository(conn)
        result = run_baseline_intelligence(
            repository,
            as_of=as_of,
            generated_at=as_of + timedelta(seconds=1),
            source_registry_version=Digest(
                "sha256:498b4afff3b5a0dcbfb448514a08a3e85adf7f8f2dd5d0863aebbcb353c361f8"
            ),
        )
        fixture_ids = {item.observation_id for item in observations}
        episode = next(
            item for item in result.snapshot.episodes if fixture_ids <= set(item.observation_ids)
        )
        assert episode.evidence_count_total == 2
        assert episode.prospective_evidence_count == 1
        assert episode.backfill_evidence_count == 1
        assert episode.mentions_1h == 1
        assert episode.confirmation == "UNAVAILABLE"
        assert episode.evidence_root_diversity is None
        assert repository.latest_complete_snapshot_id() == result.snapshot.snapshot_id

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.status, p.ranking_policy_version, s.output_digest
                FROM baseline_intelligence_snapshots s
                JOIN projection_receipts p ON p.receipt_id = s.receipt_id
                WHERE s.snapshot_id = %s
                """,
                (result.snapshot.snapshot_id,),
            )
            row = cur.fetchone()
        assert row == (
            "COMPLETE",
            "naive-episode-activity-v0",
            str(result.receipt.output_digest),
        )

        conflicting_receipt = replace(
            result.receipt,
            source_registry_version=Digest("sha256:" + "2" * 64),
        )
        assert conflicting_receipt.receipt_id != result.receipt.receipt_id
        with pytest.raises(RuntimeError, match="different receipt"):
            repository.publish_complete_snapshot(result.snapshot, conflicting_receipt)
        assert repository.latest_complete_snapshot_id() == result.snapshot.snapshot_id
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM projection_receipts WHERE receipt_id = %s",
                (conflicting_receipt.receipt_id,),
            )
            assert cur.fetchone() == (0,)

        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE baseline_intelligence_snapshots SET as_of = as_of "
                "WHERE snapshot_id = %s",
                (result.snapshot.snapshot_id,),
            )
