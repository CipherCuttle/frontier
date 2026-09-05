"""SELECT-only PostgreSQL read adapter for EXPERIMENTAL_SHADOW summaries (G).

Mirrors the public-read boundary discipline: the session is verified
read-only (``default_transaction_read_only=on`` with autocommit), only SELECT
statements are issued, and missing rows are ``None`` — never fabricated data
(R4). Summaries expose identity/digest/status fields only (R7, R8).
"""

from __future__ import annotations

from datetime import datetime
from typing import LiteralString, cast

import psycopg

from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    AnalysisArtifactSummary,
    EvaluationReceiptSummary,
    ExperimentalReadFailure,
    FeatureBatchSummary,
    PefArtifactSummary,
    ShadowRunSummary,
)


class PostgresExperimentalReadRepository:
    """Read-only queries over append-only EXPERIMENTAL artifacts/tables.

    Fails closed unless the session is verified read-only (R5-adjacent
    discipline inherited from the public read plane).
    """

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        if not connection.autocommit:
            raise ValueError("experimental read connection must use autocommit")
        self._connection = connection
        with self._connection.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute("SHOW default_transaction_read_only")
            row = cur.fetchone()
        if row is None or cast(str, row[0]) != "on":
            raise RuntimeError("experimental read database session is not read-only")

    @classmethod
    def connect(cls, dsn: str) -> PostgresExperimentalReadRepository:
        return cls(psycopg.connect(dsn, autocommit=True))

    def close(self) -> None:
        self._connection.close()

    def latest_shadow_run(self, *, as_of: datetime | None = None) -> ShadowRunSummary | None:
        row = self._fetch_one(
            """
            SELECT run_id, run_digest, experiment_id, candidate_id,
                   schema_version, algorithm_version, configuration_digest,
                   authority_state, status, as_of, control_snapshot_id,
                   control_receipt_id, candidate_artifact_id,
                   candidate_output_digest, episode_universe_digest,
                   failure_reason, run_json->>'generated_at',
                   run_json->>'candidate_freeze_receipt_id'
            FROM shadow_experiment_runs
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, run_id DESC
            LIMIT 1
            """,
            (as_of,),
        )
        if row is None:
            return None
        return ShadowRunSummary(
            run_id=cast(str, row[0]),
            run_digest=cast(str, row[1]),
            experiment_id=cast(str, row[2]),
            candidate_id=cast(str, row[3]),
            schema_version=cast(str, row[4]),
            algorithm_version=cast(str, row[5]),
            configuration_digest=cast(str, row[6]),
            authority_state=cast(str, row[7]),
            status=cast(str, row[8]),
            as_of=_canonical(row[9]),
            generated_at=cast(str, row[16]),
            control_snapshot_id=cast(str, row[10]),
            control_receipt_id=cast(str, row[11]),
            candidate_artifact_id=cast(str, row[12]),
            candidate_output_digest=cast(str, row[13]),
            episode_universe_digest=cast(str, row[14]),
            candidate_freeze_receipt_id=cast(str | None, row[17]),
            failure_reason=cast(str | None, row[15]),
        )

    def latest_pef_artifact(self, *, as_of: datetime | None = None) -> PefArtifactSummary | None:
        row = self._fetch_one(
            """
            SELECT artifact_id, output_digest, receipt_id, status, as_of,
                   control_snapshot_id, control_receipt_id, schema_version,
                   algorithm_version, ranking_policy_version,
                   configuration_digest, authority_state, failure_reason,
                   artifact_json->>'generated_at',
                   artifact_json->>'experiment_id',
                   artifact_json->>'candidate_id',
                   CASE WHEN status = 'RAN'
                        THEN jsonb_array_length(artifact_json->'episodes') END
            FROM pef_ranking_artifacts
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, artifact_id DESC
            LIMIT 1
            """,
            (as_of,),
        )
        if row is None:
            return None
        return PefArtifactSummary(
            artifact_id=cast(str, row[0]),
            output_digest=cast(str, row[1]),
            receipt_id=cast(str, row[2]),
            status=cast(str, row[3]),
            as_of=_canonical(row[4]),
            generated_at=cast(str, row[13]),
            experiment_id=cast(str, row[14]),
            candidate_id=cast(str, row[15]),
            schema_version=cast(str, row[7]),
            algorithm_version=cast(str, row[8]),
            ranking_policy_version=cast(str, row[9]),
            configuration_digest=cast(str, row[10]),
            authority_state=cast(str, row[11]),
            control_snapshot_id=cast(str, row[5]),
            control_receipt_id=cast(str, row[6]),
            episode_count=None if row[16] is None else int(cast(int, row[16])),
            failure_reason=cast(str | None, row[12]),
        )

    def latest_evaluation_receipt(
        self, *, as_of: datetime | None = None
    ) -> EvaluationReceiptSummary | None:
        row = self._fetch_one(
            """
            SELECT evaluation_id, receipt_digest, status, as_of, generated_at,
                   experiment_id, candidate_id, schema_version,
                   evaluation_algorithm_version, candidate_configuration_digest,
                   evaluation_configuration_digest, authority_state,
                   candidate_freeze_receipt_id, freeze_receipt_digest,
                   freeze_status, preregistration_digest, shadow_run_ids,
                   receipt_json->>'status_reason', receipt_json->>'verdict'
            FROM evaluation_receipts
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, evaluation_id DESC
            LIMIT 1
            """,
            (as_of,),
        )
        if row is None:
            return None
        run_ids_raw = row[16]
        if not isinstance(run_ids_raw, list):
            raise ExperimentalReadFailure("evaluation shadow run ids are not a list")
        run_ids: list[str] = []
        for item in cast(list[object], run_ids_raw):
            if not isinstance(item, str):
                raise ExperimentalReadFailure("evaluation shadow run id is not a string")
            run_ids.append(item)
        return EvaluationReceiptSummary(
            evaluation_id=cast(str, row[0]),
            receipt_digest=cast(str, row[1]),
            status=cast(str, row[2]),
            as_of=_canonical(row[3]),
            generated_at=_canonical(row[4]),
            experiment_id=cast(str, row[5]),
            candidate_id=cast(str, row[6]),
            schema_version=cast(str, row[7]),
            evaluation_algorithm_version=cast(str, row[8]),
            candidate_configuration_digest=cast(str, row[9]),
            evaluation_configuration_digest=cast(str, row[10]),
            authority_state=cast(str, row[11]),
            candidate_freeze_receipt_id=cast(str, row[12]),
            freeze_receipt_digest=cast(str, row[13]),
            freeze_status=cast(str, row[14]),
            preregistration_digest=cast(str, row[15]),
            shadow_run_ids=tuple(run_ids),
            status_reason=cast(str | None, row[17]),
            verdict=cast(str | None, row[18]),
        )

    def latest_feature_batch(self, *, as_of: datetime | None = None) -> FeatureBatchSummary | None:
        row = self._fetch_one(
            """
            SELECT batch_id, batch_digest, status, as_of, generated_at,
                   control_snapshot_id, control_receipt_id,
                   episode_universe_digest, configuration_digest,
                   schema_version, algorithm_version, authority_state
            FROM feature_vectors
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, feature_vector_id DESC
            LIMIT 1
            """,
            (as_of,),
        )
        if row is None:
            return None
        batch_id = cast(str, row[0])
        vector_count = self._fetch_scalar(
            "SELECT count(*) FROM feature_vectors WHERE batch_id = %s", (batch_id,)
        )
        return FeatureBatchSummary(
            batch_id=batch_id,
            batch_digest=cast(str, row[1]),
            status=cast(str, row[2]),
            as_of=_canonical(row[3]),
            generated_at=_canonical(row[4]),
            control_snapshot_id=cast(str, row[5]),
            control_receipt_id=cast(str, row[6]),
            episode_universe_digest=cast(str, row[7]),
            configuration_digest=cast(str, row[8]),
            schema_version=cast(str, row[9]),
            algorithm_version=cast(str, row[10]),
            authority_state=cast(str, row[11]),
            vector_count=vector_count,
        )

    def latest_analysis_artifacts(
        self, *, as_of: datetime | None = None
    ) -> dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]:
        rows = self._fetch_all(
            """
            SELECT DISTINCT ON (artifact_kind)
                   analysis_id, artifact_kind, status, authority_state, as_of,
                   generated_at, control_snapshot_id, control_receipt_id,
                   source_registry_version, episode_universe_digest,
                   schema_version, algorithm_version, configuration_digest,
                   input_digest, output_digest
            FROM experimental_analysis_artifacts
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY artifact_kind, as_of DESC, analysis_id DESC
            """,
            (as_of,),
        )
        result: dict[ExperimentalAnalysisKind, AnalysisArtifactSummary] = {}
        for row in rows:
            summary = _analysis_summary(row)
            kind = ExperimentalAnalysisKind(summary.kind)
            result[kind] = summary
        return result

    def _fetch_one(
        self, query: LiteralString, params: tuple[object, ...]
    ) -> tuple[object, ...] | None:
        with self._connection.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def _fetch_all(
        self, query: LiteralString, params: tuple[object, ...]
    ) -> list[tuple[object, ...]]:
        with self._connection.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def _fetch_scalar(self, query: LiteralString, params: tuple[object, ...]) -> int | None:
        row = self._fetch_one(query, params)
        if row is None or row[0] is None:
            return None
        return int(cast(int, row[0]))


def _analysis_summary(row: tuple[object, ...]) -> AnalysisArtifactSummary:
    return AnalysisArtifactSummary(
        analysis_id=cast(str, row[0]),
        kind=cast(str, row[1]),
        status=cast(str, row[2]),
        authority_state=cast(str, row[3]),
        as_of=_canonical(row[4]),
        generated_at=_canonical(row[5]),
        control_snapshot_id=cast(str | None, row[6]),
        control_receipt_id=cast(str | None, row[7]),
        source_registry_version=cast(str | None, row[8]),
        episode_universe_digest=cast(str | None, row[9]),
        schema_version=cast(str, row[10]),
        algorithm_version=cast(str, row[11]),
        configuration_digest=cast(str, row[12]),
        input_digest=cast(str | None, row[13]),
        output_digest=cast(str, row[14]),
    )


def _canonical(value: object) -> str:
    from datetime import datetime

    from frontier.domain.canonical_json import canonical_timestamp

    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    raise ExperimentalReadFailure("unexpected non-canonical timestamp column")
