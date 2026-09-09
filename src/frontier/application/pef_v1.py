from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast

from frontier.application.advanced_intelligence import PefRankingRun
from frontier.application.intelligence import BaselineIntelligenceRepository
from frontier.domain.advanced_intelligence import PefArtifact, ShadowExperimentRun, ShadowRunStatus
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_hex
from frontier.domain.grouping import GroupingProjection, GroupingRelationInput
from frontier.domain.grouping_v1 import (
    GROUPING_V1_ALGORITHM_VERSION,
    CompactGroupingProjection,
    build_compact_grouping_projection,
    build_compact_grouping_receipt,
)
from frontier.domain.intelligence import (
    BaselineEpisode,
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_CONTROL_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    build_pef_v1_artifact,
    build_pef_v1_receipt,
    build_shadow_experiment_run_v1,
    failed_pef_v1_artifact,
)
from frontier.domain.receipt import ProjectionReceipt


@dataclass(frozen=True, slots=True)
class PefV1ControlRun:
    snapshot: BaselineSnapshot
    receipt: ProjectionReceipt
    grouping_projection: CompactGroupingProjection
    grouping_receipt: ProjectionReceipt


@dataclass(frozen=True, slots=True)
class PefV1PairedRun:
    control: PefV1ControlRun
    shadow: ShadowExperimentRun


def _v1_episode_id(observation_ids: tuple[str, ...]) -> str:
    material: dict[str, CanonicalValue] = {
        "grouping_algorithm_version": GROUPING_V1_ALGORITHM_VERSION,
        "observation_ids": list(observation_ids),
    }
    return "episode_" + sha256_hex(canonical_json_bytes(material))


def _rerank_control(episodes: tuple[BaselineEpisode, ...]) -> tuple[BaselineEpisode, ...]:
    ordered = list(episodes)
    ordered.sort(key=lambda episode: episode.episode_id)
    ordered.sort(key=lambda episode: episode.evidence_count_total, reverse=True)
    ordered.sort(key=lambda episode: episode.last_observed_at, reverse=True)
    ordered.sort(key=lambda episode: episode.source_role_diversity, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_24h, reverse=True)
    ordered.sort(key=lambda episode: episode.acceleration_6h, reverse=True)
    ordered.sort(key=lambda episode: episode.velocity_6h_delta, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_6h, reverse=True)
    ordered.sort(key=lambda episode: episode.mentions_1h, reverse=True)
    return tuple(replace(episode, rank=index) for index, episode in enumerate(ordered, start=1))


def _bind_v1_episode_identity(snapshot: BaselineSnapshot) -> BaselineSnapshot:
    episodes = tuple(
        replace(episode, episode_id=_v1_episode_id(episode.observation_ids))
        for episode in snapshot.episodes
    )
    return replace(snapshot, episodes=_rerank_control(episodes))


def run_pef_v1_control(
    repository: BaselineIntelligenceRepository,
    *,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
    observations: tuple[BaselineObservationInput, ...] | None = None,
    relations: tuple[GroupingRelationInput, ...] | None = None,
    enabled_source_ids: tuple[str, ...] | None = None,
    health: tuple[BaselineHealthInput, ...] | None = None,
) -> PefV1ControlRun:
    """Build the frozen naive control on the scalable V1 grouping universe.

    The public baseline projection identity and ranking policy stay unchanged,
    exactly as preregistered. Only the grouping input authority changes. The
    experiment-only control receipt binds the V1 grouping configuration, while
    the separate grouping receipt binds V1 grouping inputs and compact output.
    """
    if observations is None:
        observations = tuple(repository.list_baseline_observations_as_of(as_of))
    if relations is None:
        relations = tuple(repository.list_grouping_relations_as_of(as_of))
    if enabled_source_ids is None:
        enabled_source_ids = tuple(repository.list_enabled_source_ids())
    if health is None:
        health = tuple(repository.list_latest_health_as_of(as_of))

    grouping_projection = build_compact_grouping_projection(
        (item.grouping for item in observations),
        relations=relations,
        as_of=as_of,
    )
    grouping_receipt = build_compact_grouping_receipt(
        grouping_projection,
        inputs=(item.grouping for item in observations),
        relations=relations,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )

    # Baseline intelligence consumes only groups, ungrouped ids, as_of and the
    # projection canonical form. CompactGroupingProjection intentionally omits
    # the V0 O(n^2) ambiguous-pair array. No V0 regrouping occurs here.
    baseline_grouping = cast(GroupingProjection, grouping_projection)
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=baseline_grouping,
        enabled_source_ids=enabled_source_ids,
        health=health,
        as_of=as_of,
    )
    snapshot = _bind_v1_episode_identity(snapshot)
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=baseline_grouping,
        enabled_source_ids=enabled_source_ids,
        health=health,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    receipt = replace(receipt, configuration_digest=PEF_V1_CONTROL_CONFIGURATION_DIGEST)
    repository.publish_complete_snapshot(snapshot, receipt)
    return PefV1ControlRun(
        snapshot=snapshot,
        receipt=receipt,
        grouping_projection=grouping_projection,
        grouping_receipt=grouping_receipt,
    )


def run_pef_v1_ranking(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> PefRankingRun:
    artifact = build_pef_v1_artifact(
        observations,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    receipt = build_pef_v1_receipt(
        artifact,
        observations=observations,
        control_snapshot=control_snapshot,
    )
    return PefRankingRun(artifact=artifact, receipt=receipt)


def run_shadow_experiment_v1(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
    candidate_freeze_receipt_id: str | None = None,
) -> ShadowExperimentRun:
    """Run PEF_V1 candidate and frozen naive control on one V1 episode universe."""
    try:
        candidate = run_pef_v1_ranking(
            observations,
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
        )
    except Exception as error:
        failed: PefArtifact = failed_pef_v1_artifact(
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            as_of=control_snapshot.as_of,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
            failure_reason=f"candidate arm failed: {error}",
        )
        failed_receipt = build_pef_v1_receipt(
            failed,
            observations=observations,
            control_snapshot=control_snapshot,
        )
        run = build_shadow_experiment_run_v1(
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            candidate_artifact=failed,
            candidate_receipt=failed_receipt,
            as_of=control_snapshot.as_of,
            generated_at=generated_at,
            candidate_freeze_receipt_id=candidate_freeze_receipt_id,
        )
        if run.status is not ShadowRunStatus.FAILED:
            raise RuntimeError(
                "failed PEF_V1 candidate must produce a FAILED shadow run"
            ) from error
        return run

    return build_shadow_experiment_run_v1(
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        candidate_freeze_receipt_id=candidate_freeze_receipt_id,
    )


def run_pef_v1_paired(
    repository: BaselineIntelligenceRepository,
    *,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> PefV1PairedRun:
    """Fetch one PIT universe and run both PEF_V1 arms over it.

    This is intentionally implementation/dev execution only. It does not
    authorize candidate freeze, publication, confirmatory classification, a
    prospective window, backfill, or reuse of any retained PEF_V0 boundary.
    """
    observations = tuple(
        sorted(
            repository.list_baseline_observations_as_of(as_of),
            key=lambda item: item.observation_id,
        )
    )
    relations = tuple(repository.list_grouping_relations_as_of(as_of))
    enabled_source_ids = tuple(repository.list_enabled_source_ids())
    health = tuple(repository.list_latest_health_as_of(as_of))
    control = run_pef_v1_control(
        repository,
        as_of=as_of,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
        observations=observations,
        relations=relations,
        enabled_source_ids=enabled_source_ids,
        health=health,
    )
    shadow = run_shadow_experiment_v1(
        observations,
        control_snapshot=control.snapshot,
        control_receipt=control.receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    if shadow.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise RuntimeError("PEF_V1 paired run emitted the wrong experiment identity")
    if shadow.candidate_id != PEF_V1_CANDIDATE_ID:
        raise RuntimeError("PEF_V1 paired run emitted the wrong candidate identity")
    if shadow.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise RuntimeError("PEF_V1 paired run emitted the wrong configuration identity")
    return PefV1PairedRun(control=control, shadow=shadow)
