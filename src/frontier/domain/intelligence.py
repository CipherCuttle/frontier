from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .grouping import GROUPING_ALGORITHM_VERSION, GroupingInput, GroupingProjection
from .health import HealthValue
from .receipt import ProjectionReceipt, ProjectionStatus

BASELINE_PROJECTION_NAME = "baseline-intelligence"
BASELINE_PROJECTION_VERSION = "baseline-intelligence-v0"
BASELINE_SCHEMA_VERSION = "baseline-intelligence-snapshot-v0"
BASELINE_ALGORITHM_VERSION = "windowed-episode-metrics-v0"
BASELINE_RANKING_POLICY_VERSION = "naive-episode-activity-v0"
BASELINE_RECEIPT_SCHEMA_VERSION = "projection-receipt-v1"

ONE_HOUR = timedelta(hours=1)
SIX_HOURS = timedelta(hours=6)
TWELVE_HOURS = timedelta(hours=12)
EIGHTEEN_HOURS = timedelta(hours=18)
TWENTY_FOUR_HOURS = timedelta(hours=24)

_activity_eligibility: dict[str, CanonicalValue] = {
    "eligible_reasons": ["ACTIVE_ENRICHMENT", "DISCOVERY", "SCHEDULED"],
    "exclude_backfill": True,
    "exclude_recovered_after_gap": True,
}
_ranking_order: list[CanonicalValue] = [
    "mentions_1h_desc",
    "mentions_6h_desc",
    "velocity_6h_delta_desc",
    "acceleration_6h_desc",
    "mentions_24h_desc",
    "source_role_diversity_desc",
    "last_observed_at_desc",
    "evidence_count_total_desc",
    "episode_id_asc",
]
_windows: dict[str, CanonicalValue] = {
    "mentions_1h": 3600,
    "mentions_6h": 21600,
    "mentions_24h": 86400,
    "preprevious_6h_start": 64800,
    "previous_6h_start": 43200,
}
BASELINE_CONFIGURATION: dict[str, CanonicalValue] = {
    "activity_eligibility": _activity_eligibility,
    "grouping_algorithm_version": GROUPING_ALGORITHM_VERSION,
    "ranking_order": _ranking_order,
    "windows_seconds": _windows,
}
BASELINE_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(BASELINE_CONFIGURATION))

_ELIGIBLE_REASONS = frozenset({"SCHEDULED", "DISCOVERY", "ACTIVE_ENRICHMENT"})
_ALL_REASONS = _ELIGIBLE_REASONS | {"BACKFILL"}


@dataclass(frozen=True, slots=True)
class BaselineObservationInput:
    grouping: GroupingInput
    first_reason: str
    recovered_after_gap: bool

    def __post_init__(self) -> None:
        if self.first_reason not in _ALL_REASONS:
            raise ValueError("baseline observation requires canonical first collection reason")

    @property
    def observation_id(self) -> str:
        return self.grouping.observation_id

    @property
    def observed_at(self) -> datetime:
        return self.grouping.observed_at

    @property
    def is_recovered_backlog(self) -> bool:
        return self.recovered_after_gap

    @property
    def is_backfill(self) -> bool:
        return not self.recovered_after_gap and self.first_reason == "BACKFILL"

    @property
    def is_prospective(self) -> bool:
        return not self.recovered_after_gap and self.first_reason in _ELIGIBLE_REASONS

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "first_reason": self.first_reason,
            "grouping": self.grouping.to_canonical(),
            "recovered_after_gap": self.recovered_after_gap,
        }


@dataclass(frozen=True, slots=True)
class BaselineHealthInput:
    source_id: str
    as_of: datetime
    transport: HealthValue
    freshness: HealthValue
    completeness: HealthValue
    schema: HealthValue

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("health as_of must be timezone-aware")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "as_of": canonical_timestamp(self.as_of),
            "completeness": self.completeness.value,
            "freshness": self.freshness.value,
            "schema": self.schema.value,
            "source_id": self.source_id,
            "transport": self.transport.value,
        }


@dataclass(frozen=True, slots=True)
class BaselineEpisode:
    rank: int
    episode_id: str
    observation_ids: tuple[str, ...]
    first_observed_at: datetime
    last_observed_at: datetime
    age_seconds: int
    evidence_count_total: int
    prospective_evidence_count: int
    backfill_evidence_count: int
    recovered_backlog_evidence_count: int
    mentions_1h: int
    mentions_6h: int
    mentions_24h: int
    previous_6h: int
    preprevious_6h: int
    velocity_6h_delta: int
    acceleration_6h: int
    source_ids: tuple[str, ...]
    source_count: int
    signal_roles: tuple[str, ...]
    source_role_diversity: int
    evidence_root_diversity: None = None
    confirmation: str = "UNAVAILABLE"

    def to_canonical(self) -> dict[str, CanonicalValue]:
        observation_ids: list[CanonicalValue] = list(self.observation_ids)
        source_ids: list[CanonicalValue] = list(self.source_ids)
        signal_roles: list[CanonicalValue] = list(self.signal_roles)
        return {
            "acceleration_6h": self.acceleration_6h,
            "age_seconds": self.age_seconds,
            "backfill_evidence_count": self.backfill_evidence_count,
            "confirmation": self.confirmation,
            "episode_id": self.episode_id,
            "evidence_count_total": self.evidence_count_total,
            "evidence_root_diversity": self.evidence_root_diversity,
            "first_observed_at": canonical_timestamp(self.first_observed_at),
            "last_observed_at": canonical_timestamp(self.last_observed_at),
            "mentions_1h": self.mentions_1h,
            "mentions_24h": self.mentions_24h,
            "mentions_6h": self.mentions_6h,
            "observation_ids": observation_ids,
            "preprevious_6h": self.preprevious_6h,
            "previous_6h": self.previous_6h,
            "prospective_evidence_count": self.prospective_evidence_count,
            "rank": self.rank,
            "recovered_backlog_evidence_count": self.recovered_backlog_evidence_count,
            "signal_roles": signal_roles,
            "source_count": self.source_count,
            "source_ids": source_ids,
            "source_role_diversity": self.source_role_diversity,
            "velocity_6h_delta": self.velocity_6h_delta,
        }


@dataclass(frozen=True, slots=True)
class BaselineSnapshot:
    as_of: datetime
    transport_state: HealthValue
    freshness_state: HealthValue
    coverage_state: HealthValue
    schema_state: HealthValue
    episodes: tuple[BaselineEpisode, ...]
    schema_version: str = BASELINE_SCHEMA_VERSION
    projection_version: str = BASELINE_PROJECTION_VERSION
    algorithm_version: str = BASELINE_ALGORITHM_VERSION
    ranking_policy_version: str = BASELINE_RANKING_POLICY_VERSION

    @property
    def snapshot_id(self) -> str:
        return "snapshot_" + sha256_hex(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        episode_values: list[CanonicalValue] = [episode.to_canonical() for episode in self.episodes]
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "coverage_state": self.coverage_state.value,
            "episodes": episode_values,
            "freshness_state": self.freshness_state.value,
            "projection_version": self.projection_version,
            "ranking_policy_version": self.ranking_policy_version,
            "schema_state": self.schema_state.value,
            "schema_version": self.schema_version,
            "transport_state": self.transport_state.value,
        }


def _age_seconds(delta: timedelta) -> int:
    if delta < timedelta(0):
        raise ValueError("episode last observation cannot be after as_of")
    return delta.days * 86400 + delta.seconds


def _in_window(observed_at: datetime, *, start: datetime, end: datetime) -> bool:
    return start < observed_at <= end


def _episode_id(observation_ids: tuple[str, ...]) -> str:
    observation_values: list[CanonicalValue] = list(observation_ids)
    material: dict[str, CanonicalValue] = {
        "grouping_algorithm_version": GROUPING_ALGORITHM_VERSION,
        "observation_ids": observation_values,
    }
    return "episode_" + sha256_hex(canonical_json_bytes(material))


def _aggregate_health(values: Iterable[HealthValue]) -> HealthValue:
    values_tuple = tuple(values)
    if HealthValue.FAILED in values_tuple:
        return HealthValue.FAILED
    if HealthValue.DEGRADED in values_tuple:
        return HealthValue.DEGRADED
    if HealthValue.UNKNOWN in values_tuple:
        return HealthValue.UNKNOWN
    return HealthValue.OK


def _health_states(
    enabled_source_ids: Iterable[str], health: Iterable[BaselineHealthInput]
) -> tuple[HealthValue, HealthValue, HealthValue, HealthValue]:
    enabled = tuple(sorted(set(enabled_source_ids)))
    health_by_source: dict[str, BaselineHealthInput] = {}
    for item in health:
        if item.source_id in health_by_source:
            raise ValueError("duplicate latest health input for source")
        health_by_source[item.source_id] = item

    transport_values = [
        health_by_source[source_id].transport
        if source_id in health_by_source
        else HealthValue.UNKNOWN
        for source_id in enabled
    ]
    freshness_values = [
        health_by_source[source_id].freshness
        if source_id in health_by_source
        else HealthValue.UNKNOWN
        for source_id in enabled
    ]
    completeness_values = [
        health_by_source[source_id].completeness
        if source_id in health_by_source
        else HealthValue.UNKNOWN
        for source_id in enabled
    ]
    schema_values = [
        health_by_source[source_id].schema
        if source_id in health_by_source
        else HealthValue.UNKNOWN
        for source_id in enabled
    ]
    if not enabled:
        return (
            HealthValue.UNKNOWN,
            HealthValue.UNKNOWN,
            HealthValue.UNKNOWN,
            HealthValue.UNKNOWN,
        )
    return (
        _aggregate_health(transport_values),
        _aggregate_health(freshness_values),
        _aggregate_health(completeness_values),
        _aggregate_health(schema_values),
    )


def _episode_without_rank(
    members: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> BaselineEpisode:
    if not members:
        raise ValueError("baseline episode cannot be empty")
    ordered = tuple(sorted(members, key=lambda item: item.observation_id))
    observed_times = tuple(item.observed_at for item in ordered)
    first_observed_at = min(observed_times)
    last_observed_at = max(observed_times)
    prospective = tuple(item for item in ordered if item.is_prospective)

    mentions_1h = sum(
        1
        for item in prospective
        if _in_window(item.observed_at, start=as_of - ONE_HOUR, end=as_of)
    )
    mentions_6h = sum(
        1
        for item in prospective
        if _in_window(item.observed_at, start=as_of - SIX_HOURS, end=as_of)
    )
    mentions_24h = sum(
        1
        for item in prospective
        if _in_window(item.observed_at, start=as_of - TWENTY_FOUR_HOURS, end=as_of)
    )
    previous_6h = sum(
        1
        for item in prospective
        if _in_window(
            item.observed_at,
            start=as_of - TWELVE_HOURS,
            end=as_of - SIX_HOURS,
        )
    )
    preprevious_6h = sum(
        1
        for item in prospective
        if _in_window(
            item.observed_at,
            start=as_of - EIGHTEEN_HOURS,
            end=as_of - TWELVE_HOURS,
        )
    )
    source_ids = tuple(sorted({item.grouping.source_id for item in ordered}))
    signal_roles = tuple(
        sorted({role for item in ordered for role in item.grouping.signal_roles})
    )
    observation_ids = tuple(item.observation_id for item in ordered)
    return BaselineEpisode(
        rank=0,
        episode_id=_episode_id(observation_ids),
        observation_ids=observation_ids,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        age_seconds=_age_seconds(as_of - last_observed_at),
        evidence_count_total=len(ordered),
        prospective_evidence_count=len(prospective),
        backfill_evidence_count=sum(1 for item in ordered if item.is_backfill),
        recovered_backlog_evidence_count=sum(
            1 for item in ordered if item.is_recovered_backlog
        ),
        mentions_1h=mentions_1h,
        mentions_6h=mentions_6h,
        mentions_24h=mentions_24h,
        previous_6h=previous_6h,
        preprevious_6h=preprevious_6h,
        velocity_6h_delta=mentions_6h - previous_6h,
        acceleration_6h=mentions_6h - (2 * previous_6h) + preprevious_6h,
        source_ids=source_ids,
        source_count=len(source_ids),
        signal_roles=signal_roles,
        source_role_diversity=len(signal_roles),
    )


def _rank(episodes: list[BaselineEpisode]) -> tuple[BaselineEpisode, ...]:
    ordered = sorted(episodes, key=lambda episode: episode.episode_id)
    ordered.sort(key=lambda episode: episode.evidence_count_total, reverse=True)
    ordered.sort(key=lambda episode: episode.last_observed_at, reverse=True)
    ordered.sort(key=lambda episode: episode.source_role_diversity, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_24h, reverse=True)
    ordered.sort(key=lambda episode: episode.acceleration_6h, reverse=True)
    ordered.sort(key=lambda episode: episode.velocity_6h_delta, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_6h, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_1h, reverse=True)
    return tuple(
        replace(episode, rank=index) for index, episode in enumerate(ordered, start=1)
    )


def build_baseline_snapshot(
    observations: Iterable[BaselineObservationInput],
    *,
    grouping_projection: GroupingProjection,
    enabled_source_ids: Iterable[str],
    health: Iterable[BaselineHealthInput],
    as_of: datetime,
) -> BaselineSnapshot:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if grouping_projection.as_of != as_of:
        raise ValueError("grouping projection as_of must match baseline as_of")

    eligible = tuple(
        sorted(
            (item for item in observations if item.observed_at <= as_of),
            key=lambda item: item.observation_id,
        )
    )
    by_id = {item.observation_id: item for item in eligible}
    if len(by_id) != len(eligible):
        raise ValueError("duplicate observation_id in baseline inputs")

    health_tuple = tuple(health)
    if any(item.as_of > as_of for item in health_tuple):
        raise ValueError("baseline health input exceeds as_of")

    grouping_ids: list[str] = []
    episode_member_ids: list[tuple[str, ...]] = []
    for group in grouping_projection.groups:
        episode_member_ids.append(group.observation_ids)
        grouping_ids.extend(group.observation_ids)
    for observation_id in grouping_projection.ungrouped_observation_ids:
        episode_member_ids.append((observation_id,))
        grouping_ids.append(observation_id)
    if len(grouping_ids) != len(set(grouping_ids)):
        raise ValueError("grouping projection assigns an observation more than once")
    if set(grouping_ids) != set(by_id):
        raise ValueError("grouping projection and baseline inputs disagree")

    episodes = [
        _episode_without_rank(
            tuple(by_id[observation_id] for observation_id in member_ids),
            as_of=as_of,
        )
        for member_ids in episode_member_ids
    ]
    transport, freshness, coverage, schema = _health_states(
        enabled_source_ids, health_tuple
    )
    return BaselineSnapshot(
        as_of=as_of,
        transport_state=transport,
        freshness_state=freshness,
        coverage_state=coverage,
        schema_state=schema,
        episodes=_rank(episodes),
    )


def baseline_input_digest(
    observations: Iterable[BaselineObservationInput],
    *,
    grouping_projection: GroupingProjection,
    enabled_source_ids: Iterable[str],
    health: Iterable[BaselineHealthInput],
) -> Digest:
    enabled_values: list[CanonicalValue] = sorted(set(enabled_source_ids))
    health_values: list[CanonicalValue] = [
        item.to_canonical()
        for item in sorted(health, key=lambda item: (item.source_id, item.as_of))
    ]
    observation_values: list[CanonicalValue] = [
        item.to_canonical()
        for item in sorted(observations, key=lambda item: item.observation_id)
    ]
    material: dict[str, CanonicalValue] = {
        "enabled_source_ids": enabled_values,
        "grouping_projection": grouping_projection.to_canonical(),
        "health": health_values,
        "observations": observation_values,
    }
    return sha256_digest(canonical_json_bytes(material))


def build_baseline_receipt(
    snapshot: BaselineSnapshot,
    *,
    observations: Iterable[BaselineObservationInput],
    grouping_projection: GroupingProjection,
    enabled_source_ids: Iterable[str],
    health: Iterable[BaselineHealthInput],
    generated_at: datetime,
    source_registry_version: Digest,
) -> ProjectionReceipt:
    return ProjectionReceipt(
        receipt_schema_version=BASELINE_RECEIPT_SCHEMA_VERSION,
        projection_name=BASELINE_PROJECTION_NAME,
        projection_version=BASELINE_PROJECTION_VERSION,
        schema_version=BASELINE_SCHEMA_VERSION,
        algorithm_version=BASELINE_ALGORITHM_VERSION,
        ranking_policy_version=BASELINE_RANKING_POLICY_VERSION,
        configuration_digest=BASELINE_CONFIGURATION_DIGEST,
        source_registry_version=source_registry_version,
        as_of=snapshot.as_of,
        generated_at=generated_at,
        input_digest=baseline_input_digest(
            observations,
            grouping_projection=grouping_projection,
            enabled_source_ids=enabled_source_ids,
            health=health,
        ),
        output_digest=sha256_digest(canonical_json_bytes(snapshot.to_canonical())),
        status=ProjectionStatus.COMPLETE,
    )
