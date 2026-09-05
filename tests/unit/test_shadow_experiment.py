from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from frontier.application.advanced_intelligence import (
    PefRankingRun,
    run_pef_v0_ranking,
    run_shadow_experiment,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    SHADOW_SCHEMA_VERSION,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_pef_receipt,
    build_shadow_experiment_run,
    failed_pef_artifact,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BASELINE_RANKING_POLICY_VERSION,
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

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


def _health(completeness: HealthValue = HealthValue.OK) -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id="fixture.primary",
        as_of=AS_OF - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=completeness,
        schema=HealthValue.OK,
    )


def _control(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
    health: BaselineHealthInput | None = None,
) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    eligible = [item for item in observations if item.observed_at <= as_of]
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=_projection(eligible, grouped=grouped, as_of=as_of),
        enabled_source_ids=("fixture.primary",),
        health=(health or _health(),),
        as_of=as_of,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=_projection(eligible, grouped=grouped, as_of=as_of),
        enabled_source_ids=("fixture.primary",),
        health=(health or _health(),),
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    return snapshot, receipt


def _run(
    observations: list[BaselineObservationInput],
    *,
    grouped: tuple[tuple[str, ...], ...] = (),
    as_of: datetime = AS_OF,
    health: BaselineHealthInput | None = None,
) -> tuple[BaselineSnapshot, ProjectionReceipt, PefRankingRun, ShadowExperimentRun]:
    snapshot, receipt = _control(observations, grouped=grouped, as_of=as_of, health=health)
    candidate = run_pef_v0_ranking(
        tuple(observations),
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    run = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=GENERATED_AT,
    )
    return snapshot, receipt, candidate, run


def _two_episode_fixture() -> tuple[list[BaselineObservationInput], tuple[tuple[str, ...], ...]]:
    live = [_observation("live", AS_OF - timedelta(minutes=1))]
    dormant = [_observation("dormant", AS_OF - timedelta(minutes=1), reason="BACKFILL")]
    observations = live + dormant
    grouped = ((live[0].observation_id,), (dormant[0].observation_id,))
    return observations, grouped


def test_paired_result_is_experimental_shadow_and_fully_bound() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, candidate, run = _run(observations, grouped=grouped)
    assert run.status is ShadowRunStatus.RAN
    assert run.authority_state == "EXPERIMENTAL_SHADOW"
    assert PEF_AUTHORITY_STATE == "EXPERIMENTAL_SHADOW"
    assert run.experiment_id == PEF_EXPERIMENT_ID
    assert run.candidate_id == PEF_CANDIDATE_ID == "prospective-primary-emission-freshness-v0"
    assert run.schema_version == SHADOW_SCHEMA_VERSION == "shadow-experiment-run-v0"
    assert run.algorithm_version == PEF_ALGORITHM_VERSION
    assert run.configuration_digest == PEF_CONFIGURATION_DIGEST
    assert run.control_snapshot_id == snapshot.snapshot_id
    assert run.control_receipt_id == candidate.artifact.control_receipt_id
    assert run.candidate_artifact_id == candidate.artifact.artifact_id
    assert run.candidate_output_digest == candidate.artifact.output_digest
    assert run.coverage_state is HealthValue.OK
    canonical = run.to_canonical()
    assert canonical["authority_state"] == "EXPERIMENTAL_SHADOW"
    assert canonical["control_ranking_policy_version"] == BASELINE_RANKING_POLICY_VERSION
    run_hexdigest = sha256(canonical_json_bytes(canonical)).hexdigest()
    assert run.run_id == "shadowrun_" + run_hexdigest
    assert run.run_digest.value == "sha256:" + run_hexdigest


def test_control_ranking_mirrors_naive_baseline_order() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, _, run = _run(observations, grouped=grouped)
    baseline_order = [episode.episode_id for episode in snapshot.episodes]
    shadow_order = [item.episode_id for item in run.control_ranking]
    assert shadow_order == baseline_order
    assert [item.rank for item in run.control_ranking] == list(range(1, len(baseline_order) + 1))


def test_determinism_same_inputs_produce_identical_run() -> None:
    observations, grouped = _two_episode_fixture()
    _, _, _, first = _run(observations, grouped=grouped)
    _, _, _, second = _run(observations, grouped=grouped)
    assert first.run_id == second.run_id
    assert first.run_digest == second.run_digest
    assert first.to_canonical() == second.to_canonical()


def test_universe_mismatch_is_rejected() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, candidate, _ = _run(observations, grouped=grouped)
    tampered_ranking = tuple(
        item
        for item in candidate.artifact.episodes
        if item.episode_id != candidate.artifact.episodes[0].episode_id
    )
    tampered_artifact = replace(candidate.artifact, episodes=tampered_ranking)
    with pytest.raises(ValueError, match="identical episode universe"):
        build_shadow_experiment_run(
            control_snapshot=snapshot,
            control_receipt=build_baseline_receipt(
                snapshot,
                observations=observations,
                grouping_projection=_projection(observations, grouped=grouped),
                enabled_source_ids=("fixture.primary",),
                health=(_health(),),
                generated_at=GENERATED_AT,
                source_registry_version=REGISTRY,
            ),
            candidate_artifact=tampered_artifact,
            candidate_receipt=build_pef_receipt(
                tampered_artifact,
                observations=tuple(observations),
                control_snapshot=snapshot,
            ),
            as_of=snapshot.as_of,
            generated_at=GENERATED_AT,
        )


def test_membership_mismatch_is_rejected() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, candidate, _ = _run(observations, grouped=grouped)
    drifted = replace(candidate.artifact.episodes[0], observation_ids=())
    tampered_artifact = replace(candidate.artifact, episodes=(drifted,))
    with pytest.raises(ValueError, match="identical episode universe"):
        build_shadow_experiment_run(
            control_snapshot=snapshot,
            control_receipt=build_baseline_receipt(
                snapshot,
                observations=observations,
                grouping_projection=_projection(observations, grouped=grouped),
                enabled_source_ids=("fixture.primary",),
                health=(_health(),),
                generated_at=GENERATED_AT,
                source_registry_version=REGISTRY,
            ),
            candidate_artifact=tampered_artifact,
            candidate_receipt=build_pef_receipt(
                tampered_artifact,
                observations=tuple(observations),
                control_snapshot=snapshot,
            ),
            as_of=snapshot.as_of,
            generated_at=GENERATED_AT,
        )


def test_as_of_mismatch_is_rejected() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, _, _ = _run(observations, grouped=grouped)
    other_as_of = AS_OF + timedelta(hours=1)
    other_observations = [_observation("other", other_as_of - timedelta(minutes=1))]
    _, _, other_candidate, _ = _run(other_observations, grouped=(), as_of=other_as_of)
    with pytest.raises(ValueError, match="as_of"):
        build_shadow_experiment_run(
            control_snapshot=snapshot,
            control_receipt=build_baseline_receipt(
                snapshot,
                observations=observations,
                grouping_projection=_projection(observations, grouped=grouped),
                enabled_source_ids=("fixture.primary",),
                health=(_health(),),
                generated_at=GENERATED_AT,
                source_registry_version=REGISTRY,
            ),
            candidate_artifact=other_candidate.artifact,
            candidate_receipt=other_candidate.receipt,
            as_of=snapshot.as_of,
            generated_at=GENERATED_AT,
        )


def test_baseline_immutability_control_snapshot_is_never_mutated() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, candidate, run = _run(observations, grouped=grouped)
    before = snapshot.to_canonical()
    snapshot_id_before = snapshot.snapshot_id
    _, _, second_candidate, second_run = _run(observations, grouped=grouped)
    assert snapshot.to_canonical() == before
    assert snapshot.snapshot_id == snapshot_id_before
    assert candidate.artifact.control_snapshot_id == snapshot.snapshot_id
    assert second_candidate.artifact.control_snapshot_id == snapshot.snapshot_id
    assert second_run.control_snapshot_id == snapshot.snapshot_id
    assert run.to_canonical() == second_run.to_canonical()


def test_unknown_coverage_is_propagated_not_coerced() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, _, _, run = _run(
        observations, grouped=grouped, health=_health(completeness=HealthValue.UNKNOWN)
    )
    assert snapshot.coverage_state is HealthValue.UNKNOWN
    assert run.coverage_state is HealthValue.UNKNOWN
    assert run.to_canonical()["control_coverage_state"] == "UNKNOWN"


def test_failed_candidate_arm_never_masquerades_as_ran() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, receipt, _, _ = _run(observations, grouped=grouped)
    failed_artifact = failed_pef_artifact(
        control_snapshot=snapshot,
        control_receipt=receipt,
        as_of=snapshot.as_of,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
        failure_reason="candidate arm halted",
    )
    failed_receipt = build_pef_receipt(
        failed_artifact, observations=tuple(observations), control_snapshot=snapshot
    )
    assert failed_receipt.status is ProjectionStatus.FAILED
    run = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=failed_artifact,
        candidate_receipt=failed_receipt,
        as_of=snapshot.as_of,
        generated_at=GENERATED_AT,
    )
    assert run.status is ShadowRunStatus.FAILED
    assert run.failure_reason == "candidate arm halted"
    assert run.control_ranking == ()
    canonical = run.to_canonical()
    assert canonical["status"] == "FAILED"
    assert canonical["failure_reason"] == "candidate arm halted"


def test_status_semantics_reject_masquerading() -> None:
    universe = Digest("sha256:" + "b" * 64)
    candidate_output = Digest("sha256:" + "d" * 64)

    def make_run(
        *, status: ShadowRunStatus, failure_reason: str | None = None
    ) -> ShadowExperimentRun:
        return ShadowExperimentRun(
            as_of=AS_OF,
            generated_at=GENERATED_AT,
            control_snapshot_id="snapshot_" + "a" * 64,
            control_receipt_id="receipt_" + "a" * 64,
            coverage_state=HealthValue.OK,
            freshness_state=HealthValue.OK,
            transport_state=HealthValue.OK,
            schema_state=HealthValue.OK,
            status=status,
            episode_universe_digest=universe,
            candidate_artifact_id="artifact_" + "c" * 64,
            candidate_output_digest=candidate_output,
            failure_reason=failure_reason,
        )

    with pytest.raises(ValueError, match="failure reason"):
        make_run(status=ShadowRunStatus.RAN, failure_reason="x")
    with pytest.raises(ValueError, match="failure reason"):
        make_run(status=ShadowRunStatus.FAILED)

    def make_ranked_failed_run() -> ShadowExperimentRun:
        return ShadowExperimentRun(
            as_of=AS_OF,
            generated_at=GENERATED_AT,
            control_snapshot_id="snapshot_" + "a" * 64,
            control_receipt_id="receipt_" + "a" * 64,
            coverage_state=HealthValue.OK,
            freshness_state=HealthValue.OK,
            transport_state=HealthValue.OK,
            schema_state=HealthValue.OK,
            status=ShadowRunStatus.FAILED,
            episode_universe_digest=universe,
            candidate_artifact_id="artifact_" + "c" * 64,
            candidate_output_digest=candidate_output,
            failure_reason="halted",
            control_ranking=(ShadowControlArmRanking(rank=1, episode_id="episode_x"),),
        )

    with pytest.raises(ValueError, match="ranking payload"):
        make_ranked_failed_run()


def test_application_service_runs_paired_experiment() -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, receipt, _, _ = _run(observations, grouped=grouped)
    run = run_shadow_experiment(
        tuple(observations),
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert run.status is ShadowRunStatus.RAN
    assert run.candidate_id == "prospective-primary-emission-freshness-v0"
    assert run.authority_state == "EXPERIMENTAL_SHADOW"
    assert len(run.control_ranking) == len(snapshot.episodes)
    canonical = run.to_canonical()
    for forbidden in ("score", "confidence", "confirmation", "truth"):
        assert all(forbidden not in key for key in canonical)


def test_application_service_records_failure_as_failed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations, grouped = _two_episode_fixture()
    snapshot, receipt, _, _ = _run(observations, grouped=grouped)

    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated candidate crash")

    monkeypatch.setattr("frontier.application.advanced_intelligence.run_pef_v0_ranking", explode)
    run = run_shadow_experiment(
        tuple(observations),
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    assert run.status is ShadowRunStatus.FAILED
    assert run.failure_reason is not None
    assert "simulated candidate crash" in run.failure_reason
    assert run.control_ranking == ()
    canonical = run.to_canonical()
    assert canonical["status"] == "FAILED"
    assert canonical["authority_state"] == "EXPERIMENTAL_SHADOW"
