from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest
from frontier.domain.features import (
    ADVANCED_FEATURES_CONFIGURATION_DIGEST,
    FEATURE_ALGORITHM_VERSION,
    FEATURE_DISCOVERY_LAG_BOUND_SECONDS,
    FEATURE_INTERPRETATION,
    FEATURE_ORDER,
    FEATURE_SCHEMA_VERSION,
    EpisodeFeatureVector,
    FeatureStatus,
    FeatureValue,
    build_feature_vector_batch,
    build_feature_vectors,
    failed_feature_vector_batch,
)
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
GENERATED_AT = AS_OF
REGISTRY = Digest("sha256:" + "1" * 64)
SOURCES = ("s.a", "s.ext", "s.other", "s.pri")


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    *,
    observed_at: datetime,
    source_id: str = "s.a",
    roles: tuple[str, ...] = ("PRIMARY_EMISSION",),
    reason: str = "SCHEDULED",
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id=source_id,
            source_item_key=label,
            kind="DOCUMENT",
            observed_at=observed_at,
            canonical_url=f"https://example.test/{label}",
            title=f"Fixture {label} episode title",
            text=None,
            signal_roles=roles,
        ),
        first_reason=reason,
        recovered_after_gap=False,
    )


def _health() -> tuple[BaselineHealthInput, ...]:
    return tuple(
        BaselineHealthInput(
            source_id=source_id,
            as_of=AS_OF - timedelta(minutes=1),
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.OK,
            schema=HealthValue.OK,
        )
        for source_id in SOURCES
    )


def _projection(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
) -> GroupingProjection:
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    return GroupingProjection(
        as_of=AS_OF,
        groups=tuple(
            EpisodeGroup(group_id=f"grp_{index:064x}", observation_ids=tuple(sorted(group)))
            for index, group in enumerate(grouped, start=1)
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=tuple(
            sorted(
                item.observation_id
                for item in observations
                if item.observation_id not in grouped_ids
            )
        ),
    )


def _control(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    eligible = [item for item in observations if item.observed_at <= AS_OF]
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_health(),
        as_of=AS_OF,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_health(),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    return snapshot, receipt


def _vectors(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
) -> tuple[EpisodeFeatureVector, ...]:
    snapshot, _receipt = _control(observations, grouped=grouped)
    return build_feature_vectors(observations, control_snapshot=snapshot, as_of=AS_OF)


def _one_episode(
    *observations: BaselineObservationInput,
) -> tuple[EpisodeFeatureVector, ...]:
    """Force every observation into one grouping episode."""
    return _vectors(
        list(observations),
        grouped=(tuple(item.observation_id for item in observations),),
    )


def _feature(vector: EpisodeFeatureVector, name: str) -> FeatureValue:
    for feature in vector.features:
        if feature.name == name:
            return feature
    raise AssertionError(f"missing feature {name}")


def test_persistence_counts_fresh_1h_subwindows() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20)),
        _observation("b", observed_at=AS_OF - timedelta(hours=10)),
        _observation("c", observed_at=AS_OF - timedelta(hours=5)),
    ]
    (vector,) = _one_episode(*observations)
    # fresh buckets {20, 10, 5} -> 3/24 -> 1250 permyriad
    assert _feature(vector, "persistence").value == 1250
    assert _feature(vector, "persistence").status == "OBSERVED"


def test_novelty_share_of_never_before_seen_sources() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20), source_id="s.a"),
        _observation("b", observed_at=AS_OF - timedelta(hours=10), source_id="s.a"),
        _observation("c", observed_at=AS_OF - timedelta(hours=5), source_id="s.ext"),
        _observation("d", observed_at=AS_OF - timedelta(hours=2), source_id="s.other"),
    ]
    (vector,) = _one_episode(*observations)
    # order a(s.a), b(s.a), c(s.ext), d(s.other): novel = a, c, d -> 3/4
    assert _feature(vector, "novelty").value == 7500


def test_recency_linear_decay_of_newest_observation() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=6))]
    (vector,) = _one_episode(*observations)
    # age 21600s -> 10000 - (21600*10000)//86400 = 7500
    assert _feature(vector, "recency").value == 7500


def test_acceleration_is_late_minus_early_half_window_counts() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=13)),
        _observation("b", observed_at=AS_OF - timedelta(hours=2)),
        _observation("c", observed_at=AS_OF - timedelta(hours=2, seconds=1)),
        _observation("d", observed_at=AS_OF - timedelta(hours=1)),
    ]
    (vector,) = _one_episode(*observations)
    # early: a (1); late: c, d, b (3) -> late - early = 2
    assert _feature(vector, "acceleration").value == 2


def test_breadth_and_propagation_counts_distinct_sources() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20), source_id="s.ext"),
        _observation("b", observed_at=AS_OF - timedelta(hours=15), source_id="s.pri"),
        _observation("c", observed_at=AS_OF - timedelta(hours=5), source_id="s.other"),
        _observation("d", observed_at=AS_OF - timedelta(hours=1), source_id="s.ext"),
    ]
    (vector,) = _one_episode(*observations)
    # breadth: {s.ext, s.pri, s.other} -> 3
    assert _feature(vector, "breadth").value == 3
    # primary lane = source of earliest windowed observation (s.ext) -> 2 others
    assert _feature(vector, "propagation").value == 2


def test_recurrence_counts_reappearances_after_gaps() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20)),
        _observation("b", observed_at=AS_OF - timedelta(hours=10)),
        _observation("c", observed_at=AS_OF - timedelta(hours=9)),
        _observation("d", observed_at=AS_OF - timedelta(seconds=1)),
    ]
    (vector,) = _one_episode(*observations)
    # gaps 10h (>=1h), 1h (>=1h), ~9h (>=1h) -> 3 reappearances
    assert _feature(vector, "recurrence").value == 3


def test_recurrence_gap_boundary_is_inclusive() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(seconds=7200)),
        _observation("b", observed_at=AS_OF - timedelta(seconds=3600)),
    ]
    (vector,) = _one_episode(*observations)
    assert _feature(vector, "recurrence").value == 1


def test_decay_counts_whole_6h_staleness_steps() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=6))]
    (vector,) = _one_episode(*observations)
    # age 21600s -> 1 whole 6h step -> 2500
    assert _feature(vector, "decay").value == 2500
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=23))]
    (vector,) = _one_episode(*observations)
    # age 82800s -> 3 whole steps -> 7500
    assert _feature(vector, "decay").value == 7500


def test_primary_emission_timing_from_first_observation() -> None:
    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(hours=5),
            source_id="s.pri",
            roles=("PRIMARY_EMISSION",),
        ),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.ext",
            roles=("DISCOVERY",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    # first primary == first observation -> 0 seconds
    assert _feature(vector, "primary_emission_timing").value == 0

    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(hours=20),
            source_id="s.ext",
            roles=("DISCOVERY",),
        ),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=15),
            source_id="s.pri",
            roles=("PRIMARY_EMISSION",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    # first observation at -20h, first primary at -15h -> 18000 seconds
    assert _feature(vector, "primary_emission_timing").value == 18000


def test_discovery_lag_is_bounded_and_never_negative() -> None:
    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(hours=20),
            source_id="s.ext",
            roles=("DISCOVERY",),
        ),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=15),
            source_id="s.pri",
            roles=("PRIMARY_EMISSION",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    # external at -20h precedes primary at -15h -> lag 18000s
    assert _feature(vector, "discovery_lag").value == 18000

    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(hours=20),
            source_id="s.pri",
            roles=("PRIMARY_EMISSION",),
        ),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=15),
            source_id="s.ext",
            roles=("DISCOVERY",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    # primary precedes the external signal -> clamped to 0
    assert _feature(vector, "discovery_lag").value == 0

    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(seconds=FEATURE_DISCOVERY_LAG_BOUND_SECONDS + 3600),
            source_id="s.ext",
            roles=("DISCOVERY",),
        ),
        _observation(
            "b",
            observed_at=AS_OF - timedelta(hours=1),
            source_id="s.pri",
            roles=("PRIMARY_EMISSION",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    # lag exceeds the bound -> clamped to 604800
    assert _feature(vector, "discovery_lag").value == FEATURE_DISCOVERY_LAG_BOUND_SECONDS


def test_unobservable_features_are_explicit_unknown_never_zero() -> None:
    observations = [
        _observation(
            "a",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    (vector,) = _one_episode(*observations)
    timing = _feature(vector, "primary_emission_timing")
    lag = _feature(vector, "discovery_lag")
    assert timing.status == "UNKNOWN" and timing.value is None
    assert lag.status == "UNKNOWN" and lag.value is None
    # observed activity features stay OBSERVED for the single attention observation
    assert _feature(vector, "persistence").value == 10000 // 24
    assert _feature(vector, "novelty").value == 10000
    assert _feature(vector, "recency").value == 9167
    assert _feature(vector, "acceleration").value == 1
    assert _feature(vector, "breadth").value == 1
    assert _feature(vector, "propagation").value == 0
    assert _feature(vector, "recurrence").value == 0
    assert _feature(vector, "decay").value == 0


def test_backfill_only_episode_is_all_unknown() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=2), reason="BACKFILL"),
    ]
    (vector,) = _one_episode(*observations)
    for name in FEATURE_ORDER:
        feature = _feature(vector, name)
        assert feature.status == "UNKNOWN"
        assert feature.value is None
        assert feature.definition


def test_recovered_after_gap_evidence_never_becomes_activity() -> None:
    recovered = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id("r"),
            source_id="s.a",
            source_item_key="r",
            kind="DOCUMENT",
            observed_at=AS_OF - timedelta(hours=2),
            canonical_url="https://example.test/r",
            title="Recovered",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="DISCOVERY",
        recovered_after_gap=True,
    )
    (vector,) = _one_episode(recovered)
    for name in FEATURE_ORDER:
        feature = _feature(vector, name)
        assert feature.status == "UNKNOWN"
        assert feature.value is None


def test_future_observations_never_influence_features() -> None:
    base = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20)),
        _observation("b", observed_at=AS_OF - timedelta(hours=10)),
        _observation("c", observed_at=AS_OF - timedelta(hours=5)),
    ]
    (without_future,) = _one_episode(*base)
    with_future = [
        *base,
        _observation("z", observed_at=AS_OF + timedelta(hours=1)),
    ]
    (with_future_vector,) = _vectors(
        with_future,
        grouped=(tuple(item.observation_id for item in base),),
    )
    assert with_future_vector.vector_digest == without_future.vector_digest
    assert with_future_vector.observation_ids == without_future.observation_ids


def test_window_start_boundary_is_inclusive() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(seconds=86400)),
    ]
    (vector,) = _one_episode(*observations)
    # single fresh sub-window (clamped bucket 23) -> 10000//24 = 416 permyriad
    assert _feature(vector, "persistence").value == 10000 // 24
    # age 86400s -> recency 0, decay 10000
    assert _feature(vector, "recency").value == 0
    assert _feature(vector, "decay").value == 10000


def test_vector_order_schema_and_digest_binding() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=2))]
    (vector,) = _one_episode(*observations)
    assert tuple(feature.name for feature in vector.features) == FEATURE_ORDER
    assert vector.schema_version == FEATURE_SCHEMA_VERSION
    assert vector.algorithm_version == FEATURE_ALGORITHM_VERSION
    assert vector.authority_state == "EXPERIMENTAL_SHADOW"
    assert vector.configuration_digest == ADVANCED_FEATURES_CONFIGURATION_DIGEST
    canonical = canonical_json_bytes(vector.to_canonical())
    assert vector.vector_digest.value == "sha256:" + sha256(canonical).hexdigest()
    assert vector.vector_id == "featurevector_" + sha256(canonical).hexdigest()


def test_determinism_same_inputs_same_vector_digest() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20), source_id="s.ext"),
        _observation("b", observed_at=AS_OF - timedelta(hours=5), source_id="s.pri"),
    ]
    first = _one_episode(*observations)
    second = _one_episode(*observations)
    assert first[0].vector_id == second[0].vector_id
    assert first[0].to_canonical() == second[0].to_canonical()


def test_batch_identity_binds_snapshot_and_evidence() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=2))]
    snapshot, receipt = _control(observations)
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    rebuilt = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert batch.batch_id == rebuilt.batch_id
    assert batch.batch_digest == rebuilt.batch_digest
    assert batch.control_snapshot_id == snapshot.snapshot_id
    assert batch.control_receipt_id == receipt.receipt_id
    assert batch.authority_state == "EXPERIMENTAL_SHADOW"
    assert batch.batch_digest.value == (
        "sha256:" + sha256(canonical_json_bytes(batch.to_canonical())).hexdigest()
    )


def test_failed_batch_carries_no_vector_payload() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=2))]
    snapshot, receipt = _control(observations)
    batch = failed_feature_vector_batch(
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
        failure_reason="upstream evidence digest mismatch",
    )
    assert batch.status == "FAILED"
    assert batch.vectors == ()
    assert batch.failure_reason == "upstream evidence digest mismatch"


def test_batch_rejects_incomplete_control_receipt() -> None:
    observations = [_observation("a", observed_at=AS_OF - timedelta(hours=2))]
    snapshot, receipt = _control(observations)
    failed_receipt = replace(receipt, status=ProjectionStatus.FAILED)
    with pytest.raises(ValueError):
        build_feature_vector_batch(
            observations,
            control_snapshot=snapshot,
            control_receipt=failed_receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )


def test_no_truth_confidence_or_confirmation_keys_are_serialized() -> None:
    observations = [
        _observation("a", observed_at=AS_OF - timedelta(hours=20), source_id="s.ext"),
        _observation("b", observed_at=AS_OF - timedelta(hours=5), source_id="s.pri"),
    ]
    (vector,) = _one_episode(*observations)
    payload = cast(
        dict[str, object],
        json.loads(canonical_json_bytes(vector.to_canonical()).decode("utf-8")),
    )
    forbidden = {"score", "confidence", "confirmation", "probability", "truth"}

    def _keys(node: object) -> set[str]:
        if isinstance(node, dict):
            mapping = cast(dict[str, object], node)
            keys = set(mapping)
            for value in mapping.values():
                keys |= _keys(value)
            return keys
        if isinstance(node, list):
            sequence = cast(list[object], node)
            collected: set[str] = set()
            for value in sequence:
                collected |= _keys(value)
            return collected
        return set()

    assert _keys(payload).isdisjoint(forbidden)
    assert payload["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert payload["interpretation"] == FEATURE_INTERPRETATION
    features = cast(list[object], payload["features"])
    for feature in features:
        entry = cast(dict[str, object], feature)
        assert entry["definition"]
        assert entry["status"] in ("OBSERVED", "UNKNOWN")
        assert entry["unit"]


def test_feature_value_unknown_invariants() -> None:
    with pytest.raises(ValueError):
        FeatureValue(
            name="persistence",
            value=100,
            unit="permyriad",
            definition="d",
            window_seconds=86400,
            status=FeatureStatus.UNKNOWN,
        )
    with pytest.raises(ValueError):
        FeatureValue(
            name="persistence",
            value=None,
            unit="permyriad",
            definition="d",
            window_seconds=86400,
            status=FeatureStatus.OBSERVED,
        )


def test_vector_rejects_non_canonical_feature_order() -> None:
    ordered = [
        FeatureValue(
            name=name,
            value=0,
            unit="u",
            definition="d",
            window_seconds=None,
            status=FeatureStatus.OBSERVED,
        )
        for name in ("novelty", "persistence")
    ]
    with pytest.raises(ValueError):
        EpisodeFeatureVector(
            episode_id="e",
            as_of=AS_OF,
            features=tuple(ordered),
            observation_ids=(),
        )
