from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

from frontier.application.experimental_analysis import (
    produce_experimental_analysis,
    produce_trajectory_analysis,
)
from frontier.domain.advanced_intelligence import build_pef_artifact
from frontier.domain.digests import Digest
from frontier.domain.experimental_analysis import (
    EXPERIMENTAL_ANALYSIS_INTERPRETATION,
    ExperimentalAnalysisKind,
    ExperimentalAnalysisStatus,
    TrajectoryFrame,
    build_corroboration_artifact,
    build_entity_provenance_artifact,
    build_grouping_hypotheses_artifact,
    build_indicators_artifact,
    build_propagation_graph_artifact,
    build_trajectory_artifact,
    forbid_truth_keys,
    scan_truth_keys,
)
from frontier.domain.features import build_feature_vector_batch
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt

AS_OF = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
GENERATED_AT = AS_OF
REGISTRY = Digest("sha256:" + "2" * 64)
SOURCES = ("s.a", "s.ext", "s.pri")
SHARED_URL = "https://example.test/shared"


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    *,
    observed_at: datetime,
    source_id: str = "s.a",
    roles: tuple[str, ...] = ("PRIMARY_EMISSION",),
    canonical_url: str | None = None,
    kind: str = "DOCUMENT",
    first_reason: str = "SCHEDULED",
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id=source_id,
            source_item_key=label,
            kind=kind,
            observed_at=observed_at,
            canonical_url=canonical_url,
            title=f"Fixture {label} episode title",
            text=None,
            signal_roles=roles,
        ),
        first_reason=first_reason,
        recovered_after_gap=False,
    )


def _artifact_observation(
    label: str,
    *,
    observed_at: datetime,
    artifact_name: str,
    artifact_version: str,
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id="s.pri",
            source_item_key=label,
            kind="ARTIFACT",
            observed_at=observed_at,
            canonical_url=None,
            title=None,
            text=None,
            artifact_type="python",
            artifact_name=artifact_name,
            artifact_version=artifact_version,
            signal_roles=("DISCOVERY",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


def _healthy() -> tuple[BaselineHealthInput, ...]:
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


def _snapshot_and_receipt(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    eligible = [item for item in observations if item.observed_at <= AS_OF]
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_healthy(),
        as_of=AS_OF,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=_projection(eligible, grouped=grouped),
        enabled_source_ids=SOURCES,
        health=_healthy(),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    return snapshot, receipt


def _two_shared_url_episodes() -> tuple[list[BaselineObservationInput], dict[str, str]]:
    """Two singleton episodes, each holding one observation of the same URL."""
    observations = [
        _observation(
            "a1",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.pri",
            canonical_url=SHARED_URL,
        ),
        _observation(
            "b1",
            observed_at=AS_OF - timedelta(hours=1),
            source_id="s.ext",
            roles=("ATTENTION",),
            canonical_url=SHARED_URL,
        ),
    ]
    snapshot, _ = _snapshot_and_receipt(observations)
    return observations, {
        "a": _episode_id_of(snapshot, _obs_id("a1")),
        "b": _episode_id_of(snapshot, _obs_id("b1")),
    }


def _episode_id_of(snapshot: BaselineSnapshot, observation_id: str) -> str:
    for episode in snapshot.episodes:
        if observation_id in episode.observation_ids:
            return episode.episode_id
    raise AssertionError(f"{observation_id} not in snapshot")


def _as_list(value: object) -> list[object]:
    return cast(list[object], value)


def _as_map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True)


# --- GROUPING_HYPOTHESES ----------------------------------------------------


def test_grouping_merge_hypotheses_are_hypothesis_labelled_and_baseline_untouched() -> None:
    observations, ids = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_grouping_hypotheses_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.HYPOTHESIS
    assert artifact.kind is ExperimentalAnalysisKind.GROUPING_HYPOTHESES
    assert artifact.authority_state == "EXPERIMENTAL_SHADOW"
    merges = _as_list(artifact.payload["merge_hypotheses"])
    assert len(merges) == 1
    merge = _as_map(merges[0])
    assert merge["hypothesis_status"] == "HYPOTHESIS"
    assert _as_list(merge["reasons"]) == ["shared-canonical-url"]
    assert _as_list(merge["shared_canonical_urls"]) == [SHARED_URL]
    assert {merge["episode_a_id"], merge["episode_b_id"]} == {ids["a"], ids["b"]}
    assert str(artifact.payload["baseline_relationship"]).startswith(
        "EXPERIMENTAL_SUGGESTIONS_ONLY"
    )
    assert "groups" not in artifact.payload


def test_grouping_split_hypothesis_for_mixed_artifact_versions() -> None:
    observations = [
        _artifact_observation(
            "v1",
            observed_at=AS_OF - timedelta(hours=3),
            artifact_name="fixture-package",
            artifact_version="1.0",
        ),
        _artifact_observation(
            "v2",
            observed_at=AS_OF - timedelta(hours=2),
            artifact_name="fixture-package",
            artifact_version="2.0",
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("v1"), _obs_id("v2")),)
    )
    artifact = build_grouping_hypotheses_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    splits = _as_list(artifact.payload["split_hypotheses"])
    assert len(splits) == 1
    split = _as_map(splits[0])
    assert split["hypothesis_status"] == "HYPOTHESIS"
    assert _as_list(split["reasons"]) == ["mixed-artifact-versions"]
    assert _as_list(split["mixed_artifact_names"]) == ["fixture-package"]
    assert sorted(cast(list[str], split["observation_ids"])) == sorted(
        [_obs_id("v1"), _obs_id("v2")]
    )


def test_grouping_hypotheses_deterministic_and_digest_bound() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    first = build_grouping_hypotheses_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    second = build_grouping_hypotheses_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert first.to_canonical() == second.to_canonical()
    assert first.analysis_id == second.analysis_id
    assert first.analysis_id.startswith("expanalysis_")
    assert str(first.analysis_digest).startswith("sha256:")
    assert first.control_snapshot_id == snapshot.snapshot_id
    assert first.control_receipt_id == receipt.receipt_id


# --- ENTITY_PROVENANCE ------------------------------------------------------


def test_entity_provenance_never_claims_true_origin() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_entity_provenance_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.HYPOTHESIS
    provenance = _as_list(artifact.payload["provenance_hypotheses"])
    assert len(provenance) == 2
    for raw in provenance:
        entry = _as_map(raw)
        assert entry["hypothesis_status"] == "HYPOTHESIS"
        assert "NEVER a factual origin claim" in str(entry["origin_interpretation"])
        assert entry["earliest_observed_source_id"]
    assert not scan_truth_keys(artifact.to_canonical())


def test_entity_link_shared_url_within_window() -> None:
    observations, ids = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_entity_provenance_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    links = _as_list(artifact.payload["entity_links"])
    assert len(links) == 1
    link = _as_map(links[0])
    assert {link["episode_a_id"], link["episode_b_id"]} == {ids["a"], ids["b"]}
    assert _as_list(link["evidence_kinds"]) == ["shared-canonical-url"]
    assert link["min_observation_distance_seconds"] == 3600
    assert "never entity certainty" in str(link["same_entity_interpretation"])


# --- CORROBORATION ----------------------------------------------------------


def test_corroboration_descriptor_singleton_episodes_hand_computed() -> None:
    observations, ids = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_corroboration_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.DESCRIPTOR
    by_episode = {
        _as_map(entry)["episode_id"]: _as_map(entry)
        for entry in _as_list(artifact.payload["descriptors"])
    }
    episode_a = by_episode[ids["a"]]
    assert episode_a["distinct_source_count"] == 1
    assert episode_a["observation_count"] == 1
    assert episode_a["time_spread_seconds"] is None  # UNKNOWN, never coerced
    episode_b = by_episode[ids["b"]]
    assert episode_b["distinct_source_count"] == 1
    assert "cross-source multiplicity descriptor only" in str(artifact.payload["semantics"])


def test_corroboration_descriptor_two_sources_time_spread() -> None:
    observations = [
        _observation("x1", observed_at=AS_OF - timedelta(hours=2), source_id="s.pri"),
        _observation(
            "x2",
            observed_at=AS_OF - timedelta(hours=1),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("x1"), _obs_id("x2")),)
    )
    artifact = build_corroboration_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    entry = _as_map(_as_list(artifact.payload["descriptors"])[0])
    assert entry["distinct_source_count"] == 2
    assert entry["lane_diversity"] == 2
    assert entry["time_spread_seconds"] == 3600


def test_forbidden_mapping_structurally_impossible() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_corroboration_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    text = json_text(artifact.to_canonical())
    assert "independent_confirmation" not in text
    assert not scan_truth_keys(artifact.to_canonical())
    with pytest.raises(ValueError):
        forbid_truth_keys({"descriptors": [{"independent_confirmation": 3}]})
    with pytest.raises(ValueError):
        forbid_truth_keys({"nested": [{"confirmed_by": ["x"]}]})
    assert not scan_truth_keys({"safe": [{"unrelated": [1, None, "x"]}]})
    with pytest.raises(ValueError):
        forbid_truth_keys({"nested": [{"confirmation_count": 2}]})


# --- PROPAGATION_GRAPH ------------------------------------------------------


def test_propagation_graph_hand_computed() -> None:
    observations = [
        _observation("p1", observed_at=AS_OF - timedelta(hours=2), source_id="s.pri"),
        _observation(
            "p2",
            observed_at=AS_OF - timedelta(hours=1),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("p1"), _obs_id("p2")),)
    )
    artifact = build_propagation_graph_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.DESCRIPTOR
    nodes = _as_list(artifact.payload["nodes"])
    assert {_as_map(node)["node_id"] for node in nodes} == {
        "s.ext#ATTENTION",
        "s.pri#PRIMARY_EMISSION",
    }
    edges = _as_list(artifact.payload["edges"])
    assert len(edges) == 1
    edge = _as_map(edges[0])
    assert edge["from_node_id"] == "s.pri#PRIMARY_EMISSION"
    assert edge["to_node_id"] == "s.ext#ATTENTION"
    assert edge["count"] == 1
    assert _as_list(edge["episode_ids"]) == [snapshot.episodes[0].episode_id]
    assert artifact.payload["window_seconds"] == 86400


def test_propagation_graph_self_loop_same_source() -> None:
    observations = [
        _observation("l1", observed_at=AS_OF - timedelta(minutes=50)),
        _observation("l2", observed_at=AS_OF - timedelta(minutes=40)),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("l1"), _obs_id("l2")),)
    )
    artifact = build_propagation_graph_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    edges = _as_list(artifact.payload["edges"])
    assert len(edges) == 1
    edge = _as_map(edges[0])
    assert edge["from_node_id"] == "s.a#PRIMARY_EMISSION"
    assert edge["to_node_id"] == "s.a#PRIMARY_EMISSION"
    assert edge["count"] == 1


# --- INDICATORS -------------------------------------------------------------


def test_indicators_unknown_propagation_and_no_verdicts() -> None:
    observations = [
        _observation(
            "bk",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.ext",
            first_reason="BACKFILL",
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(observations)
    artifact = build_indicators_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.INDICATORS
    assert artifact.kind is ExperimentalAnalysisKind.INDICATORS
    assert artifact.payload["verdict_policy"] == "INDICATORS_ONLY_NEVER_A_MANIPULATION_VERDICT"
    entry = _as_map(_as_list(artifact.payload["episodes"])[0])
    assert entry["indicator_status"] == "INDICATORS"
    indicators = _as_list(entry["indicators"])
    assert [_as_map(indicator)["name"] for indicator in indicators] == [
        "burst_rate_excess",
        "same_source_adjacency",
        "identical_timing_gap_run",
    ]
    for raw in indicators:
        indicator = _as_map(raw)
        assert indicator["status"] == "UNKNOWN"
        assert indicator["value"] is None
    assert not scan_truth_keys(artifact.to_canonical())
    text = json_text(artifact.to_canonical())
    assert "manipulation_verdict" not in text


def test_indicators_burst_excess_hand_computed() -> None:
    observations = [
        _observation("c1", observed_at=AS_OF - timedelta(hours=2), source_id="s.pri"),
        _observation(
            "c2",
            observed_at=AS_OF - timedelta(minutes=30),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("c1"), _obs_id("c2")),)
    )
    artifact = build_indicators_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    indicators = {
        _as_map(indicator)["name"]: _as_map(indicator)
        for indicator in _as_list(_as_map(_as_list(artifact.payload["episodes"])[0])["indicators"])
    }
    # windowed count = 2; last hour = 1; expected = 2 * 3600 // 86400 = 0
    assert indicators["burst_rate_excess"]["value"] == 1
    assert indicators["burst_rate_excess"]["status"] == "OBSERVED"
    assert indicators["same_source_adjacency"]["value"] == 0
    # fewer than 3 windowed observations: timing regularity is UNKNOWN
    assert indicators["identical_timing_gap_run"]["status"] == "UNKNOWN"
    assert indicators["identical_timing_gap_run"]["value"] is None


def test_indicators_identical_gap_run_hand_computed() -> None:
    observations = [
        _observation("g1", observed_at=AS_OF - timedelta(minutes=90), source_id="s.pri"),
        _observation(
            "g2",
            observed_at=AS_OF - timedelta(minutes=60),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
        _observation("g3", observed_at=AS_OF - timedelta(minutes=30)),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations,
        grouped=((_obs_id("g1"), _obs_id("g2"), _obs_id("g3")),),
    )
    artifact = build_indicators_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    indicators = {
        _as_map(indicator)["name"]: _as_map(indicator)
        for indicator in _as_list(_as_map(_as_list(artifact.payload["episodes"])[0])["indicators"])
    }
    # gaps 1800s, 1800s: longest identical-gap run length = 2
    assert indicators["identical_timing_gap_run"]["value"] == 2


# --- TRAJECTORY -------------------------------------------------------------


def test_trajectory_projection_deterministic_and_labelled() -> None:
    observations = [
        _observation("t1", observed_at=AS_OF - timedelta(hours=3), source_id="s.pri"),
        _observation(
            "t2",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("t1"), _obs_id("t2")),)
    )
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    pef = build_pef_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    artifact = build_trajectory_artifact(
        (TrajectoryFrame(feature_batch=batch, pef_artifact=pef),),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert artifact.status is ExperimentalAnalysisStatus.PROJECTION
    assert artifact.kind is ExperimentalAnalysisKind.TRAJECTORY
    assert artifact.authority_state == "EXPERIMENTAL_SHADOW"
    assert artifact.control_snapshot_id is None
    assert artifact.control_receipt_id is None
    assert artifact.interpretation == EXPERIMENTAL_ANALYSIS_INTERPRETATION
    trajectory = _as_map(_as_list(artifact.payload["trajectories"])[0])
    points = _as_list(trajectory["points"])
    assert len(points) == 1
    point = _as_map(points[0])
    assert point["candidate_rank"] == 1
    assert set(_as_map(point["values"])) == {
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
    }
    again = build_trajectory_artifact(
        (TrajectoryFrame(feature_batch=batch, pef_artifact=pef),),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert again.to_canonical() == artifact.to_canonical()
    assert again.analysis_id == artifact.analysis_id


def test_trajectory_frames_must_be_strictly_ordered() -> None:
    observations = [
        _observation("o1", observed_at=AS_OF - timedelta(hours=3), source_id="s.pri"),
    ]
    snapshot, receipt = _snapshot_and_receipt(observations)
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    with pytest.raises(ValueError):
        build_trajectory_artifact(
            (TrajectoryFrame(feature_batch=batch), TrajectoryFrame(feature_batch=batch)),
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )


# --- point-in-time and eligibility ------------------------------------------


def test_point_in_time_future_observations_excluded() -> None:
    observations = [
        _observation("f1", observed_at=AS_OF, source_id="s.pri"),
        _observation(
            "f2",
            observed_at=AS_OF + timedelta(hours=1),
            source_id="s.ext",
            roles=("ATTENTION",),
        ),
    ]
    # The snapshot only covers eligible evidence; the future observation is
    # part of no episode and must never enter any analysis payload (R1).
    snapshot, receipt = _snapshot_and_receipt([observations[0]])
    artifact = build_corroboration_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    entry = _as_map(_as_list(artifact.payload["descriptors"])[0])
    assert entry["observation_count"] == 1
    assert _as_list(entry["source_ids"]) == ["s.pri"]


def test_backfill_never_feeds_descriptors() -> None:
    observations = [
        _observation(
            "bf1",
            observed_at=AS_OF - timedelta(hours=2),
            source_id="s.ext",
            first_reason="BACKFILL",
        ),
        _observation("bf2", observed_at=AS_OF - timedelta(hours=1), source_id="s.pri"),
    ]
    snapshot, receipt = _snapshot_and_receipt(
        observations, grouped=((_obs_id("bf1"), _obs_id("bf2")),)
    )
    artifact = build_corroboration_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    entry = _as_map(_as_list(artifact.payload["descriptors"])[0])
    # Only the prospective-eligible member feeds the descriptor (R3).
    assert entry["observation_count"] == 1
    assert _as_list(entry["source_ids"]) == ["s.pri"]


# --- application service ----------------------------------------------------


def test_produce_experimental_analysis_all_snapshot_bound_kinds() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    for kind in (
        ExperimentalAnalysisKind.GROUPING_HYPOTHESES,
        ExperimentalAnalysisKind.ENTITY_PROVENANCE,
        ExperimentalAnalysisKind.CORROBORATION,
        ExperimentalAnalysisKind.PROPAGATION_GRAPH,
        ExperimentalAnalysisKind.INDICATORS,
    ):
        run = produce_experimental_analysis(
            observations,
            kind=kind,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )
        assert run.artifact.kind is kind
        assert run.artifact.authority_state == "EXPERIMENTAL_SHADOW"
        assert not scan_truth_keys(run.artifact.to_canonical())


def test_produce_experimental_analysis_rejects_trajectory_kind() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    with pytest.raises(ValueError):
        produce_experimental_analysis(
            observations,
            kind=ExperimentalAnalysisKind.TRAJECTORY,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )


def test_produce_experimental_analysis_fail_closed_on_unbound_receipt() -> None:
    observations, _ = _two_shared_url_episodes()
    other_observations = [
        _observation("z1", observed_at=AS_OF - timedelta(hours=1), source_id="s.pri"),
    ]
    snapshot, _ = _snapshot_and_receipt(observations)
    _, unrelated_receipt = _snapshot_and_receipt(other_observations)
    with pytest.raises(ValueError):
        produce_experimental_analysis(
            observations,
            kind=ExperimentalAnalysisKind.CORROBORATION,
            control_snapshot=snapshot,
            control_receipt=unrelated_receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )


def test_produce_trajectory_analysis_via_application() -> None:
    observations = [
        _observation("s1", observed_at=AS_OF - timedelta(hours=3), source_id="s.pri"),
    ]
    snapshot, receipt = _snapshot_and_receipt(observations)
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    run = produce_trajectory_analysis(
        (TrajectoryFrame(feature_batch=batch),),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert run.artifact.kind is ExperimentalAnalysisKind.TRAJECTORY
    assert run.artifact.status is ExperimentalAnalysisStatus.PROJECTION
    assert not scan_truth_keys(run.artifact.to_canonical())


# --- no-truth-labelling scan over every kind --------------------------------


def test_no_truth_labelling_keys_in_any_kind() -> None:
    observations, _ = _two_shared_url_episodes()
    snapshot, receipt = _snapshot_and_receipt(observations)
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    artifacts = [
        build_grouping_hypotheses_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
        build_entity_provenance_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
        build_corroboration_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
        build_propagation_graph_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
        build_indicators_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
        build_trajectory_artifact(
            (TrajectoryFrame(feature_batch=batch),),
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        ),
    ]
    for artifact in artifacts:
        assert not scan_truth_keys(artifact.to_canonical())
        text = json_text(artifact.to_canonical())
        assert "independent_confirmation" not in text
        assert "true_origin" not in text
        assert "manipulation_verdict" not in text
