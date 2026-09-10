from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    PefEpisodeRanking,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.grouping import GroupingInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import BaselineObservationInput
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus
from frontier.domain.zero_day import (
    ZeroDayFollowOnEvidence,
    ZeroDayGradeStatus,
    ZeroDayMemberStatus,
    ZeroDayPefPersistenceBinding,
    build_zero_day_grade,
    build_zero_day_seal,
)

AS_OF = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)
DIGEST_A = Digest("sha256:" + "a" * 64)
FREEZE_ID = "freezereceipt_" + "b" * 64


def _observation(
    suffix: str,
    *,
    roles: tuple[str, ...] = ("PRIMARY_EMISSION",),
    observed_at: datetime = AS_OF - timedelta(minutes=5),
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=f"obs_{suffix}",
            source_id=f"source.{suffix}",
            source_item_key=suffix,
            kind="TEST",
            observed_at=observed_at,
            canonical_url=None,
            title=suffix,
            text=None,
            signal_roles=roles,
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


def _ranking(
    rank: int,
    suffix: str,
    *,
    primary: bool = True,
) -> PefEpisodeRanking:
    return PefEpisodeRanking(
        rank=rank,
        episode_id=f"episode_{suffix}",
        observation_ids=(f"obs_{suffix}",),
        has_any_prospective_evidence=True,
        has_prospective_primary_emission=primary,
        prospective_last_observed_at=AS_OF - timedelta(minutes=5),
        prospective_age_seconds=300,
        prospective_source_role_diversity=1,
        prospective_evidence_count=1,
        mentions_1h=1,
        mentions_6h=1,
        mentions_24h=1,
        velocity_6h_delta=0,
        acceleration_6h=0,
    )


def _pair() -> tuple[PefV1Artifact, ShadowExperimentRun, tuple[BaselineObservationInput, ...]]:
    episodes = (
        _ranking(1, "a"),
        _ranking(2, "b"),
        _ranking(3, "c"),
        _ranking(4, "d", primary=False),
    )
    artifact = PefV1Artifact(
        as_of=AS_OF,
        control_snapshot_id="snapshot_control",
        control_receipt_id="receipt_control",
        source_registry_version=DIGEST_A,
        generated_at=AS_OF,
        episodes=episodes,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        grouping_receipt_id="receipt_grouping",
    )
    control = (
        ShadowControlArmRanking(rank=4, episode_id="episode_a"),
        ShadowControlArmRanking(rank=3, episode_id="episode_b"),
        ShadowControlArmRanking(rank=1, episode_id="episode_c"),
        ShadowControlArmRanking(rank=2, episode_id="episode_d"),
    )
    run = ShadowExperimentRun(
        as_of=AS_OF,
        generated_at=AS_OF,
        control_snapshot_id=artifact.control_snapshot_id,
        control_receipt_id=artifact.control_receipt_id,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=ShadowRunStatus.RAN,
        episode_universe_digest=DIGEST_A,
        candidate_artifact_id=artifact.artifact_id,
        candidate_output_digest=artifact.output_digest,
        control_ranking=control,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        candidate_freeze_receipt_id=FREEZE_ID,
    )
    observations = (
        _observation("a"),
        _observation("b", roles=("PRIMARY_EMISSION", "ATTENTION")),
        _observation("c"),
        _observation("d"),
    )
    return artifact, run, observations


def _input_digest(
    artifact: PefV1Artifact,
    observations: tuple[BaselineObservationInput, ...],
) -> Digest:
    observation_values: list[CanonicalValue] = [
        item.to_canonical() for item in sorted(observations, key=lambda item: item.observation_id)
    ]
    material: dict[str, CanonicalValue] = {
        "control_snapshot_id": artifact.control_snapshot_id,
        "observations": observation_values,
    }
    return sha256_digest(canonical_json_bytes(material))


def _persistence(
    artifact: PefV1Artifact,
    observations: tuple[BaselineObservationInput, ...],
    *,
    persisted_at: datetime = AS_OF + timedelta(seconds=30),
) -> ZeroDayPefPersistenceBinding:
    receipt = ProjectionReceipt(
        receipt_schema_version=PEF_RECEIPT_SCHEMA_VERSION,
        projection_name=PEF_V1_PROJECTION_NAME,
        projection_version=PEF_V1_PROJECTION_VERSION,
        schema_version=PEF_SCHEMA_VERSION,
        algorithm_version=PEF_ALGORITHM_VERSION,
        ranking_policy_version=PEF_RANKING_POLICY_VERSION,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        source_registry_version=artifact.source_registry_version,
        as_of=artifact.as_of,
        generated_at=artifact.generated_at,
        input_digest=_input_digest(artifact, observations),
        output_digest=artifact.output_digest,
        status=ProjectionStatus.COMPLETE,
    )
    return ZeroDayPefPersistenceBinding(
        candidate_receipt=receipt,
        artifact_receipt_id=receipt.receipt_id,
        artifact_persisted_at=persisted_at,
        candidate_receipt_persisted_at=persisted_at,
        run_persisted_at=persisted_at,
    )


def _seal(
    artifact: PefV1Artifact,
    run: ShadowExperimentRun,
    observations: tuple[BaselineObservationInput, ...],
    *,
    persistence: ZeroDayPefPersistenceBinding | None = None,
    sealed_at: datetime = AS_OF + timedelta(minutes=1),
):
    return build_zero_day_seal(
        artifact,
        run,
        observations,
        _persistence(artifact, observations) if persistence is None else persistence,
        run_class="CONFIRMATORY",
        sealed_at=sealed_at,
    )


def test_seal_uses_candidate_order_and_excludes_attention_and_control_losses() -> None:
    artifact, run, observations = _pair()

    seal = _seal(artifact, run, observations)

    assert [item.episode_id for item in seal.candidates] == ["episode_a"]
    assert seal.candidates[0].candidate_rank == 1
    assert seal.candidates[0].control_rank == 4
    assert seal.candidates[0].rank_advantage == 3
    assert seal.authority_state == "DIAGNOSTIC_ONLY"
    assert seal.candidate_receipt_id.startswith("receipt_")
    assert seal.candidate_input_digest == _input_digest(artifact, observations)


def test_seal_identity_is_deterministic() -> None:
    artifact, run, observations = _pair()
    persistence = _persistence(artifact, observations)

    first = _seal(
        artifact,
        run,
        observations,
        persistence=persistence,
    )
    second = build_zero_day_seal(
        artifact,
        run,
        reversed(observations),
        persistence,
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )

    assert first.to_canonical() == second.to_canonical()
    assert first.seal_id == second.seal_id
    assert first.seal_digest == second.seal_digest


def test_seal_rejects_manual_non_six_hour_boundary() -> None:
    artifact, run, observations = _pair()
    bad_as_of = AS_OF + timedelta(minutes=5)
    artifact = replace(artifact, as_of=bad_as_of, generated_at=bad_as_of)
    run = replace(
        run,
        as_of=bad_as_of,
        generated_at=bad_as_of,
        candidate_artifact_id=artifact.artifact_id,
        candidate_output_digest=artifact.output_digest,
    )
    persistence = _persistence(
        artifact,
        observations,
        persisted_at=bad_as_of + timedelta(seconds=30),
    )

    with pytest.raises(ValueError, match="6-hour UTC boundary"):
        build_zero_day_seal(
            artifact,
            run,
            observations,
            persistence,
            run_class="CONFIRMATORY",
            sealed_at=bad_as_of + timedelta(minutes=1),
        )


def test_seal_rejects_retrospective_creation_after_live_window() -> None:
    artifact, run, observations = _pair()

    with pytest.raises(ValueError, match="30-minute live sealing window"):
        _seal(
            artifact,
            run,
            observations,
            sealed_at=AS_OF + timedelta(minutes=31),
        )


def test_seal_rejects_source_rows_not_persisted_by_claimed_seal() -> None:
    artifact, run, observations = _pair()
    persistence = replace(
        _persistence(artifact, observations),
        run_persisted_at=AS_OF + timedelta(minutes=31),
    )

    with pytest.raises(ValueError, match="shadow run was not persisted by sealed_at"):
        _seal(
            artifact,
            run,
            observations,
            persistence=persistence,
            sealed_at=AS_OF + timedelta(minutes=1),
        )


def test_seal_binds_exact_persisted_pef_input_not_only_observation_ids() -> None:
    artifact, run, observations = _pair()
    persistence = _persistence(artifact, observations)
    substituted = tuple(
        _observation("b", roles=("PRIMARY_EMISSION",)) if item.observation_id == "obs_b" else item
        for item in observations
    )

    with pytest.raises(ValueError, match="persisted PEF_V1 input digest"):
        _seal(
            artifact,
            run,
            substituted,
            persistence=persistence,
        )


def test_seal_fails_closed_when_persisted_input_is_incomplete() -> None:
    artifact, run, observations = _pair()
    persistence = _persistence(artifact, observations)
    incomplete = tuple(item for item in observations if item.observation_id != "obs_a")

    with pytest.raises(ValueError, match="persisted PEF_V1 input digest"):
        _seal(
            artifact,
            run,
            incomplete,
            persistence=persistence,
        )


def test_seal_fails_closed_on_non_ok_health() -> None:
    artifact, run, observations = _pair()

    with pytest.raises(ValueError, match="fully OK"):
        _seal(
            artifact,
            replace(run, coverage_state=HealthValue.DEGRADED),
            observations,
        )


def test_seal_rejects_freeze_unbound_or_nonconfirmatory_runs() -> None:
    artifact, run, observations = _pair()
    persistence = _persistence(artifact, observations)

    with pytest.raises(ValueError, match="freeze-unbound"):
        build_zero_day_seal(
            artifact,
            replace(run, candidate_freeze_receipt_id=None),
            observations,
            persistence,
            run_class="CONFIRMATORY",
            sealed_at=AS_OF + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="CONFIRMATORY"):
        build_zero_day_seal(
            artifact,
            run,
            observations,
            persistence,
            run_class="DEVELOPMENT",
            sealed_at=AS_OF + timedelta(minutes=1),
        )


def _follow_on(*, observed_at: datetime) -> ZeroDayFollowOnEvidence:
    return ZeroDayFollowOnEvidence(
        episode_id="episode_a",
        observation_id="obs_follow_on",
        source_id="hn.frontpage",
        observed_at=observed_at,
        signal_roles=("ATTENTION",),
        membership_receipt_id="receipt_fake",
    )


def test_grade_remains_unverified_until_membership_authority_exists() -> None:
    artifact, run, observations = _pair()
    seal = _seal(artifact, run, observations)

    pending = build_zero_day_grade(
        seal,
        (),
        horizon_seconds=21_600,
        graded_at=AS_OF + timedelta(hours=3),
    )
    unverified = build_zero_day_grade(
        seal,
        (),
        horizon_seconds=21_600,
        graded_at=AS_OF + timedelta(hours=6),
    )

    assert pending.status is ZeroDayGradeStatus.PENDING
    assert pending.members[0].status is ZeroDayMemberStatus.PENDING
    assert unverified.status is ZeroDayGradeStatus.UNVERIFIED
    assert unverified.members[0].status is ZeroDayMemberStatus.UNVERIFIED
    assert unverified.members[0].first_follow_on_observed_at is None
    assert unverified.members[0].lead_seconds is None
    assert len(pending.members) == len(unverified.members) == len(seal.candidates)


def test_grade_rejects_unverified_follow_on_receipt_instead_of_emitting_hit() -> None:
    artifact, run, observations = _pair()
    seal = _seal(artifact, run, observations)

    with pytest.raises(ValueError, match="membership authority is unavailable"):
        build_zero_day_grade(
            seal,
            (_follow_on(observed_at=AS_OF + timedelta(hours=2)),),
            horizon_seconds=21_600,
            graded_at=AS_OF + timedelta(hours=6),
        )


def test_grade_rejects_unfrozen_horizon() -> None:
    artifact, run, observations = _pair()
    seal = _seal(artifact, run, observations)

    with pytest.raises(ValueError, match="not frozen"):
        build_zero_day_grade(
            seal,
            (),
            horizon_seconds=3600,
            graded_at=AS_OF + timedelta(hours=6),
        )
