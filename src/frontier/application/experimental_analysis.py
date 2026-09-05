"""Application service: EXPERIMENTAL richer experimental analysis (slice F).

``produce_experimental_analysis`` consumes the exact control baseline
snapshot, its COMPLETE projection receipt, and the paired observation
universe at the same ``as_of``, and produces a deterministic, replayable,
digest-bound EXPERIMENTAL analysis artifact (R8) for one of the five
snapshot-bound kinds. ``produce_trajectory_analysis`` projects stored
EXPERIMENTAL_SHADOW artifacts (feature batches and optional PEF artifacts)
into a per-episode trajectory read model.

All output is EXPERIMENTAL_SHADOW (R7): hypothesis-level statuses only
(HYPOTHESIS / DESCRIPTOR / INDICATORS / PROJECTION) — never truth,
confirmation, factual origin, or manipulation verdicts. The frozen
grouping baseline and the baseline ranking are never modified.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.advanced_intelligence import shadow_universe_digest
from frontier.domain.digests import Digest
from frontier.domain.experimental_analysis import (
    EXPERIMENTAL_ANALYSIS_ALGORITHM_VERSION,
    EXPERIMENTAL_ANALYSIS_AUTHORITY_STATE,
    EXPERIMENTAL_ANALYSIS_CONFIGURATION_DIGEST,
    EXPERIMENTAL_ANALYSIS_SCHEMA_VERSION,
    ExperimentalAnalysisArtifact,
    ExperimentalAnalysisKind,
    TrajectoryFrame,
    build_corroboration_artifact,
    build_entity_provenance_artifact,
    build_grouping_hypotheses_artifact,
    build_indicators_artifact,
    build_propagation_graph_artifact,
    build_trajectory_artifact,
    experimental_analysis_input_digest,
    trajectory_input_digest,
)
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

_SNAPSHOT_BOUND_BUILDERS = {
    ExperimentalAnalysisKind.GROUPING_HYPOTHESES: build_grouping_hypotheses_artifact,
    ExperimentalAnalysisKind.ENTITY_PROVENANCE: build_entity_provenance_artifact,
    ExperimentalAnalysisKind.CORROBORATION: build_corroboration_artifact,
    ExperimentalAnalysisKind.PROPAGATION_GRAPH: build_propagation_graph_artifact,
    ExperimentalAnalysisKind.INDICATORS: build_indicators_artifact,
}


class ExperimentalAnalysisRepository(Protocol):
    """Persistence port for durable EXPERIMENTAL analysis artifacts."""

    def record_artifact(self, artifact: ExperimentalAnalysisArtifact) -> None: ...


@dataclass(frozen=True, slots=True)
class ExperimentalAnalysisRun:
    """Produced analysis artifact plus the exact evidence digest it consumed (R8)."""

    artifact: ExperimentalAnalysisArtifact
    input_digest: Digest


def _require_control_identity(
    control_snapshot: BaselineSnapshot, control_receipt: ProjectionReceipt
) -> None:
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("experimental analysis requires a COMPLETE control snapshot")
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


def produce_experimental_analysis(
    observations: Iterable[BaselineObservationInput],
    *,
    kind: ExperimentalAnalysisKind,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisRun:
    """Produce one deterministic EXPERIMENTAL analysis artifact (R7, R8).

    Snapshot-bound kinds are computed from the exact control grouping episode
    universe and eligible evidence at ``as_of`` (R1 point-in-time, R3 backfill
    safety) and bound to the snapshot identity, configuration digest, and
    evidence digest. The frozen grouping baseline and the baseline ranking are
    never modified (R6).
    """
    if kind is ExperimentalAnalysisKind.TRAJECTORY:
        raise ValueError("TRAJECTORY artifacts are produced by produce_trajectory_analysis")
    _require_control_identity(control_snapshot, control_receipt)
    builder = _SNAPSHOT_BOUND_BUILDERS[kind]
    artifact = builder(
        observations,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    input_digest = experimental_analysis_input_digest(
        observations, control_snapshot=control_snapshot
    )
    return ExperimentalAnalysisRun(artifact=artifact, input_digest=input_digest)


def produce_trajectory_analysis(
    frames: Iterable[TrajectoryFrame],
    *,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisRun:
    """Project stored EXPERIMENTAL_SHADOW artifacts into a trajectory (R8).

    Read-only: this projection reads stored feature-vector batches and
    optional PEF artifacts and never rewrites them.
    """
    frame_tuple = tuple(frames)
    artifact = build_trajectory_artifact(
        frame_tuple,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    return ExperimentalAnalysisRun(
        artifact=artifact,
        input_digest=trajectory_input_digest(frame_tuple),
    )


__all__ = [
    "EXPERIMENTAL_ANALYSIS_ALGORITHM_VERSION",
    "EXPERIMENTAL_ANALYSIS_AUTHORITY_STATE",
    "EXPERIMENTAL_ANALYSIS_CONFIGURATION_DIGEST",
    "EXPERIMENTAL_ANALYSIS_SCHEMA_VERSION",
    "ExperimentalAnalysisRepository",
    "ExperimentalAnalysisRun",
    "produce_experimental_analysis",
    "produce_trajectory_analysis",
    "shadow_universe_digest",
]
