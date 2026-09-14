from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)


class OrdinaryHorizonSafetyStatus(StrEnum):
    EVIDENCE_COMPLETE_PENDING_AUTHORITY = "EVIDENCE_COMPLETE_PENDING_AUTHORITY"
    BLOCKED_UNPROVEN = "BLOCKED_UNPROVEN"


class OrdinaryHorizonSafetyMechanism(StrEnum):
    SOURCE_NATIVE_AS_OF = "SOURCE_NATIVE_AS_OF"
    AUTHORITY_MIRROR_HISTORY = "AUTHORITY_MIRROR_HISTORY"
    IMMUTABLE_PRECAPTURE_SNAPSHOT = "IMMUTABLE_PRECAPTURE_SNAPSHOT"
    NONE = "NONE"


class OrdinaryHorizonSafetyVerdict(StrEnum):
    EVIDENCE_COMPLETE_PENDING_AUTHORITY = "EVIDENCE_COMPLETE_PENDING_AUTHORITY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class OrdinarySourceHorizonSafetyProof:
    """Caller-supplied horizon-safety evidence claim; never trusted authority."""

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
        if self.status is OrdinaryHorizonSafetyStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY:
            if self.mechanism is OrdinaryHorizonSafetyMechanism.NONE:
                raise ValueError("evidence-complete source claim requires an explicit mechanism")
        elif self.mechanism is not OrdinaryHorizonSafetyMechanism.NONE:
            raise ValueError("blocked source cannot claim a horizon-safety mechanism")


@dataclass(frozen=True, slots=True)
class OrdinaryHorizonSafetyBlocker:
    source_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class OrdinaryHorizonSafetyAssessment:
    """Pure evidence-completeness result; never implementation or activation authority."""

    verdict: OrdinaryHorizonSafetyVerdict
    evidence_complete_source_ids: tuple[str, ...]
    blocked_source_ids: tuple[str, ...]
    blockers: tuple[OrdinaryHorizonSafetyBlocker, ...]


def assess_ordinary_horizon_safety_v0(
    proofs: tuple[OrdinarySourceHorizonSafetyProof, ...],
) -> OrdinaryHorizonSafetyAssessment:
    """Assess source-by-source PIT evidence without granting executor authority.

    All proof rows are caller supplied. Missing, extra, or duplicate source claims are integrity
    failures rather than partial success. Even when every claim is internally complete, the
    strongest possible verdict is EVIDENCE_COMPLETE_PENDING_AUTHORITY. A later separately reviewed
    authority phase must bind the exact approved proof artifact and independently verify its
    evidence before executor implementation can be authorized.
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

    evidence_complete = tuple(
        source_id
        for source_id in sorted(by_source)
        if by_source[source_id].status
        is OrdinaryHorizonSafetyStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY
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
        OrdinaryHorizonSafetyVerdict.EVIDENCE_COMPLETE_PENDING_AUTHORITY
        if not blocked
        else OrdinaryHorizonSafetyVerdict.BLOCKED
    )
    return OrdinaryHorizonSafetyAssessment(
        verdict=verdict,
        evidence_complete_source_ids=evidence_complete,
        blocked_source_ids=blocked,
        blockers=blockers,
    )
