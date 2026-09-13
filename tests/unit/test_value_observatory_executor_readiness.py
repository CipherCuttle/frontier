from __future__ import annotations

import pytest

from frontier.application.value_observatory_dry_run import BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
    BenchmarkExecutorBlockerCode,
    BenchmarkExecutorCapability,
    BenchmarkExecutorReadinessEvidence,
    BenchmarkExecutorReadinessStatus,
    assess_benchmark_executor_readiness_v0,
)
from frontier.domain.value_observatory import ObservatoryArm

ALL_CAPABILITIES = frozenset(BenchmarkExecutorCapability)


def ready_evidence(arm: ObservatoryArm) -> BenchmarkExecutorReadinessEvidence:
    if arm is ObservatoryArm.ORDINARY_AGGREGATION:
        return BenchmarkExecutorReadinessEvidence(
            arm=arm,
            capabilities=ALL_CAPABILITIES,
            source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
            horizon_safe_source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
        )
    return BenchmarkExecutorReadinessEvidence(arm=arm, capabilities=ALL_CAPABILITIES)


def ready_all() -> tuple[BenchmarkExecutorReadinessEvidence, ...]:
    return tuple(ready_evidence(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)


def test_all_four_frozen_executors_must_be_ready() -> None:
    assessment = assess_benchmark_executor_readiness_v0(ready_all())

    assert assessment.status is BenchmarkExecutorReadinessStatus.READY
    assert assessment.ready_arms == BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
    assert assessment.blocked_arms == ()
    assert assessment.blockers == ()


def test_missing_arm_evidence_blocks_readiness_instead_of_inferring_capability() -> None:
    evidence = tuple(
        item for item in ready_all() if item.arm is not ObservatoryArm.WEB_LLM_BENCHMARK
    )

    assessment = assess_benchmark_executor_readiness_v0(evidence)

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.WEB_LLM_BENCHMARK,)
    assert [(item.code, item.arm) for item in assessment.blockers] == [
        (
            BenchmarkExecutorBlockerCode.ARM_EVIDENCE_MISSING,
            ObservatoryArm.WEB_LLM_BENCHMARK,
        )
    ]


def test_pef_arm_blocks_without_exact_boundary_frozen_output_capability() -> None:
    evidence = list(ready_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL)
    current = evidence[index]
    evidence[index] = BenchmarkExecutorReadinessEvidence(
        arm=current.arm,
        capabilities=current.capabilities
        - {BenchmarkExecutorCapability.EXACT_BOUNDARY_FROZEN_PEF_V1},
    )

    assessment = assess_benchmark_executor_readiness_v0(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,)
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.MISSING_CAPABILITY
        and blocker.detail == BenchmarkExecutorCapability.EXACT_BOUNDARY_FROZEN_PEF_V1.value
        for blocker in assessment.blockers
    )


def test_ordinary_aggregation_requires_exact_frozen_source_set() -> None:
    evidence = list(ready_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.ORDINARY_AGGREGATION)
    source_ids = BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - {"hn.frontpage"}
    evidence[index] = BenchmarkExecutorReadinessEvidence(
        arm=ObservatoryArm.ORDINARY_AGGREGATION,
        capabilities=ALL_CAPABILITIES,
        source_ids=source_ids,
        horizon_safe_source_ids=source_ids,
    )

    assessment = assess_benchmark_executor_readiness_v0(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert ObservatoryArm.ORDINARY_AGGREGATION in assessment.blocked_arms
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_SET_MISMATCH
        and "hn.frontpage" in blocker.detail
        for blocker in assessment.blockers
    )


def test_ordinary_aggregation_blocks_if_one_collection_state_is_not_horizon_safe() -> None:
    evidence = list(ready_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.ORDINARY_AGGREGATION)
    evidence[index] = BenchmarkExecutorReadinessEvidence(
        arm=ObservatoryArm.ORDINARY_AGGREGATION,
        capabilities=ALL_CAPABILITIES,
        source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
        horizon_safe_source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - {"pypi.updates"},
    )

    assessment = assess_benchmark_executor_readiness_v0(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_HORIZON_UNSAFE
        and blocker.detail == "pypi.updates"
        for blocker in assessment.blockers
    )


def test_web_llm_timestamp_metadata_cannot_replace_retrieval_cutoff_enforcement() -> None:
    evidence = list(ready_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.WEB_LLM_BENCHMARK)
    current = evidence[index]
    evidence[index] = BenchmarkExecutorReadinessEvidence(
        arm=current.arm,
        capabilities=current.capabilities
        - {BenchmarkExecutorCapability.RETRIEVAL_KNOWLEDGE_CUTOFF},
    )

    assessment = assess_benchmark_executor_readiness_v0(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.MISSING_CAPABILITY
        and blocker.detail == BenchmarkExecutorCapability.RETRIEVAL_KNOWLEDGE_CUTOFF.value
        for blocker in assessment.blockers
    )


def test_failed_capture_emission_is_required_for_every_arm() -> None:
    evidence = list(ready_all())
    current = evidence[0]
    evidence[0] = BenchmarkExecutorReadinessEvidence(
        arm=current.arm,
        capabilities=current.capabilities - {BenchmarkExecutorCapability.FAILED_CAPTURE_EMISSION},
    )

    assessment = assess_benchmark_executor_readiness_v0(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_NAIVE_CONTROL,)


def test_source_bindings_are_forbidden_on_non_ordinary_arms() -> None:
    with pytest.raises(ValueError, match="only ORDINARY_AGGREGATION"):
        BenchmarkExecutorReadinessEvidence(
            arm=ObservatoryArm.FRONTIER_NAIVE_CONTROL,
            capabilities=ALL_CAPABILITIES,
            source_ids=frozenset({"pypi.updates"}),
        )


def test_duplicate_arm_evidence_fails_closed() -> None:
    duplicate = ready_evidence(ObservatoryArm.FRONTIER_NAIVE_CONTROL)

    with pytest.raises(ValueError, match="duplicate benchmark arm"):
        assess_benchmark_executor_readiness_v0((*ready_all(), duplicate))
