from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    PEF_PREREGISTERED_CONFIG_DIGEST,
    PefArtifact,
    PefArtifactStatus,
    build_pef_artifact,
    build_pef_ranking,
    build_pef_receipt,
    failed_pef_artifact,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
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

ROOT = Path(__file__).resolve().parents[2]
PREREGISTRATION_PATH = (
    ROOT / "experiments" / "advanced_intelligence" / "pef_v0" / "preregistration.json"
)
AS_OF = datetime(2026, 9, 5, 12, tzinfo=UTC)
GENERATED_AT = AS_OF
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
            sorted(
                item.observation_id
                for item in observations
                if item.observation_id not in grouped_ids
            )
        ),
    )


def _healthy() -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id="fixture.primary",
        as_of=AS_OF - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def _control(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
) -> BaselineSnapshot:
    eligible = [item for item in observations if item.observed_at <= as_of]
    return build_baseline_snapshot(
        observations,
        grouping_projection=_projection(eligible, grouped=grouped, as_of=as_of),
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        as_of=as_of,
    )


def _receipt(
    snapshot: BaselineSnapshot,
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
) -> ProjectionReceipt:
    eligible = [item for item in observations if item.observed_at <= as_of]
    return build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=_projection(eligible, grouped=grouped, as_of=as_of),
        enabled_source_ids=("fixture.primary",),
        health=(_healthy(),),
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )


def _artifact(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
    generated_at: datetime = GENERATED_AT,
    registry: Digest = REGISTRY,
) -> tuple[BaselineSnapshot, ProjectionReceipt, PefArtifact]:
    snapshot = _control(observations, grouped=grouped, as_of=as_of)
    receipt = _receipt(snapshot, observations, grouped=grouped, as_of=as_of)
    artifact = build_pef_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=as_of,
        generated_at=generated_at,
        source_registry_version=registry,
    )
    return snapshot, receipt, artifact


def test_configuration_digest_is_frozen_to_preregistration() -> None:
    document = json.loads(PREREGISTRATION_PATH.read_text(encoding="utf-8"))
    preregistered_digest = sha256_digest(
        canonical_json_bytes(document["candidate"]["configuration"])
    )
    assert preregistered_digest == PEF_CONFIGURATION_DIGEST
    assert PEF_CONFIGURATION_DIGEST == PEF_PREREGISTERED_CONFIG_DIGEST
    assert PEF_CONFIGURATION["algorithm_version"] == PEF_ALGORITHM_VERSION
    assert PEF_AUTHORITY_STATE == "EXPERIMENTAL_SHADOW"
    assert PEF_CANDIDATE_ID == "prospective-primary-emission-freshness-v0"
    assert PEF_EXPERIMENT_ID == "advanced-ranking-pef-v0"


def test_features_are_computed_from_prospective_members_only() -> None:
    observations = [
        _observation("live", AS_OF - timedelta(minutes=1)),
        _observation("backfill", AS_OF - timedelta(minutes=2), reason="BACKFILL"),
        _observation("recovered", AS_OF - timedelta(minutes=3), recovered_after_gap=True),
        _observation(
            "attention",
            AS_OF - timedelta(minutes=4),
            source_id="hn.frontpage",
            roles=("ATTENTION",),
        ),
    ]
    grouped = (tuple(item.observation_id for item in observations),)
    snapshot = _control(observations, grouped=grouped)
    ranking = build_pef_ranking(observations, control_snapshot=snapshot, as_of=AS_OF)
    assert len(ranking) == 1
    episode = ranking[0]
    assert episode.prospective_evidence_count == 2
    assert episode.has_any_prospective_evidence is True
    assert episode.has_prospective_primary_emission is True
    assert episode.prospective_last_observed_at == AS_OF - timedelta(minutes=1)
    assert episode.prospective_age_seconds == 60
    assert episode.prospective_source_role_diversity == 2


def test_no_prospective_evidence_sorts_after_any_prospective_evidence() -> None:
    busy = [
        _observation("busy-0", AS_OF - timedelta(minutes=5)),
        _observation("busy-1", AS_OF - timedelta(minutes=2), reason="BACKFILL"),
    ]
    dormant = [_observation("dormant", AS_OF - timedelta(minutes=1), reason="BACKFILL")]
    observations = busy + dormant
    grouped = (
        tuple(item.observation_id for item in busy),
        (dormant[0].observation_id,),
    )
    snapshot = _control(observations, grouped=grouped)
    ranking = build_pef_ranking(observations, control_snapshot=snapshot, as_of=AS_OF)
    assert ranking[0].has_any_prospective_evidence is True
    assert ranking[1].has_any_prospective_evidence is False
    assert ranking[1].prospective_evidence_count == 0
    assert ranking[1].prospective_age_seconds is None
    assert ranking[1].prospective_last_observed_at is None
    assert ranking[1].prospective_source_role_diversity == 0


def test_ranking_follows_preregistered_lexicographic_order() -> None:
    # episode-primary: prospective PRIMARY_EMISSION (wins on first key).
    primary = [_observation("primary", AS_OF - timedelta(minutes=2))]
    # episode-fresh: prospective ATTENTION only, fresher but no primary emission.
    fresh = [
        _observation(
            "fresh-0",
            AS_OF - timedelta(minutes=1),
            source_id="hn.frontpage",
            roles=("ATTENTION",),
        )
    ]
    # episode-faster: no primary emission, higher velocity/mentions, older age.
    faster = [
        _observation("faster-0", AS_OF - timedelta(hours=2), roles=("DISCOVERY",)),
        _observation("faster-1", AS_OF - timedelta(hours=1), roles=("DISCOVERY",)),
        _observation(
            "faster-2",
            AS_OF - timedelta(minutes=30),
            source_id="hn.frontpage",
            roles=("ATTENTION",),
        ),
    ]
    observations = primary + fresh + faster
    grouped = (
        (primary[0].observation_id,),
        (fresh[0].observation_id,),
        tuple(item.observation_id for item in faster),
    )
    snapshot = _control(observations, grouped=grouped)
    ranking = build_pef_ranking(observations, control_snapshot=snapshot, as_of=AS_OF)
    primary_ids = {primary[0].observation_id}
    fresh_ids = {fresh[0].observation_id}
    faster_ids = {item.observation_id for item in faster}
    ordered_ids = [set(episode.observation_ids) for episode in ranking]
    assert ordered_ids == [primary_ids, fresh_ids, faster_ids]
    assert [episode.rank for episode in ranking] == [1, 2, 3]


def test_identical_features_tie_break_on_episode_id() -> None:
    left = [_observation("left", AS_OF - timedelta(minutes=1))]
    right = [_observation("right", AS_OF - timedelta(minutes=1))]
    observations = left + right
    grouped = (
        (left[0].observation_id,),
        (right[0].observation_id,),
    )
    snapshot = _control(observations, grouped=grouped)
    ranking = build_pef_ranking(observations, control_snapshot=snapshot, as_of=AS_OF)
    # Identical features: the lexicographically smaller episode_id wins deterministically.
    assert ranking[0].episode_id < ranking[1].episode_id
    assert ranking[0].prospective_age_seconds == ranking[1].prospective_age_seconds == 60


def test_same_inputs_produce_identical_artifact_and_digest() -> None:
    observations = [
        _observation("a", AS_OF - timedelta(minutes=1)),
        _observation("b", AS_OF - timedelta(hours=1)),
        _observation("c", AS_OF - timedelta(minutes=2), reason="DISCOVERY"),
    ]
    grouped = (tuple(item.observation_id for item in observations),)
    snapshot = _control(observations, grouped=grouped)
    receipt = _receipt(snapshot, observations, grouped=grouped)
    artifact_a = build_pef_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=AS_OF,
        generated_at=AS_OF + timedelta(seconds=1),
        source_registry_version=REGISTRY,
    )
    artifact_b = build_pef_artifact(
        reversed(observations),
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=AS_OF,
        generated_at=AS_OF + timedelta(hours=1),
        source_registry_version=REGISTRY,
    )
    assert artifact_a.to_canonical() == artifact_b.to_canonical()
    assert artifact_a.artifact_id == artifact_b.artifact_id
    assert artifact_a.output_digest == artifact_b.output_digest

    receipt_a = build_pef_receipt(artifact_a, observations=observations, control_snapshot=snapshot)
    receipt_b = build_pef_receipt(
        artifact_b, observations=reversed(observations), control_snapshot=snapshot
    )
    assert receipt_a.receipt_id == receipt_b.receipt_id
    assert receipt_a.output_digest == artifact_a.output_digest


def test_artifact_binds_control_snapshot_and_receipt_identity() -> None:
    observations = [_observation("bound", AS_OF - timedelta(minutes=1))]
    snapshot, receipt, artifact = _artifact(observations)
    assert artifact.control_snapshot_id == snapshot.snapshot_id
    assert artifact.control_receipt_id == receipt.receipt_id
    assert artifact.status is PefArtifactStatus.RAN
    assert artifact.failure_reason is None
    canonical = artifact.to_canonical()
    assert canonical["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert canonical["status"] == "RAN"
    assert canonical["candidate_id"] == PEF_CANDIDATE_ID
    assert canonical["configuration_digest"] == str(PEF_CONFIGURATION_DIGEST)
    assert "score" not in canonical
    for episode in artifact.episodes:
        assert "score" not in episode.to_canonical()


def test_future_observations_never_enter_features() -> None:
    known = _observation("known", AS_OF - timedelta(minutes=1))
    future = _observation("future", AS_OF + timedelta(minutes=1))
    snapshot, _, artifact = _artifact([known, future])
    assert len(artifact.episodes) == 1
    assert artifact.episodes[0].prospective_evidence_count == 1
    assert artifact.episodes[0].observation_ids == (known.observation_id,)
    assert snapshot.episodes[0].prospective_evidence_count == 1


def test_status_semantics_fail_closed() -> None:
    observations = [_observation("status", AS_OF - timedelta(minutes=1))]
    snapshot, receipt, artifact = _artifact(observations)
    assert artifact.status is PefArtifactStatus.RAN
    ran_receipt = build_pef_receipt(artifact, observations=observations, control_snapshot=snapshot)
    assert ran_receipt.status is ProjectionStatus.COMPLETE

    failed = failed_pef_artifact(
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
        failure_reason="evaluation halted before ranking",
    )
    assert failed.status is PefArtifactStatus.FAILED
    assert failed.episodes == ()
    assert failed.failure_reason == "evaluation halted before ranking"
    failed_receipt = build_pef_receipt(failed, observations=observations, control_snapshot=snapshot)
    assert failed_receipt.status is ProjectionStatus.FAILED

    with pytest.raises(ValueError, match="failure reason"):
        PefArtifact(
            as_of=AS_OF,
            control_snapshot_id=snapshot.snapshot_id,
            control_receipt_id=receipt.receipt_id,
            source_registry_version=REGISTRY,
            generated_at=GENERATED_AT,
            status=PefArtifactStatus.FAILED,
        )
    with pytest.raises(ValueError, match="failure reason"):
        PefArtifact(
            as_of=AS_OF,
            control_snapshot_id=snapshot.snapshot_id,
            control_receipt_id=receipt.receipt_id,
            source_registry_version=REGISTRY,
            generated_at=GENERATED_AT,
            status=PefArtifactStatus.RAN,
            failure_reason="not allowed",
        )
    not_run = PefArtifact(
        as_of=AS_OF,
        control_snapshot_id=snapshot.snapshot_id,
        control_receipt_id=receipt.receipt_id,
        source_registry_version=REGISTRY,
        generated_at=GENERATED_AT,
        status=PefArtifactStatus.NOT_RUN,
    )
    with pytest.raises(ValueError, match="NOT_RUN"):
        build_pef_receipt(not_run, observations=observations, control_snapshot=snapshot)


def test_control_mismatch_fails_closed() -> None:
    observations = [_observation("mismatch", AS_OF - timedelta(minutes=1))]
    snapshot, receipt, _ = _artifact(observations)
    later = AS_OF + timedelta(minutes=5)
    with pytest.raises(ValueError, match="as_of"):
        build_pef_ranking(observations, control_snapshot=snapshot, as_of=later)

    incomplete_receipt = replace(receipt, status=ProjectionStatus.FAILED)
    with pytest.raises(ValueError, match="COMPLETE"):
        build_pef_artifact(
            observations,
            control_snapshot=snapshot,
            control_receipt=incomplete_receipt,
            as_of=AS_OF,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
        )

    drifted_registry = build_pef_artifact(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        source_registry_version=Digest("sha256:" + "2" * 64),
    )
    assert drifted_registry.source_registry_version != receipt.source_registry_version


def test_output_digest_and_artifact_id_are_canonical_material() -> None:
    observations = [_observation("digest", AS_OF - timedelta(minutes=1))]
    _, _, artifact = _artifact(observations)
    material = canonical_json_bytes(artifact.to_canonical())
    expected_digest = sha256_digest(material)
    assert artifact.output_digest == expected_digest
    assert artifact.artifact_id == "artifact_" + sha256(material).hexdigest()
    assert artifact.artifact_id != "artifact_" + sha256(expected_digest.value.encode()).hexdigest()
