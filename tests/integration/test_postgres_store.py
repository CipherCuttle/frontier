# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.observation import DocumentPayload
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

FIXTURE = Path("fixtures/sources/hostile_document_v1")
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def source() -> SourceContract:
    return SourceContract(
        source_id="fixture.hostile_document",
        display_name="Hostile document fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def reset(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE projection_receipts, source_health_observations, observation_relations, "
            "collection_run_observations, observations, collection_runs, sources CASCADE"
        )
    conn.commit()


def test_postgres_idempotency_occurrence_history_and_knowledge_horizon() -> None:
    assert DB_URL is not None
    candidate, _ = load_fixture_candidate(FIXTURE)
    with psycopg.connect(DB_URL) as conn:
        reset(conn)
        store = PostgresEvidenceStore(conn)
        store.upsert_source(source())
        first_observation = None
        for index in range(100):
            run = CollectionRun(
                run_id=uuid4(),
                source_id=source().source_id,
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
            cur.execute("SELECT count(*) FROM observations")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM collection_run_observations")
            assert cur.fetchone()[0] == 100

        assert first_observation is not None
        assert (
            store.list_observation_ids_as_of(
                first_observation.observed_at - timedelta(microseconds=1)
            )
            == []
        )
        assert store.list_observation_ids_as_of(first_observation.observed_at) == [
            candidate.observation_id
        ]

        retry_candidate = replace(
            candidate,
            retrieved_at=candidate.retrieved_at + timedelta(minutes=5),
            fetch_digest=sha256_digest(b"different transport bytes, same semantic evidence"),
        )
        assert retry_candidate.observation_id == candidate.observation_id
        retry_run = CollectionRun(
            run_id=uuid4(),
            source_id=source().source_id,
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
            source_id=source().source_id,
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
            source_id=source().source_id,
            as_of=second.observed_at,
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.DEGRADED,
            schema=HealthValue.OK,
            details={"pagination_complete": False},
        )
        store.add_source_health(health)
        with conn.cursor() as cur:
            cur.execute("SELECT completeness_health FROM source_health_observations")
            assert cur.fetchone()[0] == "DEGRADED"


def test_canonical_tables_are_database_enforced_append_only() -> None:
    assert DB_URL is not None
    candidate, _ = load_fixture_candidate(FIXTURE)
    with psycopg.connect(DB_URL) as conn:
        reset(conn)
        store = PostgresEvidenceStore(conn)
        store.upsert_source(source())
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source().source_id,
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
                "frontier_append_only_collection_occurrences",
                "frontier_append_only_observations",
                "frontier_append_only_projection_receipts",
                "frontier_append_only_relations",
                "frontier_append_only_source_health",
            }

        with pytest.raises(psycopg.Error) as update_error:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "UPDATE observations SET retrieved_at = retrieved_at WHERE observation_id = %s",
                    (observation.observation_id,),
                )
        assert update_error.value.sqlstate == "55000"

        with pytest.raises(psycopg.Error) as delete_error:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM observations WHERE observation_id = %s",
                    (observation.observation_id,),
                )
        assert delete_error.value.sqlstate == "55000"
