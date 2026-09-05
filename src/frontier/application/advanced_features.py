"""Application service: EXPERIMENTAL transparent advanced feature vectors (slice E).

``compute_advanced_features`` consumes the exact control baseline snapshot,
its COMPLETE projection receipt, and the paired observation universe at the
same ``as_of``, and produces deterministic, replayable per-episode feature
vectors (R8) bound to the snapshot identity. The output is EXPERIMENTAL_SHADOW
(R7): interpretable feature values only — never a scalar score, never truth,
confidence, or confirmation semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.advanced_intelligence import shadow_universe_digest
from frontier.domain.digests import Digest
from frontier.domain.features import (
    ADVANCED_FEATURES_CONFIGURATION_DIGEST,
    FEATURE_ALGORITHM_VERSION,
    FEATURE_AUTHORITY_STATE,
    FEATURE_SCHEMA_VERSION,
    FeatureVectorBatch,
    build_feature_vector_batch,
    build_feature_vectors,
    failed_feature_vector_batch,
    feature_input_digest,
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


class FeatureVectorRepository(Protocol):
    """Persistence port for durable feature-vector batches."""

    def publish_batch(self, batch: FeatureVectorBatch) -> None: ...


@dataclass(frozen=True, slots=True)
class AdvancedFeatureRun:
    """Computed feature batch plus the exact evidence digest it consumed (R8)."""

    batch: FeatureVectorBatch
    input_digest: Digest


def _require_control_identity(
    control_snapshot: BaselineSnapshot, control_receipt: ProjectionReceipt
) -> None:
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("feature vectors require a COMPLETE control snapshot")
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


def compute_advanced_features(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> AdvancedFeatureRun:
    """Compute deterministic per-episode advanced feature vectors.

    The vectors are computed from the exact control grouping episode universe
    and eligible evidence at ``as_of`` (R1 point-in-time, R3 backfill safety)
    and bound to the snapshot identity, configuration digest, and evidence
    digest (R8). They are EXPERIMENTAL_SHADOW output (R7).
    """
    _require_control_identity(control_snapshot, control_receipt)
    batch = build_feature_vector_batch(
        observations,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    input_digest = feature_input_digest(observations, control_snapshot=control_snapshot)
    return AdvancedFeatureRun(batch=batch, input_digest=input_digest)


def record_failed_advanced_features(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
    failure_reason: str,
) -> AdvancedFeatureRun:
    """Record an explicit FAILED feature batch without a vector payload (R8)."""
    _require_control_identity(control_snapshot, control_receipt)
    batch = failed_feature_vector_batch(
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
        failure_reason=failure_reason,
    )
    return AdvancedFeatureRun(
        batch=batch,
        input_digest=Digest("sha256:" + "0" * 64),
    )


__all__ = [
    "ADVANCED_FEATURES_CONFIGURATION_DIGEST",
    "FEATURE_ALGORITHM_VERSION",
    "FEATURE_AUTHORITY_STATE",
    "FEATURE_SCHEMA_VERSION",
    "AdvancedFeatureRun",
    "FeatureVectorRepository",
    "build_feature_vectors",
    "compute_advanced_features",
    "record_failed_advanced_features",
    "shadow_universe_digest",
]
