from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.advanced_intelligence import (
    PefArtifact,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_pef_artifact,
    build_pef_receipt,
    build_shadow_experiment_run,
    failed_pef_artifact,
)
from frontier.domain.digests import Digest
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus


class PefArtifactRepository(Protocol):
    def publish_complete_artifact(
        self, artifact: PefArtifact, receipt: ProjectionReceipt
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PefRankingRun:
    artifact: PefArtifact
    receipt: ProjectionReceipt


def run_pef_v0_ranking(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> PefRankingRun:
    """Compute the deterministic PEF_V0 ranking for an existing control snapshot.

    The candidate consumes the exact baseline evidence snapshot (R6 permanent
    comparator) for the same ``as_of`` and never regroups observations. The
    resulting artifact is EXPERIMENTAL_SHADOW output (R7) bound to the exact
    control snapshot id, control receipt id, configuration digest, and output
    digest (R8).
    """
    _require_control_identity(control_snapshot, control_receipt)
    artifact = build_pef_artifact(
        observations,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    receipt = build_pef_receipt(
        artifact, observations=observations, control_snapshot=control_snapshot
    )
    return PefRankingRun(artifact=artifact, receipt=receipt)


def _require_control_identity(
    control_snapshot: BaselineSnapshot, control_receipt: ProjectionReceipt
) -> None:
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("pef ranking requires a COMPLETE control snapshot")
    if (
        control_receipt.output_digest.value.removeprefix("sha256:")
        != (control_snapshot.snapshot_id.split("snapshot_")[-1])
    ):
        raise ValueError("control receipt does not bind the given control snapshot")
    if control_receipt.projection_name != BASELINE_PROJECTION_NAME:
        raise ValueError("control receipt projection name mismatch")
    if control_receipt.projection_version != BASELINE_PROJECTION_VERSION:
        raise ValueError("control receipt projection version mismatch")
    if control_receipt.schema_version != BASELINE_SCHEMA_VERSION:
        raise ValueError("control receipt schema version mismatch")
    if control_receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise ValueError("control receipt algorithm version mismatch")
    if control_receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise ValueError("control receipt ranking policy version mismatch")


def run_shadow_experiment(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ShadowExperimentRun:
    """Run the control arm and the PEF_V0 candidate arm on identical inputs.

    Both arms consume exactly the same observation universe, ``as_of`` (the
    control snapshot's knowledge horizon), source registry version, health
    state, and canonical evidence (R1): the candidate reuses the existing
    control snapshot and never regroups or re-baselines anything (R6). The
    control snapshot is only read, never written. If the candidate arm raises,
    the paired run is recorded as FAILED with an explicit failure reason (R8)
    instead of silently presenting the control arm alone.
    """
    _require_control_identity(control_snapshot, control_receipt)
    as_of = control_snapshot.as_of
    try:
        candidate = run_pef_v0_ranking(
            observations,
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
        )
    except Exception as error:  # FAILED runs must stay explicit (R8)
        candidate_artifact = failed_pef_artifact(
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            as_of=as_of,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
            failure_reason=f"candidate arm failed: {error}",
        )
        candidate_receipt = build_pef_receipt(
            candidate_artifact, observations=observations, control_snapshot=control_snapshot
        )
        run = build_shadow_experiment_run(
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            candidate_artifact=candidate_artifact,
            candidate_receipt=candidate_receipt,
            as_of=as_of,
            generated_at=generated_at,
        )
        if run.status is not ShadowRunStatus.FAILED:
            raise RuntimeError("failed candidate arm must produce a FAILED shadow run") from error
        return run
    return build_shadow_experiment_run(
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=as_of,
        generated_at=generated_at,
    )
