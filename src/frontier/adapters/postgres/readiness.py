from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import psycopg

EXPECTED_DATABASE_REVISION = "0010_experiment_outcome_state"
REQUIRED_RELATIONS = (
    "sources",
    "collection_runs",
    "observations",
    "source_health_observations",
    "source_fetch_state",
    "projection_receipts",
    "baseline_intelligence_snapshots",
    "pef_ranking_artifacts",
    "shadow_experiment_runs",
    "candidate_freeze_receipts",
    "evaluation_receipts",
    "feature_vectors",
    "experimental_analysis_artifacts",
    "opportunity_anchors",
    "outcome_resolutions",
    "opportunity_transitions",
    "experiment_run_attempts",
    "worker_heartbeats",
)


class DatabaseReadinessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    database_name: str
    migration_revision: str
    postgres_version: str
    required_relations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "database_name": self.database_name,
            "migration_revision": self.migration_revision,
            "postgres_version": self.postgres_version,
            "required_relations": list(self.required_relations),
        }


def verify_database_readiness(
    connection: psycopg.Connection[tuple[object, ...]],
) -> DatabaseReadiness:
    try:
        with connection.transaction():
            metadata = connection.execute(
                "SELECT current_database(), current_setting('server_version')"
            ).fetchone()
            if metadata is None:
                raise DatabaseReadinessError("database metadata query returned no row")

            revisions = connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).fetchall()
            found_revisions = tuple(cast(str, row[0]) for row in revisions)
            if found_revisions != (EXPECTED_DATABASE_REVISION,):
                raise DatabaseReadinessError(
                    "database migration revision mismatch: "
                    f"expected {EXPECTED_DATABASE_REVISION!r}, found {found_revisions!r}"
                )

            missing: list[str] = []
            for relation in REQUIRED_RELATIONS:
                row = connection.execute(
                    "SELECT to_regclass(%s)",
                    (f"public.{relation}",),
                ).fetchone()
                if row is None or row[0] is None:
                    missing.append(relation)
            if missing:
                raise DatabaseReadinessError(
                    "database is missing required relations: " + ", ".join(missing)
                )

            return DatabaseReadiness(
                database_name=cast(str, metadata[0]),
                migration_revision=EXPECTED_DATABASE_REVISION,
                postgres_version=cast(str, metadata[1]),
                required_relations=REQUIRED_RELATIONS,
            )
    except DatabaseReadinessError:
        raise
    except psycopg.Error as exc:
        raise DatabaseReadinessError("database readiness query failed") from exc
