from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast

import psycopg
from psycopg import sql as psycopg_sql

from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import sha256_digest
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
)
from frontier.domain.public_read import (
    CollectionOccurrenceRead,
    NoCompleteSnapshotError,
    ObservationEvidenceRead,
    ObservationRelationRead,
    ResolvedPublicSnapshot,
    SnapshotBinding,
    SnapshotIntegrityError,
    SnapshotNotFoundError,
    SourceHealthRead,
)


class PostgresPublicReadRepository:
    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        *,
        owns_connection: bool = False,
    ) -> None:
        if not connection.autocommit:
            raise ValueError("public read connection must use autocommit")
        self._connection = connection
        self._owns_connection = owns_connection
        with self._connection.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute("SHOW default_transaction_read_only")
            row = cur.fetchone()
        if row is None or cast(str, row[0]) != "on":
            raise RuntimeError("public read database session is not read-only")

    @classmethod
    def connect(cls, dsn: str) -> PostgresPublicReadRepository:
        connection = psycopg.connect(dsn, autocommit=True)
        return cls(connection, owns_connection=True)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def verify_read_only_session(self) -> bool:
        with self._connection.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            row = cur.fetchone()
        return row is not None and cast(str, row[0]) == "on"

    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot:
        if snapshot_id is None:
            row = self._select_latest_complete_snapshot()
            if row is None:
                raise NoCompleteSnapshotError("no COMPLETE baseline snapshot is available")
        else:
            row = self._select_snapshot(snapshot_id)
            if row is None:
                raise SnapshotNotFoundError(snapshot_id)
            status = cast(str, row[22])
            if status != "COMPLETE" or cast(str, row[11]) != BASELINE_PROJECTION_NAME:
                raise SnapshotNotFoundError(snapshot_id)
        return self._validated_snapshot(row)

    def _snapshot_select_sql(self) -> psycopg_sql.SQL:
        return psycopg_sql.SQL(
            """
            SELECT
                b.snapshot_id, b.projection_version, b.schema_version,
                b.algorithm_version, b.ranking_policy_version, b.as_of,
                b.output_digest, b.receipt_id, b.snapshot_json,
                r.receipt_id, r.receipt_schema_version, r.projection_name,
                r.projection_version, r.schema_version, r.algorithm_version,
                r.ranking_policy_version, r.configuration_digest,
                r.source_registry_version, r.as_of, r.generated_at,
                r.input_digest, r.output_digest, r.status
            FROM baseline_intelligence_snapshots b
            JOIN projection_receipts r ON r.receipt_id = b.receipt_id
            """
        )

    def _select_latest_complete_snapshot(self) -> tuple[object, ...] | None:
        query = self._snapshot_select_sql() + psycopg_sql.SQL(
            """
            WHERE r.status = 'COMPLETE'
              AND r.projection_name = %s
              AND r.projection_version = %s
            ORDER BY b.as_of DESC, b.snapshot_id DESC
            LIMIT 1
            """
        )
        with self._connection.cursor() as cur:
            cur.execute(query, (BASELINE_PROJECTION_NAME, BASELINE_PROJECTION_VERSION))
            return cur.fetchone()

    def _select_snapshot(self, snapshot_id: str) -> tuple[object, ...] | None:
        query = self._snapshot_select_sql() + psycopg_sql.SQL(" WHERE b.snapshot_id = %s")
        with self._connection.cursor() as cur:
            cur.execute(query, (snapshot_id,))
            return cur.fetchone()

    def _validated_snapshot(self, row: tuple[object, ...]) -> ResolvedPublicSnapshot:
        snapshot_id = cast(str, row[0])
        snapshot_projection_version = cast(str, row[1])
        snapshot_schema_version = cast(str, row[2])
        snapshot_algorithm_version = cast(str, row[3])
        snapshot_ranking_policy_version = cast(str, row[4])
        snapshot_as_of = cast(datetime, row[5])
        snapshot_output_digest = cast(str, row[6])
        snapshot_receipt_id = cast(str, row[7])
        payload = cast(dict[str, CanonicalValue], row[8])
        receipt_id = cast(str, row[9])
        receipt_schema_version = cast(str, row[10])
        projection_name = cast(str, row[11])
        receipt_projection_version = cast(str, row[12])
        receipt_schema = cast(str, row[13])
        receipt_algorithm = cast(str, row[14])
        receipt_ranking = cast(str, row[15])
        configuration_digest = cast(str, row[16])
        source_registry_version = cast(str, row[17])
        receipt_as_of = cast(datetime, row[18])
        generated_at = cast(datetime, row[19])
        input_digest = cast(str, row[20])
        receipt_output_digest = cast(str, row[21])
        status = cast(str, row[22])

        if status != "COMPLETE":
            raise SnapshotIntegrityError("non-COMPLETE receipt reached snapshot validation")
        if snapshot_receipt_id != receipt_id:
            raise SnapshotIntegrityError("snapshot receipt binding mismatch")
        if snapshot_output_digest != receipt_output_digest:
            raise SnapshotIntegrityError("snapshot output digest binding mismatch")
        expected_versions = (
            BASELINE_PROJECTION_VERSION,
            BASELINE_SCHEMA_VERSION,
            BASELINE_ALGORITHM_VERSION,
            BASELINE_RANKING_POLICY_VERSION,
        )
        if (
            snapshot_projection_version,
            snapshot_schema_version,
            snapshot_algorithm_version,
            snapshot_ranking_policy_version,
        ) != expected_versions:
            raise SnapshotIntegrityError("snapshot version identity mismatch")
        if projection_name != BASELINE_PROJECTION_NAME:
            raise SnapshotIntegrityError("receipt projection name mismatch")
        if (
            receipt_projection_version,
            receipt_schema,
            receipt_algorithm,
            receipt_ranking,
        ) != expected_versions:
            raise SnapshotIntegrityError("receipt version identity mismatch")
        if snapshot_as_of != receipt_as_of:
            raise SnapshotIntegrityError("snapshot and receipt as_of mismatch")
        if str(sha256_digest(canonical_json_bytes(payload))) != receipt_output_digest:
            raise SnapshotIntegrityError("snapshot canonical payload digest mismatch")

        payload_as_of = payload.get("as_of")
        if payload_as_of != canonical_timestamp(snapshot_as_of):
            raise SnapshotIntegrityError("snapshot payload as_of mismatch")
        if payload.get("projection_version") != BASELINE_PROJECTION_VERSION:
            raise SnapshotIntegrityError("snapshot payload projection version mismatch")
        if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
            raise SnapshotIntegrityError("snapshot payload schema version mismatch")
        if payload.get("algorithm_version") != BASELINE_ALGORITHM_VERSION:
            raise SnapshotIntegrityError("snapshot payload algorithm version mismatch")
        if payload.get("ranking_policy_version") != BASELINE_RANKING_POLICY_VERSION:
            raise SnapshotIntegrityError("snapshot payload ranking policy version mismatch")

        episodes_raw = payload.get("episodes")
        if not isinstance(episodes_raw, list):
            raise SnapshotIntegrityError("snapshot payload episodes is not a list")
        episodes: list[dict[str, CanonicalValue]] = []
        for item in episodes_raw:
            if not isinstance(item, dict):
                raise SnapshotIntegrityError("snapshot payload contains non-object episode")
            episodes.append(cast(dict[str, CanonicalValue], item))

        transport = _require_string(payload, "transport_state")
        freshness = _require_string(payload, "freshness_state")
        coverage = _require_string(payload, "coverage_state")
        schema = _require_string(payload, "schema_state")
        binding = SnapshotBinding(
            snapshot_id=snapshot_id,
            receipt_id=receipt_id,
            receipt_schema_version=receipt_schema_version,
            projection_name=projection_name,
            projection_version=receipt_projection_version,
            schema_version=receipt_schema,
            algorithm_version=receipt_algorithm,
            ranking_policy_version=receipt_ranking,
            configuration_digest=configuration_digest,
            source_registry_version=source_registry_version,
            as_of=canonical_timestamp(receipt_as_of),
            input_digest=input_digest,
            output_digest=receipt_output_digest,
        )
        return ResolvedPublicSnapshot(
            binding=binding,
            generated_at=canonical_timestamp(generated_at),
            transport_state=transport,
            freshness_state=freshness,
            coverage_state=coverage,
            schema_state=schema,
            episodes=tuple(episodes),
        )

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]:
        if not observation_ids:
            return []
        unique_ids = tuple(dict.fromkeys(observation_ids))
        observations = self._observation_rows(unique_ids, as_of=as_of)
        occurrences = self._occurrence_rows(unique_ids, as_of=as_of)
        relations = self._relation_rows(unique_ids, as_of=as_of)
        occurrence_map: dict[str, list[CollectionOccurrenceRead]] = {key: [] for key in unique_ids}
        for observation_id, occurrence in occurrences:
            if observation_id in occurrence_map:
                occurrence_map[observation_id].append(occurrence)
        relation_map: dict[str, list[ObservationRelationRead]] = {key: [] for key in unique_ids}
        for relation in relations:
            touched = {relation.from_observation_id, relation.target_observation_id}
            for observation_id in unique_ids:
                if observation_id in touched:
                    relation_map[observation_id].append(relation)

        result: list[ObservationEvidenceRead] = []
        for row in observations:
            observation_id = cast(str, row[0])
            result.append(
                ObservationEvidenceRead(
                    observation_id=observation_id,
                    schema_version=cast(str, row[1]),
                    canonicalization_version=cast(str, row[2]),
                    source_id=cast(str, row[3]),
                    source_item_key=cast(str, row[4]),
                    kind=cast(str, row[5]),
                    payload=cast(dict[str, CanonicalValue], row[6]),
                    source_published_at=_optional_timestamp(row[7]),
                    effective_at=_optional_timestamp(row[8]),
                    observed_at=canonical_timestamp(cast(datetime, row[9])),
                    retrieved_at=canonical_timestamp(cast(datetime, row[10])),
                    content_digest=cast(str, row[11]),
                    fetch_digest=cast(str, row[12]),
                    collection_occurrences=tuple(occurrence_map[observation_id]),
                    relations=tuple(relation_map[observation_id]),
                )
            )
        return result

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None:
        values = self.list_observations((observation_id,), as_of=as_of)
        return values[0] if values else None

    def _observation_rows(
        self, observation_ids: Sequence[str], *, as_of: datetime
    ) -> list[tuple[object, ...]]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT observation_id, schema_version, canonicalization_version,
                       source_id, source_item_key, kind, payload_json,
                       source_published_at, effective_at, observed_at, retrieved_at,
                       content_digest, fetch_digest
                FROM observations
                WHERE observation_id = ANY(%s) AND observed_at <= %s
                ORDER BY observation_id
                """,
                (list(observation_ids), as_of),
            )
            return cur.fetchall()

    def _occurrence_rows(
        self, observation_ids: Sequence[str], *, as_of: datetime
    ) -> list[tuple[str, CollectionOccurrenceRead]]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT cro.observation_id, cr.run_id::text, cr.reason, cr.trigger_id,
                       cr.recovered_after_gap, cro.occurrence_status,
                       cr.started_at,
                       CASE WHEN cr.completed_at <= %s THEN cr.completed_at ELSE NULL END
                FROM collection_run_observations cro
                JOIN collection_runs cr ON cr.run_id = cro.run_id
                WHERE cro.observation_id = ANY(%s)
                  AND cro.recorded_at <= %s
                  AND cr.started_at <= %s
                ORDER BY cro.observation_id, cr.started_at, cr.run_id
                """,
                (as_of, list(observation_ids), as_of, as_of),
            )
            rows = cur.fetchall()
        result: list[tuple[str, CollectionOccurrenceRead]] = []
        for row in rows:
            result.append(
                (
                    cast(str, row[0]),
                    CollectionOccurrenceRead(
                        run_id=cast(str, row[1]),
                        reason=cast(str, row[2]),
                        trigger_id=cast(str | None, row[3]),
                        recovered_after_gap=cast(bool, row[4]),
                        occurrence_status=cast(str, row[5]),
                        started_at=canonical_timestamp(cast(datetime, row[6])),
                        completed_at=_optional_timestamp(row[7]),
                    ),
                )
            )
        return result

    def _relation_rows(
        self, observation_ids: Sequence[str], *, as_of: datetime
    ) -> list[ObservationRelationRead]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT relation_id, relation_type, from_observation_id,
                       target_observation_id, target_external_ref, authority,
                       algorithm_version, confidence, evidence_json
                FROM observation_relations
                WHERE created_at <= %s
                  AND (from_observation_id = ANY(%s) OR target_observation_id = ANY(%s))
                ORDER BY relation_id
                """,
                (as_of, list(observation_ids), list(observation_ids)),
            )
            rows = cur.fetchall()
        return [
            ObservationRelationRead(
                relation_id=cast(str, row[0]),
                relation_type=cast(str, row[1]),
                from_observation_id=cast(str, row[2]),
                target_observation_id=cast(str | None, row[3]),
                target_external_ref=cast(str | None, row[4]),
                authority=cast(str, row[5]),
                algorithm_version=cast(str | None, row[6]),
                confidence=cast(str | None, row[7]),
                evidence=cast(dict[str, CanonicalValue], row[8]),
            )
            for row in rows
        ]

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT source_id, as_of, transport_health, freshness_health,
                       completeness_health, schema_health, details_json,
                       health_observation_id
                FROM source_health_observations
                WHERE as_of <= %s
                ORDER BY source_id, as_of DESC, health_observation_id DESC
                """,
                (as_of,),
            )
            rows = cur.fetchall()

        latest: dict[str, SourceHealthRead] = {}
        latest_as_of: dict[str, datetime] = {}
        for row in rows:
            source_id = cast(str, row[0])
            health_as_of = cast(datetime, row[1])
            if source_id in latest:
                if latest_as_of[source_id] == health_as_of:
                    raise SnapshotIntegrityError(
                        "ambiguous latest source health at selected snapshot horizon"
                    )
                continue
            latest_as_of[source_id] = health_as_of
            latest[source_id] = SourceHealthRead(
                source_id=source_id,
                as_of=canonical_timestamp(health_as_of),
                transport=cast(str, row[2]),
                freshness=cast(str, row[3]),
                completeness=cast(str, row[4]),
                schema=cast(str, row[5]),
                details=cast(dict[str, CanonicalValue], row[6]),
            )
        return [latest[source_id] for source_id in sorted(latest)]


def _require_string(payload: dict[str, CanonicalValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise SnapshotIntegrityError(f"snapshot payload {key} is not a string")
    return value


def _optional_timestamp(value: object) -> str | None:
    return None if value is None else canonical_timestamp(cast(datetime, value))
