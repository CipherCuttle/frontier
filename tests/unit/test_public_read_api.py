from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from frontier.adapters.api.public_read import create_public_read_app
from frontier.application.public_read import PublicReadService
from frontier.domain.canonical_json import CanonicalValue
from frontier.domain.public_read import (
    NoCompleteSnapshotError,
    ObservationEvidenceRead,
    ResolvedPublicSnapshot,
    SnapshotBinding,
    SourceHealthRead,
)


class _GetClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Response: ...


def _snapshot() -> ResolvedPublicSnapshot:
    binding = SnapshotBinding(
        snapshot_id="snapshot_" + "1" * 64,
        receipt_id="receipt_" + "2" * 64,
        receipt_schema_version="projection-receipt-v1",
        projection_name="baseline-intelligence",
        projection_version="baseline-intelligence-v0",
        schema_version="baseline-intelligence-snapshot-v0",
        algorithm_version="windowed-episode-metrics-v0",
        ranking_policy_version="naive-episode-activity-v0",
        configuration_digest="sha256:" + "3" * 64,
        source_registry_version="sha256:" + "4" * 64,
        as_of="2026-09-05T12:00:00.000000Z",
        input_digest="sha256:" + "5" * 64,
        output_digest="sha256:" + "6" * 64,
    )
    episode = cast(
        dict[str, CanonicalValue],
        {
            "acceleration_6h": 1,
            "age_seconds": 60,
            "backfill_evidence_count": 0,
            "confirmation": "UNAVAILABLE",
            "episode_id": "episode_" + "a" * 64,
            "evidence_count_total": 1,
            "evidence_root_diversity": None,
            "first_observed_at": "2026-09-05T11:59:00.000000Z",
            "last_observed_at": "2026-09-05T11:59:00.000000Z",
            "mentions_1h": 1,
            "mentions_24h": 1,
            "mentions_6h": 1,
            "observation_ids": ["obs_" + "b" * 64],
            "preprevious_6h": 0,
            "previous_6h": 0,
            "prospective_evidence_count": 1,
            "rank": 1,
            "recovered_backlog_evidence_count": 0,
            "signal_roles": ["ATTENTION"],
            "source_count": 1,
            "source_ids": ["hn.frontpage"],
            "source_role_diversity": 1,
            "velocity_6h_delta": 1,
        },
    )
    return ResolvedPublicSnapshot(
        binding=binding,
        generated_at="2026-09-05T12:00:01.000000Z",
        transport_state="OK",
        freshness_state="DEGRADED",
        coverage_state="UNKNOWN",
        schema_state="OK",
        episodes=(episode,),
    )


class _FakeRepository:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot:
        if not self.available:
            raise NoCompleteSnapshotError("fixture")
        return _snapshot()

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]:
        return []

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None:
        return None

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]:
        return []


def test_openapi_exposes_only_get_operations() -> None:
    app = create_public_read_app(PublicReadService(_FakeRepository()))
    document = app.openapi()
    paths = cast(dict[str, dict[str, Any]], document["paths"])
    methods = {method.upper() for path_item in paths.values() for method in path_item}
    assert methods == {"GET"}
    assert set(paths) == {
        "/v0/meta",
        "/v0/radar",
        "/v0/now",
        "/v0/trending",
        "/v0/episodes/{episode_id}",
        "/v0/observations/{observation_id}",
        "/v0/health",
    }


def test_view_exposes_binding_health_and_baseline_semantic_scope() -> None:
    client = cast(
        _GetClient,
        TestClient(create_public_read_app(PublicReadService(_FakeRepository()))),
    )
    response = client.get("/v0/now")
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    snapshot = cast(dict[str, Any], body["snapshot"])
    items = cast(list[dict[str, Any]], body["items"])
    assert body["schema_version"] == "public-read-response-v0"
    assert snapshot["projection_version"] == "baseline-intelligence-v0"
    assert body["freshness_state"] == "DEGRADED"
    assert body["coverage_state"] == "UNKNOWN"
    assert body["semantic_scope"] == "BASELINE_SUBSTRATE"
    assert items[0]["rank"] == 1
    assert items[0]["confirmation"] == "UNAVAILABLE"


def test_no_complete_snapshot_is_explicit_503_without_internal_detail() -> None:
    client = cast(
        _GetClient,
        TestClient(
            create_public_read_app(PublicReadService(_FakeRepository(available=False)))
        ),
    )
    response = client.get("/v0/radar")
    assert response.status_code == 503
    assert cast(dict[str, Any], response.json()) == {
        "error": "NO_COMPLETE_SNAPSHOT",
        "detail": "No publishable COMPLETE baseline snapshot is available.",
    }
