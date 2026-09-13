from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from frontier.application.value_observatory_dry_run import BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
from frontier.domain.digests import Digest
from frontier.domain.value_observatory import BenchmarkExecutorIdentity, ObservatoryArm

BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS = frozenset(
    {
        "arxiv.cs-ai",
        "cisa.kev",
        "gdelt.frontier",
        "github.ml-repos",
        "hf.models",
        "hn.frontpage",
        "pypi.updates",
    }
)


class BenchmarkExecutorCapability(StrEnum):
    EXECUTOR_PRESENT = "EXECUTOR_PRESENT"
    KNOWLEDGE_HORIZON_ENFORCED = "KNOWLEDGE_HORIZON_ENFORCED"
    IMMUTABLE_CAPTURE_EMISSION = "IMMUTABLE_CAPTURE_EMISSION"
    FAILED_CAPTURE_EMISSION = "FAILED_CAPTURE_EMISSION"

    PIT_CANDIDATE_POPULATION = "PIT_CANDIDATE_POPULATION"
    NAIVE_ORDERING = "NAIVE_ORDERING"
    NO_EXPERIMENTAL_SCORE = "NO_EXPERIMENTAL_SCORE"

    EXACT_BOUNDARY_FROZEN_PEF_V1 = "EXACT_BOUNDARY_FROZEN_PEF_V1"
    NO_PRIOR_BOUNDARY_FALLBACK = "NO_PRIOR_BOUNDARY_FALLBACK"
    NO_PEF_RECOMPUTE = "NO_PEF_RECOMPUTE"

    SOURCE_ATTEMPT_STATUS = "SOURCE_ATTEMPT_STATUS"
    RAW_PAYLOAD_DIGESTS = "RAW_PAYLOAD_DIGESTS"
    NO_FRONTIER_PRIVATE_STATE = "NO_FRONTIER_PRIVATE_STATE"
    ORDINARY_TIMESTAMP_ORDERING = "ORDINARY_TIMESTAMP_ORDERING"

    PROVIDER_IDENTITY = "PROVIDER_IDENTITY"
    EXACT_MODEL_IDENTITY = "EXACT_MODEL_IDENTITY"
    PROMPT_DIGEST = "PROMPT_DIGEST"
    RAW_RESPONSE_DIGEST = "RAW_RESPONSE_DIGEST"
    CITATIONS = "CITATIONS"
    RETRIEVAL_KNOWLEDGE_CUTOFF = "RETRIEVAL_KNOWLEDGE_CUTOFF"
    NO_SILENT_FALLBACK = "NO_SILENT_FALLBACK"


class BenchmarkExecutorReadinessStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class BenchmarkExecutorBlockerCode(StrEnum):
    ARM_EVIDENCE_MISSING = "ARM_EVIDENCE_MISSING"
    EXECUTOR_EXPECTATION_MISSING = "EXECUTOR_EXPECTATION_MISSING"
    EXECUTOR_IDENTITY_MISMATCH = "EXECUTOR_IDENTITY_MISMATCH"
    PROTOCOL_DIGEST_MISMATCH = "PROTOCOL_DIGEST_MISMATCH"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    ORDINARY_SOURCE_SET_MISMATCH = "ORDINARY_SOURCE_SET_MISMATCH"
    ORDINARY_SOURCE_HORIZON_UNSAFE = "ORDINARY_SOURCE_HORIZON_UNSAFE"


_COMMON_CAPABILITIES = frozenset(
    {
        BenchmarkExecutorCapability.EXECUTOR_PRESENT,
        BenchmarkExecutorCapability.KNOWLEDGE_HORIZON_ENFORCED,
        BenchmarkExecutorCapability.IMMUTABLE_CAPTURE_EMISSION,
        BenchmarkExecutorCapability.FAILED_CAPTURE_EMISSION,
    }
)

_REQUIRED_CAPABILITIES = {
    ObservatoryArm.FRONTIER_NAIVE_CONTROL: _COMMON_CAPABILITIES
    | frozenset(
        {
            BenchmarkExecutorCapability.PIT_CANDIDATE_POPULATION,
            BenchmarkExecutorCapability.NAIVE_ORDERING,
            BenchmarkExecutorCapability.NO_EXPERIMENTAL_SCORE,
        }
    ),
    ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL: _COMMON_CAPABILITIES
    | frozenset(
        {
            BenchmarkExecutorCapability.EXACT_BOUNDARY_FROZEN_PEF_V1,
            BenchmarkExecutorCapability.NO_PRIOR_BOUNDARY_FALLBACK,
            BenchmarkExecutorCapability.NO_PEF_RECOMPUTE,
        }
    ),
    ObservatoryArm.ORDINARY_AGGREGATION: _COMMON_CAPABILITIES
    | frozenset(
        {
            BenchmarkExecutorCapability.SOURCE_ATTEMPT_STATUS,
            BenchmarkExecutorCapability.RAW_PAYLOAD_DIGESTS,
            BenchmarkExecutorCapability.NO_FRONTIER_PRIVATE_STATE,
            BenchmarkExecutorCapability.ORDINARY_TIMESTAMP_ORDERING,
        }
    ),
    ObservatoryArm.WEB_LLM_BENCHMARK: _COMMON_CAPABILITIES
    | frozenset(
        {
            BenchmarkExecutorCapability.PROVIDER_IDENTITY,
            BenchmarkExecutorCapability.EXACT_MODEL_IDENTITY,
            BenchmarkExecutorCapability.PROMPT_DIGEST,
            BenchmarkExecutorCapability.RAW_RESPONSE_DIGEST,
            BenchmarkExecutorCapability.CITATIONS,
            BenchmarkExecutorCapability.RETRIEVAL_KNOWLEDGE_CUTOFF,
            BenchmarkExecutorCapability.NO_FRONTIER_PRIVATE_STATE,
            BenchmarkExecutorCapability.NO_SILENT_FALLBACK,
        }
    ),
}


def _require_nonempty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _require_web_llm_identity(
    arm: ObservatoryArm,
    executor: BenchmarkExecutorIdentity,
) -> None:
    if arm is not ObservatoryArm.WEB_LLM_BENCHMARK:
        return
    if executor.provider is None or executor.model is None or executor.prompt_digest is None:
        raise ValueError(
            "WEB_LLM_BENCHMARK executor identity requires provider, model, and prompt digest"
        )


@dataclass(frozen=True, slots=True)
class BenchmarkExecutorExpectation:
    """Trusted expected executor identity for one frozen arm."""

    arm: ObservatoryArm
    executor: BenchmarkExecutorIdentity

    def __post_init__(self) -> None:
        _require_web_llm_identity(self.arm, self.executor)


@dataclass(frozen=True, slots=True)
class BenchmarkExecutorReadinessEvidence:
    """Diagnostic capability evidence bound to one exact executor and proof artifact."""

    arm: ObservatoryArm
    executor: BenchmarkExecutorIdentity
    protocol_digest: Digest
    proof_ref: str
    proof_digest: Digest
    capabilities: frozenset[BenchmarkExecutorCapability]
    source_ids: frozenset[str] = frozenset()
    horizon_safe_source_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_nonempty(self.proof_ref, "executor readiness proof_ref")
        _require_web_llm_identity(self.arm, self.executor)
        if any(not source_id.strip() for source_id in self.source_ids):
            raise ValueError("executor readiness source ids must be non-empty")
        if any(not source_id.strip() for source_id in self.horizon_safe_source_ids):
            raise ValueError("executor readiness horizon-safe source ids must be non-empty")
        if not self.horizon_safe_source_ids.issubset(self.source_ids):
            raise ValueError("horizon-safe source ids must be a subset of attempted source ids")
        if self.arm is not ObservatoryArm.ORDINARY_AGGREGATION and (
            self.source_ids or self.horizon_safe_source_ids
        ):
            raise ValueError("only ORDINARY_AGGREGATION readiness evidence may bind source ids")


@dataclass(frozen=True, slots=True)
class BenchmarkExecutorReadinessBlocker:
    arm: ObservatoryArm
    code: BenchmarkExecutorBlockerCode
    detail: str


@dataclass(frozen=True, slots=True)
class BenchmarkExecutorReadinessAssessment:
    """Pure fail-closed readiness result; never a scored capture or activation receipt."""

    status: BenchmarkExecutorReadinessStatus
    ready_arms: tuple[ObservatoryArm, ...]
    blocked_arms: tuple[ObservatoryArm, ...]
    blockers: tuple[BenchmarkExecutorReadinessBlocker, ...]


def assess_benchmark_executor_readiness_v0(
    *,
    protocol_digest: Digest,
    expected_executors: tuple[BenchmarkExecutorExpectation, ...],
    evidence: tuple[BenchmarkExecutorReadinessEvidence, ...],
) -> BenchmarkExecutorReadinessAssessment:
    """Assess whether all four exact frozen executors satisfy their activation contract."""

    required_arms: set[ObservatoryArm] = set(BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)
    expected_by_arm = _index_expectations(expected_executors, required_arms=required_arms)
    evidence_by_arm = _index_evidence(evidence, required_arms=required_arms)

    blockers: list[BenchmarkExecutorReadinessBlocker] = []
    ready_arms: list[ObservatoryArm] = []
    blocked_arms: list[ObservatoryArm] = []

    for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS:
        expectation = expected_by_arm.get(arm)
        item = evidence_by_arm.get(arm)
        arm_blockers: list[BenchmarkExecutorReadinessBlocker] = []

        if expectation is None:
            arm_blockers.append(
                BenchmarkExecutorReadinessBlocker(
                    arm=arm,
                    code=BenchmarkExecutorBlockerCode.EXECUTOR_EXPECTATION_MISSING,
                    detail="no trusted exact executor identity supplied for frozen arm",
                )
            )

        if item is None:
            arm_blockers.append(
                BenchmarkExecutorReadinessBlocker(
                    arm=arm,
                    code=BenchmarkExecutorBlockerCode.ARM_EVIDENCE_MISSING,
                    detail="no executor readiness evidence supplied for frozen arm",
                )
            )
        else:
            if item.protocol_digest != protocol_digest:
                arm_blockers.append(
                    BenchmarkExecutorReadinessBlocker(
                        arm=arm,
                        code=BenchmarkExecutorBlockerCode.PROTOCOL_DIGEST_MISMATCH,
                        detail="readiness evidence does not bind the frozen benchmark protocol",
                    )
                )
            if expectation is not None and item.executor != expectation.executor:
                arm_blockers.append(
                    BenchmarkExecutorReadinessBlocker(
                        arm=arm,
                        code=BenchmarkExecutorBlockerCode.EXECUTOR_IDENTITY_MISMATCH,
                        detail="readiness evidence does not bind the trusted executor identity",
                    )
                )

            missing_capabilities = _REQUIRED_CAPABILITIES[arm] - item.capabilities
            arm_blockers.extend(
                BenchmarkExecutorReadinessBlocker(
                    arm=arm,
                    code=BenchmarkExecutorBlockerCode.MISSING_CAPABILITY,
                    detail=capability.value,
                )
                for capability in sorted(missing_capabilities, key=lambda value: value.value)
            )
            if arm is ObservatoryArm.ORDINARY_AGGREGATION:
                arm_blockers.extend(_ordinary_source_blockers(item))

        if arm_blockers:
            blocked_arms.append(arm)
            blockers.extend(arm_blockers)
        else:
            ready_arms.append(arm)

    status = (
        BenchmarkExecutorReadinessStatus.READY
        if not blockers
        else BenchmarkExecutorReadinessStatus.BLOCKED
    )
    return BenchmarkExecutorReadinessAssessment(
        status=status,
        ready_arms=tuple(ready_arms),
        blocked_arms=tuple(blocked_arms),
        blockers=tuple(blockers),
    )


def _index_expectations(
    expectations: tuple[BenchmarkExecutorExpectation, ...],
    *,
    required_arms: set[ObservatoryArm],
) -> dict[ObservatoryArm, BenchmarkExecutorExpectation]:
    indexed: dict[ObservatoryArm, BenchmarkExecutorExpectation] = {}
    for item in expectations:
        if item.arm not in required_arms:
            raise ValueError("executor expectation contains a non-V0 benchmark arm")
        if item.arm in indexed:
            raise ValueError("executor expectation contains a duplicate benchmark arm")
        indexed[item.arm] = item
    return indexed


def _index_evidence(
    evidence: tuple[BenchmarkExecutorReadinessEvidence, ...],
    *,
    required_arms: set[ObservatoryArm],
) -> dict[ObservatoryArm, BenchmarkExecutorReadinessEvidence]:
    indexed: dict[ObservatoryArm, BenchmarkExecutorReadinessEvidence] = {}
    for item in evidence:
        if item.arm not in required_arms:
            raise ValueError("executor readiness evidence contains a non-V0 benchmark arm")
        if item.arm in indexed:
            raise ValueError("executor readiness evidence contains a duplicate benchmark arm")
        indexed[item.arm] = item
    return indexed


def _ordinary_source_blockers(
    evidence: BenchmarkExecutorReadinessEvidence,
) -> tuple[BenchmarkExecutorReadinessBlocker, ...]:
    blockers: list[BenchmarkExecutorReadinessBlocker] = []
    if evidence.source_ids != BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS:
        missing = sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - evidence.source_ids)
        unexpected = sorted(evidence.source_ids - BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS)
        blockers.append(
            BenchmarkExecutorReadinessBlocker(
                arm=evidence.arm,
                code=BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_SET_MISMATCH,
                detail=f"missing={missing}; unexpected={unexpected}",
            )
        )

    unsafe = sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - evidence.horizon_safe_source_ids)
    blockers.extend(
        BenchmarkExecutorReadinessBlocker(
            arm=evidence.arm,
            code=BenchmarkExecutorBlockerCode.ORDINARY_SOURCE_HORIZON_UNSAFE,
            detail=source_id,
        )
        for source_id in unsafe
    )
    return tuple(blockers)


__all__ = [
    "BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS",
    "BenchmarkExecutorBlockerCode",
    "BenchmarkExecutorCapability",
    "BenchmarkExecutorExpectation",
    "BenchmarkExecutorReadinessAssessment",
    "BenchmarkExecutorReadinessBlocker",
    "BenchmarkExecutorReadinessEvidence",
    "BenchmarkExecutorReadinessStatus",
    "assess_benchmark_executor_readiness_v0",
]
