from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.domain.advanced_intelligence import (
    PefEpisodeRanking,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import BaselineObservationInput
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PefV1Artifact,
)
from frontier.domain.zero_day import (
    ZeroDayFollowOnEvidence,
    ZeroDayGradeStatus,
    ZeroDayMemberStatus,
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


def test_seal_uses_candidate_order_and_excludes_attention_and_control_losses() -> None:
    artifact, run, observations = _pair()

    seal = build_zero_day_seal(
        artifact,
        run,
        observations,
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )

    assert [item.episode_id for item in seal.candidates] == ["episode_a"]
    assert seal.candidates[0].candidate_rank == 1
    assert seal.candidates[0].control_rank == 4
    assert seal.candidates[0].rank_advantage == 3
    assert seal.authority_state == "DIAGNOSTIC_ONLY"


def test_seal_identity_is_deterministic() -> None:
    artifact, run, observations = _pair()
    sealed_at = AS_OF + timedelta(minutes=1)

    first = build_zero_day_seal(
        artifact,
        run,
        observations,
        run_class="CONFIRMATORY",
        sealed_at=sealed_at,
    )
    second = build_zero_day_seal(
        artifact,
        run,
        reversed(observations),
        run_class="CONFIRMATORY",
        sealed_at=sealed_at,
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

    with pytest.raises(ValueError, match="6-hour UTC boundary"):
        build_zero_day_seal(
            artifact,
            run,
            observations,
            run_class="CONFIRMATORY",
            sealed_at=bad_as_of + timedelta(minutes=1),
        )


def test_seal_rejects_retrospective_creation_after_live_window() -> None:
    artifact, run, observations = _pair()

    with pytest.raises(ValueError, match="30-minute live sealing window"):
        build_zero_day_seal(
            artifact,
            run,
            observations,
            run_class="CONFIRMATORY",
            sealed_at=AS_OF + timedelta(minutes=31),
        )


def test_seal_fails_closed_when_attention_state_inputs_are_incomplete() -> None:
    artifact, run, observations = _pair()

    with pytest.raises(ValueError, match="incomplete inputs"):
        build_zero_day_seal(
            artifact,
            run,
            tuple(item for item in observations if item.observation_id != "obs_a"),
            run_class="CONFIRMATORY",
            sealed_at=AS_OF + timedelta(minutes=1),
        )


def test_seal_rejects_freeze_unbound_or_nonconfirmatory_runs() -> None:
    artifact, run, observations = _pair()

    with pytest.raises(ValueError, match="freeze-unbound"):
        build_zero_day_seal(
            artifact,
            replace(run, candidate_freeze_receipt_id=None),
            observations,
            run_class="CONFIRMATORY",
            sealed_at=AS_OF + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="CONFIRMATORY"):
        build_zero_day_seal(
            artifact,
            run,
            observations,
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
        membership_receipt_id="receipt_follow_on_grouping",
    )


def test_grade_is_pending_before_cutoff_then_retains_hit_or_miss_denominator() -> None:
    artifact, run, observations = _pair()
    seal = build_zero_day_seal(
        artifact,
        run,
        observations,
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )
    evidence = _follow_on(observed_at=AS_OF + timedelta(hours=2))

    pending = build_zero_day_grade(
        seal,
        (evidence,),
        horizon_seconds=21_600,
        graded_at=AS_OF + timedelta(hours=3),
    )
    complete = build_zero_day_grade(
        seal,
        (evidence,),
        horizon_seconds=21_600,
        graded_at=AS_OF + timedelta(hours=6),
    )
    miss = build_zero_day_grade(
        seal,
        (),
        horizon_seconds=21_600,
        graded_at=AS_OF + timedelta(hours=6),
    )

    assert pending.status is ZeroDayGradeStatus.PENDING
    assert pending.members[0].status is ZeroDayMemberStatus.PENDING
    assert complete.status is ZeroDayGradeStatus.COMPLETE
    assert complete.members[0].status is ZeroDayMemberStatus.HIT
    assert complete.members[0].lead_seconds == 7200
    assert miss.members[0].status is ZeroDayMemberStatus.MISS
    assert len(complete.members) == len(miss.members) == len(seal.candidates)


def test_grade_rejects_preseal_or_future_leakage_evidence() -> None:
    artifact, run, observations = _pair()
    seal = build_zero_day_seal(
        artifact,
        run,
        observations,
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="strictly after"):
        build_zero_day_grade(
            seal,
            (_follow_on(observed_at=AS_OF),),
            horizon_seconds=21_600,
            graded_at=AS_OF + timedelta(hours=6),
        )
    with pytest.raises(ValueError, match="not yet known"):
        build_zero_day_grade(
            seal,
            (_follow_on(observed_at=AS_OF + timedelta(hours=5)),),
            horizon_seconds=21_600,
            graded_at=AS_OF + timedelta(hours=4),
        )


def test_grade_rejects_unfrozen_horizon() -> None:
    artifact, run, observations = _pair()
    seal = build_zero_day_seal(
        artifact,
        run,
        observations,
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="not frozen"):
        build_zero_day_grade(
            seal,
            (),
            horizon_seconds=3600,
            graded_at=AS_OF + timedelta(hours=6),
        )
