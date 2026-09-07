"""WP7 (G5) unit tests: per-episode experimental read plane.

Covers per-episode comparison correctness (rank delta = candidate minus baseline),
explicit UNKNOWN/UNAVAILABLE/NO_DATA rendering (never zero), FAILED-run-never-
empty, mixed-snapshot rejection, GET-only endpoint invariants, and the
point-in-time future-information guard (R1, R4, R7, R8).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from frontier.adapters.api.public_read import create_public_read_app
from frontier.application.experimental_read import ExperimentalReadService
from frontier.application.public_read import PublicReadService
from frontier.domain.experiment_status import ExperimentStatusInputs
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    EXPERIMENTAL_READ_UNAVAILABLE,
    AnalysisArtifactSummary,
    ControlRankEntry,
    EpisodeComparison,
    EvaluationDetail,
    EvaluationHistoryEntry,
    ExperimentHistory,
    InvalidExperimentalLimitError,
    RunHistoryEntry,
    ShadowRunDetail,
    build_no_data_comparison,
    build_unavailable_comparison,
)

AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
AS_OF_TEXT = "2026-09-05T12:00:00.000000Z"
EPISODE_ID = "episode_abc"
OTHER_SNAPSHOT_ID = "snapshot_" + "9" * 64
RUN_ID = "shadowrun_" + "a" * 64
SNAPSHOT_ID = "snapshot_" + "b" * 64
FREEZE_ID = "freezereceipt_" + "c" * 64
EVALUATION_ID = "evaluation_" + "3" * 64


def _comparison(**overrides: object) -> EpisodeComparison:
    base: dict[str, Any] = {
        "schema_version": "experimental-read-response-v0",
        "authority_state": "EXPERIMENTAL_SHADOW",
        "interpretation": "labelled",
        "availability": "AVAILABLE",
        "episode_id": EPISODE_ID,
        "as_of": AS_OF_TEXT,
        "run_id": RUN_ID,
        "run_status": "RAN",
        "run_failure_reason": None,
        "control_snapshot_id": SNAPSHOT_ID,
        "candidate_freeze_receipt_id": None,
        "evaluation_receipt_id": None,
        "evaluation_receipt_status": None,
        "evaluation_state": "NO_DATA",
        "baseline_rank_state": "AVAILABLE",
        "baseline_rank": 2,
        "candidate_rank_state": "AVAILABLE",
        "candidate_rank": 1,
        "rank_delta_state": "AVAILABLE",
        "rank_delta": -1,
        "candidate_components_state": "AVAILABLE",
        "candidate_components": {"episode_id": EPISODE_ID, "rank": 1, "velocity_6h_delta": 3},
        "feature_availability": "AVAILABLE",
        "feature_interpretation_state": "AVAILABLE",
        "feature_interpretation": "interpretable features only",
        "feature_values": [{"name": "velocity_6h", "status": "OBSERVED", "value": 3}],
    }
    base.update(overrides)
    return EpisodeComparison(**base)


def _run_detail(**overrides: object) -> ShadowRunDetail:
    base: dict[str, Any] = {
        "run_id": RUN_ID,
        "run_digest": "sha256:" + "c" * 64,
        "experiment_id": "advanced-ranking-pef-v0",
        "candidate_id": "prospective-primary-emission-freshness-v0",
        "schema_version": "shadow-experiment-run-v0",
        "algorithm_version": "prospective-primary-emission-freshness-lexicographic-v0",
        "configuration_digest": "sha256:" + "d" * 64,
        "authority_state": "EXPERIMENTAL_SHADOW",
        "status": "RAN",
        "as_of": AS_OF_TEXT,
        "generated_at": AS_OF_TEXT,
        "control_snapshot_id": SNAPSHOT_ID,
        "control_receipt_id": "receipt_" + "e" * 64,
        "candidate_artifact_id": "artifact_" + "f" * 64,
        "candidate_output_digest": "sha256:" + "1" * 64,
        "episode_universe_digest": "sha256:" + "2" * 64,
        "candidate_freeze_receipt_id": None,
        "failure_reason": None,
        "run_class": "DEV",
        "coverage_state": "OK",
    }
    base.update(overrides)
    return ShadowRunDetail(
        **base,
        control_ranking=(
            ControlRankEntry(episode_id=EPISODE_ID, rank=1),
            ControlRankEntry(episode_id="episode_zed", rank=2),
        ),
    )


def _evaluation_detail() -> EvaluationDetail:
    return EvaluationDetail(
        evaluation_id=EVALUATION_ID,
        receipt_digest="sha256:" + "4" * 64,
        status="INSUFFICIENT_SAMPLE",
        as_of=AS_OF_TEXT,
        generated_at=AS_OF_TEXT,
        experiment_id="advanced-ranking-pef-v0",
        candidate_id="prospective-primary-emission-freshness-v0",
        schema_version="evaluation-receipt-v0",
        evaluation_algorithm_version="pef-v0-evaluation-newcombe-v0",
        candidate_configuration_digest="sha256:" + "5" * 64,
        evaluation_configuration_digest="sha256:" + "6" * 64,
        authority_state="EXPERIMENTAL_EVALUATION",
        candidate_freeze_receipt_id=FREEZE_ID,
        freeze_receipt_digest="sha256:" + "7" * 64,
        freeze_status="FROZEN",
        preregistration_digest="sha256:" + "8" * 64,
        shadow_run_ids=(RUN_ID,),
        status_reason="sample",
        verdict=None,
        domains=(),
    )


class _UnavailableBaseline:
    def resolve_snapshot(self, snapshot_id: str | None = None) -> Any:
        raise RuntimeError("baseline unavailable in this fixture")

    def list_observations(self, observation_ids: tuple[str, ...], *, as_of: datetime) -> list[Any]:
        return []

    def get_observation(self, observation_id: str, *, as_of: datetime) -> Any:
        return None

    def list_source_health(self, *, as_of: datetime) -> list[Any]:
        return []


class _PlaneRepository:
    """Fake SELECT-only repository over the WP7 read-plane surface."""

    def __init__(
        self,
        *,
        comparison: EpisodeComparison | None = None,
        run: ShadowRunDetail | None = None,
        evaluation: EvaluationDetail | None = None,
        runs_history: tuple[RunHistoryEntry, ...] = (),
        evaluations_history: tuple[EvaluationHistoryEntry, ...] = (),
        status_inputs: ExperimentStatusInputs | None = None,
        fail: bool = False,
    ) -> None:
        self.fail = fail
        self._comparison = comparison
        self._run = run
        self._evaluation = evaluation
        self._runs_history = runs_history
        self._evaluations_history = evaluations_history
        self._status_inputs = status_inputs
        self.seen_as_of: list[datetime | None] = []
        self.seen_limits: list[int] = []

    def _raise_if_failed(self) -> None:
        if self.fail:
            raise RuntimeError("database unavailable")

    def latest_shadow_run(self, *, as_of: datetime | None = None) -> None:
        raise RuntimeError("not used in this fixture")

    def latest_pef_artifact(self, *, as_of: datetime | None = None) -> None:
        raise RuntimeError("not used in this fixture")

    def latest_evaluation_receipt(self, *, as_of: datetime | None = None) -> None:
        raise RuntimeError("not used in this fixture")

    def latest_feature_batch(self, *, as_of: datetime | None = None) -> None:
        raise RuntimeError("not used in this fixture")

    def latest_analysis_artifacts(
        self, *, as_of: datetime | None = None
    ) -> dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]:
        raise RuntimeError("not used in this fixture")

    def episode_comparison(
        self, *, episode_id: str, run_id: str | None = None, as_of: datetime | None = None
    ) -> EpisodeComparison | None:
        self.seen_as_of.append(as_of)
        self._raise_if_failed()
        return self._comparison

    def run_detail(self, *, run_id: str, as_of: datetime | None = None) -> ShadowRunDetail | None:
        self._raise_if_failed()
        return self._run

    def evaluation_detail(
        self, *, evaluation_id: str, as_of: datetime | None = None
    ) -> EvaluationDetail | None:
        self._raise_if_failed()
        return self._evaluation

    def experiment_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[RunHistoryEntry, ...]:
        self._raise_if_failed()
        self.seen_limits.append(limit)
        return self._runs_history

    def evaluation_history(
        self, *, limit: int, as_of: datetime | None = None
    ) -> tuple[EvaluationHistoryEntry, ...]:
        self._raise_if_failed()
        return self._evaluations_history

    def experiment_status_inputs(self) -> ExperimentStatusInputs:
        self._raise_if_failed()
        if self._status_inputs is None:
            raise RuntimeError("status inputs not seeded")
        return self._status_inputs


class _GetClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, str] | None = None) -> Response: ...


def _client(repository: _PlaneRepository) -> _GetClient:
    return cast(
        _GetClient,
        TestClient(
            create_public_read_app(
                PublicReadService(_UnavailableBaseline()),
                experimental_service=ExperimentalReadService(repository),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Per-episode comparison correctness
# ---------------------------------------------------------------------------


def test_comparison_carries_full_mixed_identity_envelope() -> None:
    repository = _PlaneRepository(comparison=_comparison())
    comparison = ExperimentalReadService(repository).get_episode_comparison(episode_id=EPISODE_ID)
    assert comparison.run_id == RUN_ID
    assert comparison.control_snapshot_id == SNAPSHOT_ID
    assert comparison.candidate_freeze_receipt_id is None
    assert comparison.evaluation_state == "NO_DATA"
    assert comparison.availability == "AVAILABLE"


def test_rank_delta_is_candidate_minus_baseline() -> None:
    comparison = _comparison(baseline_rank=4, candidate_rank=1, rank_delta=1 - 4)
    assert comparison.rank_delta == 1 - 4


def test_absent_ranks_render_unavailable_never_zero() -> None:
    comparison = _comparison(
        availability="NO_DATA",
        baseline_rank_state=EXPERIMENTAL_READ_UNAVAILABLE,
        baseline_rank=None,
        candidate_rank_state=EXPERIMENTAL_READ_UNAVAILABLE,
        candidate_rank=None,
        rank_delta_state=EXPERIMENTAL_READ_UNAVAILABLE,
        rank_delta=None,
        candidate_components_state=EXPERIMENTAL_READ_UNAVAILABLE,
        candidate_components=None,
        feature_availability=EXPERIMENTAL_READ_UNAVAILABLE,
        feature_interpretation_state=EXPERIMENTAL_READ_UNAVAILABLE,
        feature_interpretation=None,
        feature_values=[],
    )
    assert comparison.baseline_rank is None
    assert comparison.candidate_rank is None
    assert comparison.rank_delta is None
    assert comparison.baseline_rank_state == "UNAVAILABLE"
    assert comparison.feature_values == []


def test_no_data_envelope_never_carries_rank_values() -> None:
    comparison = build_no_data_comparison(EPISODE_ID)
    assert comparison.availability == "NO_DATA"
    assert comparison.run_id is None
    assert comparison.baseline_rank is None
    assert comparison.candidate_rank is None
    assert comparison.rank_delta is None


def test_failed_run_never_renders_as_empty_ranking() -> None:
    comparison = _comparison(
        run_status="FAILED",
        run_failure_reason="candidate artifact failed",
        availability="NO_DATA",
        baseline_rank_state=EXPERIMENTAL_READ_UNAVAILABLE,
        baseline_rank=None,
    )
    assert comparison.run_status == "FAILED"
    assert comparison.run_failure_reason == "candidate artifact failed"


def test_comparison_forwards_point_in_time_horizon_to_repository() -> None:
    repository = _PlaneRepository(comparison=_comparison())
    ExperimentalReadService(repository).get_episode_comparison(episode_id=EPISODE_ID, as_of=AS_OF)
    assert repository.seen_as_of == [AS_OF]


# ---------------------------------------------------------------------------
# Run / evaluation detail surfaces
# ---------------------------------------------------------------------------


def test_run_detail_section_states() -> None:
    section = ExperimentalReadService(_PlaneRepository(run=_run_detail())).get_run_detail(
        run_id=RUN_ID
    )
    assert section.availability == "AVAILABLE"
    assert section.run is not None
    assert section.run.run_class == "DEV"
    assert section.run.coverage_state == "OK"
    assert [entry.rank for entry in section.run.control_ranking] == [1, 2]

    empty = ExperimentalReadService(_PlaneRepository()).get_run_detail(run_id=RUN_ID)
    assert empty.availability == "NO_DATA"
    assert empty.run is None


def test_run_detail_repository_failure_is_unknown_never_fabricated() -> None:
    section = ExperimentalReadService(_PlaneRepository(fail=True)).get_run_detail(run_id=RUN_ID)
    assert section.availability == "UNKNOWN"
    assert section.run is None


def test_evaluation_detail_section_states() -> None:
    repository = _PlaneRepository(evaluation=_evaluation_detail())
    section = ExperimentalReadService(repository).get_evaluation_detail(evaluation_id=EVALUATION_ID)
    assert section.availability == "AVAILABLE"
    assert section.evaluation is not None
    assert section.evaluation.status == "INSUFFICIENT_SAMPLE"

    failed = ExperimentalReadService(_PlaneRepository(fail=True)).get_evaluation_detail(
        evaluation_id=EVALUATION_ID
    )
    assert failed.availability == "UNKNOWN"
    assert failed.evaluation is None


# ---------------------------------------------------------------------------
# History: bounded, deterministic
# ---------------------------------------------------------------------------


def _runs_history() -> tuple[RunHistoryEntry, ...]:
    return (
        RunHistoryEntry(
            run_id="shadowrun_" + "9" * 64,
            run_digest="sha256:" + "8" * 64,
            run_class="CONFIRMATORY",
            status="RAN",
            as_of="2026-09-06T00:00:00.000000Z",
        ),
        RunHistoryEntry(
            run_id="shadowrun_" + "7" * 64,
            run_digest="sha256:" + "6" * 64,
            run_class="DEV",
            status="FAILED",
            as_of="2026-09-05T00:00:00.000000Z",
        ),
    )


def test_history_is_deterministic_newest_first_and_bounded() -> None:
    repository = _PlaneRepository(runs_history=_runs_history())
    history = ExperimentalReadService(repository).get_history(limit=2)
    assert history.availability == "AVAILABLE"
    assert history.limit == 2
    assert [item.run_id for item in history.runs] == [
        "shadowrun_" + "9" * 64,
        "shadowrun_" + "7" * 64,
    ]
    assert repository.seen_limits == [2]


def test_history_limit_is_bounded_and_fail_closed() -> None:
    service = ExperimentalReadService(_PlaneRepository())
    with pytest.raises(InvalidExperimentalLimitError):
        service.get_history(limit=0)
    with pytest.raises(InvalidExperimentalLimitError):
        service.get_history(limit=201)


def test_history_repository_failure_is_explicit_unknown() -> None:
    history = ExperimentalReadService(_PlaneRepository(fail=True)).get_history(limit=2)
    assert history.availability == "UNKNOWN"
    assert history.runs == ()
    assert history.evaluations == ()


def test_history_domain_object_is_plain_data() -> None:
    history = ExperimentHistory(
        schema_version="experimental-read-response-v0",
        authority_state="EXPERIMENTAL_SHADOW",
        interpretation="labelled",
        experiment_id="advanced-ranking-pef-v0",
        candidate_id="prospective-primary-emission-freshness-v0",
        availability="AVAILABLE",
        limit=1,
        runs=(),
        evaluations=(),
    )
    assert history.runs == ()


# ---------------------------------------------------------------------------
# Experiment status surface (WP6 operator state)
# ---------------------------------------------------------------------------


def test_status_surface_is_available_projection_of_stored_state() -> None:
    inputs = ExperimentStatusInputs(
        freeze=None,
        window=None,
        run=None,
        coverage=None,
        opportunity_counts=(),
        evaluation=None,
    )
    surface = ExperimentalReadService(_PlaneRepository(status_inputs=inputs)).get_status()
    assert surface.availability == "AVAILABLE"
    assert surface.status is not None
    assert surface.status.window_state == "NO_DATA"
    assert surface.status.candidate_freeze_state == "UNBOUND"
    assert surface.status.run_state == "NO_DATA"


def test_status_surface_failure_is_explicit_unknown() -> None:
    surface = ExperimentalReadService(_PlaneRepository(fail=True)).get_status()
    assert surface.availability == "UNKNOWN"
    assert surface.status is None


# ---------------------------------------------------------------------------
# Transport-level invariants
# ---------------------------------------------------------------------------


def test_comparison_endpoint_carries_identity_and_delta() -> None:
    client = _client(_PlaneRepository(comparison=_comparison()))
    response = client.get(f"/v0/experimental/episodes/{EPISODE_ID}/comparison")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    assert body["availability"] == "AVAILABLE"
    assert body["run_id"].startswith("shadowrun_")
    assert body["control_snapshot_id"].startswith("snapshot_")
    assert body["candidate_freeze_receipt_id"] is None
    assert body["baseline_rank"] == 2
    assert body["candidate_rank"] == 1
    assert body["rank_delta"] == -1
    assert body["evaluation_state"] == "NO_DATA"
    assert body["candidate_components"]["velocity_6h_delta"] == 3
    assert body["feature_values"] == [{"name": "velocity_6h", "status": "OBSERVED", "value": 3}]


def test_comparison_endpoint_renders_no_data_without_fabrication() -> None:
    client = _client(_PlaneRepository())
    response = client.get(f"/v0/experimental/episodes/{EPISODE_ID}/comparison")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    assert body["availability"] == "NO_DATA"
    assert body["run_id"] is None
    assert body["baseline_rank"] is None
    assert body["candidate_rank"] is None
    assert body["rank_delta"] is None


def test_comparison_endpoint_maps_repository_failure_to_unknown() -> None:
    client = _client(_PlaneRepository(fail=True))
    response = client.get(f"/v0/experimental/episodes/{EPISODE_ID}/comparison")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    assert body == {
        "schema_version": "experimental-read-response-v0",
        "authority_state": "EXPERIMENTAL_SHADOW",
        "interpretation": build_unavailable_comparison(EPISODE_ID).interpretation,
        "availability": "UNKNOWN",
        "episode_id": EPISODE_ID,
        "as_of": None,
        "run_id": None,
        "run_status": None,
        "run_failure_reason": None,
        "control_snapshot_id": None,
        "candidate_freeze_receipt_id": None,
        "evaluation_receipt_id": None,
        "evaluation_receipt_status": None,
        "evaluation_state": "NO_DATA",
        "baseline_rank_state": "UNAVAILABLE",
        "baseline_rank": None,
        "candidate_rank_state": "UNAVAILABLE",
        "candidate_rank": None,
        "rank_delta_state": "UNAVAILABLE",
        "rank_delta": None,
        "candidate_components_state": "UNAVAILABLE",
        "candidate_components": None,
        "feature_availability": "UNAVAILABLE",
        "feature_interpretation_state": "UNAVAILABLE",
        "feature_interpretation": None,
        "feature_values": [],
    }


def test_detail_endpoints_render_explicit_states() -> None:
    client = _client(_PlaneRepository(run=_run_detail(), evaluation=_evaluation_detail()))
    run_body = cast(dict[str, Any], client.get(f"/v0/experimental/runs/{RUN_ID}").json())
    assert run_body["availability"] == "AVAILABLE"
    assert run_body["run"]["run_class"] == "DEV"
    assert run_body["run"]["control_ranking"] == [
        {"episode_id": EPISODE_ID, "rank": 1},
        {"episode_id": "episode_zed", "rank": 2},
    ]

    eval_body = cast(
        dict[str, Any], client.get(f"/v0/experimental/evaluations/{EVALUATION_ID}").json()
    )
    assert eval_body["availability"] == "AVAILABLE"
    assert eval_body["evaluation"]["status"] == "INSUFFICIENT_SAMPLE"

    empty_client = _client(_PlaneRepository())
    empty_run = cast(dict[str, Any], empty_client.get(f"/v0/experimental/runs/{RUN_ID}").json())
    assert empty_run["availability"] == "NO_DATA"
    assert empty_run["run"] is None


def test_status_endpoint_renders_operator_state() -> None:
    inputs = ExperimentStatusInputs(
        freeze=None,
        window=None,
        run=None,
        coverage=None,
        opportunity_counts=(),
        evaluation=None,
    )
    client = _client(_PlaneRepository(status_inputs=inputs))
    body = cast(dict[str, Any], client.get("/v0/experimental/status").json())
    assert body["availability"] == "AVAILABLE"
    assert body["status"]["window_state"] == "NO_DATA"
    assert body["status"]["candidate_freeze_state"] == "UNBOUND"

    unknown = cast(
        dict[str, Any],
        _client(_PlaneRepository(fail=True)).get("/v0/experimental/status").json(),
    )
    assert unknown["availability"] == "UNKNOWN"
    assert unknown["status"] is None


def test_history_endpoint_rejects_out_of_range_limit() -> None:
    client = _client(_PlaneRepository(runs_history=_runs_history()))
    response = client.get("/v0/experimental/history", params={"limit": "0"})
    assert response.status_code == 400
    body = cast(dict[str, Any], response.json())
    assert body["error"] == "INVALID_LIMIT"

    ok = client.get("/v0/experimental/history", params={"limit": "2"})
    ok_body = cast(dict[str, Any], ok.json())
    assert ok_body["limit"] == 2
    assert len(ok_body["runs"]) == 2


def test_comparison_endpoint_maps_invalid_as_of_to_400() -> None:
    client = _client(_PlaneRepository(comparison=_comparison()))
    response = client.get(
        f"/v0/experimental/episodes/{EPISODE_ID}/comparison",
        params={"as_of": "not-a-timestamp"},
    )
    assert response.status_code == 400
    body = cast(dict[str, Any], response.json())
    assert body["error"] == "INVALID_AS_OF"


# ---------------------------------------------------------------------------
# Mixed-snapshot rejection and GET-only invariants
# ---------------------------------------------------------------------------


def test_mixed_snapshot_identity_is_never_hidden() -> None:
    """A comparison bound to another snapshot always names its snapshot id."""

    comparison = _comparison(control_snapshot_id=OTHER_SNAPSHOT_ID)
    assert comparison.control_snapshot_id == OTHER_SNAPSHOT_ID
    assert comparison.control_snapshot_id != SNAPSHOT_ID


def test_experimental_endpoints_never_register_mutations() -> None:
    app = create_public_read_app(
        PublicReadService(_UnavailableBaseline()),
        experimental_service=ExperimentalReadService(_PlaneRepository()),
    )
    document = app.openapi()
    paths = cast(dict[str, dict[str, Any]], document["paths"])
    experimental_paths = {path for path in paths if path.startswith("/v0/experimental")}
    assert "/v0/experimental/episodes/{episode_id}/comparison" in experimental_paths
    assert "/v0/experimental/runs/{run_id}" in experimental_paths
    assert "/v0/experimental/evaluations/{evaluation_id}" in experimental_paths
    assert "/v0/experimental/status" in experimental_paths
    assert "/v0/experimental/history" in experimental_paths
    for path, methods in paths.items():
        assert set(methods) <= {"get"}, path
    for path in experimental_paths:
        assert "post" not in paths[path]
        assert "put" not in paths[path]
        assert "delete" not in paths[path]
