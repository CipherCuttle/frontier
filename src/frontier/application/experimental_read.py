"""Read-only application service for EXPERIMENTAL_SHADOW read models (slice G).

Wraps a read-only repository of stored advanced-intelligence outputs and maps
repository failures to explicit ``UNKNOWN`` availability instead of fabricating
or crashing (R4). No write path exists here and no baseline response is touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from frontier.application.experiment_status import build_experiment_status
from frontier.domain.experiment_status import ExperimentStatusInputs
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    EXPERIMENTAL_READ_AUTHORITY_STATE,
    EXPERIMENTAL_READ_AVAILABLE,
    EXPERIMENTAL_READ_INTERPRETATION,
    EXPERIMENTAL_READ_NO_DATA,
    EXPERIMENTAL_READ_SCHEMA_VERSION,
    EXPERIMENTAL_READ_UNKNOWN,
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    PEF_CANDIDATE_ID,
    PEF_EXPERIMENT_ID,
    AnalysisArtifactSummary,
    EpisodeComparison,
    EvaluationDetail,
    EvaluationDetailSection,
    EvaluationHistoryEntry,
    EvaluationReceiptSummary,
    ExperimentalOverview,
    ExperimentHistory,
    ExperimentStatusSurface,
    FeatureBatchSummary,
    InvalidExperimentalLimitError,
    PefArtifactSummary,
    RunDetailSection,
    RunHistoryEntry,
    ShadowRunDetail,
    ShadowRunSummary,
    build_experimental_overview,
    build_no_data_comparison,
    build_unavailable_comparison,
)


class ExperimentalReadRepository(Protocol):
    """SELECT-only port over stored EXPERIMENTAL advanced-intelligence items."""

    def latest_shadow_run(self, *, as_of: datetime | None = None) -> ShadowRunSummary | None: ...

    def latest_pef_artifact(
        self, *, as_of: datetime | None = None
    ) -> PefArtifactSummary | None: ...

    def latest_evaluation_receipt(
        self, *, as_of: datetime | None = None
    ) -> EvaluationReceiptSummary | None: ...

    def latest_feature_batch(
        self, *, as_of: datetime | None = None
    ) -> FeatureBatchSummary | None: ...

    def latest_analysis_artifacts(
        self, *, as_of: datetime | None = None
    ) -> dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]: ...

    # WP7 (G5): per-episode comparison and detail/history/status reads.

    def episode_comparison(
        self,
        *,
        episode_id: str,
        run_id: str | None = None,
        as_of: datetime | None = None,
    ) -> EpisodeComparison | None: ...

    def run_detail(
        self, *, run_id: str, as_of: datetime | None = None
    ) -> ShadowRunDetail | None: ...

    def evaluation_detail(
        self, *, evaluation_id: str, as_of: datetime | None = None
    ) -> EvaluationDetail | None: ...

    def experiment_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[RunHistoryEntry, ...]: ...

    def evaluation_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[EvaluationHistoryEntry, ...]: ...

    def experiment_status_inputs(self) -> ExperimentStatusInputs: ...


@dataclass(frozen=True, slots=True)
class _SectionResult:
    """One section's outcome: a summary, explicit no-data, or a failure (R4)."""

    summary: object | None
    failed: bool


def _fetch(
    factory: Callable[..., object],
    *,
    as_of: datetime | None,
) -> _SectionResult:
    """Fetch one section; a repository failure is explicit, never fabricated."""
    try:
        return _SectionResult(summary=factory(as_of=as_of), failed=False)
    except Exception:
        return _SectionResult(summary=None, failed=True)


class ExperimentalReadService:
    """Assemble the labelled EXPERIMENTAL_SHADOW overview envelope."""

    def __init__(self, repository: ExperimentalReadRepository) -> None:
        self._repository = repository

    def get_overview(self, *, as_of: datetime | None = None) -> ExperimentalOverview:
        shadow_run = _fetch(self._repository.latest_shadow_run, as_of=as_of)
        pef_artifact = _fetch(self._repository.latest_pef_artifact, as_of=as_of)
        evaluation_receipt = _fetch(self._repository.latest_evaluation_receipt, as_of=as_of)
        feature_batch = _fetch(self._repository.latest_feature_batch, as_of=as_of)
        try:
            analysis = self._repository.latest_analysis_artifacts(as_of=as_of)
            analysis_failed = False
        except Exception:
            analysis = {}
            analysis_failed = True
        return build_experimental_overview(
            as_of=as_of.isoformat() if as_of is not None else None,
            shadow_run=cast(ShadowRunSummary | None, shadow_run.summary),
            pef_artifact=cast(PefArtifactSummary | None, pef_artifact.summary),
            evaluation_receipt=cast(EvaluationReceiptSummary | None, evaluation_receipt.summary),
            feature_batch=cast(FeatureBatchSummary | None, feature_batch.summary),
            analysis_artifacts=analysis,
            shadow_run_failed=shadow_run.failed,
            pef_artifact_failed=pef_artifact.failed,
            evaluation_receipt_failed=evaluation_receipt.failed,
            feature_batch_failed=feature_batch.failed,
            analysis_failed=analysis_failed,
        )

    # ------------------------------------------------------------------
    # WP7 (G5): per-episode comparison, detail, status, and history reads.
    # Every method maps a repository failure to an explicit UNKNOWN surface
    # instead of fabricating data (R4); reads stay SELECT-only.
    # ------------------------------------------------------------------

    def get_episode_comparison(
        self,
        *,
        episode_id: str,
        run_id: str | None = None,
        as_of: datetime | None = None,
    ) -> EpisodeComparison:
        """Per-episode comparison; absent data is explicit, never zeroed."""
        try:
            data = self._repository.episode_comparison(
                episode_id=episode_id, run_id=run_id, as_of=as_of
            )
        except Exception:
            return build_unavailable_comparison(episode_id)
        if data is None:
            return build_no_data_comparison(episode_id)
        return data

    def get_run_detail(self, *, run_id: str, as_of: datetime | None = None) -> RunDetailSection:
        """Full run record; missing row is NO_DATA, failure is UNKNOWN."""
        try:
            run = self._repository.run_detail(run_id=run_id, as_of=as_of)
        except Exception:
            return RunDetailSection(availability=EXPERIMENTAL_READ_UNKNOWN, run=None)
        if run is None:
            return RunDetailSection(availability=EXPERIMENTAL_READ_NO_DATA, run=None)
        return RunDetailSection(availability=EXPERIMENTAL_READ_AVAILABLE, run=run)

    def get_evaluation_detail(
        self, *, evaluation_id: str, as_of: datetime | None = None
    ) -> EvaluationDetailSection:
        """Full evaluation receipt; missing row is NO_DATA, failure is UNKNOWN."""
        try:
            evaluation = self._repository.evaluation_detail(
                evaluation_id=evaluation_id, as_of=as_of
            )
        except Exception:
            return EvaluationDetailSection(availability=EXPERIMENTAL_READ_UNKNOWN, evaluation=None)
        if evaluation is None:
            return EvaluationDetailSection(availability=EXPERIMENTAL_READ_NO_DATA, evaluation=None)
        return EvaluationDetailSection(
            availability=EXPERIMENTAL_READ_AVAILABLE, evaluation=evaluation
        )

    def get_status(self) -> ExperimentStatusSurface:
        """WP6 coherent experiment status; repository failure stays UNKNOWN."""
        try:
            inputs = self._repository.experiment_status_inputs()
        except Exception:
            return ExperimentStatusSurface(availability=EXPERIMENTAL_READ_UNKNOWN, status=None)
        status = build_experiment_status(
            freeze=inputs.freeze,
            window=inputs.window,
            run=inputs.run,
            coverage=inputs.coverage,
            opportunity_counts=inputs.opportunity_counts,
            evaluation=inputs.evaluation,
        )
        return ExperimentStatusSurface(availability=EXPERIMENTAL_READ_AVAILABLE, status=status)

    def get_history(self, *, limit: int = HISTORY_LIMIT_DEFAULT) -> ExperimentHistory:
        """Bounded, deterministically ordered run/evaluation history (R4, R8)."""
        if limit < 1 or limit > HISTORY_LIMIT_MAX:
            raise InvalidExperimentalLimitError(f"limit must be between 1 and {HISTORY_LIMIT_MAX}")
        try:
            runs = self._repository.experiment_history(limit=limit)
            evaluations = self._repository.evaluation_history(limit=limit)
        except Exception:
            return ExperimentHistory(
                schema_version=EXPERIMENTAL_READ_SCHEMA_VERSION,
                authority_state=EXPERIMENTAL_READ_AUTHORITY_STATE,
                interpretation=EXPERIMENTAL_READ_INTERPRETATION,
                experiment_id=PEF_EXPERIMENT_ID,
                candidate_id=PEF_CANDIDATE_ID,
                availability=EXPERIMENTAL_READ_UNKNOWN,
                limit=limit,
                runs=(),
                evaluations=(),
            )
        return ExperimentHistory(
            schema_version=EXPERIMENTAL_READ_SCHEMA_VERSION,
            authority_state=EXPERIMENTAL_READ_AUTHORITY_STATE,
            interpretation=EXPERIMENTAL_READ_INTERPRETATION,
            experiment_id=PEF_EXPERIMENT_ID,
            candidate_id=PEF_CANDIDATE_ID,
            availability=EXPERIMENTAL_READ_AVAILABLE,
            limit=limit,
            runs=runs,
            evaluations=evaluations,
        )
