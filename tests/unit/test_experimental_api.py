from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from frontier.adapters.api.public_read import create_public_read_app
from frontier.application.experimental_read import ExperimentalReadService
from frontier.application.public_read import PublicReadService
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.experimental_read import (
    AnalysisArtifactSummary,
    FeatureBatchSummary,
    PefArtifactSummary,
    ShadowRunSummary,
)

EXPERIMENTAL_TEST_AS_OF = "2026-09-05T12:00:00.000000Z"
AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


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
        as_of=EXPERIMENTAL_TEST_AS_OF,
        generated_at=EXPERIMENTAL_TEST_AS_OF,
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
        as_of=EXPERIMENTAL_TEST_AS_OF,
        generated_at=EXPERIMENTAL_TEST_AS_OF,
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
        as_of=EXPERIMENTAL_TEST_AS_OF,
        generated_at=EXPERIMENTAL_TEST_AS_OF,
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
        as_of=EXPERIMENTAL_TEST_AS_OF,
        generated_at=EXPERIMENTAL_TEST_AS_OF,
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


FORBIDDEN_RESPONSE_KEY_FRAGMENTS = (
    "score",
    "confidence",
    "confirmation",
    "truth",
    "independent",
    "verdict_origin",
    "manipulation_verdict",
)

EXPERIMENTAL_PATHS = {
    "/v0/experimental/overview",
    "/v0/experimental/shadow-runs",
    "/v0/experimental/pef-artifacts",
    "/v0/experimental/evaluation-receipts",
    "/v0/experimental/feature-batches",
    "/v0/experimental/analysis/{kind}",
}


class _GetClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Response: ...


class _FakeBaselineRepository:
    def resolve_snapshot(self, snapshot_id: str | None = None) -> Any:
        raise RuntimeError("baseline unavailable in this fixture")

    def list_observations(self, observation_ids: tuple[str, ...], *, as_of: datetime) -> list[Any]:
        return []

    def get_observation(self, observation_id: str, *, as_of: datetime) -> Any:
        return None

    def list_source_health(self, *, as_of: datetime) -> list[Any]:
        return []


class _FakeExperimentalRepository:
    def __init__(self, *, populated: bool = True, fail: bool = False) -> None:
        self.populated = populated
        self.fail = fail
        self.seen_as_of: list[datetime | None] = []

    def latest_shadow_run(self, *, as_of: datetime | None = None) -> Any:
        self.seen_as_of.append(as_of)
        if self.fail:
            raise RuntimeError("database unavailable")
        return _shadow_run_summary() if self.populated else None

    def latest_pef_artifact(self, *, as_of: datetime | None = None) -> Any:
        if self.fail:
            raise RuntimeError("database unavailable")
        return _pef_artifact_summary() if self.populated else None

    def latest_evaluation_receipt(self, *, as_of: datetime | None = None) -> Any:
        if self.fail:
            raise RuntimeError("database unavailable")
        return None

    def latest_feature_batch(self, *, as_of: datetime | None = None) -> Any:
        if self.fail:
            raise RuntimeError("database unavailable")
        return _feature_batch_summary() if self.populated else None

    def latest_analysis_artifacts(
        self, *, as_of: datetime | None = None
    ) -> dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]:
        if self.fail:
            raise RuntimeError("database unavailable")
        if not self.populated:
            return {}
        return {
            ExperimentalAnalysisKind.CORROBORATION: _analysis_summary(
                ExperimentalAnalysisKind.CORROBORATION
            )
        }


def _client(repository: _FakeExperimentalRepository) -> _GetClient:
    return cast(
        _GetClient,
        TestClient(
            create_public_read_app(
                PublicReadService(_FakeBaselineRepository()),
                experimental_service=ExperimentalReadService(repository),
            )
        ),
    )


def _assert_no_forbidden_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            lowered = str(key).lower()
            assert not any(fragment in lowered for fragment in FORBIDDEN_RESPONSE_KEY_FRAGMENTS), (
                f"forbidden key leaked: {key}"
            )
            _assert_no_forbidden_keys(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            _assert_no_forbidden_keys(item)


def test_overview_is_experimental_shadow_labelled_with_visible_identity() -> None:
    client = _client(_FakeExperimentalRepository())
    response = client.get("/v0/experimental/overview")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    _assert_no_forbidden_keys(body)
    assert body["schema_version"] == "experimental-read-response-v0"
    assert body["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert body["experiment_id"] == "advanced-ranking-pef-v0"
    assert body["candidate_id"] == "prospective-primary-emission-freshness-v0"
    assert body["configuration_digest"].startswith("sha256:")
    assert body["as_of"] == "2026-09-05T12:00:00.000000Z"
    assert body["availability"]["shadow_run"] == "AVAILABLE"
    assert body["availability"]["evaluation_receipt"] == "NO_DATA"
    assert body["availability"]["analysis:CORROBORATION"] == "AVAILABLE"
    run = cast(dict[str, Any], body["latest_shadow_run"])
    assert run["run_id"].startswith("shadowrun_")
    assert run["run_digest"].startswith("sha256:")
    assert run["status"] == "RAN"
    assert run["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert run["candidate_artifact_id"].startswith("artifact_")
    assert run["control_snapshot_id"].startswith("snapshot_")
    assert run["control_receipt_id"].startswith("receipt_")
    analysis = cast(dict[str, Any], body["analysis_artifacts"])
    assert analysis["CORROBORATION"]["analysis_id"].startswith("expanalysis_")


def test_no_scalar_score_or_truth_keys_leak_into_responses() -> None:
    client = _client(_FakeExperimentalRepository())
    for path in (
        "/v0/experimental/overview",
        "/v0/experimental/shadow-runs",
        "/v0/experimental/pef-artifacts",
        "/v0/experimental/evaluation-receipts",
        "/v0/experimental/feature-batches",
        "/v0/experimental/analysis/CORROBORATION",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        _assert_no_forbidden_keys(response.json())


def test_empty_repository_returns_explicit_no_data_never_fabricated() -> None:
    client = _client(_FakeExperimentalRepository(populated=False))
    response = client.get("/v0/experimental/overview")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    _assert_no_forbidden_keys(body)
    assert body["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert body["as_of"] == "UNKNOWN"
    for section in (
        "shadow_run",
        "pef_artifact",
        "evaluation_receipt",
        "feature_batch",
    ):
        assert body["availability"][section] == "NO_DATA"
        assert body[_section_mapping(section)] is None
    assert body["analysis_artifacts"] == {}
    assert all(state == "NO_DATA" for state in body["availability"].values())


def _section_mapping(section: str) -> str:
    return {
        "shadow_run": "latest_shadow_run",
        "pef_artifact": "latest_pef_artifact",
        "evaluation_receipt": "latest_evaluation_receipt",
        "feature_batch": "latest_feature_batch",
    }[section]


def test_repository_failure_returns_explicit_unknown_status() -> None:
    client = _client(_FakeExperimentalRepository(fail=True))
    response = client.get("/v0/experimental/overview")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    _assert_no_forbidden_keys(body)
    assert all(state == "UNKNOWN" for state in body["availability"].values())
    assert body["latest_shadow_run"] is None


def test_section_endpoints_carry_labelling_and_availability() -> None:
    client = _client(_FakeExperimentalRepository())
    runs = cast(dict[str, Any], client.get("/v0/experimental/shadow-runs").json())
    _assert_no_forbidden_keys(runs)
    assert runs["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert runs["availability"] == "AVAILABLE"
    assert cast(dict[str, Any], runs["latest"])["run_id"].startswith("shadowrun_")

    empty = cast(
        dict[str, Any],
        client.get("/v0/experimental/analysis/GROUPING_HYPOTHESES").json(),
    )
    _assert_no_forbidden_keys(empty)
    assert empty["availability"] == "NO_DATA"
    assert empty["latest"] is None


def test_invalid_as_of_and_kind_are_explicit_400_errors() -> None:
    client = _client(_FakeExperimentalRepository())
    bad_as_of = client.get("/v0/experimental/overview", params={"as_of": "not-a-timestamp"})
    assert bad_as_of.status_code == 400
    assert cast(dict[str, Any], bad_as_of.json())["error"] == "INVALID_AS_OF"

    bad_kind = client.get("/v0/experimental/analysis/NOT_A_KIND")
    assert bad_kind.status_code == 400
    assert cast(dict[str, Any], bad_kind.json())["error"] == "INVALID_ANALYSIS_KIND"


def test_as_of_horizon_is_forwarded_to_the_repository() -> None:
    repository = _FakeExperimentalRepository()
    client = _client(repository)
    response = client.get(
        "/v0/experimental/overview",
        params={"as_of": "2026-09-05T12:00:00.000000Z"},
    )
    assert response.status_code == 200
    assert repository.seen_as_of == [AS_OF]


def test_experimental_openapi_paths_are_get_only_and_namespaced() -> None:
    app = create_public_read_app(
        PublicReadService(_FakeBaselineRepository()),
        experimental_service=ExperimentalReadService(_FakeExperimentalRepository()),
    )
    document = app.openapi()
    paths = cast(dict[str, dict[str, Any]], document["paths"])
    experimental_paths = {path for path in paths if path.startswith("/v0/experimental")}
    assert experimental_paths >= EXPERIMENTAL_PATHS
    for path, methods in paths.items():
        assert set(methods) <= {"get"}
        if path in EXPERIMENTAL_PATHS:
            operation = methods["get"]
            assert "Experimental" in str(operation.get("operationId"))
