# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.advanced_intelligence import (
    PostgresShadowRunRepository,
)
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.application.advanced_intelligence import run_shadow_experiment
from frontier.application.intelligence import run_baseline_intelligence
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_EXPERIMENT_ID,
    SHADOW_SCHEMA_VERSION,
    ShadowRunStatus,
)
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.observation import Observation
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_postgres_shadow_run_persists_paired_result_and_is_append_only() -> None:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Shadow paired live</title><link>https://example.com/shadow-live</link>
        <comments>https://news.ycombinator.com/item?id=89001</comments></item>
      <item><title>Backfilled shadow item</title><link>https://example.com/shadow-backfill</link>
        <comments>https://news.ycombinator.com/item?id=89002</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source_id = "fixture.shadow.emission"
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)
    source = SourceContract(
        source_id=source_id,
        display_name="Shadow fixture emission source",
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
        shadow_observations = tuple(baseline.list_baseline_observations_as_of(as_of))
        result = run_shadow_experiment(
            shadow_observations,
            control_snapshot=control.snapshot,
            control_receipt=control.receipt,
            generated_at=as_of + timedelta(seconds=2),
            source_registry_version=control.receipt.source_registry_version,
        )
        assert result.status is ShadowRunStatus.RAN
        assert result.authority_state == PEF_AUTHORITY_STATE == "EXPERIMENTAL_SHADOW"
        assert result.experiment_id == PEF_EXPERIMENT_ID
        assert result.candidate_id == PEF_CANDIDATE_ID
        assert result.algorithm_version == PEF_ALGORITHM_VERSION
        assert result.schema_version == SHADOW_SCHEMA_VERSION
        assert result.control_snapshot_id == control.snapshot.snapshot_id
        assert isinstance(result.coverage_state, HealthValue)
        assert len(result.control_ranking) == len(control.snapshot.episodes)

        repository = PostgresShadowRunRepository(conn)
        repository.record_run(result)
        retained = repository.get_run_json(result.run_id)
        assert retained == result.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, authority_state, coverage_state,
                       control_snapshot_id, candidate_artifact_id,
                       candidate_output_digest, episode_universe_digest,
                       run_digest, failure_reason
                FROM shadow_experiment_runs
                WHERE run_id = %s
                """,
                (result.run_id,),
            )
            row = cur.fetchone()
        assert row == (
            "RAN",
            "EXPERIMENTAL_SHADOW",
            result.coverage_state.value,
            result.control_snapshot_id,
            result.candidate_artifact_id,
            str(result.candidate_output_digest),
            str(result.episode_universe_digest),
            str(result.run_digest),
            None,
        )

        # Re-recording the identical run is an append-only no-op, not a rewrite.
        repository.record_run(result)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM shadow_experiment_runs WHERE run_id = %s",
                (result.run_id,),
            )
            assert cur.fetchone() == (1,)

        # A conflicting identity with a different digest must never be stored.
        drifted_payload = dict(result.to_canonical())
        drifted_payload["failure_reason"] = "drifted"
        with (
            pytest.raises(psycopg.errors.UniqueViolation),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                INSERT INTO shadow_experiment_runs (
                    run_id, experiment_id, candidate_id, schema_version,
                    algorithm_version, configuration_digest, authority_state,
                    status, as_of, control_snapshot_id, control_receipt_id,
                    candidate_artifact_id, candidate_output_digest,
                    coverage_state, episode_universe_digest, run_digest,
                    failure_reason, run_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    result.run_id,
                    result.experiment_id,
                    result.candidate_id,
                    result.schema_version,
                    result.algorithm_version,
                    str(result.configuration_digest),
                    result.authority_state,
                    "FAILED",
                    result.as_of,
                    result.control_snapshot_id,
                    result.control_receipt_id,
                    result.candidate_artifact_id,
                    str(result.candidate_output_digest),
                    result.coverage_state.value,
                    str(result.episode_universe_digest),
                    "sha256:" + "e" * 64,
                    "drifted",
                    Jsonb(drifted_payload),
                ),
            )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM shadow_experiment_runs WHERE run_id = %s",
                (result.run_id,),
            )
            assert cur.fetchone() == (1,)

        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE shadow_experiment_runs SET as_of = as_of WHERE run_id = %s",
                (result.run_id,),
            )
