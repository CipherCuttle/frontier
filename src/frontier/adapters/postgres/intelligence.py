from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import sha256_digest
from frontier.domain.grouping import GroupingRelationInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

from .grouping import PostgresGroupingRepository


class PostgresBaselineIntelligenceRepository:
    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection
        self._grouping = PostgresGroupingRepository(connection)

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]:
        grouping_inputs = self._grouping.list_grouping_inputs_as_of(as_of)
        if not grouping_inputs:
            return []
        observation_ids = [item.observation_id for item in grouping_inputs]
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT cro.observation_id, cr.reason, cr.recovered_after_gap
                FROM collection_run_observations cro
                JOIN collection_runs cr ON cr.run_id = cro.run_id
                WHERE cro.occurrence_status = 'INSERTED'
                  AND cro.observation_id = ANY(%s)
                ORDER BY cro.observation_id, cr.started_at, cr.run_id
                """,
                (observation_ids,),
            )
            rows = cur.fetchall()

        causality: dict[str, tuple[str, bool]] = {}
        for row in rows:
            observation_id = cast(str, row[0])
            if observation_id in causality:
                raise RuntimeError("multiple INSERTED collection occurrences for observation")
            causality[observation_id] = (cast(str, row[1]), cast(bool, row[2]))

        result: list[BaselineObservationInput] = []
        for item in grouping_inputs:
            first = causality.get(item.observation_id)
            if first is None:
                raise RuntimeError("baseline observation missing INSERTED collection causality")
            result.append(
                BaselineObservationInput(
                    grouping=item,
                    first_reason=first[0],
                    recovered_after_gap=first[1],
                )
            )
        return result

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        return self._grouping.list_grouping_relations_as_of(as_of)

    def list_enabled_source_ids(self) -> list[str]:
        with self._connection.cursor() as cur:
            cur.execute("SELECT source_id FROM sources WHERE enabled ORDER BY source_id")
            return [cast(str, row[0]) for row in cur.fetchall()]

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT h.source_id, h.as_of, h.transport_health, h.freshness_health,
                       h.completeness_health, h.schema_health, h.health_observation_id
                FROM source_health_observations h
                JOIN sources s ON s.source_id = h.source_id
                WHERE s.enabled AND h.as_of <= %s
                ORDER BY h.source_id, h.as_of DESC, h.health_observation_id DESC
                """,
                (as_of,),
            )
            rows = cur.fetchall()

        latest: dict[str, BaselineHealthInput] = {}
        latest_as_of: dict[str, datetime] = {}
        for row in rows:
            source_id = cast(str, row[0])
            health_as_of = cast(datetime, row[1])
            if source_id in latest:
                if latest_as_of[source_id] == health_as_of:
                    raise RuntimeError("ambiguous latest source health at identical as_of")
                continue
            latest_as_of[source_id] = health_as_of
            latest[source_id] = BaselineHealthInput(
                source_id=source_id,
                as_of=health_as_of,
                transport=HealthValue(cast(str, row[2])),
                freshness=HealthValue(cast(str, row[3])),
                completeness=HealthValue(cast(str, row[4])),
                schema=HealthValue(cast(str, row[5])),
            )
        return [latest[source_id] for source_id in sorted(latest)]

    def publish_complete_snapshot(
        self, snapshot: BaselineSnapshot, receipt: ProjectionReceipt
    ) -> None:
        if receipt.status is not ProjectionStatus.COMPLETE:
            raise ValueError("only COMPLETE baseline snapshots may be published")
        if receipt.projection_name != BASELINE_PROJECTION_NAME:
            raise ValueError("baseline receipt projection name mismatch")
        if receipt.projection_version != BASELINE_PROJECTION_VERSION:
            raise ValueError("baseline receipt projection version mismatch")
        if receipt.schema_version != BASELINE_SCHEMA_VERSION:
            raise ValueError("baseline receipt schema version mismatch")
        if receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
            raise ValueError("baseline receipt algorithm version mismatch")
        if receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
            raise ValueError("baseline receipt ranking policy version mismatch")
        output_digest = sha256_digest(canonical_json_bytes(snapshot.to_canonical()))
        if output_digest != receipt.output_digest:
            raise ValueError("baseline receipt output digest mismatch")

        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projection_receipts (
                    receipt_id, receipt_schema_version, projection_name,
                    projection_version, schema_version, algorithm_version,
                    ranking_policy_version, configuration_digest,
                    source_registry_version, as_of, generated_at,
                    input_digest, output_digest, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (receipt_id) DO NOTHING
                """,
                (
                    receipt.receipt_id,
                    receipt.receipt_schema_version,
                    receipt.projection_name,
                    receipt.projection_version,
                    receipt.schema_version,
                    receipt.algorithm_version,
                    receipt.ranking_policy_version,
                    str(receipt.configuration_digest),
                    str(receipt.source_registry_version),
                    receipt.as_of,
                    receipt.generated_at,
                    str(receipt.input_digest),
                    str(receipt.output_digest),
                    receipt.status.value,
                ),
            )
            cur.execute(
                """
                INSERT INTO baseline_intelligence_snapshots (
                    snapshot_id, projection_version, schema_version,
                    algorithm_version, ranking_policy_version, as_of,
                    output_digest, receipt_id, snapshot_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (snapshot_id) DO NOTHING
                RETURNING snapshot_id
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.projection_version,
                    snapshot.schema_version,
                    snapshot.algorithm_version,
                    snapshot.ranking_policy_version,
                    snapshot.as_of,
                    str(receipt.output_digest),
                    receipt.receipt_id,
                    Jsonb(snapshot.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT receipt_id, output_digest FROM baseline_intelligence_snapshots "
                    "WHERE snapshot_id = %s",
                    (snapshot.snapshot_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("snapshot conflict without existing row")
                if cast(str, existing[0]) != receipt.receipt_id or cast(str, existing[1]) != str(
                    receipt.output_digest
                ):
                    raise RuntimeError("snapshot identity conflict with different receipt")

    def latest_complete_snapshot_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id
                FROM baseline_intelligence_snapshots
                ORDER BY as_of DESC, snapshot_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])
