from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from frontier.application.public_read import PublicReadService
from frontier.domain.canonical_json import CanonicalValue
from frontier.domain.public_read import (
    EvidenceQueryInvalidError,
    ObservationEvidenceRead,
    PublicViewKind,
    ResolvedPublicSnapshot,
    SnapshotBinding,
    SnapshotIntegrityError,
    SourceHealthRead,
    normalize_evidence_query,
    select_public_view,
)


def _binding() -> SnapshotBinding:
    return SnapshotBinding(
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


def _episode(
    episode_id: str,
    rank: int,
    *,
    mentions_1h: int = 0,
    velocity_6h_delta: int = 0,
    observation_ids: list[str] | None = None,
) -> dict[str, CanonicalValue]:
    return cast(
        dict[str, CanonicalValue],
        {
            "episode_id": episode_id,
            "rank": rank,
            "mentions_1h": mentions_1h,
            "velocity_6h_delta": velocity_6h_delta,
            "observation_ids": observation_ids or [],
            "confirmation": "UNAVAILABLE",
            "evidence_root_diversity": None,
        },
    )


def _snapshot(*episodes: dict[str, CanonicalValue]) -> ResolvedPublicSnapshot:
    return ResolvedPublicSnapshot(
        binding=_binding(),
        generated_at="2026-09-05T12:00:01.000000Z",
        transport_state="OK",
        freshness_state="OK",
        coverage_state="DEGRADED",
        schema_state="OK",
        episodes=tuple(episodes),
    )


def test_radar_orders_by_existing_baseline_rank_without_renumbering() -> None:
    page = select_public_view(
        _snapshot(
            _episode("episode-c", 3),
            _episode("episode-a", 1),
            _episode("episode-b", 2),
        ),
        view=PublicViewKind.RADAR,
    )
    assert [item["episode_id"] for item in page.items] == [
        "episode-a",
        "episode-b",
        "episode-c",
    ]
    assert [item["rank"] for item in page.items] == [1, 2, 3]
    assert page.semantic_scope == "BASELINE_SUBSTRATE"
    assert page.coverage_state == "DEGRADED"


def test_now_and_trending_filter_without_reranking() -> None:
    snapshot = _snapshot(
        _episode("episode-a", 1, mentions_1h=0, velocity_6h_delta=0),
        _episode("episode-b", 2, mentions_1h=1, velocity_6h_delta=3),
        _episode("episode-c", 3, mentions_1h=4, velocity_6h_delta=-1),
        _episode("episode-d", 4, mentions_1h=0, velocity_6h_delta=1),
    )
    now = select_public_view(snapshot, view=PublicViewKind.NOW)
    trending = select_public_view(snapshot, view=PublicViewKind.TRENDING)
    assert [item["rank"] for item in now.items] == [2, 3]
    assert [item["rank"] for item in trending.items] == [2, 4]
    assert all(item["confirmation"] == "UNAVAILABLE" for item in now.items)


def test_filtering_happens_before_pagination() -> None:
    snapshot = _snapshot(
        _episode("episode-a", 1, mentions_1h=0),
        _episode("episode-b", 2, mentions_1h=1),
        _episode("episode-c", 3, mentions_1h=1),
        _episode("episode-d", 4, mentions_1h=1),
    )
    page = select_public_view(snapshot, view=PublicViewKind.NOW, limit=1, offset=1)
    assert page.total == 3
    assert [item["rank"] for item in page.items] == [3]


def test_duplicate_or_noncontiguous_baseline_ranks_fail_closed() -> None:
    with pytest.raises(SnapshotIntegrityError):
        select_public_view(
            _snapshot(_episode("episode-a", 1), _episode("episode-b", 1)),
            view=PublicViewKind.RADAR,
        )
    with pytest.raises(SnapshotIntegrityError):
        select_public_view(
            _snapshot(_episode("episode-a", 1), _episode("episode-c", 3)),
            view=PublicViewKind.RADAR,
        )


class _MembershipRepository:
    def __init__(self, returned_ids: tuple[str, ...]) -> None:
        self.returned_ids = returned_ids
        self.snapshot = _snapshot(
            _episode(
                "episode-a",
                1,
                observation_ids=["obs_" + "a" * 64, "obs_" + "b" * 64],
            )
        )

    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot:
        return self.snapshot

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]:
        assert as_of == datetime(2026, 9, 5, 12, tzinfo=UTC)
        return [self._observation(observation_id) for observation_id in self.returned_ids]

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None:
        return self._observation(observation_id)

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]:
        return []

    def _observation(self, observation_id: str) -> ObservationEvidenceRead:
        return ObservationEvidenceRead(
            observation_id=observation_id,
            schema_version="observation-v1",
            canonicalization_version="frontier-canonical-json-v1",
            source_id="fixture.source",
            source_item_key=observation_id,
            kind="DOCUMENT",
            payload={},
            source_published_at=None,
            effective_at=None,
            observed_at="2026-09-05T11:00:00.000000Z",
            retrieved_at="2026-09-05T11:00:00.000000Z",
            content_digest="sha256:" + "7" * 64,
            fetch_digest="sha256:" + "8" * 64,
            collection_occurrences=(),
            relations=(),
        )


def test_episode_drilldown_requires_exact_membership() -> None:
    expected = ("obs_" + "a" * 64, "obs_" + "b" * 64)
    value = PublicReadService(_MembershipRepository(expected)).get_episode("episode-a")
    assert tuple(item.observation_id for item in value.observations) == expected

    extra = (*expected, "obs_" + "c" * 64)
    with pytest.raises(SnapshotIntegrityError, match="exactly match"):
        PublicReadService(_MembershipRepository(extra)).get_episode("episode-a")


class _QueryRepository:
    def __init__(self, *, returned_ids: tuple[str, ...] | None = None) -> None:
        self.ids = tuple("obs_" + char * 64 for char in "abcd")
        self.snapshot = _snapshot(
            _episode("episode-a", 1, observation_ids=[self.ids[0]]),
            _episode("episode-b", 2, observation_ids=[self.ids[1], self.ids[2]]),
            _episode("episode-c", 3, observation_ids=[self.ids[3]]),
        )
        self.returned_ids = returned_ids or self.ids

    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot:
        return self.snapshot

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]:
        assert observation_ids == self.ids
        assert as_of == datetime(2026, 9, 5, 12, tzinfo=UTC)
        return [self._observation(observation_id) for observation_id in self.returned_ids]

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None:
        return self._observation(observation_id)

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]:
        return []

    def _observation(self, observation_id: str) -> ObservationEvidenceRead:
        index = self.ids.index(observation_id) if observation_id in self.ids else -1
        payloads: list[dict[str, CanonicalValue]] = [
            {"title": "Frontier Agent needle", "secretword": "benign", "count": 12345},
            {"left": "alpha needle"},
            {"right": "beta"},
            {"title": "needle needle needle"},
        ]
        source_item_keys = ["item-a", "item-b", "item-c", "special-item-key"]
        kinds = ["DOCUMENT", "DOCUMENT", "DOCUMENT", "SPECIAL_KIND"]
        return ObservationEvidenceRead(
            observation_id=observation_id,
            schema_version="observation-v1",
            canonicalization_version="frontier-canonical-json-v1",
            source_id="fixture.source",
            source_item_key=source_item_keys[index] if index >= 0 else "outside-item",
            kind=kinds[index] if index >= 0 else "DOCUMENT",
            payload=payloads[index] if index >= 0 else {"title": "outside needle"},
            source_published_at=None,
            effective_at=None,
            observed_at="2026-09-05T11:00:00.000000Z",
            retrieved_at="2026-09-05T11:00:00.000000Z",
            content_digest="sha256:" + "7" * 64,
            fetch_digest="sha256:" + "8" * 64,
            collection_occurrences=(),
            relations=(),
        )


def test_evidence_query_normalizes_casefold_and_deduplicates_tokens() -> None:
    assert normalize_evidence_query("  Alpha alpha BETA beta  ") == ("alpha", "beta")
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query("   ")
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query(" ".join(f"t{index}" for index in range(13)))
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query("x" * 257)


def test_evidence_query_matches_only_authorized_string_values_and_and_spans_observations() -> None:
    service = PublicReadService(_QueryRepository())
    page = service.search_evidence("frontier AGENT")
    assert page.normalized_tokens == ("frontier", "agent")
    assert [item.episode["rank"] for item in page.items] == [1]

    cross_observation = service.search_evidence("alpha beta")
    assert [item.episode["rank"] for item in cross_observation.items] == [2]
    assert cross_observation.items[0].matched_observation_ids == tuple(
        "obs_" + char * 64 for char in "bc"
    )

    assert service.search_evidence("secretword").total == 0
    assert service.search_evidence("12345").total == 0
    assert service.search_evidence("fixture.source").total == 0
    assert service.search_evidence("special-item-key").total == 1
    assert service.search_evidence("special_kind").total == 1


def test_evidence_query_preserves_baseline_order_and_filters_before_pagination() -> None:
    service = PublicReadService(_QueryRepository())
    page = service.search_evidence("needle", limit=1, offset=1)
    assert page.total == 3
    assert [item.episode["rank"] for item in page.items] == [2]
    assert page.query_policy_version == "evidence-query-lexical-filter-v0"
    assert page.semantic_scope == "BASELINE_SUBSTRATE_QUERY"


def test_evidence_query_requires_exact_snapshot_observation_membership() -> None:
    expected = tuple("obs_" + char * 64 for char in "abcd")
    with pytest.raises(SnapshotIntegrityError, match="exactly match"):
        PublicReadService(_QueryRepository(returned_ids=expected[:-1])).search_evidence("needle")
    with pytest.raises(SnapshotIntegrityError, match="duplicate"):
        PublicReadService(_QueryRepository(returned_ids=(*expected, expected[0]))).search_evidence(
            "needle"
        )
