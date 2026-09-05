from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from frontier.domain.digests import Digest
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    build_baseline_receipt,
    build_baseline_snapshot,
)

AS_OF = datetime(2026, 9, 5, 12, tzinfo=UTC)
REGISTRY = Digest("sha256:" + "1" * 64)


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    observed_at: datetime,
    *,
    source_id: str = "fixture.primary",
    roles: tuple[str, ...] = ("PRIMARY_EMISSION",),
    reason: str = "SCHEDULED",
    recovered_after_gap: bool = False,
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
        recovered_after_gap=recovered_after_gap,
    )


def _projection(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
) -> GroupingProjection:
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    return GroupingProjection(
        as_of=as_of,
        groups=tuple(
            EpisodeGroup(group_id=f"grp_{index:064x}", observation_ids=tuple(sorted(group)))
            for index, group in enumerate(grouped, start=1)
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=tuple(
            sorted(item.observation_id for item in observations if item.observation_id not in grouped_ids)
        ),
    )


def _healthy(source_id: str = "fixture.primary") -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id=source_id,
        as_of=AS_OF - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def test_window_math_and_ranking_are_frozen() -> None:
    accelerating = [
        _observation("a0", AS_OF - timedelta(hours=15)),
        _observation("a1", AS_OF - timedelta(hours=9)),
        _observation("a2", AS_OF - timedelta(hours=5)),
        _observation("a3", AS_OF - timedelta(hours=3)),
        _observation("a4", AS_OF - timedelta(minutes=30)),
    ]
    cooling = [
        _observation("c0", AS_OF - timedelta(hours=16)),
        _observation("c1", AS_OF - timedelta(hours=14)),
        _observation("c2", AS_OF - timedelta(hours=11)),
        _observation("c3", AS_OF - timedelta(hours=9)),
        _observation("c4", AS_OF - timedelta(hours=7)),
        _observation("c5", AS_OF - timedelta(hours=2)),
    ]
    observations = accelerating + cooling
    projection = _projection(
        observations,
        grouped=(
            tuple(item.observation_id for item in accelerating),
            tuple(item.observation_id for item in cooling),
        ),
    )
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=AS_OF,
    )
    first, second = snapshot.episodes
    assert first.observation_ids == tuple(sorted(item.observation_id for item in accelerating))
    assert (first.mentions_6h, first.previous_6h, first.preprevious_6h) == (3, 1, 1)
    assert (first.velocity_6h_delta, first.acceleration_6h) == (2, 2)
    assert (second.mentions_6h, second.previous_6h, second.preprevious_6h) == (1, 3, 2)
    assert (second.velocity_6h_delta, second.acceleration_6h) == (-2, -3)


def test_backfill_and_recovered_backlog_do_not_drive_live_activity() -> None:
    observations = [
        _observation("live", AS_OF - timedelta(minutes=30)),
        _observation("backfill", AS_OF - timedelta(minutes=20), reason="BACKFILL"),
        _observation("recovered-a", AS_OF - timedelta(minutes=15), recovered_after_gap=True),
        _observation(
            "recovered-b",
            AS_OF - timedelta(minutes=10),
            reason="DISCOVERY",
            recovered_after_gap=True,
        ),
    ]
    projection = _projection(
        observations, grouped=(tuple(item.observation_id for item in observations),)
    )
    episode = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=AS_OF,
    ).episodes[0]
    assert episode.evidence_count_total == 4
    assert episode.prospective_evidence_count == 1
    assert episode.backfill_evidence_count == 1
    assert episode.recovered_backlog_evidence_count == 2
    assert episode.mentions_1h == 1
    assert episode.mentions_6h == 1


def test_future_observation_is_excluded_before_metrics() -> None:
    known = _observation("known", AS_OF - timedelta(minutes=1))
    future = _observation("future", AS_OF + timedelta(minutes=1))
    projection = GroupingProjection(
        as_of=AS_OF,
        groups=(),
        ambiguous_pairs=(),
        ungrouped_observation_ids=(known.observation_id,),
    )
    snapshot = build_baseline_snapshot(
        (future, known),
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=AS_OF,
    )
    assert len(snapshot.episodes) == 1
    assert snapshot.episodes[0].observation_ids == (known.observation_id,)
    assert snapshot.episodes[0].mentions_1h == 1


def test_health_degradation_and_missing_health_are_explicit() -> None:
    health = (
        _healthy("source.a"),
        BaselineHealthInput(
            source_id="source.b",
            as_of=AS_OF - timedelta(minutes=1),
            transport=HealthValue.FAILED,
            freshness=HealthValue.UNKNOWN,
            completeness=HealthValue.DEGRADED,
            schema=HealthValue.OK,
        ),
    )
    snapshot = build_baseline_snapshot(
        (),
        grouping_projection=_projection([]),
        enabled_source_ids=("source.a", "source.b"),
        health=health,
        as_of=AS_OF,
    )
    assert snapshot.transport_state is HealthValue.FAILED
    assert snapshot.freshness_state is HealthValue.UNKNOWN
    assert snapshot.coverage_state is HealthValue.DEGRADED
    assert snapshot.schema_state is HealthValue.OK

    missing = build_baseline_snapshot(
        (),
        grouping_projection=_projection([]),
        enabled_source_ids=("source.a", "source.b"),
        health=(_healthy("source.a"),),
        as_of=AS_OF,
    )
    assert missing.transport_state is HealthValue.UNKNOWN
    assert missing.freshness_state is HealthValue.UNKNOWN
    assert missing.coverage_state is HealthValue.UNKNOWN
    assert missing.schema_state is HealthValue.UNKNOWN


def test_source_diversity_never_becomes_confirmation() -> None:
    observations = [
        _observation("attention", AS_OF - timedelta(minutes=10), source_id="hn.frontpage", roles=("ATTENTION",)),
        _observation("discovery", AS_OF - timedelta(minutes=5), source_id="gdelt.frontier", roles=("DISCOVERY",)),
    ]
    projection = _projection(
        observations, grouped=(tuple(item.observation_id for item in observations),)
    )
    episode = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("hn.frontpage", "gdelt.frontier"),
        health=(),
        as_of=AS_OF,
    ).episodes[0]
    assert episode.source_count == 2
    assert episode.source_role_diversity == 2
    assert episode.evidence_root_diversity is None
    assert episode.confirmation == "UNAVAILABLE"


def test_snapshot_and_receipt_replay_ignore_generated_at() -> None:
    observation = _observation("replay", AS_OF - timedelta(minutes=5))
    observations = (observation,)
    projection = _projection(list(observations))
    snapshot_a = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=AS_OF,
    )
    snapshot_b = build_baseline_snapshot(
        reversed(observations),
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=AS_OF,
    )
    assert snapshot_a.to_canonical() == snapshot_b.to_canonical()
    assert snapshot_a.snapshot_id == snapshot_b.snapshot_id

    receipt_a = build_baseline_receipt(
        snapshot_a,
        observations=observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        generated_at=AS_OF + timedelta(seconds=1),
        source_registry_version=REGISTRY,
    )
    receipt_b = build_baseline_receipt(
        snapshot_b,
        observations=reversed(observations),
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        generated_at=AS_OF + timedelta(hours=1),
        source_registry_version=REGISTRY,
    )
    assert receipt_a.receipt_id == receipt_b.receipt_id
    assert receipt_a.output_digest == receipt_b.output_digest


def test_grouping_membership_mismatch_fails_closed() -> None:
    observation = _observation("orphan", AS_OF - timedelta(minutes=1))
    with pytest.raises(ValueError, match="disagree"):
        build_baseline_snapshot(
            (observation,),
            grouping_projection=_projection([]),
            enabled_source_ids=("fixture.primary",),
            health=(),
            as_of=AS_OF,
        )
