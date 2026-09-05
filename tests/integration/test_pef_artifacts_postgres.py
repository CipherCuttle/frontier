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
from frontier.adapters.postgres.advanced_intelligence import PostgresPefArtifactRepository
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.application.advanced_intelligence import run_pef_v0_ranking
from frontier.application.intelligence import run_baseline_intelligence
from frontier.domain.advanced_intelligence import (
    PEF_CONFIGURATION_DIGEST,
    PEF_PROJECTION_NAME,
    PefArtifactStatus,
    build_pef_receipt,
)
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.observation import Observation
from frontier.domain.receipt import ProjectionStatus
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_postgres_pef_artifact_retains_ranking_and_rolls_back_conflict() -> None:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Prospective emission live</title><link>https://example.com/pef-live</link>
        <comments>https://news.ycombinator.com/item?id=88001</comments></item>
      <item><title>Backfilled emission</title><link>https://example.com/pef-backfill</link>
        <comments>https://news.ycombinator.com/item?id=88002</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source_id = "fixture.pef.emission"
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)
    source = SourceContract(
        source_id=source_id,
        display_name="PEF fixture emission source",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(source)
        observations: list[Observation] = []
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

        baseline = PostgresBaselineIntelligenceRepository(conn)
        control = run_baseline_intelligence(
            baseline,
            as_of=as_of,
            generated_at=as_of + timedelta(seconds=1),
            source_registry_version=Digest(
                "sha256:498b4afff3b5a0dcbfb448514a08a3e85adf7f8f2dd5d0863aebbcb353c361f8"
            ),
        )
        pef_observations = tuple(baseline.list_baseline_observations_as_of(as_of))
        result = run_pef_v0_ranking(
            pef_observations,
            control_snapshot=control.snapshot,
            control_receipt=control.receipt,
            generated_at=as_of + timedelta(seconds=2),
            source_registry_version=control.receipt.source_registry_version,
        )
        assert result.artifact.status is PefArtifactStatus.RAN
        assert result.artifact.control_snapshot_id == control.snapshot.snapshot_id
        assert result.artifact.control_receipt_id == control.receipt.receipt_id
        assert str(result.receipt.configuration_digest) == str(PEF_CONFIGURATION_DIGEST)
        assert result.receipt.projection_name == PEF_PROJECTION_NAME
        assert result.artifact.output_digest == result.receipt.output_digest
        assert len(result.artifact.episodes) == len(control.snapshot.episodes)
        episode = next(
            item
            for item in result.artifact.episodes
            if {obs.observation_id for obs in observations} <= set(item.observation_ids)
        )
        assert episode.prospective_evidence_count == 1
        assert episode.has_any_prospective_evidence is True

        repository = PostgresPefArtifactRepository(conn)
        repository.publish_complete_artifact(result.artifact, result.receipt)
        assert repository.latest_artifact_id() == result.artifact.artifact_id
        retained = repository.get_artifact_json(result.artifact.artifact_id)
        assert retained == result.artifact.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.status, p.projection_name, s.status, s.output_digest
                FROM pef_ranking_artifacts s
                JOIN projection_receipts p ON p.receipt_id = s.receipt_id
                WHERE s.artifact_id = %s
                """,
                (result.artifact.artifact_id,),
            )
            row = cur.fetchone()
        assert row == (
            "COMPLETE",
            PEF_PROJECTION_NAME,
            "RAN",
            str(result.receipt.output_digest),
        )

        conflicting_receipt = replace(
            result.receipt,
            source_registry_version=Digest("sha256:" + "3" * 64),
        )
        assert conflicting_receipt.receipt_id != result.receipt.receipt_id
        with pytest.raises(RuntimeError, match="different receipt"):
            repository.publish_complete_artifact(result.artifact, conflicting_receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM projection_receipts WHERE receipt_id = %s",
                (conflicting_receipt.receipt_id,),
            )
            assert cur.fetchone() == (0,)

        failed_artifact = replace(
            result.artifact,
            status=PefArtifactStatus.FAILED,
            failure_reason="shadow ranking halted",
            episodes=(),
        )
        failed_receipt = build_pef_receipt(
            failed_artifact,
            observations=pef_observations,
            control_snapshot=control.snapshot,
        )
        assert failed_receipt.status is ProjectionStatus.FAILED
        repository.record_failed_artifact(failed_artifact, failed_receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM pef_ranking_artifacts WHERE artifact_id = %s",
                (failed_artifact.artifact_id,),
            )
            assert cur.fetchone() == ("FAILED",)

        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE pef_ranking_artifacts SET as_of = as_of WHERE artifact_id = %s",
                (result.artifact.artifact_id,),
            )
