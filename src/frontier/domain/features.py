"""EXPERIMENTAL transparent advanced feature vectors (sprint slice E).

Each episode receives an ordered, interpretable feature vector over the ten
sprint-E features: persistence, novelty, recency, acceleration, breadth,
propagation, recurrence, decay, primary_emission_timing, discovery_lag.

Hard properties (ZOOCODE_SPRINT1.md):

- R1 point-in-time: every feature is computed from member observations with
  ``observed_at <= as_of`` only; future evidence is excluded, never peeked.
- R3 backfill safety: only prospective-eligible member observations
  (``BaselineObservationInput.is_prospective``) feed any feature; BACKFILL and
  recovered-after-gap evidence can never become organic activity.
- R4 coverage: unobservable features are explicitly ``UNKNOWN``; they are
  never silently coerced to zero or to a healthy value.
- R7 epistemic non-escalation: features are tagged interpretable values, not
  scalar scores. Nothing here is truth probability, factual confidence,
  confirmation, provenance origin, or importance.
- R8 replay: vectors are deterministic, canonical-JSON serialized, digest
  bound to the exact evidence and configuration identity.

Feature scope: the eight activity features (persistence, novelty, recency,
acceleration, breadth, propagation, recurrence, decay) are computed over the
observation window ``[as_of - 86400s, as_of]``; the two timing features
(primary_emission_timing, discovery_lag) span the full eligible episode
history up to ``as_of`` and are bounded (discovery_lag clamped, UNKNOWN when
unobservable).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

from .advanced_intelligence import pef_input_digest, shadow_universe_digest
from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .intelligence import BaselineObservationInput, BaselineSnapshot
from .receipt import ProjectionReceipt, ProjectionStatus

FEATURE_SCHEMA_VERSION = "advanced-features-v0"
FEATURE_AUTHORITY_STATE = "EXPERIMENTAL_SHADOW"
FEATURE_ALGORITHM_VERSION = "transparent-advanced-features-v0"
FEATURE_VECTOR_ID_PREFIX = "featurevector_"
FEATURE_BATCH_ID_PREFIX = "featurebatch_"
FEATURE_PRIMARY_EMISSION_ROLE = "PRIMARY_EMISSION"
FEATURE_EXTERNAL_SIGNAL_ROLES = frozenset({"ATTENTION", "DISCOVERY"})
FEATURE_INTERPRETATION = (
    "EXPERIMENTAL interpretable feature vector; not evidence of truth, "
    "factual confidence, confirmation, provenance origin, or importance"
)

FEATURE_OBSERVATION_WINDOW_SECONDS = 86400
FEATURE_PERSISTENCE_SUB_WINDOWS = 24
FEATURE_RECURRENCE_GAP_SECONDS = 3600
FEATURE_DECAY_STALENESS_STEP_SECONDS = 21600
FEATURE_DECAY_STALENESS_STEP_PERMYRIAD = 2500
FEATURE_DISCOVERY_LAG_BOUND_SECONDS = 604800

FEATURE_ORDER: tuple[str, ...] = (
    "persistence",
    "novelty",
    "recency",
    "acceleration",
    "breadth",
    "propagation",
    "recurrence",
    "decay",
    "primary_emission_timing",
    "discovery_lag",
)

_persistence_definition = (
    "permyriad share of the 24 one-hour sub-windows of the observation window "
    "[as_of-86400s, as_of] that contain at least one prospective-eligible "
    "member observation; sub-window index is floor(age_seconds/3600) with the "
    "first sub-window clamped to 23"
)
_novelty_definition = (
    "permyriad share of windowed prospective-eligible member observations "
    "whose source_id has not contributed any earlier windowed observation for "
    "this episode (observations ordered by observed_at then observation_id)"
)
_recency_definition = (
    "linear recency decay of the newest windowed prospective-eligible member "
    "observation: 10000 - floor(age_seconds * 10000 / 86400), monotone "
    "decreasing in age from 10000 (age 0) to 0 (age >= 86400s)"
)
_acceleration_definition = (
    "late minus early half-window prospective-eligible observation counts "
    "within the observation window (late = [as_of-43200s, as_of], "
    "early = [as_of-86400s, as_of-43200s))"
)
_breadth_definition = (
    "count of distinct source_ids among windowed prospective-eligible member "
    "observations of this episode"
)
_propagation_definition = (
    "count of distinct source_ids contributing windowed prospective-eligible "
    "member observations beyond the primary lane (the source of the earliest "
    "such observation)"
)
_recurrence_definition = (
    "count of consecutive windowed prospective-eligible member observation "
    "pairs (ordered by observed_at then observation_id) whose observed_at gap "
    "is >= 3600 seconds: reappearances after gaps"
)
_decay_definition = (
    "staleness of the newest windowed prospective-eligible member observation "
    "in whole 6-hour steps: min(10000, floor(age_seconds / 21600) * 2500), "
    "monotone increasing in age"
)
_primary_emission_timing_definition = (
    "whole seconds from the episode's earliest prospective-eligible member "
    "observation to its earliest prospective-eligible PRIMARY_EMISSION member "
    "observation over the full eligible episode history up to as_of; UNKNOWN "
    "when no such primary-emission observation exists (never coerced)"
)
_discovery_lag_definition = (
    "whole seconds from the earliest prospective-eligible external-signal "
    "member observation (signal role ATTENTION or DISCOVERY) to the earliest "
    "prospective-eligible PRIMARY_EMISSION member observation over the full "
    "eligible episode history up to as_of, clamped to [0, 604800]; UNKNOWN "
    "when either lane is absent (never coerced)"
)

_ACTIVITY_ELIGIBILITY: dict[str, CanonicalValue] = {
    "eligible_reasons": ["ACTIVE_ENRICHMENT", "DISCOVERY", "SCHEDULED"],
    "exclude_backfill": True,
    "exclude_recovered_after_gap": True,
}
_FEATURE_DEFINITIONS: dict[str, CanonicalValue] = {
    "acceleration": _acceleration_definition,
    "breadth": _breadth_definition,
    "decay": _decay_definition,
    "discovery_lag": _discovery_lag_definition,
    "novelty": _novelty_definition,
    "persistence": _persistence_definition,
    "primary_emission_timing": _primary_emission_timing_definition,
    "propagation": _propagation_definition,
    "recency": _recency_definition,
    "recurrence": _recurrence_definition,
}

ADVANCED_FEATURES_CONFIGURATION: dict[str, CanonicalValue] = {
    "activity_eligibility": _ACTIVITY_ELIGIBILITY,
    "algorithm_version": FEATURE_ALGORITHM_VERSION,
    "authority_state": FEATURE_AUTHORITY_STATE,
    "decay_staleness_step_permyriad": FEATURE_DECAY_STALENESS_STEP_PERMYRIAD,
    "decay_staleness_step_seconds": FEATURE_DECAY_STALENESS_STEP_SECONDS,
    "discovery_lag_bound_seconds": FEATURE_DISCOVERY_LAG_BOUND_SECONDS,
    "external_signal_roles": ["ATTENTION", "DISCOVERY"],
    "feature_definitions": _FEATURE_DEFINITIONS,
    "feature_order": list(FEATURE_ORDER),
    "interpretation": FEATURE_INTERPRETATION,
    "observation_window_seconds": FEATURE_OBSERVATION_WINDOW_SECONDS,
    "persistence_sub_windows": FEATURE_PERSISTENCE_SUB_WINDOWS,
    "primary_emission_role": FEATURE_PRIMARY_EMISSION_ROLE,
    "recurrence_gap_seconds": FEATURE_RECURRENCE_GAP_SECONDS,
    "score_semantics": "NO_SCALAR_SCORE_INTERPRETABLE_FEATURES_ONLY",
}
ADVANCED_FEATURES_CONFIGURATION_DIGEST = sha256_digest(
    canonical_json_bytes(ADVANCED_FEATURES_CONFIGURATION)
)


class FeatureStatus(StrEnum):
    """Interpretable-feature value status (R4).

    UNKNOWN is an explicit epistemic state: coverage did not allow the feature
    to be observed. It must never be flattened to zero or to a healthy value.
    """

    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"


class FeatureVectorStatus(StrEnum):
    """Batch lifecycle status (R8): FAILED output never masquerades as RAN."""

    RAN = "RAN"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FeatureValue:
    """One tagged interpretable feature value (never a scalar score, R7)."""

    name: str
    value: int | str | None
    unit: str
    definition: str
    window_seconds: int | None
    status: FeatureStatus

    def __post_init__(self) -> None:
        if self.status is FeatureStatus.UNKNOWN:
            if self.value is not None:
                raise ValueError("UNKNOWN feature value must be None")
        elif self.value is None:
            raise ValueError("OBSERVED feature requires an explicit value")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "definition": self.definition,
            "name": self.name,
            "status": self.status.value,
            "unit": self.unit,
            "value": self.value,
            "window_seconds": self.window_seconds,
        }


def _observed(
    name: str,
    value: int | str,
    *,
    unit: str,
    definition: str,
    window_seconds: int | None,
) -> FeatureValue:
    return FeatureValue(
        name=name,
        value=value,
        unit=unit,
        definition=definition,
        window_seconds=window_seconds,
        status=FeatureStatus.OBSERVED,
    )


def _unknown(
    name: str,
    *,
    unit: str,
    definition: str,
    window_seconds: int | None,
) -> FeatureValue:
    return FeatureValue(
        name=name,
        value=None,
        unit=unit,
        definition=definition,
        window_seconds=window_seconds,
        status=FeatureStatus.UNKNOWN,
    )


@dataclass(frozen=True, slots=True)
class EpisodeFeatureVector:
    """Ordered interpretable feature vector for one episode at one ``as_of``.

    The feature order is exactly ``FEATURE_ORDER``; the vector is canonically
    serialized and digest bound (R8). The payload is EXPERIMENTAL_SHADOW
    output (R7) and carries no score, confidence, or confirmation semantics.
    """

    episode_id: str
    as_of: datetime
    features: tuple[FeatureValue, ...]
    observation_ids: tuple[str, ...]
    observation_window_seconds: int = FEATURE_OBSERVATION_WINDOW_SECONDS
    schema_version: str = FEATURE_SCHEMA_VERSION
    algorithm_version: str = FEATURE_ALGORITHM_VERSION
    configuration_digest: Digest = ADVANCED_FEATURES_CONFIGURATION_DIGEST
    authority_state: str = FEATURE_AUTHORITY_STATE
    interpretation: str = FEATURE_INTERPRETATION

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("feature vector as_of must be timezone-aware")
        names = tuple(feature.name for feature in self.features)
        if names != FEATURE_ORDER:
            raise ValueError("feature vector must carry the canonical ordered feature list")
        statuses = {feature.status for feature in self.features}
        if FeatureStatus.OBSERVED in statuses and all(
            feature.status is FeatureStatus.UNKNOWN for feature in self.features
        ):  # pragma: no cover - defensive, unreachable by construction
            raise ValueError("inconsistent feature statuses")

    @property
    def vector_id(self) -> str:
        return FEATURE_VECTOR_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def vector_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        feature_values: list[CanonicalValue] = [feature.to_canonical() for feature in self.features]
        observation_ids: list[CanonicalValue] = list(self.observation_ids)
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "configuration_digest": str(self.configuration_digest),
            "episode_id": self.episode_id,
            "feature_schema_version": self.schema_version,
            "features": feature_values,
            "interpretation": self.interpretation,
            "observation_ids": observation_ids,
            "observation_window_seconds": self.observation_window_seconds,
        }


@dataclass(frozen=True, slots=True)
class FeatureVectorBatch:
    """Digest-bound batch of per-episode feature vectors for one snapshot (R8)."""

    as_of: datetime
    generated_at: datetime
    control_snapshot_id: str
    control_receipt_id: str
    source_registry_version: Digest
    episode_universe_digest: Digest
    status: FeatureVectorStatus = FeatureVectorStatus.RAN
    vectors: tuple[EpisodeFeatureVector, ...] = ()
    failure_reason: str | None = None
    schema_version: str = FEATURE_SCHEMA_VERSION
    algorithm_version: str = FEATURE_ALGORITHM_VERSION
    configuration_digest: Digest = ADVANCED_FEATURES_CONFIGURATION_DIGEST
    authority_state: str = FEATURE_AUTHORITY_STATE
    interpretation: str = FEATURE_INTERPRETATION

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("feature batch as_of must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("feature batch generated_at must be timezone-aware")
        if self.status is FeatureVectorStatus.RAN and self.failure_reason is not None:
            raise ValueError("RAN feature batch cannot carry a failure reason")
        if self.status is FeatureVectorStatus.FAILED and not self.failure_reason:
            raise ValueError("FAILED feature batch requires an explicit failure reason")
        if self.status is not FeatureVectorStatus.RAN and self.vectors:
            raise ValueError("only RAN feature batches may carry vector payloads")

    @property
    def batch_id(self) -> str:
        return FEATURE_BATCH_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def batch_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        vector_values: list[CanonicalValue] = [vector.to_canonical() for vector in self.vectors]
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "configuration_digest": str(self.configuration_digest),
            "control_receipt_id": self.control_receipt_id,
            "control_snapshot_id": self.control_snapshot_id,
            "episode_universe_digest": str(self.episode_universe_digest),
            "failure_reason": self.failure_reason,
            "feature_schema_version": self.schema_version,
            "generated_at": canonical_timestamp(self.generated_at),
            "interpretation": self.interpretation,
            "source_registry_version": str(self.source_registry_version),
            "status": self.status.value,
            "vectors": vector_values,
        }


def _seconds(delta: timedelta) -> int:
    """Whole seconds of a non-negative timedelta (integer, never float)."""
    if delta < timedelta(0):
        raise ValueError("feature time delta cannot be negative")
    return delta.days * 86400 + delta.seconds


def _windowed_members(
    members: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> tuple[BaselineObservationInput, ...]:
    """Prospective-eligible members inside [as_of-86400s, as_of] (R1, R3)."""
    window_start = as_of - timedelta(seconds=FEATURE_OBSERVATION_WINDOW_SECONDS)
    windowed = tuple(
        item
        for item in members
        if item.is_prospective and window_start <= item.observed_at <= as_of
    )
    return tuple(sorted(windowed, key=lambda item: (item.observed_at, item.observation_id)))


def _persistence(
    windowed: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> FeatureValue:
    if not windowed:
        return _unknown(
            "persistence",
            unit="permyriad_of_fresh_1h_subwindows",
            definition=_persistence_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    fresh = {
        min(_seconds(as_of - item.observed_at) // 3600, FEATURE_PERSISTENCE_SUB_WINDOWS - 1)
        for item in windowed
    }
    value = len(fresh) * 10000 // FEATURE_PERSISTENCE_SUB_WINDOWS
    return _observed(
        "persistence",
        value,
        unit="permyriad_of_fresh_1h_subwindows",
        definition=_persistence_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _novelty(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not windowed:
        return _unknown(
            "novelty",
            unit="permyriad_of_never_before_seen_source_observations",
            definition=_novelty_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    seen: set[str] = set()
    novel = 0
    for item in windowed:
        if item.grouping.source_id not in seen:
            novel += 1
        seen.add(item.grouping.source_id)
    return _observed(
        "novelty",
        novel * 10000 // len(windowed),
        unit="permyriad_of_never_before_seen_source_observations",
        definition=_novelty_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _recency(windowed: tuple[BaselineObservationInput, ...], *, as_of: datetime) -> FeatureValue:
    if not windowed:
        return _unknown(
            "recency",
            unit="permyriad_of_linear_recency_decay_24h",
            definition=_recency_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    age = _seconds(as_of - windowed[-1].observed_at)
    return _observed(
        "recency",
        10000 - (age * 10000) // FEATURE_OBSERVATION_WINDOW_SECONDS,
        unit="permyriad_of_linear_recency_decay_24h",
        definition=_recency_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _acceleration(
    windowed: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> FeatureValue:
    if not windowed:
        return _unknown(
            "acceleration",
            unit="windowed_observations_12h_delta",
            definition=_acceleration_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    half = FEATURE_OBSERVATION_WINDOW_SECONDS // 2
    early = sum(1 for item in windowed if _seconds(as_of - item.observed_at) >= half)
    late = len(windowed) - early
    return _observed(
        "acceleration",
        late - early,
        unit="windowed_observations_12h_delta",
        definition=_acceleration_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _breadth(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not windowed:
        return _unknown(
            "breadth",
            unit="distinct_sources",
            definition=_breadth_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    sources = {item.grouping.source_id for item in windowed}
    return _observed(
        "breadth",
        len(sources),
        unit="distinct_sources",
        definition=_breadth_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _propagation(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not windowed:
        return _unknown(
            "propagation",
            unit="secondary_sources",
            definition=_propagation_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    primary_source = windowed[0].grouping.source_id
    sources = {item.grouping.source_id for item in windowed}
    return _observed(
        "propagation",
        len(sources - {primary_source}),
        unit="secondary_sources",
        definition=_propagation_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _recurrence(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not windowed:
        return _unknown(
            "recurrence",
            unit="reappearances_after_gaps_ge_1h",
            definition=_recurrence_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    count = 0
    for earlier, later in pairwise(windowed):
        gap = _seconds(later.observed_at - earlier.observed_at)
        if gap >= FEATURE_RECURRENCE_GAP_SECONDS:
            count += 1
    return _observed(
        "recurrence",
        count,
        unit="reappearances_after_gaps_ge_1h",
        definition=_recurrence_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _decay(windowed: tuple[BaselineObservationInput, ...], *, as_of: datetime) -> FeatureValue:
    if not windowed:
        return _unknown(
            "decay",
            unit="permyriad_of_staleness_steps_6h",
            definition=_decay_definition,
            window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
        )
    age = _seconds(as_of - windowed[-1].observed_at)
    value = min(
        10000,
        (age // FEATURE_DECAY_STALENESS_STEP_SECONDS) * FEATURE_DECAY_STALENESS_STEP_PERMYRIAD,
    )
    return _observed(
        "decay",
        value,
        unit="permyriad_of_staleness_steps_6h",
        definition=_decay_definition,
        window_seconds=FEATURE_OBSERVATION_WINDOW_SECONDS,
    )


def _primary_emission_timing(
    eligible: tuple[BaselineObservationInput, ...],
) -> FeatureValue:
    if not eligible:
        return _unknown(
            "primary_emission_timing",
            unit="seconds",
            definition=_primary_emission_timing_definition,
            window_seconds=None,
        )
    first_any = min(item.observed_at for item in eligible)
    primaries = [
        item for item in eligible if FEATURE_PRIMARY_EMISSION_ROLE in item.grouping.signal_roles
    ]
    if not primaries:
        return _unknown(
            "primary_emission_timing",
            unit="seconds",
            definition=_primary_emission_timing_definition,
            window_seconds=None,
        )
    first_primary = min(item.observed_at for item in primaries)
    return _observed(
        "primary_emission_timing",
        _seconds(first_primary - first_any),
        unit="seconds",
        definition=_primary_emission_timing_definition,
        window_seconds=None,
    )


def _discovery_lag(eligible: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not eligible:
        return _unknown(
            "discovery_lag",
            unit="seconds_bounded_604800",
            definition=_discovery_lag_definition,
            window_seconds=None,
        )
    external = [
        item
        for item in eligible
        if FEATURE_EXTERNAL_SIGNAL_ROLES.intersection(item.grouping.signal_roles)
    ]
    primaries = [
        item for item in eligible if FEATURE_PRIMARY_EMISSION_ROLE in item.grouping.signal_roles
    ]
    if not external or not primaries:
        return _unknown(
            "discovery_lag",
            unit="seconds_bounded_604800",
            definition=_discovery_lag_definition,
            window_seconds=None,
        )
    external_earliest = min(item.observed_at for item in external)
    primary_earliest = min(item.observed_at for item in primaries)
    lag = (
        _seconds(primary_earliest - external_earliest)
        if primary_earliest > external_earliest
        else 0
    )
    value = min(lag, FEATURE_DISCOVERY_LAG_BOUND_SECONDS)
    return _observed(
        "discovery_lag",
        value,
        unit="seconds_bounded_604800",
        definition=_discovery_lag_definition,
        window_seconds=None,
    )


def _episode_vector(
    episode_id: str,
    members: tuple[BaselineObservationInput, ...],
    *,
    as_of: datetime,
) -> EpisodeFeatureVector:
    eligible = tuple(
        sorted(
            (item for item in members if item.is_prospective and item.observed_at <= as_of),
            key=lambda item: item.observation_id,
        )
    )
    windowed = _windowed_members(members, as_of=as_of)
    features = (
        _persistence(windowed, as_of=as_of),
        _novelty(windowed),
        _recency(windowed, as_of=as_of),
        _acceleration(windowed, as_of=as_of),
        _breadth(windowed),
        _propagation(windowed),
        _recurrence(windowed),
        _decay(windowed, as_of=as_of),
        _primary_emission_timing(eligible),
        _discovery_lag(eligible),
    )
    return EpisodeFeatureVector(
        episode_id=episode_id,
        as_of=as_of,
        features=features,
        observation_ids=tuple(item.observation_id for item in eligible),
    )


def build_feature_vectors(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> tuple[EpisodeFeatureVector, ...]:
    """Deterministically build the ordered per-episode feature vectors.

    Point-in-time discipline (R1): observations after ``as_of`` are excluded
    before any computation. Backfill safety (R3): only prospective-eligible
    member observations feed features.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("feature as_of must be timezone-aware")
    if control_snapshot.as_of != as_of:
        raise ValueError("control snapshot as_of must match feature as_of")

    eligible = sorted(
        (item for item in observations if item.observed_at <= as_of),
        key=lambda item: item.observation_id,
    )
    by_id = {item.observation_id: item for item in eligible}
    if len(by_id) != len(eligible):
        raise ValueError("duplicate observation_id in feature inputs")

    vectors: list[EpisodeFeatureVector] = []
    for episode in control_snapshot.episodes:
        members: list[BaselineObservationInput] = []
        for observation_id in episode.observation_ids:
            item = by_id.get(observation_id)
            if item is None:
                raise ValueError("control snapshot episode references unknown observation")
            members.append(item)
        vectors.append(_episode_vector(episode.episode_id, tuple(members), as_of=as_of))
    return tuple(sorted(vectors, key=lambda vector: vector.episode_id))


def build_feature_vector_batch(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> FeatureVectorBatch:
    """Bind per-episode feature vectors to the exact control snapshot (R8)."""
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("feature vectors require a COMPLETE control snapshot")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("feature batch generated_at must be timezone-aware")
    vectors = build_feature_vectors(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return FeatureVectorBatch(
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        episode_universe_digest=shadow_universe_digest(control_snapshot),
        vectors=vectors,
    )


def failed_feature_vector_batch(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
    failure_reason: str,
) -> FeatureVectorBatch:
    """Explicit FAILED batch identity without any vector payload (R8)."""
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("feature batch generated_at must be timezone-aware")
    if not failure_reason:
        raise ValueError("FAILED feature batch requires an explicit failure reason")
    return FeatureVectorBatch(
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        episode_universe_digest=shadow_universe_digest(control_snapshot),
        status=FeatureVectorStatus.FAILED,
        failure_reason=failure_reason,
    )


def feature_input_digest(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
) -> Digest:
    """Digest the exact evidence inputs bound into a feature batch (R8)."""
    return pef_input_digest(observations, control_snapshot=control_snapshot)
