from __future__ import annotations

from dataclasses import replace

import pytest

from frontier.application.value_observatory_dry_run import BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
    BenchmarkExecutorBlockerCode,
    BenchmarkExecutorCandidate,
    BenchmarkExecutorCapability,
    BenchmarkExecutorReadinessEvidence,
    BenchmarkExecutorReadinessStatus,
    assess_benchmark_executor_readiness_v0,
)
from frontier.domain.digests import Digest
from frontier.domain.value_observatory import BenchmarkExecutorIdentity, ObservatoryArm

ALL_CAPABILITIES = frozenset(BenchmarkExecutorCapability)
PROTOCOL_DIGEST = Digest("sha256:" + "9" * 64)


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def executor_identity(arm: ObservatoryArm) -> BenchmarkExecutorIdentity:
    kwargs: dict[str, object] = {
        "executor_id": f"{arm.value.lower()}-executor",
        "executor_version": "v0",
        "configuration_digest": digest("5"),
    }
    if arm is ObservatoryArm.WEB_LLM_BENCHMARK:
        kwargs.update(
            provider="test-provider",
            model="test-model-v1",
            prompt_digest=digest("6"),
        )
    return BenchmarkExecutorIdentity(**kwargs)  # type: ignore[arg-type]


def candidate_all() -> tuple[BenchmarkExecutorCandidate, ...]:
    return tuple(
        BenchmarkExecutorCandidate(arm=arm, executor=executor_identity(arm))
        for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
    )


def complete_evidence(arm: ObservatoryArm) -> BenchmarkExecutorReadinessEvidence:
    kwargs: dict[str, object] = {
        "arm": arm,
        "executor": executor_identity(arm),
        "protocol_digest": PROTOCOL_DIGEST,
        "proof_ref": f"claim://executor-proof/{arm.value}",
        "proof_digest": digest("a"),
        "capabilities": ALL_CAPABILITIES,
    }
    if arm is ObservatoryArm.ORDINARY_AGGREGATION:
        kwargs.update(
            source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
            horizon_safe_source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
        )
    return BenchmarkExecutorReadinessEvidence(**kwargs)  # type: ignore[arg-type]


def complete_all() -> tuple[BenchmarkExecutorReadinessEvidence, ...]:
    return tuple(complete_evidence(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)


def assess(
    evidence: tuple[BenchmarkExecutorReadinessEvidence, ...],
    *,
    candidates: tuple[BenchmarkExecutorCandidate, ...] | None = None,
    protocol_digest: Digest = PROTOCOL_DIGEST,
):
    if candidates is None:
        candidates = candidate_all()
    return assess_benchmark_executor_readiness_v0(
        candidate_protocol_digest=protocol_digest,
        candidate_executors=candidates,
        evidence=evidence,
    )


def test_complete_self_declared_bundle_stays_pending_trusted_authority() -> None:
    assessment = assess(complete_all())

    assert (
        assessment.status
        is BenchmarkExecutorReadinessStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY
    )
    assert assessment.evidence_complete_arms == BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
    assert assessment.blocked_arms == ()
    assert assessment.blockers == ()
    assert "READY" not in BenchmarkExecutorReadinessStatus.__members__


def test_arbitrary_self_claim_cannot_become_activation_ready() -> None:
    arbitrary_protocol = digest("f")
    candidates = tuple(
        BenchmarkExecutorCandidate(
            arm=arm,
            executor=replace(executor_identity(arm), executor_version="self-declared-v999"),
        )
        for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
    )
    evidence = tuple(
        replace(
            complete_evidence(arm),
            executor=candidates[index].executor,
            protocol_digest=arbitrary_protocol,
            proof_ref="not-verified://self-claim",
            proof_digest=digest("e"),
        )
        for index, arm in enumerate(BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)
    )

    assessment = assess(
        evidence,
        candidates=candidates,
        protocol_digest=arbitrary_protocol,
    )

    assert (
        assessment.status
        is BenchmarkExecutorReadinessStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY
    )
    assert assessment.evidence_complete_arms == BENCHMARK_CAPTURE_V0_REQUIRED_ARMS


def test_missing_arm_evidence_blocks_instead_of_inferring_capability() -> None:
    evidence = tuple(
        item for item in complete_all() if item.arm is not ObservatoryArm.WEB_LLM_BENCHMARK
    )

    assessment = assess(evidence)

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.WEB_LLM_BENCHMARK,)
    assert [(item.code, item.arm) for item in assessment.blockers] == [
        (
            BenchmarkExecutorBlockerCode.ARM_EVIDENCE_MISSING,
            ObservatoryArm.WEB_LLM_BENCHMARK,
        )
    ]


def test_missing_executor_candidate_blocks_evidence_completeness() -> None:
    candidates = tuple(
        item for item in candidate_all() if item.arm is not ObservatoryArm.FRONTIER_NAIVE_CONTROL
    )

    assessment = assess(complete_all(), candidates=candidates)

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_NAIVE_CONTROL,)
    assert assessment.blockers[0].code is BenchmarkExecutorBlockerCode.EXECUTOR_CANDIDATE_MISSING


def test_executor_identity_mismatch_blocks_even_when_capabilities_are_complete() -> None:
    evidence = list(complete_all())
    current = evidence[0]
    evidence[0] = replace(
        current,
        executor=replace(current.executor, executor_version="v1-mutated"),
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_NAIVE_CONTROL,)
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.EXECUTOR_IDENTITY_MISMATCH
        for blocker in assessment.blockers
    )


def test_protocol_digest_mismatch_blocks_internal_candidate_bundle() -> None:
    evidence = list(complete_all())
    evidence[0] = replace(evidence[0], protocol_digest=digest("b"))

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.PROTOCOL_DIGEST_MISMATCH
        for blocker in assessment.blockers
    )


def test_evidence_claim_requires_nonempty_proof_reference() -> None:
    with pytest.raises(ValueError, match="proof_ref must be non-empty"):
        replace(complete_evidence(ObservatoryArm.FRONTIER_NAIVE_CONTROL), proof_ref="   ")


def test_web_llm_candidate_identity_requires_provider_model_and_prompt_digest() -> None:
    with pytest.raises(ValueError, match="requires provider, model, and prompt digest"):
        BenchmarkExecutorCandidate(
            arm=ObservatoryArm.WEB_LLM_BENCHMARK,
            executor=BenchmarkExecutorIdentity(
                executor_id="web-llm",
                executor_version="v0",
                configuration_digest=digest("c"),
            ),
        )


def test_pef_arm_blocks_without_exact_boundary_frozen_output_capability() -> None:
    evidence = list(complete_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL)
    current = evidence[index]
    evidence[index] = replace(
        current,
        capabilities=current.capabilities
        - {BenchmarkExecutorCapability.EXACT_BOUNDARY_FROZEN_PEF_V1},
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,)
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.MISSING_CAPABILITY
        and blocker.detail == BenchmarkExecutorCapability.EXACT_BOUNDARY_FROZEN_PEF_V1.value
        for blocker in assessment.blockers
    )


def test_ordinary_aggregation_requires_exact_frozen_source_set() -> None:
    evidence = list(complete_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.ORDINARY_AGGREGATION)
    source_ids = BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - {"hn.frontpage"}
    evidence[index] = replace(
        evidence[index],
        source_ids=source_ids,
        horizon_safe_source_ids=source_ids,
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert ObservatoryArm.ORDINARY_AGGREGATION in assessment.blocked_arms
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_SET_MISMATCH
        and "hn.frontpage" in blocker.detail
        for blocker in assessment.blockers
    )


def test_ordinary_aggregation_blocks_if_one_collection_state_is_not_horizon_safe() -> None:
    evidence = list(complete_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.ORDINARY_AGGREGATION)
    evidence[index] = replace(
        evidence[index],
        horizon_safe_source_ids=BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - {"pypi.updates"},
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_HORIZON_UNSAFE
        and blocker.detail == "pypi.updates"
        for blocker in assessment.blockers
    )


def test_web_llm_timestamp_metadata_cannot_replace_retrieval_cutoff_enforcement() -> None:
    evidence = list(complete_all())
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.WEB_LLM_BENCHMARK)
    current = evidence[index]
    evidence[index] = replace(
        current,
        capabilities=current.capabilities
        - {BenchmarkExecutorCapability.RETRIEVAL_KNOWLEDGE_CUTOFF},
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert any(
        blocker.code is BenchmarkExecutorBlockerCode.MISSING_CAPABILITY
        and blocker.detail == BenchmarkExecutorCapability.RETRIEVAL_KNOWLEDGE_CUTOFF.value
        for blocker in assessment.blockers
    )


def test_failed_capture_emission_is_required_for_every_arm() -> None:
    evidence = list(complete_all())
    current = evidence[0]
    evidence[0] = replace(
        current,
        capabilities=current.capabilities - {BenchmarkExecutorCapability.FAILED_CAPTURE_EMISSION},
    )

    assessment = assess(tuple(evidence))

    assert assessment.status is BenchmarkExecutorReadinessStatus.BLOCKED
    assert assessment.blocked_arms == (ObservatoryArm.FRONTIER_NAIVE_CONTROL,)


def test_source_bindings_are_forbidden_on_non_ordinary_arms() -> None:
    with pytest.raises(ValueError, match="only ORDINARY_AGGREGATION"):
        replace(
            complete_evidence(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
            source_ids=frozenset({"pypi.updates"}),
        )


def test_duplicate_arm_evidence_fails_closed() -> None:
    duplicate = complete_evidence(ObservatoryArm.FRONTIER_NAIVE_CONTROL)

    with pytest.raises(ValueError, match="duplicate benchmark arm"):
        assess((*complete_all(), duplicate))


def test_duplicate_executor_candidate_fails_closed() -> None:
    duplicate = BenchmarkExecutorCandidate(
        arm=ObservatoryArm.FRONTIER_NAIVE_CONTROL,
        executor=executor_identity(ObservatoryArm.FRONTIER_NAIVE_CONTROL),
    )

    with pytest.raises(ValueError, match="duplicate benchmark arm"):
        assess(complete_all(), candidates=(*candidate_all(), duplicate))
