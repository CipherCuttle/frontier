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

from frontier.domain.experiment_status import (
    BoundFreezeStatus,
    CoverageHealthStatus,
    DomainEvaluationStatusRow,
    DomainOpportunityCounts,
    EvaluationStatisticsStatus,
    LatestRunStatus,
    WindowBoundaryStatus,
)
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    AnalysisArtifactSummary,
    EvaluationReceiptSummary,
    ExperimentalReadFailure,
    FeatureBatchSummary,
    PefArtifactSummary,
    ShadowRunSummary,
)
from frontier.domain.health import HealthValue


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
                   feature_schema_version AS schema_version,
                   algorithm_version, authority_state
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

    # ------------------------------------------------------------------
    # WP6 (G4): SELECT-only status inputs for the coherent experiment
    # status projection (fail-closed; missing rows are None, never data).
    # ------------------------------------------------------------------

    def latest_freeze_status(self) -> BoundFreezeStatus | None:
        """Latest bound candidate freeze receipt (None = unbound)."""
        row = self._fetch_one(
            """
            SELECT receipt_id, status, durable_freeze_at, implementation_commit,
                   implementation_tree_digest, source_registry_digest, frozen_at
            FROM candidate_freeze_receipts
            ORDER BY frozen_at DESC, receipt_id DESC
            LIMIT 1
            """,
            (),
        )
        if row is None:
            return None
        return BoundFreezeStatus(
            receipt_id=cast(str, row[0]),
            status=cast(str, row[1]),
            durable_freeze_at=_canonical(row[2]),
            implementation_commit=cast(str | None, row[3]),
            implementation_tree_digest=cast(str | None, row[4]),
            source_registry_digest=cast(str | None, row[5]),
            frozen_at=_canonical(row[6]),
        )

    def window_boundaries(self) -> WindowBoundaryStatus | None:
        """Earliest/latest stored run boundary plus latest attempt state."""
        row = self._fetch_one(
            """
            SELECT
              (SELECT min(as_of) FROM shadow_experiment_runs),
              (SELECT max(as_of) FROM shadow_experiment_runs),
              (SELECT status FROM experiment_run_attempts
                ORDER BY as_of DESC, attempt_no DESC, attempt_id DESC LIMIT 1),
              (SELECT detail FROM experiment_run_attempts
                ORDER BY as_of DESC, attempt_no DESC, attempt_id DESC LIMIT 1)
            """,
            (),
        )
        if row is None or row[0] is None or row[1] is None:
            return None
        return WindowBoundaryStatus(
            window_start=_canonical(row[0]),
            latest_boundary_as_of=_canonical(row[1]),
            latest_attempt_status=cast(str | None, row[2]),
            latest_attempt_detail=cast(str | None, row[3]),
        )

    def latest_run_state(self) -> LatestRunStatus | None:
        """Latest paired run lifecycle state (FAILED stays explicit)."""
        row = self._fetch_one(
            """
            SELECT run_id, status, run_class
            FROM shadow_experiment_runs
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, run_id DESC
            LIMIT 1
            """,
            (None,),
        )
        if row is None:
            return None
        return LatestRunStatus(
            run_id=cast(str, row[0]),
            status=cast(str, row[1]),
            run_class=cast(str | None, row[2]),
        )

    def coverage_health(self) -> CoverageHealthStatus | None:
        """Control coverage health of the latest paired boundary (R4).

        Unknown lane strings fail closed instead of rendering as OK.
        """
        row = self._fetch_one(
            """
            SELECT run_json->>'control_transport_state',
                   run_json->>'control_freshness_state',
                   run_json->>'control_coverage_state',
                   run_json->>'control_schema_state'
            FROM shadow_experiment_runs
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, run_id DESC
            LIMIT 1
            """,
            (None,),
        )
        if row is None:
            return None
        states = (
            cast(str | None, row[0]),
            cast(str | None, row[1]),
            cast(str | None, row[2]),
            cast(str | None, row[3]),
        )
        parsed: list[str] = []
        for value in states:
            if value is None:
                raise ExperimentalReadFailure("run coverage lane state is missing")
            try:
                parsed.append(HealthValue(value).value)
            except ValueError as exc:
                raise ExperimentalReadFailure(
                    "run coverage lane state is not a known health value"
                ) from exc
        return CoverageHealthStatus(
            transport_state=parsed[0],
            freshness_state=parsed[1],
            completeness_state=parsed[2],
            schema_state=parsed[3],
        )

    def opportunity_domain_counts(self) -> tuple[DomainOpportunityCounts, ...]:
        """Anchor-derived per-stratum counts (anchors ONLY, deterministic)."""
        rows = self._fetch_all(
            """
            SELECT a.domain_stratum,
                   count(*) AS anchors,
                   count(*) FILTER (
                       WHERE r.resolution_state = 'RESOLVED' AND r.label = 'POSITIVE'),
                   count(*) FILTER (
                       WHERE r.resolution_state = 'RESOLVED' AND r.label = 'NEGATIVE'),
                   count(*) FILTER (
                       WHERE r.resolution_state = 'UNKNOWN'
                         AND r.label = 'UNRESOLVED_COVERAGE'),
                   count(*) FILTER (WHERE r.resolution_state = 'EXCLUDED'),
                   count(*) FILTER (WHERE r.anchor_id IS NULL)
            FROM opportunity_anchors a
            LEFT JOIN outcome_resolutions r USING (anchor_id)
            GROUP BY a.domain_stratum
            ORDER BY a.domain_stratum
            """,
            (),
        )
        counts: list[DomainOpportunityCounts] = []
        for item in rows:
            counts.append(
                DomainOpportunityCounts(
                    domain=cast(str, item[0]),
                    anchor_count=int(cast(int, item[1])),
                    resolved_positive_count=int(cast(int, item[2])),
                    resolved_negative_count=int(cast(int, item[3])),
                    unresolved_coverage_count=int(cast(int, item[4])),
                    unknown_count=int(cast(int, item[4])),
                    excluded_count=int(cast(int, item[5])),
                    pending_count=int(cast(int, item[6])),
                )
            )
        return tuple(counts)

    def latest_evaluation_statistics(self) -> EvaluationStatisticsStatus | None:
        """Latest receipt's status and its OWN stored statistics (verbatim)."""
        row = self._fetch_one(
            """
            SELECT evaluation_id, status, freeze_status, receipt_json
            FROM evaluation_receipts
            WHERE as_of <= COALESCE(%s, 'infinity'::timestamptz)
            ORDER BY as_of DESC, evaluation_id DESC
            LIMIT 1
            """,
            (None,),
        )
        if row is None:
            return None
        receipt_json = row[3]
        if not isinstance(receipt_json, dict):
            raise ExperimentalReadFailure("evaluation receipt payload is not a mapping")
        payload = cast(dict[str, object], receipt_json)
        domains = _evaluation_domain_rows(payload)
        pooled = _optional_text_field(
            payload.get("pooled_median_lead_time_advantage_seconds"),
            "pooled median lead time advantage seconds",
        )
        return EvaluationStatisticsStatus(
            evaluation_id=cast(str, row[0]),
            status=cast(str, row[1]),
            freeze_status=cast(str | None, row[2]),
            verdict=_optional_text_field(payload.get("verdict"), "verdict"),
            status_reason=_optional_text_field(payload.get("status_reason"), "status reason"),
            pooled_median_lead_time_advantage_seconds=pooled,
            domains=domains,
        )

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


def _require_text_field(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExperimentalReadFailure(f"evaluation receipt {what} is missing or not text")
    return value


def _optional_text_field(value: object, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ExperimentalReadFailure(f"evaluation receipt {what} is missing or not text")
    return value


def _optional_decimal_text(value: object, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExperimentalReadFailure(f"evaluation receipt {what} is not a canonical decimal")
    return value


def _arm_counts(payload: object, what: str) -> tuple[str | None, int | None, int | None]:
    if not isinstance(payload, dict):
        raise ExperimentalReadFailure(f"evaluation receipt {what} is not a mapping")
    arm = cast(dict[str, object], payload)
    surfaced = arm.get("surfaced_resolved")
    positive = arm.get("positive_surfaced_resolved")
    for item in (surfaced, positive):
        if item is not None and (not isinstance(item, int) or isinstance(item, bool)):
            raise ExperimentalReadFailure(f"evaluation receipt {what} count is not an integer")
    return (
        _optional_decimal_text(arm.get("precision"), f"{what} precision"),
        cast("int | None", surfaced),
        cast("int | None", positive),
    )


def _evaluation_domain_rows(
    payload: dict[str, object],
) -> tuple[DomainEvaluationStatusRow, ...]:
    """Parse the receipt's stored per-domain rows fail-closed (verbatim)."""
    raw_domains = payload.get("domains")
    if raw_domains is None:
        return ()
    if not isinstance(raw_domains, list):
        raise ExperimentalReadFailure("evaluation receipt domains are not a list")
    rows: list[DomainEvaluationStatusRow] = []
    for entry in cast("list[object]", raw_domains):
        if not isinstance(entry, dict):
            raise ExperimentalReadFailure("evaluation receipt domain row is not a mapping")
        row = cast(dict[str, object], entry)
        candidate_precision, candidate_surfaced, candidate_positive = _arm_counts(
            row.get("candidate_arm"), "candidate arm"
        )
        control_precision, control_surfaced, control_positive = _arm_counts(
            row.get("control_arm"), "control arm"
        )
        noninferiority = row.get("noninferiority_pass")
        if noninferiority is not None and not isinstance(noninferiority, bool):
            raise ExperimentalReadFailure("evaluation receipt noninferiority_pass is not a boolean")
        adequacy = row.get("qualifies_sample_adequacy")
        if adequacy is not None and not isinstance(adequacy, bool):
            raise ExperimentalReadFailure(
                "evaluation receipt qualifies_sample_adequacy is not a boolean"
            )
        rows.append(
            DomainEvaluationStatusRow(
                domain=_require_text_field(row.get("domain"), "domain"),
                candidate_precision=candidate_precision,
                candidate_surfaced_resolved=candidate_surfaced,
                candidate_positive_surfaced_resolved=candidate_positive,
                control_precision=control_precision,
                control_surfaced_resolved=control_surfaced,
                control_positive_surfaced_resolved=control_positive,
                difference_lower_bound=_optional_decimal_text(
                    row.get("difference_lower_bound"), "difference lower bound"
                ),
                noninferiority_pass=noninferiority,
                median_lead_time_advantage_seconds=_optional_decimal_text(
                    row.get("lead_time_median_advantage_seconds"),
                    "median lead time advantage seconds",
                ),
                qualifies_sample_adequacy=adequacy,
            )
        )
    return tuple(rows)


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
