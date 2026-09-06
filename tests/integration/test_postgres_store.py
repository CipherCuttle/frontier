# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.observation import DocumentPayload, ObservationCandidate
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

FIXTURE = Path("fixtures/sources/hostile_document_v1")
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def source(source_id: str) -> SourceContract:
    return SourceContract(
        source_id=source_id,
        display_name="Hostile document fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def candidate_for(source_id: str) -> ObservationCandidate:
    candidate, _ = load_fixture_candidate(FIXTURE)
    return replace(candidate, source_id=source_id)


def test_postgres_idempotency_occurrence_history_and_knowledge_horizon() -> None:
    assert DB_URL is not None
    source_id = "fixture.idempotency"
    candidate = candidate_for(source_id)
    with psycopg.connect(DB_URL) as conn:
        store = PostgresEvidenceStore(conn)
        store.upsert_source(source(source_id))
        first_observation = None
        for index in range(100):
            run = CollectionRun(
                run_id=uuid4(),
                source_id=source_id,
                reason=CollectionReason.SCHEDULED,
                started_at=candidate.retrieved_at + timedelta(seconds=index),
            )
            store.start_collection_run(run)
            observation, inserted = store.append_observation(candidate, run.run_id)
            if index == 0:
                assert inserted
                first_observation = observation
            else:
                assert not inserted
                assert first_observation is not None
                assert observation.observed_at == first_observation.observed_at

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM observations WHERE source_id = %s", (source_id,))
            assert cur.fetchone()[0] == 1
            cur.execute(
                """
                SELECT count(*)
                FROM collection_run_observations cro
                JOIN collection_runs cr ON cr.run_id = cro.run_id
                WHERE cr.source_id = %s
                """,
                (source_id,),
            )
            assert cur.fetchone()[0] == 100

        assert first_observation is not None
        before_horizon = store.list_observation_ids_as_of(
            first_observation.observed_at - timedelta(microseconds=1)
        )
        assert candidate.observation_id not in before_horizon
        assert candidate.observation_id in store.list_observation_ids_as_of(
            first_observation.observed_at
        )

        retry_candidate = replace(
            candidate,
            retrieved_at=candidate.retrieved_at + timedelta(minutes=5),
            fetch_digest=sha256_digest(b"different transport bytes, same semantic evidence"),
        )
        assert retry_candidate.observation_id == candidate.observation_id
        retry_run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=retry_candidate.retrieved_at,
        )
        store.start_collection_run(retry_run)
        retry_observation, inserted = store.append_observation(retry_candidate, retry_run.run_id)
        assert not inserted
        assert retry_observation.observed_at == first_observation.observed_at
        assert retry_observation.candidate.retrieved_at == first_observation.candidate.retrieved_at
        assert retry_observation.candidate.fetch_digest == first_observation.candidate.fetch_digest
        assert retry_observation.to_canonical() == first_observation.to_canonical()

        document_payload = cast(DocumentPayload, candidate.payload)
        changed = replace(
            candidate,
            payload=DocumentPayload(
                canonical_url=document_payload.canonical_url,
                title="changed",
                excerpt=document_payload.excerpt,
                language=document_payload.language,
                source_metadata=document_payload.source_metadata,
            ),
        )
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=CollectionReason.BACKFILL,
            started_at=candidate.retrieved_at,
        )
        store.start_collection_run(run)
        second, inserted = store.append_observation(changed, run.run_id)
        assert inserted
        assert second.observation_id != first_observation.observation_id

        relation = ObservationRelation(
            relation_type=RelationType.CORRECTS,
            from_observation_id=second.observation_id,
            target_observation_id=first_observation.observation_id,
            authority=RelationAuthority.EXPLICIT,
            evidence={"fixture": "correction"},
        )
        store.add_relation(relation)

        health = SourceHealthObservation(
            source_id=source_id,
            as_of=second.observed_at,
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.DEGRADED,
            schema=HealthValue.OK,
            details={"pagination_complete": False},
        )
        store.add_source_health(health)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT completeness_health FROM source_health_observations WHERE source_id = %s",
                (source_id,),
            )
            assert cur.fetchone()[0] == "DEGRADED"


def test_canonical_tables_are_database_enforced_append_only() -> None:
    assert DB_URL is not None
    source_id = "fixture.append_only"
    candidate = candidate_for(source_id)
    with psycopg.connect(DB_URL) as conn:
        store = PostgresEvidenceStore(conn)
        store.upsert_source(source(source_id))
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=candidate.retrieved_at,
        )
        store.start_collection_run(run)
        observation, inserted = store.append_observation(candidate, run.run_id)
        assert inserted

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tgname
                FROM pg_trigger
                WHERE NOT tgisinternal AND tgname LIKE 'frontier_append_only_%'
                ORDER BY tgname
                """
            )
            assert {row[0] for row in cur.fetchall()} == {
                "frontier_append_only_baseline_snapshots",
                "frontier_append_only_baseline_snapshots_truncate",
                "frontier_append_only_candidate_freeze_receipts",
                "frontier_append_only_candidate_freeze_receipts_truncate",
                "frontier_append_only_collection_occurrences",
                "frontier_append_only_collection_occurrences_truncate",
                "frontier_append_only_evaluation_receipts",
                "frontier_append_only_evaluation_receipts_truncate",
                "frontier_append_only_experimental_analysis",
                "frontier_append_only_experimental_analysis_truncate",
                "frontier_append_only_feature_vectors",
                "frontier_append_only_feature_vectors_truncate",
                "frontier_append_only_observations",
                "frontier_append_only_observations_truncate",
                "frontier_append_only_pef_artifacts",
                "frontier_append_only_pef_artifacts_truncate",
                "frontier_append_only_projection_receipts",
                "frontier_append_only_projection_receipts_truncate",
                "frontier_append_only_relations",
                "frontier_append_only_relations_truncate",
                "frontier_append_only_shadow_experiment_runs",
                "frontier_append_only_shadow_experiment_runs_truncate",
                "frontier_append_only_source_health",
                "frontier_append_only_source_health_truncate",
            }

        with (
            pytest.raises(psycopg.Error) as update_error,
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE observations SET retrieved_at = retrieved_at WHERE observation_id = %s",
                (observation.observation_id,),
            )
        assert update_error.value.sqlstate == "55000"

        with (
            pytest.raises(psycopg.Error) as delete_error,
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "DELETE FROM observations WHERE observation_id = %s",
                (observation.observation_id,),
            )
        assert delete_error.value.sqlstate == "55000"

        with (
            pytest.raises(psycopg.Error) as truncate_error,
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute("TRUNCATE projection_receipts, baseline_intelligence_snapshots")
        assert truncate_error.value.sqlstate == "55000"
