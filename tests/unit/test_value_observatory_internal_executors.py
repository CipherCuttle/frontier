from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.application.value_observatory_internal_executors import (
    build_failed_internal_observatory_capture,
    build_naive_observatory_capture,
    build_pef_v1_observatory_capture,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    PefArtifactStatus,
    PefEpisodeRanking,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_CONFIGURATION_DIGEST,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_RECEIPT_SCHEMA_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineEpisode,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus
from frontier.domain.value_observatory import (
    BenchmarkExecutorIdentity,
    CaptureStatus,
    ObservatoryArm,
    SourceHealthBinding,
)

HORIZON = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
CAPTURED_AT = HORIZON + timedelta(seconds=10)
PROTOCOL_DIGEST = Digest("sha256:" + "9" * 64)
SOURCE_REGISTRY_DIGEST = Digest("sha256:" + "7" * 64)


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def executor(arm: ObservatoryArm) -> BenchmarkExecutorIdentity:
    return BenchmarkExecutorIdentity(
        executor_id=f"{arm.value.lower()}-candidate",
        executor_version="v0",
        configuration_digest=digest("5"),
    )


def health() -> tuple[SourceHealthBinding, ...]:
    return (
        SourceHealthBinding(
            health_observation_id="health_" + "a" * 64,
            source_id="pypi.updates",
            as_of=HORIZON - timedelta(seconds=1),
            transport=HealthValue.OK,
            freshness=HealthValue.OK,
            completeness=HealthValue.OK,
            schema=HealthValue.OK,
        ),
    )


def baseline_episode(rank: int) -> BaselineEpisode:
    observed_at = HORIZON - timedelta(minutes=rank)
    return BaselineEpisode(
        rank=rank,
        episode_id=f"episode-naive-{rank}",
        observation_ids=(f"obs-naive-{rank}",),
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        age_seconds=rank * 60,
        evidence_count_total=1,
        prospective_evidence_count=1,
        backfill_evidence_count=0,
        recovered_backlog_evidence_count=0,
        mentions_1h=1,
        mentions_6h=1,
        mentions_24h=1,
        previous_6h=0,
        preprevious_6h=0,
        velocity_6h_delta=1,
        acceleration_6h=1,
        source_ids=("pypi.updates",),
        source_count=1,
        signal_roles=("DISCOVERY",),
        source_role_diversity=1,
    )


def baseline_snapshot(count: int = 6) -> BaselineSnapshot:
    return BaselineSnapshot(
        as_of=HORIZON,
        transport_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        coverage_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        episodes=tuple(baseline_episode(rank) for rank in range(1, count + 1)),
    )


def baseline_receipt(snapshot: BaselineSnapshot) -> ProjectionReceipt:
    return ProjectionReceipt(
        receipt_schema_version=BASELINE_RECEIPT_SCHEMA_VERSION,
        projection_name=BASELINE_PROJECTION_NAME,
        projection_version=BASELINE_PROJECTION_VERSION,
        schema_version=BASELINE_SCHEMA_VERSION,
        algorithm_version=BASELINE_ALGORITHM_VERSION,
        ranking_policy_version=BASELINE_RANKING_POLICY_VERSION,
        configuration_digest=BASELINE_CONFIGURATION_DIGEST,
        source_registry_version=SOURCE_REGISTRY_DIGEST,
        as_of=snapshot.as_of,
        generated_at=snapshot.as_of + timedelta(seconds=1),
        input_digest=digest("1"),
        output_digest=sha256_digest(canonical_json_bytes(snapshot.to_canonical())),
        status=ProjectionStatus.COMPLETE,
    )


def pef_episode(rank: int) -> PefEpisodeRanking:
    observed_at = HORIZON - timedelta(minutes=rank)
    return PefEpisodeRanking(
        rank=rank,
        episode_id=f"episode-pef-{rank}",
        observation_ids=(f"obs-pef-{rank}",),
        has_any_prospective_evidence=True,
        has_prospective_primary_emission=rank == 1,
        prospective_last_observed_at=observed_at,
        prospective_age_seconds=rank * 60,
        prospective_source_role_diversity=1,
        prospective_evidence_count=1,
        mentions_1h=1,
        mentions_6h=1,
        mentions_24h=1,
        velocity_6h_delta=1,
        acceleration_6h=1,
    )


def pef_artifact(count: int = 6) -> PefV1Artifact:
    return PefV1Artifact(
        as_of=HORIZON,
        control_snapshot_id="snapshot_" + "1" * 64,
        control_receipt_id="receipt_" + "2" * 64,
        source_registry_version=SOURCE_REGISTRY_DIGEST,
        generated_at=HORIZON + timedelta(seconds=2),
        status=PefArtifactStatus.RAN,
        episodes=tuple(pef_episode(rank) for rank in range(1, count + 1)),
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        grouping_receipt_id="receipt_" + "3" * 64,
    )


def pef_receipt(artifact: PefV1Artifact) -> ProjectionReceipt:
    return ProjectionReceipt(
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
        input_digest=digest("4"),
        output_digest=artifact.output_digest,
        status=ProjectionStatus.COMPLETE,
    )


def test_naive_adapter_emits_frozen_top_five_capture_from_exact_snapshot() -> None:
    snapshot = baseline_snapshot()
    receipt = baseline_receipt(snapshot)

    capture = build_naive_observatory_capture(
        snapshot,
        receipt,
        knowledge_horizon=HORIZON,
        captured_at=CAPTURED_AT,
        executor=executor(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
        protocol_digest=PROTOCOL_DIGEST,
        source_health_bindings=health(),
    )

    assert capture.arm is ObservatoryArm.FRONTIER_NAIVE_CONTROL
    assert capture.status is CaptureStatus.COMPLETE
    assert capture.knowledge_horizon == HORIZON
    assert capture.selection_window_start == HORIZON - timedelta(hours=24)
    assert capture.selection_window_end == HORIZON
    assert capture.alert_budget == 5
    assert tuple(item.position for item in capture.items) == (1, 2, 3, 4, 5)
    assert tuple(item.item_key for item in capture.items) == tuple(
        f"episode-naive-{rank}" for rank in range(1, 6)
    )
    assert capture.items[0].evidence_refs == ("obs-naive-1",)
    assert capture.raw_response_digest == receipt.output_digest


def test_naive_adapter_rejects_prior_boundary_snapshot() -> None:
    snapshot = replace(baseline_snapshot(), as_of=HORIZON - timedelta(hours=6))
    receipt = baseline_receipt(snapshot)

    with pytest.raises(ValueError, match="exact benchmark knowledge horizon"):
        build_naive_observatory_capture(
            snapshot,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_naive_adapter_rejects_receipt_not_binding_snapshot() -> None:
    snapshot = baseline_snapshot()
    receipt = replace(baseline_receipt(snapshot), output_digest=digest("f"))

    with pytest.raises(ValueError, match="does not bind"):
        build_naive_observatory_capture(
            snapshot,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_naive_adapter_rejects_noncontiguous_source_ranking() -> None:
    snapshot = baseline_snapshot(count=2)
    invalid = replace(snapshot, episodes=(snapshot.episodes[0], replace(snapshot.episodes[1], rank=3)))
    receipt = baseline_receipt(invalid)

    with pytest.raises(ValueError, match="contiguous from one"):
        build_naive_observatory_capture(
            invalid,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_pef_adapter_emits_frozen_top_five_without_recomputation() -> None:
    artifact = pef_artifact()
    receipt = pef_receipt(artifact)

    capture = build_pef_v1_observatory_capture(
        artifact,
        receipt,
        knowledge_horizon=HORIZON,
        captured_at=CAPTURED_AT,
        executor=executor(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL),
        protocol_digest=PROTOCOL_DIGEST,
        source_health_bindings=health(),
    )

    assert capture.arm is ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL
    assert capture.status is CaptureStatus.COMPLETE
    assert tuple(item.item_key for item in capture.items) == tuple(
        f"episode-pef-{rank}" for rank in range(1, 6)
    )
    assert capture.items[0].evidence_refs == ("obs-pef-1",)
    assert capture.raw_response_digest == artifact.output_digest


def test_pef_adapter_rejects_prior_boundary_artifact() -> None:
    artifact = replace(pef_artifact(), as_of=HORIZON - timedelta(hours=6))
    receipt = pef_receipt(artifact)

    with pytest.raises(ValueError, match="exact benchmark knowledge horizon"):
        build_pef_v1_observatory_capture(
            artifact,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_pef_adapter_rejects_wrong_receipt_family() -> None:
    artifact = pef_artifact()
    receipt = replace(pef_receipt(artifact), receipt_schema_version="wrong-receipt-v0")

    with pytest.raises(ValueError, match="schema-family mismatch"):
        build_pef_v1_observatory_capture(
            artifact,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_pef_adapter_rejects_failed_artifact_as_complete_capture() -> None:
    artifact = PefV1Artifact(
        as_of=HORIZON,
        control_snapshot_id="snapshot_" + "1" * 64,
        control_receipt_id="receipt_" + "2" * 64,
        source_registry_version=SOURCE_REGISTRY_DIGEST,
        generated_at=HORIZON + timedelta(seconds=2),
        status=PefArtifactStatus.FAILED,
        failure_reason="candidate failed",
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        grouping_receipt_id="receipt_" + "3" * 64,
    )
    receipt = replace(pef_receipt(artifact), status=ProjectionStatus.FAILED)

    with pytest.raises(ValueError, match="requires a RAN artifact"):
        build_pef_v1_observatory_capture(
            artifact,
            receipt,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
        )


def test_internal_failure_adapter_emits_explicit_failed_capture() -> None:
    capture = build_failed_internal_observatory_capture(
        arm=ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
        knowledge_horizon=HORIZON,
        captured_at=CAPTURED_AT,
        executor=executor(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL),
        protocol_digest=PROTOCOL_DIGEST,
        source_health_bindings=health(),
        failure_reason="exact PEF_V1 boundary missing",
    )

    assert capture.status is CaptureStatus.FAILED
    assert capture.items == ()
    assert capture.raw_response_digest is None
    assert capture.failure_reason == "exact PEF_V1 boundary missing"


def test_internal_failure_adapter_rejects_external_comparator_arm() -> None:
    with pytest.raises(ValueError, match="two FRONTIER benchmark arms"):
        build_failed_internal_observatory_capture(
            arm=ObservatoryArm.ORDINARY_AGGREGATION,
            knowledge_horizon=HORIZON,
            captured_at=CAPTURED_AT,
            executor=executor(ObservatoryArm.ORDINARY_AGGREGATION),
            protocol_digest=PROTOCOL_DIGEST,
            source_health_bindings=health(),
            failure_reason="not an internal arm",
        )
