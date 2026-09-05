from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical_json import CanonicalValue

PUBLIC_READ_API_VERSION = "public-read-api-v0"
PUBLIC_READ_RESPONSE_SCHEMA = "public-read-response-v0"
PUBLIC_READ_VIEW_POLICY_VERSION = "baseline-read-views-v0"
PUBLIC_READ_SEMANTIC_SCOPE = "BASELINE_SUBSTRATE"
PUBLIC_READ_DEFAULT_LIMIT = 50
PUBLIC_READ_MAX_LIMIT = 100


class PublicReadFailure(RuntimeError):
    code: str


class NoCompleteSnapshotError(PublicReadFailure):
    code = "NO_COMPLETE_SNAPSHOT"


class SnapshotNotFoundError(PublicReadFailure):
    code = "SNAPSHOT_NOT_FOUND"


class SnapshotIntegrityError(PublicReadFailure):
    code = "SNAPSHOT_INTEGRITY_FAILURE"


class EpisodeNotFoundError(PublicReadFailure):
    code = "EPISODE_NOT_FOUND"


class ObservationNotFoundError(PublicReadFailure):
    code = "OBSERVATION_NOT_FOUND"


class PublicViewKind(StrEnum):
    RADAR = "RADAR"
    NOW = "NOW"
    TRENDING = "TRENDING"


@dataclass(frozen=True, slots=True)
class SnapshotBinding:
    snapshot_id: str
    receipt_id: str
    receipt_schema_version: str
    projection_name: str
    projection_version: str
    schema_version: str
    algorithm_version: str
    ranking_policy_version: str
    configuration_digest: str
    source_registry_version: str
    as_of: str
    input_digest: str
    output_digest: str


@dataclass(frozen=True, slots=True)
class ResolvedPublicSnapshot:
    binding: SnapshotBinding
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    episodes: tuple[dict[str, CanonicalValue], ...]


@dataclass(frozen=True, slots=True)
class PublicViewPage:
    snapshot: SnapshotBinding
    generated_at: str
    view: PublicViewKind
    view_policy_version: str
    semantic_scope: str
    total: int
    limit: int
    offset: int
    items: tuple[dict[str, CanonicalValue], ...]


@dataclass(frozen=True, slots=True)
class CollectionOccurrenceRead:
    run_id: str
    reason: str
    trigger_id: str | None
    recovered_after_gap: bool
    occurrence_status: str
    started_at: str
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class ObservationRelationRead:
    relation_id: str
    relation_type: str
    from_observation_id: str
    target_observation_id: str | None
    target_external_ref: str | None
    authority: str
    algorithm_version: str | None
    confidence: str | None
    evidence: dict[str, CanonicalValue]


@dataclass(frozen=True, slots=True)
class ObservationEvidenceRead:
    observation_id: str
    schema_version: str
    canonicalization_version: str
    source_id: str
    source_item_key: str
    kind: str
    payload: dict[str, CanonicalValue]
    source_published_at: str | None
    effective_at: str | None
    observed_at: str
    retrieved_at: str
    content_digest: str
    fetch_digest: str
    collection_occurrences: tuple[CollectionOccurrenceRead, ...]
    relations: tuple[ObservationRelationRead, ...]


@dataclass(frozen=True, slots=True)
class EpisodeEvidenceRead:
    snapshot: SnapshotBinding
    generated_at: str
    episode: dict[str, CanonicalValue]
    observations: tuple[ObservationEvidenceRead, ...]


@dataclass(frozen=True, slots=True)
class ObservationResponseRead:
    snapshot: SnapshotBinding
    generated_at: str
    observation: ObservationEvidenceRead


@dataclass(frozen=True, slots=True)
class SourceHealthRead:
    source_id: str
    as_of: str
    transport: str
    freshness: str
    completeness: str
    schema: str
    details: dict[str, CanonicalValue]


@dataclass(frozen=True, slots=True)
class PublicHealthRead:
    snapshot: SnapshotBinding
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    sources: tuple[SourceHealthRead, ...]


def _episode_int(episode: dict[str, CanonicalValue], field: str) -> int:
    value = episode.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotIntegrityError(f"baseline episode field {field} is not an integer")
    return value


def _ordered_episodes(
    episodes: tuple[dict[str, CanonicalValue], ...],
) -> tuple[dict[str, CanonicalValue], ...]:
    seen_ids: set[str] = set()
    seen_ranks: set[int] = set()
    indexed: list[tuple[int, dict[str, CanonicalValue]]] = []
    for episode in episodes:
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise SnapshotIntegrityError("baseline episode missing episode_id")
        rank = _episode_int(episode, "rank")
        if rank < 1:
            raise SnapshotIntegrityError("baseline episode rank must be positive")
        if episode_id in seen_ids or rank in seen_ranks:
            raise SnapshotIntegrityError("baseline snapshot contains duplicate episode id/rank")
        seen_ids.add(episode_id)
        seen_ranks.add(rank)
        indexed.append((rank, episode))
    indexed.sort(key=lambda item: item[0])
    if indexed and [rank for rank, _ in indexed] != list(range(1, len(indexed) + 1)):
        raise SnapshotIntegrityError("baseline episode ranks must be contiguous")
    return tuple(episode for _, episode in indexed)


def select_public_view(
    snapshot: ResolvedPublicSnapshot,
    *,
    view: PublicViewKind,
    limit: int = PUBLIC_READ_DEFAULT_LIMIT,
    offset: int = 0,
) -> PublicViewPage:
    if limit < 1 or limit > PUBLIC_READ_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {PUBLIC_READ_MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    ordered = _ordered_episodes(snapshot.episodes)
    if view is PublicViewKind.RADAR:
        filtered = ordered
    elif view is PublicViewKind.NOW:
        filtered = tuple(item for item in ordered if _episode_int(item, "mentions_1h") > 0)
    else:
        filtered = tuple(
            item for item in ordered if _episode_int(item, "velocity_6h_delta") > 0
        )

    return PublicViewPage(
        snapshot=snapshot.binding,
        generated_at=snapshot.generated_at,
        view=view,
        view_policy_version=PUBLIC_READ_VIEW_POLICY_VERSION,
        semantic_scope=PUBLIC_READ_SEMANTIC_SCOPE,
        total=len(filtered),
        limit=limit,
        offset=offset,
        items=filtered[offset : offset + limit],
    )


def find_episode(
    snapshot: ResolvedPublicSnapshot, episode_id: str
) -> dict[str, CanonicalValue]:
    for episode in _ordered_episodes(snapshot.episodes):
        if episode.get("episode_id") == episode_id:
            return episode
    raise EpisodeNotFoundError(episode_id)


def episode_observation_ids(episode: dict[str, CanonicalValue]) -> tuple[str, ...]:
    raw = episode.get("observation_ids")
    if not isinstance(raw, list):
        raise SnapshotIntegrityError("baseline episode observation_ids is not a list")
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise SnapshotIntegrityError("baseline episode contains invalid observation id")
        result.append(item)
    if len(result) != len(set(result)):
        raise SnapshotIntegrityError("baseline episode contains duplicate observation id")
    return tuple(result)
