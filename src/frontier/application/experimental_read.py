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

from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    AnalysisArtifactSummary,
    EvaluationReceiptSummary,
    ExperimentalOverview,
    FeatureBatchSummary,
    PefArtifactSummary,
    ShadowRunSummary,
    build_experimental_overview,
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
