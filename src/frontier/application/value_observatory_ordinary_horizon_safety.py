from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)


class OrdinaryHorizonSafetyStatus(StrEnum):
    PROVEN_HORIZON_SAFE = "PROVEN_HORIZON_SAFE"
    BLOCKED_UNPROVEN = "BLOCKED_UNPROVEN"


class OrdinaryHorizonSafetyMechanism(StrEnum):
    SOURCE_NATIVE_AS_OF = "SOURCE_NATIVE_AS_OF"
    AUTHORITY_MIRROR_HISTORY = "AUTHORITY_MIRROR_HISTORY"
    IMMUTABLE_PRECAPTURE_SNAPSHOT = "IMMUTABLE_PRECAPTURE_SNAPSHOT"
    NONE = "NONE"


class OrdinaryHorizonSafetyVerdict(StrEnum):
    READY_FOR_EXECUTOR_IMPLEMENTATION = "READY_FOR_EXECUTOR_IMPLEMENTATION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class OrdinarySourceHorizonSafetyProof:
    source_id: str
    status: OrdinaryHorizonSafetyStatus
    mechanism: OrdinaryHorizonSafetyMechanism
    evidence_refs: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("ordinary horizon-safety source_id must be non-empty")
        if not self.detail.strip():
            raise ValueError("ordinary horizon-safety detail must be non-empty")
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("ordinary horizon-safety evidence_refs must be non-empty")
        if self.status is OrdinaryHorizonSafetyStatus.PROVEN_HORIZON_SAFE:
            if self.mechanism is OrdinaryHorizonSafetyMechanism.NONE:
                raise ValueError("proven horizon-safe source requires an explicit mechanism")
        elif self.mechanism is not OrdinaryHorizonSafetyMechanism.NONE:
            raise ValueError("blocked source cannot claim a proven horizon-safety mechanism")


@dataclass(frozen=True, slots=True)
class OrdinaryHorizonSafetyBlocker:
    source_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class OrdinaryHorizonSafetyAssessment:
    verdict: OrdinaryHorizonSafetyVerdict
    proven_source_ids: tuple[str, ...]
    blocked_source_ids: tuple[str, ...]
    blockers: tuple[OrdinaryHorizonSafetyBlocker, ...]


def assess_ordinary_horizon_safety_v0(
    proofs: tuple[OrdinarySourceHorizonSafetyProof, ...],
) -> OrdinaryHorizonSafetyAssessment:
    """Assess source-by-source PIT feasibility without granting executor authority.

    The frozen ordinary-aggregation source set is all-or-nothing for implementation readiness.
    Missing, extra, or duplicate source proofs are integrity failures rather than partial success.
    A source is counted as horizon-safe only when the proof explicitly records a validated
    mechanism; item timestamps or current mutable collection state are insufficient.
    """

    by_source: dict[str, OrdinarySourceHorizonSafetyProof] = {}
    for proof in proofs:
        if proof.source_id in by_source:
            raise ValueError(f"duplicate ordinary horizon-safety proof for {proof.source_id}")
        by_source[proof.source_id] = proof

    supplied_source_ids = frozenset(by_source)
    if supplied_source_ids != BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS:
        missing = sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - supplied_source_ids)
        extra = sorted(supplied_source_ids - BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS)
        raise ValueError(
            "ordinary horizon-safety proof source set mismatch: "
            f"missing={missing!r} extra={extra!r}"
        )

    proven = tuple(
        source_id
        for source_id in sorted(by_source)
        if by_source[source_id].status is OrdinaryHorizonSafetyStatus.PROVEN_HORIZON_SAFE
    )
    blocked = tuple(
        source_id
        for source_id in sorted(by_source)
        if by_source[source_id].status is OrdinaryHorizonSafetyStatus.BLOCKED_UNPROVEN
    )
    blockers = tuple(
        OrdinaryHorizonSafetyBlocker(source_id=source_id, detail=by_source[source_id].detail)
        for source_id in blocked
    )

    verdict = (
        OrdinaryHorizonSafetyVerdict.READY_FOR_EXECUTOR_IMPLEMENTATION
        if not blocked
        else OrdinaryHorizonSafetyVerdict.BLOCKED
    )
    return OrdinaryHorizonSafetyAssessment(
        verdict=verdict,
        proven_source_ids=proven,
        blocked_source_ids=blocked,
        blockers=blockers,
    )
