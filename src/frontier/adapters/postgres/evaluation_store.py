"""PostgreSQL read-plane store for persisted evaluation loading (WP4, G2).

Implements :class:`frontier.application.evaluation_loaders.EvaluationArtifactStore`
as a narrow READ-ONLY gateway over the append-only experiment artifact tables.
The loader performs every identity check; this adapter only shapes rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from frontier.application.evaluation_loaders import (
    PersistedArtifactRow,
    PersistedBaselineSnapshotRow,
    PersistedFeatureVectorRow,
    PersistedFreezePublicationRow,
    PersistedFreezeReceiptRow,
    PersistedProjectionReceiptRow,
    PersistedRunRow,
)


class PostgresEvaluationArtifactStore:
    """Read-only artifact-row access for the persisted evaluation loader."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def fetch_run_row(self, run_id: str) -> PersistedRunRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, run_digest, run_class, status, run_json
                FROM shadow_experiment_runs
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedRunRow(
            run_id=cast(str, row[0]),
            run_digest=cast(str, row[1]),
            run_class=cast(str, row[2]),
            status=cast(str, row[3]),
            run_json=cast(dict[str, object], row[4]),
        )

    def fetch_candidate_artifact_row(self, artifact_id: str) -> PersistedArtifactRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT artifact_id, output_digest, status, receipt_id, artifact_json
                FROM pef_ranking_artifacts
                WHERE artifact_id = %s
                """,
                (artifact_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedArtifactRow(
            artifact_id=cast(str, row[0]),
            output_digest=cast(str, row[1]),
            status=cast(str, row[2]),
            receipt_id=cast(str, row[3]),
            artifact_json=cast(dict[str, object], row[4]),
        )

    def fetch_baseline_snapshot_row(self, snapshot_id: str) -> PersistedBaselineSnapshotRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id, output_digest, receipt_id, snapshot_json
                FROM baseline_intelligence_snapshots
                WHERE snapshot_id = %s
                """,
                (snapshot_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedBaselineSnapshotRow(
            snapshot_id=cast(str, row[0]),
            output_digest=cast(str, row[1]),
            receipt_id=cast(str, row[2]),
            snapshot_json=cast(dict[str, object], row[3]),
        )

    def fetch_projection_receipt_row(self, receipt_id: str) -> PersistedProjectionReceiptRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT receipt_id, projection_name, projection_version, schema_version,
                       algorithm_version, ranking_policy_version, configuration_digest,
                       source_registry_version, output_digest, status
                FROM projection_receipts
                WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedProjectionReceiptRow(
            receipt_id=cast(str, row[0]),
            projection_name=cast(str, row[1]),
            projection_version=cast(str, row[2]),
            schema_version=cast(str, row[3]),
            algorithm_version=None if row[4] is None else cast(str, row[4]),
            ranking_policy_version=None if row[5] is None else cast(str, row[5]),
            configuration_digest=cast(str, row[6]),
            source_registry_version=cast(str, row[7]),
            output_digest=cast(str, row[8]),
            status=cast(str, row[9]),
        )

    def fetch_freeze_receipt_row(self, receipt_id: str) -> PersistedFreezeReceiptRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT receipt_id, receipt_digest, status, durable_freeze_at, receipt_json
                FROM candidate_freeze_receipts
                WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedFreezeReceiptRow(
            receipt_id=cast(str, row[0]),
            receipt_digest=cast(str, row[1]),
            status=cast(str, row[2]),
            durable_freeze_at=None if row[3] is None else cast(datetime, row[3]),
            receipt_json=cast(dict[str, object], row[4]),
        )

    def fetch_freeze_publication_row(self, receipt_id: str) -> PersistedFreezePublicationRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT receipt_id, schema_version, freeze_receipt_digest,
                       implementation_commit, implementation_tree_digest,
                       publication_commit, publication_committer_at, publication_digest
                FROM candidate_freeze_publications
                WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedFreezePublicationRow(
            receipt_id=cast(str, row[0]),
            schema_version=cast(str, row[1]),
            freeze_receipt_digest=cast(str, row[2]),
            implementation_commit=cast(str, row[3]),
            implementation_tree_digest=cast(str, row[4]),
            publication_commit=cast(str, row[5]),
            publication_committer_at=cast(datetime, row[6]),
            publication_digest=cast(str, row[7]),
        )

    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT feature_vector_id, batch_id, batch_digest, episode_id,
                       control_snapshot_id, episode_universe_digest, as_of,
                       vector_digest, vector_json
                FROM feature_vectors
                WHERE batch_id = %s
                ORDER BY episode_id, feature_vector_id
                """,
                (batch_id,),
            )
            rows = cur.fetchall()
        return tuple(
            PersistedFeatureVectorRow(
                vector_id=cast(str, row[0]),
                batch_id=cast(str, row[1]),
                batch_digest=cast(str, row[2]),
                episode_id=cast(str, row[3]),
                control_snapshot_id=cast(str, row[4]),
                episode_universe_digest=cast(str, row[5]),
                as_of=cast(datetime, row[6]),
                vector_digest=cast(str, row[7]),
                vector_json=cast(dict[str, object], row[8]),
            )
            for row in rows
        )


__all__ = ["PostgresEvaluationArtifactStore"]
