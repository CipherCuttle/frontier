from __future__ import annotations

from datetime import datetime
from typing import Protocol

from frontier.domain.public_read import (
    EpisodeEvidenceRead,
    ObservationEvidenceRead,
    ObservationNotFoundError,
    ObservationResponseRead,
    PublicHealthRead,
    PublicViewKind,
    PublicViewPage,
    ResolvedPublicSnapshot,
    SnapshotIntegrityError,
    SourceHealthRead,
    episode_observation_ids,
    find_episode,
    select_public_view,
)


class PublicReadRepository(Protocol):
    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot: ...

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]: ...

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None: ...

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]: ...


class PublicReadService:
    def __init__(self, repository: PublicReadRepository) -> None:
        self._repository = repository

    def get_view(
        self,
        view: PublicViewKind,
        *,
        snapshot_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PublicViewPage:
        snapshot = self._repository.resolve_snapshot(snapshot_id)
        return select_public_view(snapshot, view=view, limit=limit, offset=offset)

    def get_episode(
        self, episode_id: str, *, snapshot_id: str | None = None
    ) -> EpisodeEvidenceRead:
        snapshot = self._repository.resolve_snapshot(snapshot_id)
        episode = find_episode(snapshot, episode_id)
        expected_ids = episode_observation_ids(episode)
        as_of = _parse_canonical_timestamp(snapshot.binding.as_of)
        observations = self._repository.list_observations(expected_ids, as_of=as_of)
        by_id = {item.observation_id: item for item in observations}
        if len(by_id) != len(observations):
            raise SnapshotIntegrityError("public evidence repository returned duplicate observations")
        if set(by_id) != set(expected_ids):
            raise SnapshotIntegrityError("episode evidence does not exactly match snapshot membership")
        ordered = tuple(by_id[observation_id] for observation_id in expected_ids)
        return EpisodeEvidenceRead(
            snapshot=snapshot.binding,
            generated_at=snapshot.generated_at,
            episode=episode,
            observations=ordered,
        )

    def get_observation(
        self, observation_id: str, *, snapshot_id: str | None = None
    ) -> ObservationResponseRead:
        snapshot = self._repository.resolve_snapshot(snapshot_id)
        as_of = _parse_canonical_timestamp(snapshot.binding.as_of)
        observation = self._repository.get_observation(observation_id, as_of=as_of)
        if observation is None:
            raise ObservationNotFoundError(observation_id)
        return ObservationResponseRead(
            snapshot=snapshot.binding,
            generated_at=snapshot.generated_at,
            observation=observation,
        )

    def get_health(self, *, snapshot_id: str | None = None) -> PublicHealthRead:
        snapshot = self._repository.resolve_snapshot(snapshot_id)
        as_of = _parse_canonical_timestamp(snapshot.binding.as_of)
        source_health = tuple(self._repository.list_source_health(as_of=as_of))
        return PublicHealthRead(
            snapshot=snapshot.binding,
            generated_at=snapshot.generated_at,
            transport_state=snapshot.transport_state,
            freshness_state=snapshot.freshness_state,
            coverage_state=snapshot.coverage_state,
            schema_state=snapshot.schema_state,
            sources=source_health,
        )


def _parse_canonical_timestamp(value: str) -> datetime:
    if not value.endswith("Z"):
        raise SnapshotIntegrityError("snapshot as_of is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SnapshotIntegrityError("snapshot as_of is not a valid canonical timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise SnapshotIntegrityError("snapshot as_of canonical timestamp shape drift")
    return parsed
