from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.adapters.acquisition.config import SourceRegistry
from frontier.adapters.postgres.advanced_intelligence import PostgresShadowRunRepository
from frontier.adapters.postgres.grouping import PostgresGroupingRepository
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import BaselineHealthInput


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("canonical observation payload is not an object")
    return cast(dict[str, object], value)


class PostgresFrozenRegistryGroupingRepository(PostgresGroupingRepository):
    """PIT grouping reads constrained to the immutable confirmatory source registry."""

    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        registry: SourceRegistry,
    ) -> None:
        super().__init__(connection)
        self._source_ids = tuple(sorted(registry.sources))
        self._roles_by_source = {
            source_id: tuple(role.value for role in registry.require(source_id).contract.signal_roles)
            for source_id in self._source_ids
        }

    def list_grouping_inputs_as_of(self, as_of: datetime) -> list[GroupingInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT o.observation_id, o.source_id, o.source_item_key, o.kind,
                       o.observed_at, o.payload_json
                FROM observations o
                WHERE o.observed_at <= %s
                  AND o.source_id = ANY(%s)
                ORDER BY o.observation_id
                """,
                (as_of, list(self._source_ids)),
            )
            rows = cur.fetchall()

        result: list[GroupingInput] = []
        for row in rows:
            source_id = cast(str, row[1])
            payload = _payload(row[5])
            result.append(
                GroupingInput(
                    observation_id=cast(str, row[0]),
                    source_id=source_id,
                    source_item_key=cast(str, row[2]),
                    kind=cast(str, row[3]),
                    observed_at=cast(datetime, row[4]),
                    canonical_url=_optional_str(payload.get("canonical_url")),
                    title=_optional_str(payload.get("title")),
                    text=_optional_str(payload.get("excerpt")),
                    artifact_type=_optional_str(payload.get("artifact_type")),
                    artifact_name=_optional_str(payload.get("name")),
                    artifact_version=_optional_str(payload.get("version")),
                    signal_roles=self._roles_by_source[source_id],
                )
            )
        return result

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT r.relation_type, r.from_observation_id, r.target_observation_id,
                       r.authority, r.created_at
                FROM observation_relations r
                JOIN observations source_observation
                  ON source_observation.observation_id = r.from_observation_id
                JOIN observations target_observation
                  ON target_observation.observation_id = r.target_observation_id
                WHERE r.target_observation_id IS NOT NULL
                  AND r.relation_type IN ('CORRECTS', 'RETRACTS')
                  AND r.created_at <= %s
                  AND source_observation.source_id = ANY(%s)
                  AND target_observation.source_id = ANY(%s)
                ORDER BY r.relation_type, r.from_observation_id, r.target_observation_id
                """,
                (as_of, list(self._source_ids), list(self._source_ids)),
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


class PostgresProspectiveBaselineIntelligenceRepository(PostgresBaselineIntelligenceRepository):
    """Permanent baseline replayed only through the frozen confirmatory registry."""

    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        registry: SourceRegistry,
    ) -> None:
        super().__init__(connection)
        self._source_ids = tuple(sorted(registry.sources))
        self._grouping = PostgresFrozenRegistryGroupingRepository(connection, registry)

    def list_enabled_source_ids(self) -> list[str]:
        return list(self._source_ids)

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT h.source_id, h.as_of, h.transport_health, h.freshness_health,
                       h.completeness_health, h.schema_health, h.health_observation_id
                FROM source_health_observations h
                WHERE h.source_id = ANY(%s)
                  AND h.as_of <= %s
                ORDER BY h.source_id, h.as_of DESC, h.health_observation_id DESC
                """,
                (list(self._source_ids), as_of),
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


class PostgresProspectiveShadowRunRepository(PostgresShadowRunRepository):
    """Shadow-run persistence with fixed-window receipt-bound boundary queries."""

    def record_window_binding(
        self,
        *,
        candidate_freeze_receipt_id: str,
        durable_freeze_commit: str,
        durable_freeze_at: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        payload = {
            "candidate_freeze_receipt_id": candidate_freeze_receipt_id,
            "durable_freeze_at": durable_freeze_at.isoformat(),
            "durable_freeze_commit": durable_freeze_commit,
            "window_end": window_end.isoformat(),
            "window_start": window_start.isoformat(),
        }
        expected = (
            durable_freeze_commit,
            durable_freeze_at,
            window_start,
            window_end,
        )
        with self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO confirmatory_window_bindings (
                    candidate_freeze_receipt_id, durable_freeze_commit,
                    durable_freeze_at, window_start, window_end, binding_json
                ) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (candidate_freeze_receipt_id) DO NOTHING
                RETURNING candidate_freeze_receipt_id
                """,
                (
                    candidate_freeze_receipt_id,
                    durable_freeze_commit,
                    durable_freeze_at,
                    window_start,
                    window_end,
                    Jsonb(payload),
                ),
            )
            inserted = cur.fetchone()
            if inserted is not None:
                return
            cur.execute(
                """
                SELECT durable_freeze_commit, durable_freeze_at, window_start, window_end
                FROM confirmatory_window_bindings
                WHERE candidate_freeze_receipt_id = %s
                """,
                (candidate_freeze_receipt_id,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("window binding conflict without existing row")
            actual = (
                cast(str, existing[0]),
                cast(datetime, existing[1]),
                cast(datetime, existing[2]),
                cast(datetime, existing[3]),
            )
            if actual != expected:
                raise RuntimeError("candidate freeze receipt has a conflicting window binding")

    def has_bound_run_at(self, *, as_of: datetime, candidate_freeze_receipt_id: str) -> bool:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM shadow_experiment_runs
                WHERE as_of = %s
                  AND run_json ->> 'candidate_freeze_receipt_id' = %s
                LIMIT 1
                """,
                (as_of, candidate_freeze_receipt_id),
            )
            return cur.fetchone() is not None

    def bound_run_boundaries(
        self,
        *,
        candidate_freeze_receipt_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, ...]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT as_of
                FROM shadow_experiment_runs
                WHERE as_of >= %s
                  AND as_of < %s
                  AND run_json ->> 'candidate_freeze_receipt_id' = %s
                ORDER BY as_of, run_id
                """,
                (start, end, candidate_freeze_receipt_id),
            )
            return tuple(cast(datetime, row[0]) for row in cur.fetchall())
