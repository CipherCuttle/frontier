from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.receipt import ProjectionReceipt


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("canonical observation payload is not an object")
    return cast(dict[str, object], value)


def _roles(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError("source signal_roles are malformed")
    raw_roles = cast(list[object], value)
    roles: list[str] = []
    for role in raw_roles:
        if not isinstance(role, str):
            raise RuntimeError("source signal_roles are malformed")
        roles.append(role)
    return tuple(roles)


class PostgresGroupingRepository:
    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def list_grouping_inputs_as_of(self, as_of: datetime) -> list[GroupingInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT o.observation_id, o.source_id, o.source_item_key, o.kind,
                       o.observed_at, o.payload_json, s.signal_roles
                FROM observations o
                JOIN sources s ON s.source_id = o.source_id
                WHERE o.observed_at <= %s
                ORDER BY o.observation_id
                """,
                (as_of,),
            )
            rows = cur.fetchall()

        result: list[GroupingInput] = []
        for row in rows:
            payload = _payload(row[5])
            kind = cast(str, row[3])
            result.append(
                GroupingInput(
                    observation_id=cast(str, row[0]),
                    source_id=cast(str, row[1]),
                    source_item_key=cast(str, row[2]),
                    kind=kind,
                    observed_at=cast(datetime, row[4]),
                    canonical_url=_optional_str(payload.get("canonical_url")),
                    title=_optional_str(payload.get("title")),
                    text=_optional_str(payload.get("excerpt")),
                    artifact_type=_optional_str(payload.get("artifact_type")),
                    artifact_name=_optional_str(payload.get("name")),
                    artifact_version=_optional_str(payload.get("version")),
                    signal_roles=_roles(row[6]),
                )
            )
        return result

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT relation_type, from_observation_id, target_observation_id,
                       authority, created_at
                FROM observation_relations
                WHERE target_observation_id IS NOT NULL
                  AND relation_type IN ('CORRECTS', 'RETRACTS')
                  AND created_at <= %s
                ORDER BY relation_type, from_observation_id, target_observation_id
                """,
                (as_of,),
            )
            rows = cur.fetchall()
        return [
            GroupingRelationInput(
                relation_type=cast(str, row[0]),
                from_observation_id=cast(str, row[1]),
                target_observation_id=cast(str, row[2]),
                authority=cast(str, row[3]),
                created_at=cast(datetime, row[4]),
            )
            for row in rows
        ]

    def add_projection_receipt(self, receipt: ProjectionReceipt) -> None:
        with self._connection.cursor() as cur:
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
        self._connection.commit()
