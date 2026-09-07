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

from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import sha256_digest
from frontier.domain.experiment_status import (
    BoundFreezeStatus,
    CoverageHealthStatus,
    DomainEvaluationStatusRow,
    DomainOpportunityCounts,
    EvaluationStatisticsStatus,
    ExperimentStatusInputs,
    LatestRunStatus,
    WindowBoundaryStatus,
)
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    EXPERIMENTAL_READ_AUTHORITY_STATE,
    EXPERIMENTAL_READ_AVAILABLE,
    EXPERIMENTAL_READ_INTERPRETATION,
    EXPERIMENTAL_READ_NO_DATA,
    EXPERIMENTAL_READ_SCHEMA_VERSION,
    EXPERIMENTAL_READ_UNAVAILABLE,
    EXPERIMENTAL_READ_UNKNOWN,
    AnalysisArtifactSummary,
    ControlRankEntry,
    EpisodeComparison,
    EvaluationDetail,
    EvaluationHistoryEntry,
    EvaluationReceiptSummary,
    ExperimentalReadFailure,
    FeatureBatchSummary,
    PefArtifactSummary,
    RunHistoryEntry,
    ShadowRunDetail,
    ShadowRunSummary,
)
from frontier.domain.health import HealthValue

_RUN_HORIZON: LiteralString = "as_of <= COALESCE(%s, 'infinity'::timestamptz)"


def _shadow_run_ids(raw: object) -> tuple[str, ...]:
    """Parse the receipt's stored shadow-run-id list fail-closed (R8)."""
    if not isinstance(raw, list):
        raise ExperimentalReadFailure("evaluation shadow run ids are not a list")
    ids: list[str] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, str):
            raise ExperimentalReadFailure("evaluation shadow run id is not a string")
        ids.append(item)
    return tuple(ids)


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
                   COALESCE(
                       artifact_json->>'generated_at',
                       to_char(as_of AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                   ),
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
        run_ids = _shadow_run_ids(row[16])
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
            shadow_run_ids=run_ids,
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

    # ------------------------------------------------------------------
    # WP7 (G5): per-episode comparison, run/evaluation detail, history,
    # and status inputs. All SELECT-only; absent rows are None, never
    # fabricated (R4); every query honours the point-in-time horizon so
    # observations stored after ``as_of`` never surface (R1).
    # ------------------------------------------------------------------

    def _run_row(
        self, *, run_id: str | None, as_of: datetime | None
    ) -> tuple[tuple[object, ...], dict[str, object]] | None:
        """Resolve the paired run (by id, else latest within the horizon)."""
        if run_id is not None:
            row = self._fetch_one(
                f"""
                SELECT run_id, status, as_of, control_snapshot_id, candidate_artifact_id,
                       failure_reason, run_json
                FROM shadow_experiment_runs
                WHERE run_id = %s AND {_RUN_HORIZON}
                """,
                (run_id, as_of),
            )
        else:
            row = self._fetch_one(
                f"""
                SELECT run_id, status, as_of, control_snapshot_id, candidate_artifact_id,
                       failure_reason, run_json
                FROM shadow_experiment_runs
                WHERE {_RUN_HORIZON}
                ORDER BY as_of DESC, run_id DESC
                LIMIT 1
                """,
                (as_of,),
            )
        if row is None:
            return None
        run_json = row[6]
        if not isinstance(run_json, dict):
            raise ExperimentalReadFailure("shadow run payload is not a mapping")
        return row, cast(dict[str, object], run_json)

    @staticmethod
    def _control_ranking(
        run_json: dict[str, object],
    ) -> tuple[ControlRankEntry, ...]:
        """Parse the stored control ranking fail-closed (deterministic order)."""
        raw = run_json.get("control_ranking")
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ExperimentalReadFailure("shadow run control ranking is not a list")
        entries: list[ControlRankEntry] = []
        for item in cast("list[object]", raw):
            if not isinstance(item, dict):
                raise ExperimentalReadFailure("control ranking entry is not a mapping")
            entry = cast(dict[str, object], item)
            episode_id = entry.get("episode_id")
            rank = entry.get("rank")
            if not isinstance(episode_id, str) or not episode_id:
                raise ExperimentalReadFailure("control ranking episode id is not text")
            if not isinstance(rank, int) or isinstance(rank, bool):
                raise ExperimentalReadFailure("control ranking rank is not an integer")
            entries.append(ControlRankEntry(episode_id=episode_id, rank=rank))
        return tuple(sorted(entries, key=lambda item: (item.rank, item.episode_id)))

    def _candidate_episode_payload(
        self, *, candidate_artifact_id: str, episode_id: str, as_of: datetime | None
    ) -> dict[str, object] | None:
        """The stored candidate episode payload, verbatim (already authorized)."""
        row = self._fetch_one(
            f"""
            SELECT artifact_json->'episodes'
            FROM pef_ranking_artifacts
            WHERE artifact_id = %s AND {_RUN_HORIZON}
            """,
            (candidate_artifact_id, as_of),
        )
        if row is None:
            return None
        raw = row[0]
        if raw is None:
            return None
        if not isinstance(raw, list):
            raise ExperimentalReadFailure("candidate artifact episodes are not a list")
        for item in cast("list[object]", raw):
            if not isinstance(item, dict):
                raise ExperimentalReadFailure("candidate episode entry is not a mapping")
            entry = cast(dict[str, object], item)
            if entry.get("episode_id") == episode_id:
                return entry
        return None

    def _latest_run_evaluation(
        self, *, run_id: str, as_of: datetime | None
    ) -> tuple[str, str] | None:
        """Latest preregistered evaluation receipt referencing this run."""
        row = self._fetch_one(
            f"""
            SELECT evaluation_id, status
            FROM evaluation_receipts
            WHERE shadow_run_ids ? %s AND {_RUN_HORIZON}
            ORDER BY as_of DESC, evaluation_id DESC
            LIMIT 1
            """,
            (run_id, as_of),
        )
        if row is None:
            return None
        return (cast(str, row[0]), cast(str, row[1]))

    def _feature_surface(
        self, *, episode_id: str, control_snapshot_id: str, as_of: datetime | None
    ) -> tuple[str, str, str | None, list[dict[str, object]]]:
        """Digest-verified transparent feature surface for one episode (R8).

        Returns ``(availability, interpretation_state, interpretation, values)``.
        A digest mismatch or non-RAN row is explicit ``UNKNOWN``: the payload is
        never surfaced unverified. Interpretation text is surfaced only when it
        is already part of the stored feature payload semantics.
        """
        row = self._fetch_one(
            f"""
            SELECT vector_json, vector_digest, status
            FROM feature_vectors
            WHERE episode_id = %s AND control_snapshot_id = %s AND {_RUN_HORIZON}
            ORDER BY as_of DESC, feature_vector_id DESC
            LIMIT 1
            """,
            (episode_id, control_snapshot_id, as_of),
        )
        if row is None:
            return (EXPERIMENTAL_READ_NO_DATA, EXPERIMENTAL_READ_UNAVAILABLE, None, [])
        vector_json = row[0]
        if not isinstance(vector_json, dict):
            raise ExperimentalReadFailure("feature vector payload is not a mapping")
        payload = cast(dict[str, object], vector_json)
        if cast(str | None, row[2]) != "RAN":
            return (EXPERIMENTAL_READ_UNKNOWN, EXPERIMENTAL_READ_UNAVAILABLE, None, [])
        computed = sha256_digest(canonical_json_bytes(payload))
        if str(computed) != cast(str, row[1]):
            return (
                EXPERIMENTAL_READ_UNKNOWN,
                EXPERIMENTAL_READ_UNAVAILABLE,
                None,
                [],
            )
        raw_features = payload.get("features")
        values: list[dict[str, object]] = []
        if raw_features is not None:
            if not isinstance(raw_features, list):
                raise ExperimentalReadFailure("feature values are not a list")
            for item in cast("list[object]", raw_features):
                if not isinstance(item, dict):
                    raise ExperimentalReadFailure("feature value entry is not a mapping")
                values.append(cast(dict[str, object], item))
        interpretation = payload.get("interpretation")
        if interpretation is None:
            return (
                EXPERIMENTAL_READ_AVAILABLE,
                EXPERIMENTAL_READ_UNAVAILABLE,
                None,
                values,
            )
        if not isinstance(interpretation, str) or not interpretation:
            raise ExperimentalReadFailure("feature interpretation is not text")
        return (
            EXPERIMENTAL_READ_AVAILABLE,
            EXPERIMENTAL_READ_AVAILABLE,
            interpretation,
            values,
        )

    def episode_comparison(
        self,
        *,
        episode_id: str,
        run_id: str | None = None,
        as_of: datetime | None = None,
    ) -> EpisodeComparison | None:
        """Per-episode comparison bound to one run identity (R1, R4, R7, R8)."""
        resolved = self._run_row(run_id=run_id, as_of=as_of)
        if resolved is None:
            return None
        run_row, run_json = resolved
        if not episode_id:
            raise ExperimentalReadFailure("episode id must be non-empty text")
        run_status = cast(str, run_row[1])
        control_snapshot_id = cast(str, run_row[3])
        candidate_artifact_id = cast(str, run_row[4])

        freeze_raw = run_json.get("candidate_freeze_receipt_id")
        if freeze_raw is not None and not isinstance(freeze_raw, str):
            raise ExperimentalReadFailure("candidate freeze receipt id is not text")

        baseline_rank: int | None = None
        for entry in self._control_ranking(run_json):
            if entry.episode_id == episode_id:
                baseline_rank = entry.rank
                break

        candidate_payload = self._candidate_episode_payload(
            candidate_artifact_id=candidate_artifact_id,
            episode_id=episode_id,
            as_of=as_of,
        )
        candidate_rank: int | None = None
        if candidate_payload is not None:
            raw_rank = candidate_payload.get("rank")
            if not isinstance(raw_rank, int) or isinstance(raw_rank, bool):
                raise ExperimentalReadFailure("candidate episode rank is not an integer")
            candidate_rank = raw_rank

        evaluation = self._latest_run_evaluation(run_id=cast(str, run_row[0]), as_of=as_of)
        (
            feature_availability,
            feature_interpretation_state,
            feature_interpretation,
            feature_values,
        ) = self._feature_surface(
            episode_id=episode_id,
            control_snapshot_id=control_snapshot_id,
            as_of=as_of,
        )

        baseline_state = (
            EXPERIMENTAL_READ_AVAILABLE
            if baseline_rank is not None
            else EXPERIMENTAL_READ_UNAVAILABLE
        )
        candidate_state = (
            EXPERIMENTAL_READ_AVAILABLE
            if candidate_rank is not None
            else EXPERIMENTAL_READ_UNAVAILABLE
        )
        rank_delta: int | None = None
        if candidate_rank is not None and baseline_rank is not None:
            rank_delta = candidate_rank - baseline_rank
        delta_state = (
            EXPERIMENTAL_READ_AVAILABLE if rank_delta is not None else EXPERIMENTAL_READ_UNAVAILABLE
        )
        components_state = (
            EXPERIMENTAL_READ_AVAILABLE
            if candidate_payload is not None
            else EXPERIMENTAL_READ_UNAVAILABLE
        )
        episode_present = (
            baseline_state == EXPERIMENTAL_READ_AVAILABLE
            or candidate_state == EXPERIMENTAL_READ_AVAILABLE
        )
        return EpisodeComparison(
            schema_version=EXPERIMENTAL_READ_SCHEMA_VERSION,
            authority_state=EXPERIMENTAL_READ_AUTHORITY_STATE,
            interpretation=EXPERIMENTAL_READ_INTERPRETATION,
            availability=(
                EXPERIMENTAL_READ_AVAILABLE if episode_present else EXPERIMENTAL_READ_NO_DATA
            ),
            episode_id=episode_id,
            as_of=_canonical(run_row[2]),
            run_id=cast(str, run_row[0]),
            run_status=run_status,
            run_failure_reason=cast(str | None, run_row[5]),
            control_snapshot_id=control_snapshot_id,
            candidate_freeze_receipt_id=freeze_raw,
            evaluation_receipt_id=None if evaluation is None else evaluation[0],
            evaluation_receipt_status=None if evaluation is None else evaluation[1],
            evaluation_state=(
                EXPERIMENTAL_READ_NO_DATA if evaluation is None else EXPERIMENTAL_READ_AVAILABLE
            ),
            baseline_rank_state=baseline_state,
            baseline_rank=baseline_rank,
            candidate_rank_state=candidate_state,
            candidate_rank=candidate_rank,
            rank_delta_state=delta_state,
            rank_delta=rank_delta,
            candidate_components_state=components_state,
            candidate_components=cast("dict[str, CanonicalValue] | None", candidate_payload),
            feature_availability=feature_availability,
            feature_interpretation_state=feature_interpretation_state,
            feature_interpretation=feature_interpretation,
            feature_values=cast("list[dict[str, CanonicalValue]]", feature_values),
        )

    def run_detail(self, *, run_id: str, as_of: datetime | None = None) -> ShadowRunDetail | None:
        """Full run record incl. bindings, run_class, and coverage (R7, R8)."""
        row = self._fetch_one(
            f"""
            SELECT run_id, run_digest, experiment_id, candidate_id, schema_version,
                   algorithm_version, configuration_digest, authority_state, status,
                   as_of, control_snapshot_id, control_receipt_id, candidate_artifact_id,
                   candidate_output_digest, episode_universe_digest, failure_reason,
                   run_class, coverage_state, run_json->>'generated_at',
                   run_json->>'candidate_freeze_receipt_id', run_json
            FROM shadow_experiment_runs
            WHERE run_id = %s AND {_RUN_HORIZON}
            """,
            (run_id, as_of),
        )
        if row is None:
            return None
        run_json = row[20]
        if not isinstance(run_json, dict):
            raise ExperimentalReadFailure("shadow run payload is not a mapping")
        payload = cast(dict[str, object], run_json)
        freeze_raw = payload.get("candidate_freeze_receipt_id")
        if freeze_raw is not None and not isinstance(freeze_raw, str):
            raise ExperimentalReadFailure("candidate freeze receipt id is not text")
        return ShadowRunDetail(
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
            control_snapshot_id=cast(str, row[10]),
            control_receipt_id=cast(str, row[11]),
            candidate_artifact_id=cast(str, row[12]),
            candidate_output_digest=cast(str, row[13]),
            episode_universe_digest=cast(str, row[14]),
            failure_reason=cast(str | None, row[15]),
            run_class=cast(str | None, row[16]),
            coverage_state=cast(str, row[17]),
            generated_at=cast(str, row[18]),
            candidate_freeze_receipt_id=freeze_raw,
            control_ranking=self._control_ranking(payload),
        )

    def evaluation_detail(
        self, *, evaluation_id: str, as_of: datetime | None = None
    ) -> EvaluationDetail | None:
        """Full evaluation receipt incl. stored per-domain rows (R8)."""
        row = self._fetch_one(
            f"""
            SELECT evaluation_id, receipt_digest, status, as_of, generated_at,
                   experiment_id, candidate_id, schema_version,
                   evaluation_algorithm_version, candidate_configuration_digest,
                   evaluation_configuration_digest, authority_state,
                   candidate_freeze_receipt_id, freeze_receipt_digest,
                   freeze_status, preregistration_digest, shadow_run_ids,
                   receipt_json->>'status_reason', receipt_json->>'verdict', receipt_json
            FROM evaluation_receipts
            WHERE evaluation_id = %s AND {_RUN_HORIZON}
            """,
            (evaluation_id, as_of),
        )
        if row is None:
            return None
        receipt_json = row[19]
        if not isinstance(receipt_json, dict):
            raise ExperimentalReadFailure("evaluation receipt payload is not a mapping")
        return EvaluationDetail(
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
            shadow_run_ids=_shadow_run_ids(row[16]),
            status_reason=cast(str | None, row[17]),
            verdict=cast(str | None, row[18]),
            domains=_evaluation_domain_rows(cast(dict[str, object], receipt_json)),
        )

    def experiment_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[RunHistoryEntry, ...]:
        """Bounded run history, newest first, deterministic order (R4, R8)."""
        rows = self._fetch_all(
            f"""
            SELECT run_id, run_digest, run_class, status, as_of
            FROM shadow_experiment_runs
            WHERE {_RUN_HORIZON}
            ORDER BY as_of DESC, run_id DESC
            LIMIT %s
            """,
            (as_of, limit),
        )
        return tuple(
            RunHistoryEntry(
                run_id=cast(str, row[0]),
                run_digest=cast(str, row[1]),
                run_class=cast(str | None, row[2]),
                status=cast(str, row[3]),
                as_of=_canonical(row[4]),
            )
            for row in rows
        )

    def evaluation_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[EvaluationHistoryEntry, ...]:
        """Bounded evaluation history, newest first, deterministic (R4, R8)."""
        rows = self._fetch_all(
            f"""
            SELECT evaluation_id, status, as_of
            FROM evaluation_receipts
            WHERE {_RUN_HORIZON}
            ORDER BY as_of DESC, evaluation_id DESC
            LIMIT %s
            """,
            (as_of, limit),
        )
        return tuple(
            EvaluationHistoryEntry(
                evaluation_id=cast(str, row[0]),
                status=cast(str, row[1]),
                as_of=_canonical(row[2]),
            )
            for row in rows
        )

    def experiment_status_inputs(self) -> ExperimentStatusInputs:
        """Gather the WP6 status inputs (SELECT-only, fail-closed)."""
        return ExperimentStatusInputs(
            freeze=self.latest_freeze_status(),
            window=self.window_boundaries(),
            run=self.latest_run_state(),
            coverage=self.coverage_health(),
            opportunity_counts=self.opportunity_domain_counts(),
            evaluation=self.latest_evaluation_statistics(),
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
