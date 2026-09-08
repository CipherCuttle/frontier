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
EVIDENCE_QUERY_POLICY_VERSION = "evidence-query-lexical-filter-v0"
EVIDENCE_QUERY_SEMANTIC_SCOPE = "BASELINE_SUBSTRATE_QUERY"
EVIDENCE_QUERY_MAX_CODEPOINTS = 256
EVIDENCE_QUERY_MAX_TOKENS = 12


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


class EvidenceQueryInvalidError(PublicReadFailure):
    code = "INVALID_QUERY"


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
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
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


@dataclass(frozen=True, slots=True)
class EvidenceQueryItem:
    episode: dict[str, CanonicalValue]
    matched_observation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceQueryPage:
    snapshot: SnapshotBinding
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    query_policy_version: str
    semantic_scope: str
    query: str
    normalized_tokens: tuple[str, ...]
    total: int
    limit: int
    offset: int
    items: tuple[EvidenceQueryItem, ...]


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
        filtered = tuple(item for item in ordered if _episode_int(item, "velocity_6h_delta") > 0)

    return PublicViewPage(
        snapshot=snapshot.binding,
        generated_at=snapshot.generated_at,
        transport_state=snapshot.transport_state,
        freshness_state=snapshot.freshness_state,
        coverage_state=snapshot.coverage_state,
        schema_state=snapshot.schema_state,
        view=view,
        view_policy_version=PUBLIC_READ_VIEW_POLICY_VERSION,
        semantic_scope=PUBLIC_READ_SEMANTIC_SCOPE,
        total=len(filtered),
        limit=limit,
        offset=offset,
        items=filtered[offset : offset + limit],
    )


def find_episode(snapshot: ResolvedPublicSnapshot, episode_id: str) -> dict[str, CanonicalValue]:
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


def normalize_evidence_query(query: str) -> tuple[str, ...]:
    trimmed = query.strip()
    if not trimmed or len(trimmed) > EVIDENCE_QUERY_MAX_CODEPOINTS:
        raise EvidenceQueryInvalidError("query length is outside the frozen bounds")
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in trimmed.split():
        token = raw_token.casefold()
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    if not tokens or len(tokens) > EVIDENCE_QUERY_MAX_TOKENS:
        raise EvidenceQueryInvalidError("query token count is outside the frozen bounds")
    return tuple(tokens)


def _append_payload_string_leaves(value: CanonicalValue, result: list[str]) -> None:
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, list):
        for item in value:
            _append_payload_string_leaves(item, result)
    elif isinstance(value, dict):
        for item in value.values():
            _append_payload_string_leaves(item, result)


def _observation_token_hits(
    observation: ObservationEvidenceRead,
    normalized_tokens: tuple[str, ...],
) -> frozenset[str]:
    searchable = [observation.source_item_key, observation.kind]
    _append_payload_string_leaves(observation.payload, searchable)
    folded = tuple(value.casefold() for value in searchable)
    return frozenset(
        token for token in normalized_tokens if any(token in value for value in folded)
    )


def evidence_query_snapshot_observation_ids(
    snapshot: ResolvedPublicSnapshot,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for episode in _ordered_episodes(snapshot.episodes):
        for observation_id in episode_observation_ids(episode):
            if observation_id not in seen:
                seen.add(observation_id)
                result.append(observation_id)
    return tuple(result)


def select_evidence_query(
    snapshot: ResolvedPublicSnapshot,
    observations_by_id: dict[str, ObservationEvidenceRead],
    *,
    query: str,
    normalized_tokens: tuple[str, ...],
    limit: int = PUBLIC_READ_DEFAULT_LIMIT,
    offset: int = 0,
) -> EvidenceQueryPage:
    expected_tokens = normalize_evidence_query(query)
    if normalized_tokens != expected_tokens:
        raise EvidenceQueryInvalidError("normalized query tokens do not match query")
    if limit < 1 or limit > PUBLIC_READ_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {PUBLIC_READ_MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    expected_observation_ids = evidence_query_snapshot_observation_ids(snapshot)
    if set(observations_by_id) != set(expected_observation_ids):
        raise SnapshotIntegrityError(
            "query evidence does not exactly match snapshot observation membership"
        )

    matches: list[EvidenceQueryItem] = []
    for episode in _ordered_episodes(snapshot.episodes):
        member_ids = episode_observation_ids(episode)
        covered_tokens: set[str] = set()
        matched_ids: list[str] = []
        for observation_id in member_ids:
            observation = observations_by_id[observation_id]
            hits = _observation_token_hits(observation, normalized_tokens)
            if hits:
                matched_ids.append(observation_id)
                covered_tokens.update(hits)
        if all(token in covered_tokens for token in normalized_tokens):
            matches.append(
                EvidenceQueryItem(
                    episode=episode,
                    matched_observation_ids=tuple(matched_ids),
                )
            )

    return EvidenceQueryPage(
        snapshot=snapshot.binding,
        generated_at=snapshot.generated_at,
        transport_state=snapshot.transport_state,
        freshness_state=snapshot.freshness_state,
        coverage_state=snapshot.coverage_state,
        schema_state=snapshot.schema_state,
        query_policy_version=EVIDENCE_QUERY_POLICY_VERSION,
        semantic_scope=EVIDENCE_QUERY_SEMANTIC_SCOPE,
        query=query,
        normalized_tokens=normalized_tokens,
        total=len(matches),
        limit=limit,
        offset=offset,
        items=tuple(matches[offset : offset + limit]),
    )
