from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from frontier.domain.collection import CollectionRun, OccurrenceStatus
from frontier.domain.health import SourceHealthObservation
from frontier.domain.observation import Observation, ObservationCandidate
from frontier.domain.relation import ObservationRelation
from frontier.domain.source import SourceContract


class PostgresEvidenceStore:
    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def upsert_source(self, source: SourceContract) -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sources (
                    source_id, contract_schema_version, display_name, acquisition_class,
                    signal_roles, transport, enabled, contract_json, contract_digest
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    acquisition_class = EXCLUDED.acquisition_class,
                    signal_roles = EXCLUDED.signal_roles,
                    transport = EXCLUDED.transport,
                    enabled = EXCLUDED.enabled,
                    contract_json = EXCLUDED.contract_json,
                    contract_digest = EXCLUDED.contract_digest
                """,
                (
                    source.source_id,
                    "source-contract-v1",
                    source.display_name,
                    source.acquisition_class.value,
                    [role.value for role in source.signal_roles],
                    source.transport.value,
                    source.enabled,
                    Jsonb(source.to_canonical()),
                    str(source.contract_digest),
                ),
            )
        self._connection.commit()

    def start_collection_run(self, run: CollectionRun) -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_runs (
                    run_id, source_id, reason, trigger_id, recovered_after_gap,
                    started_at, status
                ) VALUES (%s,%s,%s,%s,%s,%s,'RUNNING')
                """,
                (
                    run.run_id,
                    run.source_id,
                    run.reason.value,
                    run.trigger_id,
                    run.recovered_after_gap,
                    run.started_at,
                ),
            )
        self._connection.commit()

    def append_observation(
        self, candidate: ObservationCandidate, run_id: UUID
    ) -> tuple[Observation, bool]:
        with self._connection.transaction():
            with self._connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO observations (
                        observation_id, schema_version, canonicalization_version,
                        source_id, source_item_key, kind, payload_json,
                        source_published_at, effective_at, observed_at, retrieved_at,
                        content_digest, fetch_digest
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),%s,%s,%s
                    )
                    ON CONFLICT (observation_id) DO NOTHING
                    RETURNING observed_at
                    """,
                    (
                        candidate.observation_id,
                        candidate.schema_version,
                        candidate.canonicalization_version,
                        candidate.source_id,
                        candidate.source_item_key,
                        candidate.kind.value,
                        Jsonb(candidate.payload.to_canonical()),
                        candidate.source_published_at,
                        candidate.effective_at,
                        candidate.retrieved_at,
                        str(candidate.content_digest),
                        str(candidate.fetch_digest),
                    ),
                )
                row = cur.fetchone()
                inserted = row is not None
                if row is None:
                    cur.execute(
                        "SELECT observed_at FROM observations WHERE observation_id = %s",
                        (candidate.observation_id,),
                    )
                    row = cur.fetchone()
                assert row is not None
                observed_at = cast(datetime, row[0])
                status = OccurrenceStatus.INSERTED if inserted else OccurrenceStatus.DUPLICATE
                cur.execute(
                    """
                    INSERT INTO collection_run_observations (
                        run_id, observation_id, occurrence_status
                    ) VALUES (%s,%s,%s)
                    ON CONFLICT (run_id, observation_id) DO NOTHING
                    """,
                    (run_id, candidate.observation_id, status.value),
                )
        return Observation(candidate=candidate, observed_at=observed_at), inserted

    def list_observation_ids_as_of(self, as_of: datetime) -> list[str]:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT observation_id FROM observations WHERE observed_at <= %s ORDER BY observation_id",
                (as_of,),
            )
            return [cast(str, row[0]) for row in cur.fetchall()]

    def add_relation(self, relation: ObservationRelation) -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO observation_relations (
                    relation_id, relation_type, from_observation_id,
                    target_observation_id, target_external_ref, authority,
                    algorithm_version, confidence, evidence_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (relation_id) DO NOTHING
                """,
                (
                    relation.relation_id,
                    relation.relation_type.value,
                    relation.from_observation_id,
                    relation.target_observation_id,
                    relation.target_external_ref,
                    relation.authority.value,
                    relation.algorithm_version,
                    relation.confidence,
                    Jsonb(relation.evidence),
                ),
            )
        self._connection.commit()

    def add_source_health(
        self, health: SourceHealthObservation, run_id: UUID | None = None
    ) -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_health_observations (
                    health_observation_id, source_id, as_of,
                    transport_health, freshness_health, completeness_health, schema_health,
                    details_json, collection_run_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (health_observation_id) DO NOTHING
                """,
                (
                    health.health_observation_id,
                    health.source_id,
                    health.as_of,
                    health.transport.value,
                    health.freshness.value,
                    health.completeness.value,
                    health.schema.value,
                    Jsonb(health.details),
                    run_id,
                ),
            )
        self._connection.commit()
