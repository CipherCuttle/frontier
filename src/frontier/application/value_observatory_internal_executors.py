from __future__ import annotations

from datetime import datetime
from typing import Protocol

from frontier.application.value_observatory_dry_run import (
    BENCHMARK_CAPTURE_V0_ALERT_BUDGET,
    BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE,
    BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE,
    BENCHMARK_CAPTURE_V0_SELECTION_WINDOW,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    PefArtifactStatus,
)
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_CONFIGURATION_DIGEST,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_RECEIPT_SCHEMA_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
    require_pef_v1_configuration_identity,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus
from frontier.domain.value_observatory import (
    BenchmarkExecutorIdentity,
    CaptureItem,
    CaptureStatus,
    ObservatoryArm,
    SourceHealthBinding,
    ValueObservatoryCapture,
)

_INTERNAL_ARMS = frozenset(
    {
        ObservatoryArm.FRONTIER_NAIVE_CONTROL,
        ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
    }
)


class _RankedCaptureSource(Protocol):
    @property
    def rank(self) -> int: ...

    @property
    def episode_id(self) -> str: ...

    @property
    def observation_ids(self) -> tuple[str, ...]: ...

    def to_canonical(self) -> dict[str, CanonicalValue]: ...


def _require_exact_horizon(actual: datetime, expected: datetime, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} must match the exact benchmark knowledge horizon")


def _require_ranked_items(items: tuple[_RankedCaptureSource, ...]) -> None:
    ranks = tuple(item.rank for item in items)
    if ranks != tuple(range(1, len(items) + 1)):
        raise ValueError("internal benchmark source ranking must be contiguous from one")


def _capture_items(items: tuple[_RankedCaptureSource, ...]) -> tuple[CaptureItem, ...]:
    selected = items[:BENCHMARK_CAPTURE_V0_ALERT_BUDGET]
    return tuple(
        CaptureItem(
            position=index,
            item_key=item.episode_id,
            raw_item_digest=sha256_digest(canonical_json_bytes(item.to_canonical())),
            evidence_refs=item.observation_ids,
        )
        for index, item in enumerate(selected, start=1)
    )


def _input_digest(
    *,
    arm: ObservatoryArm,
    knowledge_horizon: datetime,
    source_artifact_id: str,
    receipt: ProjectionReceipt,
) -> Digest:
    material: dict[str, CanonicalValue] = {
        "arm": arm.value,
        "knowledge_horizon": canonical_timestamp(knowledge_horizon),
        "receipt_id": receipt.receipt_id,
        "source_artifact_id": source_artifact_id,
    }
    return sha256_digest(canonical_json_bytes(material))


def _capture(
    *,
    arm: ObservatoryArm,
    knowledge_horizon: datetime,
    captured_at: datetime,
    executor: BenchmarkExecutorIdentity,
    protocol_digest: Digest,
    source_health_bindings: tuple[SourceHealthBinding, ...],
    input_digest: Digest,
    items: tuple[CaptureItem, ...],
    raw_response_digest: Digest,
) -> ValueObservatoryCapture:
    if captured_at > knowledge_horizon + BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE:
        raise ValueError(
            "complete internal benchmark capture exceeds the frozen 30-minute deadline"
        )
    return ValueObservatoryCapture(
        arm=arm,
        captured_at=captured_at,
        knowledge_horizon=knowledge_horizon,
        selection_window_start=knowledge_horizon - BENCHMARK_CAPTURE_V0_SELECTION_WINDOW,
        selection_window_end=knowledge_horizon,
        alert_budget=BENCHMARK_CAPTURE_V0_ALERT_BUDGET,
        domain_scope=BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE,
        executor=executor,
        protocol_digest=protocol_digest,
        input_digest=input_digest,
        source_health_bindings=source_health_bindings,
        items=items,
        status=CaptureStatus.COMPLETE,
        raw_response_digest=raw_response_digest,
    )


def build_naive_observatory_capture(
    snapshot: BaselineSnapshot,
    receipt: ProjectionReceipt,
    *,
    knowledge_horizon: datetime,
    captured_at: datetime,
    executor: BenchmarkExecutorIdentity,
    protocol_digest: Digest,
    source_health_bindings: tuple[SourceHealthBinding, ...],
) -> ValueObservatoryCapture:
    """Adapt one exact retained naive baseline boundary into a benchmark capture."""

    _require_exact_horizon(snapshot.as_of, knowledge_horizon, "baseline snapshot as_of")
    _require_exact_horizon(receipt.as_of, knowledge_horizon, "baseline receipt as_of")
    if receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("naive benchmark requires a COMPLETE baseline receipt")
    if receipt.receipt_schema_version != BASELINE_RECEIPT_SCHEMA_VERSION:
        raise ValueError("naive benchmark baseline receipt schema mismatch")
    if receipt.projection_name != BASELINE_PROJECTION_NAME:
        raise ValueError("naive benchmark baseline projection name mismatch")
    if receipt.projection_version != BASELINE_PROJECTION_VERSION:
        raise ValueError("naive benchmark baseline projection version mismatch")
    if receipt.schema_version != BASELINE_SCHEMA_VERSION:
        raise ValueError("naive benchmark baseline schema mismatch")
    if receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise ValueError("naive benchmark baseline algorithm mismatch")
    if receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise ValueError("naive benchmark baseline ranking policy mismatch")
    if receipt.configuration_digest != BASELINE_CONFIGURATION_DIGEST:
        raise ValueError("naive benchmark baseline configuration mismatch")

    snapshot_digest = sha256_digest(canonical_json_bytes(snapshot.to_canonical()))
    if receipt.output_digest != snapshot_digest:
        raise ValueError("naive benchmark receipt does not bind the supplied snapshot")

    source_ranked = tuple(sorted(snapshot.episodes, key=lambda item: item.rank))
    _require_ranked_items(source_ranked)
    lexical = tuple(sorted(snapshot.episodes, key=lambda item: item.episode_id))
    ordered = tuple(sorted(lexical, key=lambda item: item.last_observed_at, reverse=True))
    capture_items = _capture_items(ordered)
    return _capture(
        arm=ObservatoryArm.FRONTIER_NAIVE_CONTROL,
        knowledge_horizon=knowledge_horizon,
        captured_at=captured_at,
        executor=executor,
        protocol_digest=protocol_digest,
        source_health_bindings=source_health_bindings,
        input_digest=_input_digest(
            arm=ObservatoryArm.FRONTIER_NAIVE_CONTROL,
            knowledge_horizon=knowledge_horizon,
            source_artifact_id=snapshot.snapshot_id,
            receipt=receipt,
        ),
        items=capture_items,
        raw_response_digest=snapshot_digest,
    )


def build_pef_v1_observatory_capture(
    artifact: PefV1Artifact,
    receipt: ProjectionReceipt,
    *,
    knowledge_horizon: datetime,
    captured_at: datetime,
    executor: BenchmarkExecutorIdentity,
    protocol_digest: Digest,
    source_health_bindings: tuple[SourceHealthBinding, ...],
) -> ValueObservatoryCapture:
    """Adapt one exact frozen PEF_V1 boundary into a benchmark capture without recomputation."""

    require_pef_v1_configuration_identity()
    _require_exact_horizon(artifact.as_of, knowledge_horizon, "PEF_V1 artifact as_of")
    _require_exact_horizon(receipt.as_of, knowledge_horizon, "PEF_V1 receipt as_of")
    if artifact.status is not PefArtifactStatus.RAN:
        raise ValueError("PEF_V1 benchmark requires a RAN artifact")
    if artifact.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("PEF_V1 benchmark experiment identity mismatch")
    if artifact.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("PEF_V1 benchmark candidate identity mismatch")
    if artifact.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 benchmark configuration mismatch")
    if artifact.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("PEF_V1 benchmark schema mismatch")
    if artifact.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 benchmark algorithm mismatch")
    if artifact.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("PEF_V1 benchmark ranking policy mismatch")
    if artifact.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("PEF_V1 benchmark authority-state mismatch")

    if receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("PEF_V1 benchmark requires a COMPLETE receipt")
    if receipt.receipt_schema_version != PEF_RECEIPT_SCHEMA_VERSION:
        raise ValueError("PEF_V1 benchmark receipt schema-family mismatch")
    if receipt.projection_name != PEF_V1_PROJECTION_NAME:
        raise ValueError("PEF_V1 benchmark receipt projection name mismatch")
    if receipt.projection_version != PEF_V1_PROJECTION_VERSION:
        raise ValueError("PEF_V1 benchmark receipt projection version mismatch")
    if receipt.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("PEF_V1 benchmark receipt schema mismatch")
    if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 benchmark receipt algorithm mismatch")
    if receipt.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("PEF_V1 benchmark receipt ranking policy mismatch")
    if receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 benchmark receipt configuration mismatch")
    if receipt.source_registry_version != artifact.source_registry_version:
        raise ValueError("PEF_V1 benchmark source-registry mismatch")
    if receipt.output_digest != artifact.output_digest:
        raise ValueError("PEF_V1 benchmark receipt does not bind the supplied artifact")
    if receipt.generated_at != artifact.generated_at:
        raise ValueError("PEF_V1 benchmark artifact/receipt generation timestamp mismatch")
    if artifact.generated_at > captured_at:
        raise ValueError("PEF_V1 benchmark artifact was generated after captured_at")
    if artifact.generated_at > knowledge_horizon + BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE:
        raise ValueError("PEF_V1 benchmark artifact exceeds the frozen 30-minute capture deadline")

    ordered: tuple[_RankedCaptureSource, ...] = tuple(
        sorted(artifact.episodes, key=lambda item: item.rank)
    )
    _require_ranked_items(ordered)
    capture_items = _capture_items(ordered)
    return _capture(
        arm=ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
        knowledge_horizon=knowledge_horizon,
        captured_at=captured_at,
        executor=executor,
        protocol_digest=protocol_digest,
        source_health_bindings=source_health_bindings,
        input_digest=_input_digest(
            arm=ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
            knowledge_horizon=knowledge_horizon,
            source_artifact_id=artifact.artifact_id,
            receipt=receipt,
        ),
        items=capture_items,
        raw_response_digest=artifact.output_digest,
    )


def build_failed_internal_observatory_capture(
    *,
    arm: ObservatoryArm,
    knowledge_horizon: datetime,
    captured_at: datetime,
    executor: BenchmarkExecutorIdentity,
    protocol_digest: Digest,
    source_health_bindings: tuple[SourceHealthBinding, ...],
    failure_reason: str,
) -> ValueObservatoryCapture:
    """Emit an explicit failed capture for either internal benchmark arm."""

    if arm not in _INTERNAL_ARMS:
        raise ValueError("failed internal capture requires one of the two FRONTIER benchmark arms")
    if not failure_reason.strip():
        raise ValueError("failed internal capture requires a non-empty failure reason")
    failure_material: dict[str, CanonicalValue] = {
        "arm": arm.value,
        "failure_reason": failure_reason,
        "knowledge_horizon": canonical_timestamp(knowledge_horizon),
    }
    return ValueObservatoryCapture(
        arm=arm,
        captured_at=captured_at,
        knowledge_horizon=knowledge_horizon,
        selection_window_start=knowledge_horizon - BENCHMARK_CAPTURE_V0_SELECTION_WINDOW,
        selection_window_end=knowledge_horizon,
        alert_budget=BENCHMARK_CAPTURE_V0_ALERT_BUDGET,
        domain_scope=BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE,
        executor=executor,
        protocol_digest=protocol_digest,
        input_digest=sha256_digest(canonical_json_bytes(failure_material)),
        source_health_bindings=source_health_bindings,
        items=(),
        status=CaptureStatus.FAILED,
        failure_reason=failure_reason,
    )


__all__ = [
    "build_failed_internal_observatory_capture",
    "build_naive_observatory_capture",
    "build_pef_v1_observatory_capture",
]
