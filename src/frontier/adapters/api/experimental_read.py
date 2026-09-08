"""FastAPI transport for EXPERIMENTAL_SHADOW read endpoints (slice G).

Namespaced under ``/v0/experimental`` so consumers can never confuse these
responses with baseline authority data. Every response is explicitly labelled
``EXPERIMENTAL_SHADOW``, carries candidate/experiment/config identity, and
returns explicit ``NO_DATA``/``UNKNOWN`` availability instead of fabricated
results (R4, R7, R8). GET only: no mutation endpoint exists here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from frontier.application.experimental_read import ExperimentalReadService
from frontier.domain.experiment_status import (
    DomainEvaluationStatusRow,
    render_experiment_status,
)
from frontier.domain.experimental_read import (
    EXPERIMENTAL_READ_AUTHORITY_STATE,
    EXPERIMENTAL_READ_INTERPRETATION,
    EXPERIMENTAL_READ_SCHEMA_VERSION,
    HISTORY_LIMIT_DEFAULT,
    AnalysisArtifactSummary,
    EpisodeComparison,
    EvaluationDetail,
    EvaluationDetailSection,
    EvaluationReceiptSummary,
    ExperimentalOverview,
    ExperimentalReadFailure,
    ExperimentHistory,
    ExperimentStatusSurface,
    FeatureBatchSummary,
    PefArtifactSummary,
    RunDetailSection,
    ShadowRunDetail,
    ShadowRunSummary,
    parse_experimental_as_of,
)

AsOfQuery = Annotated[str | None, Query()]


def _forbid() -> ConfigDict:
    return ConfigDict(extra="forbid")


class ExperimentalShadowRunResponse(BaseModel):
    model_config = _forbid()

    run_id: str
    run_digest: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    algorithm_version: str
    configuration_digest: str
    authority_state: str
    status: str
    as_of: str
    generated_at: str
    control_snapshot_id: str
    control_receipt_id: str
    candidate_artifact_id: str
    candidate_output_digest: str
    episode_universe_digest: str
    candidate_freeze_receipt_id: str | None
    failure_reason: str | None


class ExperimentalPefArtifactResponse(BaseModel):
    model_config = _forbid()

    artifact_id: str
    output_digest: str
    receipt_id: str
    status: str
    as_of: str
    generated_at: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    algorithm_version: str
    ranking_policy_version: str
    configuration_digest: str
    authority_state: str
    control_snapshot_id: str
    control_receipt_id: str
    episode_count: int | None
    failure_reason: str | None


class ExperimentalEvaluationReceiptResponse(BaseModel):
    model_config = _forbid()

    evaluation_id: str
    receipt_digest: str
    status: str
    as_of: str
    generated_at: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    evaluation_algorithm_version: str
    candidate_configuration_digest: str
    evaluation_configuration_digest: str
    authority_state: str
    candidate_freeze_receipt_id: str
    freeze_receipt_digest: str
    freeze_status: str
    preregistration_digest: str
    shadow_run_ids: list[str]
    status_reason: str | None
    verdict: str | None


class ExperimentalFeatureBatchResponse(BaseModel):
    model_config = _forbid()

    batch_id: str
    batch_digest: str
    status: str
    as_of: str
    generated_at: str
    control_snapshot_id: str
    control_receipt_id: str
    episode_universe_digest: str
    configuration_digest: str
    schema_version: str
    algorithm_version: str
    authority_state: str
    vector_count: int | None


class ExperimentalAnalysisArtifactResponse(BaseModel):
    model_config = _forbid()

    analysis_id: str
    kind: str
    status: str
    authority_state: str
    as_of: str
    generated_at: str
    configuration_digest: str
    output_digest: str
    schema_version: str
    algorithm_version: str
    control_snapshot_id: str | None
    control_receipt_id: str | None
    source_registry_version: str | None
    episode_universe_digest: str | None
    input_digest: str | None


class ExperimentalOverviewResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    experiment_id: str
    candidate_id: str
    configuration_digest: str
    as_of: str
    as_of_consistency: str
    generated_at: str
    availability: dict[str, str]
    latest_shadow_run: ExperimentalShadowRunResponse | None
    latest_pef_artifact: ExperimentalPefArtifactResponse | None
    latest_evaluation_receipt: ExperimentalEvaluationReceiptResponse | None
    latest_feature_batch: ExperimentalFeatureBatchResponse | None
    analysis_artifacts: dict[str, ExperimentalAnalysisArtifactResponse]


class ExperimentalShadowRunSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    latest: ExperimentalShadowRunResponse | None


class ExperimentalPefArtifactSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    latest: ExperimentalPefArtifactResponse | None


class ExperimentalEvaluationReceiptSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    latest: ExperimentalEvaluationReceiptResponse | None


class ExperimentalFeatureBatchSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    latest: ExperimentalFeatureBatchResponse | None


class ExperimentalAnalysisArtifactSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    kind: str
    availability: str
    latest: ExperimentalAnalysisArtifactResponse | None


class ExperimentalControlRankEntryResponse(BaseModel):
    model_config = _forbid()

    episode_id: str
    rank: int


class ExperimentalEpisodeComparisonResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    episode_id: str
    as_of: str | None
    run_id: str | None
    run_status: str | None
    run_failure_reason: str | None
    control_snapshot_id: str | None
    candidate_freeze_receipt_id: str | None
    evaluation_receipt_id: str | None
    evaluation_receipt_status: str | None
    evaluation_state: str
    baseline_rank_state: str
    baseline_rank: int | None
    candidate_rank_state: str
    candidate_rank: int | None
    rank_delta_state: str
    rank_delta: int | None
    candidate_components_state: str
    candidate_components: dict[str, Any] | None
    feature_availability: str
    feature_interpretation_state: str
    feature_interpretation: str | None
    feature_values: list[dict[str, Any]]


class ExperimentalRunDetailResponse(BaseModel):
    model_config = _forbid()

    run_id: str
    run_digest: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    algorithm_version: str
    configuration_digest: str
    authority_state: str
    status: str
    as_of: str
    generated_at: str
    control_snapshot_id: str
    control_receipt_id: str
    candidate_artifact_id: str
    candidate_output_digest: str
    episode_universe_digest: str
    candidate_freeze_receipt_id: str | None
    failure_reason: str | None
    run_class: str | None
    coverage_state: str
    control_ranking: list[ExperimentalControlRankEntryResponse]


class ExperimentalEvaluationDomainRowResponse(BaseModel):
    model_config = _forbid()

    domain: str
    candidate_precision: str | None
    candidate_surfaced_resolved: int | None
    candidate_positive_surfaced_resolved: int | None
    control_precision: str | None
    control_surfaced_resolved: int | None
    control_positive_surfaced_resolved: int | None
    difference_lower_bound: str | None
    noninferiority_pass: bool | None
    median_lead_time_advantage_seconds: str | None
    qualifies_sample_adequacy: bool | None


class ExperimentalEvaluationDetailResponse(BaseModel):
    model_config = _forbid()

    evaluation_id: str
    receipt_digest: str
    status: str
    as_of: str
    generated_at: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    evaluation_algorithm_version: str
    candidate_configuration_digest: str
    evaluation_configuration_digest: str
    authority_state: str
    candidate_freeze_receipt_id: str
    freeze_receipt_digest: str
    freeze_status: str
    preregistration_digest: str
    shadow_run_ids: list[str]
    status_reason: str | None
    verdict: str | None
    domains: list[ExperimentalEvaluationDomainRowResponse]


class ExperimentalStatusResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    status: dict[str, Any] | None


class ExperimentalRunDetailSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    run: ExperimentalRunDetailResponse | None


class ExperimentalEvaluationDetailSectionResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    availability: str
    evaluation: ExperimentalEvaluationDetailResponse | None


class ExperimentalRunHistoryEntryResponse(BaseModel):
    model_config = _forbid()

    run_id: str
    run_digest: str
    run_class: str | None
    status: str
    as_of: str


class ExperimentalEvaluationHistoryEntryResponse(BaseModel):
    model_config = _forbid()

    evaluation_id: str
    status: str
    as_of: str


class ExperimentalHistoryResponse(BaseModel):
    model_config = _forbid()

    schema_version: str = EXPERIMENTAL_READ_SCHEMA_VERSION
    authority_state: str = EXPERIMENTAL_READ_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_READ_INTERPRETATION
    experiment_id: str
    candidate_id: str
    availability: str
    limit: int
    runs: list[ExperimentalRunHistoryEntryResponse]
    evaluations: list[ExperimentalEvaluationHistoryEntryResponse]


def _shadow_run_model(summary: ShadowRunSummary) -> ExperimentalShadowRunResponse:
    return ExperimentalShadowRunResponse.model_validate(
        {
            "run_id": summary.run_id,
            "run_digest": summary.run_digest,
            "experiment_id": summary.experiment_id,
            "candidate_id": summary.candidate_id,
            "schema_version": summary.schema_version,
            "algorithm_version": summary.algorithm_version,
            "configuration_digest": summary.configuration_digest,
            "authority_state": summary.authority_state,
            "status": summary.status,
            "as_of": summary.as_of,
            "generated_at": summary.generated_at,
            "control_snapshot_id": summary.control_snapshot_id,
            "control_receipt_id": summary.control_receipt_id,
            "candidate_artifact_id": summary.candidate_artifact_id,
            "candidate_output_digest": summary.candidate_output_digest,
            "episode_universe_digest": summary.episode_universe_digest,
            "candidate_freeze_receipt_id": summary.candidate_freeze_receipt_id,
            "failure_reason": summary.failure_reason,
        }
    )


def _pef_artifact_model(summary: PefArtifactSummary) -> ExperimentalPefArtifactResponse:
    return ExperimentalPefArtifactResponse.model_validate(
        {
            "artifact_id": summary.artifact_id,
            "output_digest": summary.output_digest,
            "receipt_id": summary.receipt_id,
            "status": summary.status,
            "as_of": summary.as_of,
            "generated_at": summary.generated_at,
            "experiment_id": summary.experiment_id,
            "candidate_id": summary.candidate_id,
            "schema_version": summary.schema_version,
            "algorithm_version": summary.algorithm_version,
            "ranking_policy_version": summary.ranking_policy_version,
            "configuration_digest": summary.configuration_digest,
            "authority_state": summary.authority_state,
            "control_snapshot_id": summary.control_snapshot_id,
            "control_receipt_id": summary.control_receipt_id,
            "episode_count": summary.episode_count,
            "failure_reason": summary.failure_reason,
        }
    )


def _evaluation_model(
    summary: EvaluationReceiptSummary,
) -> ExperimentalEvaluationReceiptResponse:
    return ExperimentalEvaluationReceiptResponse.model_validate(
        {
            "evaluation_id": summary.evaluation_id,
            "receipt_digest": summary.receipt_digest,
            "status": summary.status,
            "as_of": summary.as_of,
            "generated_at": summary.generated_at,
            "experiment_id": summary.experiment_id,
            "candidate_id": summary.candidate_id,
            "schema_version": summary.schema_version,
            "evaluation_algorithm_version": summary.evaluation_algorithm_version,
            "candidate_configuration_digest": summary.candidate_configuration_digest,
            "evaluation_configuration_digest": summary.evaluation_configuration_digest,
            "authority_state": summary.authority_state,
            "candidate_freeze_receipt_id": summary.candidate_freeze_receipt_id,
            "freeze_receipt_digest": summary.freeze_receipt_digest,
            "freeze_status": summary.freeze_status,
            "preregistration_digest": summary.preregistration_digest,
            "shadow_run_ids": list(summary.shadow_run_ids),
            "status_reason": summary.status_reason,
            "verdict": summary.verdict,
        }
    )


def _feature_batch_model(
    summary: FeatureBatchSummary,
) -> ExperimentalFeatureBatchResponse:
    return ExperimentalFeatureBatchResponse.model_validate(
        {
            "batch_id": summary.batch_id,
            "batch_digest": summary.batch_digest,
            "status": summary.status,
            "as_of": summary.as_of,
            "generated_at": summary.generated_at,
            "control_snapshot_id": summary.control_snapshot_id,
            "control_receipt_id": summary.control_receipt_id,
            "episode_universe_digest": summary.episode_universe_digest,
            "configuration_digest": summary.configuration_digest,
            "schema_version": summary.schema_version,
            "algorithm_version": summary.algorithm_version,
            "authority_state": summary.authority_state,
            "vector_count": summary.vector_count,
        }
    )


def _analysis_model(
    summary: AnalysisArtifactSummary,
) -> ExperimentalAnalysisArtifactResponse:
    return ExperimentalAnalysisArtifactResponse.model_validate(
        {
            "analysis_id": summary.analysis_id,
            "kind": summary.kind,
            "status": summary.status,
            "authority_state": summary.authority_state,
            "as_of": summary.as_of,
            "generated_at": summary.generated_at,
            "configuration_digest": summary.configuration_digest,
            "output_digest": summary.output_digest,
            "schema_version": summary.schema_version,
            "algorithm_version": summary.algorithm_version,
            "control_snapshot_id": summary.control_snapshot_id,
            "control_receipt_id": summary.control_receipt_id,
            "source_registry_version": summary.source_registry_version,
            "episode_universe_digest": summary.episode_universe_digest,
            "input_digest": summary.input_digest,
        }
    )


def _overview_model(overview: ExperimentalOverview) -> ExperimentalOverviewResponse:
    return ExperimentalOverviewResponse.model_validate(
        {
            "schema_version": overview.schema_version,
            "authority_state": overview.authority_state,
            "interpretation": overview.interpretation,
            "experiment_id": overview.experiment_id,
            "candidate_id": overview.candidate_id,
            "configuration_digest": overview.configuration_digest,
            "as_of": overview.as_of,
            "as_of_consistency": overview.as_of_consistency,
            "generated_at": overview.generated_at,
            "availability": overview.availability,
            "latest_shadow_run": (
                None
                if overview.latest_shadow_run is None
                else _shadow_run_model(overview.latest_shadow_run)
            ),
            "latest_pef_artifact": (
                None
                if overview.latest_pef_artifact is None
                else _pef_artifact_model(overview.latest_pef_artifact)
            ),
            "latest_evaluation_receipt": (
                None
                if overview.latest_evaluation_receipt is None
                else _evaluation_model(overview.latest_evaluation_receipt)
            ),
            "latest_feature_batch": (
                None
                if overview.latest_feature_batch is None
                else _feature_batch_model(overview.latest_feature_batch)
            ),
            "analysis_artifacts": {
                kind.value: _analysis_model(summary)
                for kind, summary in overview.analysis_artifacts.items()
            },
        }
    )


def _run_detail_model(detail: ShadowRunDetail) -> ExperimentalRunDetailResponse:
    return ExperimentalRunDetailResponse.model_validate(
        {
            "run_id": detail.run_id,
            "run_digest": detail.run_digest,
            "experiment_id": detail.experiment_id,
            "candidate_id": detail.candidate_id,
            "schema_version": detail.schema_version,
            "algorithm_version": detail.algorithm_version,
            "configuration_digest": detail.configuration_digest,
            "authority_state": detail.authority_state,
            "status": detail.status,
            "as_of": detail.as_of,
            "generated_at": detail.generated_at,
            "control_snapshot_id": detail.control_snapshot_id,
            "control_receipt_id": detail.control_receipt_id,
            "candidate_artifact_id": detail.candidate_artifact_id,
            "candidate_output_digest": detail.candidate_output_digest,
            "episode_universe_digest": detail.episode_universe_digest,
            "candidate_freeze_receipt_id": detail.candidate_freeze_receipt_id,
            "failure_reason": detail.failure_reason,
            "run_class": detail.run_class,
            "coverage_state": detail.coverage_state,
            "control_ranking": [
                {"episode_id": entry.episode_id, "rank": entry.rank}
                for entry in detail.control_ranking
            ],
        }
    )


def _evaluation_domain_row_model(
    row: DomainEvaluationStatusRow,
) -> ExperimentalEvaluationDomainRowResponse:
    return ExperimentalEvaluationDomainRowResponse.model_validate(
        {
            "domain": row.domain,
            "candidate_precision": row.candidate_precision,
            "candidate_surfaced_resolved": row.candidate_surfaced_resolved,
            "candidate_positive_surfaced_resolved": row.candidate_positive_surfaced_resolved,
            "control_precision": row.control_precision,
            "control_surfaced_resolved": row.control_surfaced_resolved,
            "control_positive_surfaced_resolved": row.control_positive_surfaced_resolved,
            "difference_lower_bound": row.difference_lower_bound,
            "noninferiority_pass": row.noninferiority_pass,
            "median_lead_time_advantage_seconds": row.median_lead_time_advantage_seconds,
            "qualifies_sample_adequacy": row.qualifies_sample_adequacy,
        }
    )


def _evaluation_detail_model(detail: EvaluationDetail) -> ExperimentalEvaluationDetailResponse:
    return ExperimentalEvaluationDetailResponse.model_validate(
        {
            "evaluation_id": detail.evaluation_id,
            "receipt_digest": detail.receipt_digest,
            "status": detail.status,
            "as_of": detail.as_of,
            "generated_at": detail.generated_at,
            "experiment_id": detail.experiment_id,
            "candidate_id": detail.candidate_id,
            "schema_version": detail.schema_version,
            "evaluation_algorithm_version": detail.evaluation_algorithm_version,
            "candidate_configuration_digest": detail.candidate_configuration_digest,
            "evaluation_configuration_digest": detail.evaluation_configuration_digest,
            "authority_state": detail.authority_state,
            "candidate_freeze_receipt_id": detail.candidate_freeze_receipt_id,
            "freeze_receipt_digest": detail.freeze_receipt_digest,
            "freeze_status": detail.freeze_status,
            "preregistration_digest": detail.preregistration_digest,
            "shadow_run_ids": list(detail.shadow_run_ids),
            "status_reason": detail.status_reason,
            "verdict": detail.verdict,
            "domains": [_evaluation_domain_row_model(row) for row in detail.domains],
        }
    )


def _comparison_model(
    comparison: EpisodeComparison,
) -> ExperimentalEpisodeComparisonResponse:
    return ExperimentalEpisodeComparisonResponse.model_validate(
        {
            "schema_version": comparison.schema_version,
            "authority_state": comparison.authority_state,
            "interpretation": comparison.interpretation,
            "availability": comparison.availability,
            "episode_id": comparison.episode_id,
            "as_of": comparison.as_of,
            "run_id": comparison.run_id,
            "run_status": comparison.run_status,
            "run_failure_reason": comparison.run_failure_reason,
            "control_snapshot_id": comparison.control_snapshot_id,
            "candidate_freeze_receipt_id": comparison.candidate_freeze_receipt_id,
            "evaluation_receipt_id": comparison.evaluation_receipt_id,
            "evaluation_receipt_status": comparison.evaluation_receipt_status,
            "evaluation_state": comparison.evaluation_state,
            "baseline_rank_state": comparison.baseline_rank_state,
            "baseline_rank": comparison.baseline_rank,
            "candidate_rank_state": comparison.candidate_rank_state,
            "candidate_rank": comparison.candidate_rank,
            "rank_delta_state": comparison.rank_delta_state,
            "rank_delta": comparison.rank_delta,
            "candidate_components_state": comparison.candidate_components_state,
            "candidate_components": comparison.candidate_components,
            "feature_availability": comparison.feature_availability,
            "feature_interpretation_state": comparison.feature_interpretation_state,
            "feature_interpretation": comparison.feature_interpretation,
            "feature_values": comparison.feature_values,
        }
    )


def _run_detail_section_model(
    section: RunDetailSection,
) -> ExperimentalRunDetailSectionResponse:
    return ExperimentalRunDetailSectionResponse.model_validate(
        {
            "availability": section.availability,
            "run": None if section.run is None else _run_detail_model(section.run),
        }
    )


def _evaluation_detail_section_model(
    section: EvaluationDetailSection,
) -> ExperimentalEvaluationDetailSectionResponse:
    return ExperimentalEvaluationDetailSectionResponse.model_validate(
        {
            "availability": section.availability,
            "evaluation": (
                None if section.evaluation is None else _evaluation_detail_model(section.evaluation)
            ),
        }
    )


def _history_model(history: ExperimentHistory) -> ExperimentalHistoryResponse:
    return ExperimentalHistoryResponse.model_validate(
        {
            "schema_version": history.schema_version,
            "authority_state": history.authority_state,
            "interpretation": history.interpretation,
            "experiment_id": history.experiment_id,
            "candidate_id": history.candidate_id,
            "availability": history.availability,
            "limit": history.limit,
            "runs": [
                {
                    "run_id": item.run_id,
                    "run_digest": item.run_digest,
                    "run_class": item.run_class,
                    "status": item.status,
                    "as_of": item.as_of,
                }
                for item in history.runs
            ],
            "evaluations": [
                {
                    "evaluation_id": item.evaluation_id,
                    "status": item.status,
                    "as_of": item.as_of,
                }
                for item in history.evaluations
            ],
        }
    )


def _status_response_model(surface: ExperimentStatusSurface) -> ExperimentalStatusResponse:
    payload = None if surface.status is None else render_experiment_status(surface.status)
    return ExperimentalStatusResponse.model_validate(
        {
            "schema_version": EXPERIMENTAL_READ_SCHEMA_VERSION,
            "authority_state": EXPERIMENTAL_READ_AUTHORITY_STATE,
            "interpretation": EXPERIMENTAL_READ_INTERPRETATION,
            "availability": surface.availability,
            "status": payload,
        }
    )


def _optional_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    return parse_experimental_as_of(value)


def register_experimental_routes(app: FastAPI, service: ExperimentalReadService) -> None:
    """Attach namespaced EXPERIMENTAL_SHADOW GET routes to the read app."""

    async def experimental_failure_handler(_request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, ExperimentalReadFailure):
            raise exc
        detail = "The experimental read request is invalid."
        if exc.code == "INVALID_AS_OF":
            detail = "as_of must be a canonical UTC timestamp."
        elif exc.code == "INVALID_ANALYSIS_KIND":
            detail = "Unknown experimental analysis artifact kind."
        elif exc.code == "INVALID_LIMIT":
            detail = "limit must be an integer between 1 and 200."
        return JSONResponse(status_code=400, content={"error": exc.code, "detail": detail})

    def episode_comparison(
        episode_id: str, run_id: AsOfQuery = None, as_of: AsOfQuery = None
    ) -> ExperimentalEpisodeComparisonResponse:
        comparison = service.get_episode_comparison(
            episode_id=episode_id,
            run_id=run_id,
            as_of=_optional_as_of(as_of),
        )
        return _comparison_model(comparison)

    def run_detail(run_id: str, as_of: AsOfQuery = None) -> ExperimentalRunDetailSectionResponse:
        return _run_detail_section_model(
            service.get_run_detail(run_id=run_id, as_of=_optional_as_of(as_of))
        )

    def evaluation_detail(
        evaluation_id: str, as_of: AsOfQuery = None
    ) -> ExperimentalEvaluationDetailSectionResponse:
        return _evaluation_detail_section_model(
            service.get_evaluation_detail(evaluation_id=evaluation_id, as_of=_optional_as_of(as_of))
        )

    def status_endpoint() -> ExperimentalStatusResponse:
        return _status_response_model(service.get_status())

    def history(limit: int = HISTORY_LIMIT_DEFAULT) -> ExperimentalHistoryResponse:
        return _history_model(service.get_history(limit=limit))

    def overview(as_of: AsOfQuery = None) -> ExperimentalOverviewResponse:
        return _overview_model(service.get_overview(as_of=_optional_as_of(as_of)))

    def shadow_runs(as_of: AsOfQuery = None) -> ExperimentalShadowRunSectionResponse:
        value = service.get_overview(as_of=_optional_as_of(as_of))
        return ExperimentalShadowRunSectionResponse(
            availability=value.availability.get("shadow_run", "UNKNOWN"),
            latest=(
                None
                if value.latest_shadow_run is None
                else _shadow_run_model(value.latest_shadow_run)
            ),
        )

    def pef_artifacts(as_of: AsOfQuery = None) -> ExperimentalPefArtifactSectionResponse:
        value = service.get_overview(as_of=_optional_as_of(as_of))
        return ExperimentalPefArtifactSectionResponse(
            availability=value.availability.get("pef_artifact", "UNKNOWN"),
            latest=(
                None
                if value.latest_pef_artifact is None
                else _pef_artifact_model(value.latest_pef_artifact)
            ),
        )

    def evaluation_receipts(
        as_of: AsOfQuery = None,
    ) -> ExperimentalEvaluationReceiptSectionResponse:
        value = service.get_overview(as_of=_optional_as_of(as_of))
        return ExperimentalEvaluationReceiptSectionResponse(
            availability=value.availability.get("evaluation_receipt", "UNKNOWN"),
            latest=(
                None
                if value.latest_evaluation_receipt is None
                else _evaluation_model(value.latest_evaluation_receipt)
            ),
        )

    def feature_batches(as_of: AsOfQuery = None) -> ExperimentalFeatureBatchSectionResponse:
        value = service.get_overview(as_of=_optional_as_of(as_of))
        return ExperimentalFeatureBatchSectionResponse(
            availability=value.availability.get("feature_batch", "UNKNOWN"),
            latest=(
                None
                if value.latest_feature_batch is None
                else _feature_batch_model(value.latest_feature_batch)
            ),
        )

    def analysis_artifacts(
        kind: str, as_of: AsOfQuery = None
    ) -> ExperimentalAnalysisArtifactSectionResponse:
        from frontier.domain.experimental_read import (
            EXPERIMENTAL_READ_NO_DATA,
            parse_experimental_analysis_kind,
        )

        parsed_kind = parse_experimental_analysis_kind(kind)
        value = service.get_overview(as_of=_optional_as_of(as_of))
        availability = value.availability.get(
            "analysis:" + parsed_kind.value, EXPERIMENTAL_READ_NO_DATA
        )
        summary = value.analysis_artifacts.get(parsed_kind)
        return ExperimentalAnalysisArtifactSectionResponse(
            kind=parsed_kind.value,
            availability=availability,
            latest=None if summary is None else _analysis_model(summary),
        )

    app.add_exception_handler(ExperimentalReadFailure, experimental_failure_handler)
    app.add_api_route(
        "/v0/experimental/overview",
        overview,
        methods=["GET"],
        response_model=ExperimentalOverviewResponse,
        operation_id="getExperimentalOverview",
    )
    app.add_api_route(
        "/v0/experimental/shadow-runs",
        shadow_runs,
        methods=["GET"],
        response_model=ExperimentalShadowRunSectionResponse,
        operation_id="getExperimentalShadowRuns",
    )
    app.add_api_route(
        "/v0/experimental/pef-artifacts",
        pef_artifacts,
        methods=["GET"],
        response_model=ExperimentalPefArtifactSectionResponse,
        operation_id="getExperimentalPefArtifacts",
    )
    app.add_api_route(
        "/v0/experimental/evaluation-receipts",
        evaluation_receipts,
        methods=["GET"],
        response_model=ExperimentalEvaluationReceiptSectionResponse,
        operation_id="getExperimentalEvaluationReceipts",
    )
    app.add_api_route(
        "/v0/experimental/feature-batches",
        feature_batches,
        methods=["GET"],
        response_model=ExperimentalFeatureBatchSectionResponse,
        operation_id="getExperimentalFeatureBatches",
    )
    app.add_api_route(
        "/v0/experimental/analysis/{kind}",
        analysis_artifacts,
        methods=["GET"],
        response_model=ExperimentalAnalysisArtifactSectionResponse,
        operation_id="getExperimentalAnalysisArtifacts",
    )
    app.add_api_route(
        "/v0/experimental/episodes/{episode_id}/comparison",
        episode_comparison,
        methods=["GET"],
        response_model=ExperimentalEpisodeComparisonResponse,
        operation_id="getExperimentalEpisodeComparison",
    )
    app.add_api_route(
        "/v0/experimental/runs/{run_id}",
        run_detail,
        methods=["GET"],
        response_model=ExperimentalRunDetailSectionResponse,
        operation_id="getExperimentalRunDetail",
    )
    app.add_api_route(
        "/v0/experimental/evaluations/{evaluation_id}",
        evaluation_detail,
        methods=["GET"],
        response_model=ExperimentalEvaluationDetailSectionResponse,
        operation_id="getExperimentalEvaluationDetail",
    )
    app.add_api_route(
        "/v0/experimental/status",
        status_endpoint,
        methods=["GET"],
        response_model=ExperimentalStatusResponse,
        operation_id="getExperimentalStatus",
    )
    app.add_api_route(
        "/v0/experimental/history",
        history,
        methods=["GET"],
        response_model=ExperimentalHistoryResponse,
        operation_id="getExperimentalHistory",
    )
