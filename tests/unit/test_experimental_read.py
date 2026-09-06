from __future__ import annotations

from datetime import UTC, datetime

import pytest

from frontier.application.experimental_read import ExperimentalReadService
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    EXPERIMENTAL_READ_AUTHORITY_STATE,
    EXPERIMENTAL_READ_AVAILABLE,
    EXPERIMENTAL_READ_INTERPRETATION,
    EXPERIMENTAL_READ_NO_DATA,
    EXPERIMENTAL_READ_SCHEMA_VERSION,
    EXPERIMENTAL_READ_UNKNOWN,
    AnalysisArtifactSummary,
    EvaluationReceiptSummary,
    ExperimentalOverview,
    FeatureBatchSummary,
    InvalidExperimentalAnalysisKindError,
    InvalidExperimentalAsOfError,
    PefArtifactSummary,
    ShadowRunSummary,
    build_experimental_overview,
    experimental_availability,
    parse_experimental_analysis_kind,
    parse_experimental_as_of,
)

AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
AS_OF_TEXT = "2026-09-05T12:00:00.000000Z"


def _shadow_run_summary() -> ShadowRunSummary:
    return ShadowRunSummary(
        run_id="shadowrun_" + "a" * 64,
        run_digest="sha256:" + "b" * 64,
        experiment_id="advanced-ranking-pef-v0",
        candidate_id="prospective-primary-emission-freshness-v0",
        schema_version="shadow-experiment-run-v0",
        algorithm_version="prospective-primary-emission-freshness-lexicographic-v0",
        configuration_digest="sha256:" + "c" * 64,
        authority_state="EXPERIMENTAL_SHADOW",
        status="RAN",
        as_of=AS_OF_TEXT,
        generated_at=AS_OF_TEXT,
        control_snapshot_id="snapshot_" + "d" * 64,
        control_receipt_id="receipt_" + "e" * 64,
        candidate_artifact_id="artifact_" + "f" * 64,
        candidate_output_digest="sha256:" + "1" * 64,
        episode_universe_digest="sha256:" + "2" * 64,
        candidate_freeze_receipt_id=None,
        failure_reason=None,
    )


def _pef_artifact_summary() -> PefArtifactSummary:
    return PefArtifactSummary(
        artifact_id="artifact_" + "f" * 64,
        output_digest="sha256:" + "1" * 64,
        receipt_id="receipt_" + "3" * 64,
        status="RAN",
        as_of=AS_OF_TEXT,
        generated_at=AS_OF_TEXT,
        experiment_id="advanced-ranking-pef-v0",
        candidate_id="prospective-primary-emission-freshness-v0",
        schema_version="pef-ranking-artifact-v0",
        algorithm_version="prospective-primary-emission-freshness-lexicographic-v0",
        ranking_policy_version="prospective-primary-emission-freshness-lexicographic-v0",
        configuration_digest="sha256:" + "c" * 64,
        authority_state="EXPERIMENTAL_SHADOW",
        control_snapshot_id="snapshot_" + "d" * 64,
        control_receipt_id="receipt_" + "e" * 64,
        episode_count=3,
        failure_reason=None,
    )


def _feature_batch_summary() -> FeatureBatchSummary:
    return FeatureBatchSummary(
        batch_id="featurebatch_" + "4" * 64,
        batch_digest="sha256:" + "5" * 64,
        status="RAN",
        as_of=AS_OF_TEXT,
        generated_at=AS_OF_TEXT,
        control_snapshot_id="snapshot_" + "d" * 64,
        control_receipt_id="receipt_" + "e" * 64,
        episode_universe_digest="sha256:" + "2" * 64,
        configuration_digest="sha256:" + "6" * 64,
        schema_version="advanced-features-v0",
        algorithm_version="advanced-transparent-features-v0",
        authority_state="EXPERIMENTAL_SHADOW",
        vector_count=3,
    )


def _analysis_summary(kind: ExperimentalAnalysisKind) -> AnalysisArtifactSummary:
    return AnalysisArtifactSummary(
        analysis_id="expanalysis_" + "7" * 64,
        kind=kind.value,
        status="HYPOTHESIS",
        authority_state="EXPERIMENTAL_SHADOW",
        as_of=AS_OF_TEXT,
        generated_at=AS_OF_TEXT,
        configuration_digest="sha256:" + "8" * 64,
        output_digest="sha256:" + "9" * 64,
        schema_version="experimental-analysis-v0",
        algorithm_version="experimental-analysis-v0",
        control_snapshot_id="snapshot_" + "d" * 64,
        control_receipt_id="receipt_" + "e" * 64,
        source_registry_version="sha256:" + "0" * 64,
        episode_universe_digest="sha256:" + "2" * 64,
        input_digest="sha256:" + "3" * 64,
    )


class _RecordingRepository:
    """Fake SELECT-only repository recording the resolved as_of horizon."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seen_as_of: list[datetime | None] = []

    def latest_shadow_run(self, *, as_of: datetime | None = None) -> ShadowRunSummary | None:
        self.seen_as_of.append(as_of)
        if self.fail:
            raise RuntimeError("database unavailable")
        return _shadow_run_summary()

    def latest_pef_artifact(self, *, as_of: datetime | None = None) -> PefArtifactSummary | None:
        if self.fail:
            raise RuntimeError("database unavailable")
        return _pef_artifact_summary()

    def latest_evaluation_receipt(
        self, *, as_of: datetime | None = None
    ) -> EvaluationReceiptSummary | None:
        if self.fail:
            raise RuntimeError("database unavailable")
        return None

    def latest_feature_batch(self, *, as_of: datetime | None = None) -> FeatureBatchSummary | None:
        if self.fail:
            raise RuntimeError("database unavailable")
        return _feature_batch_summary()

    def latest_analysis_artifacts(
        self, *, as_of: datetime | None = None
    ) -> dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]:
        if self.fail:
            raise RuntimeError("database unavailable")
        return {
            ExperimentalAnalysisKind.CORROBORATION: _analysis_summary(
                ExperimentalAnalysisKind.CORROBORATION
            )
        }


def test_availability_states_are_explicit() -> None:
    assert experimental_availability(None, failed=False) == EXPERIMENTAL_READ_NO_DATA
    assert experimental_availability(object(), failed=False) == EXPERIMENTAL_READ_AVAILABLE
    assert experimental_availability(None, failed=True) == EXPERIMENTAL_READ_UNKNOWN


def test_as_of_parser_accepts_canonical_and_rejects_drift() -> None:
    assert parse_experimental_as_of(AS_OF_TEXT) == AS_OF
    with pytest.raises(InvalidExperimentalAsOfError):
        parse_experimental_as_of("2026-09-05T12:00:00+02:00")
    with pytest.raises(InvalidExperimentalAsOfError):
        parse_experimental_as_of("not-a-timestamp")


def test_analysis_kind_parser_validates_frozen_kinds() -> None:
    assert (
        parse_experimental_analysis_kind("CORROBORATION") is ExperimentalAnalysisKind.CORROBORATION
    )
    with pytest.raises(InvalidExperimentalAnalysisKindError):
        parse_experimental_analysis_kind("NOT_A_KIND")


def test_overview_resolves_horizon_and_unknown_when_empty() -> None:
    overview = build_experimental_overview(
        as_of=None,
        shadow_run=None,
        pef_artifact=None,
        evaluation_receipt=None,
        feature_batch=None,
        analysis_artifacts={},
        shadow_run_failed=False,
        pef_artifact_failed=False,
        evaluation_receipt_failed=False,
        feature_batch_failed=False,
        analysis_failed=False,
    )
    assert overview.as_of == EXPERIMENTAL_READ_UNKNOWN
    assert overview.generated_at == EXPERIMENTAL_READ_UNKNOWN
    assert all(state == EXPERIMENTAL_READ_NO_DATA for state in overview.availability.values())


def test_overview_labels_authority_state_and_identities() -> None:
    overview = build_experimental_overview(
        as_of=AS_OF_TEXT,
        shadow_run=_shadow_run_summary(),
        pef_artifact=_pef_artifact_summary(),
        evaluation_receipt=None,
        feature_batch=_feature_batch_summary(),
        analysis_artifacts={
            ExperimentalAnalysisKind.CORROBORATION: _analysis_summary(
                ExperimentalAnalysisKind.CORROBORATION
            )
        },
        shadow_run_failed=False,
        pef_artifact_failed=False,
        evaluation_receipt_failed=False,
        feature_batch_failed=False,
        analysis_failed=False,
    )
    assert isinstance(overview, ExperimentalOverview)
    assert overview.authority_state == EXPERIMENTAL_READ_AUTHORITY_STATE
    assert overview.schema_version == EXPERIMENTAL_READ_SCHEMA_VERSION
    assert overview.interpretation == EXPERIMENTAL_READ_INTERPRETATION
    assert overview.experiment_id == "advanced-ranking-pef-v0"
    assert overview.candidate_id == "prospective-primary-emission-freshness-v0"
    assert overview.as_of == AS_OF_TEXT
    assert overview.availability["shadow_run"] == EXPERIMENTAL_READ_AVAILABLE
    assert overview.availability["pef_artifact"] == EXPERIMENTAL_READ_AVAILABLE
    assert overview.availability["evaluation_receipt"] == EXPERIMENTAL_READ_NO_DATA
    assert overview.availability["analysis:CORROBORATION"] == EXPERIMENTAL_READ_AVAILABLE
    assert overview.latest_shadow_run is not None
    assert overview.latest_shadow_run.run_digest.startswith("sha256:")
    assert overview.analysis_artifacts[
        ExperimentalAnalysisKind.CORROBORATION
    ].output_digest.startswith("sha256:")


def test_service_maps_repository_failure_to_unknown() -> None:
    service = ExperimentalReadService(_RecordingRepository(fail=True))
    overview = service.get_overview()
    assert overview.availability["shadow_run"] == EXPERIMENTAL_READ_UNKNOWN
    assert overview.availability["pef_artifact"] == EXPERIMENTAL_READ_UNKNOWN
    assert overview.availability["feature_batch"] == EXPERIMENTAL_READ_UNKNOWN
    assert overview.availability["analysis:CORROBORATION"] == EXPERIMENTAL_READ_UNKNOWN
    assert overview.latest_shadow_run is None


def test_service_passes_requested_as_of_to_repository() -> None:
    repository = _RecordingRepository()
    service = ExperimentalReadService(repository)
    overview = service.get_overview(as_of=AS_OF)
    assert repository.seen_as_of == [AS_OF]
    assert overview.as_of == AS_OF.isoformat()
    assert overview.availability["shadow_run"] == EXPERIMENTAL_READ_AVAILABLE
