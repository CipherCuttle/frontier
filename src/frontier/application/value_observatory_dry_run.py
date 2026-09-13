from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from frontier.domain.digests import Digest
from frontier.domain.value_observatory import (
    CaptureStatus,
    ObservatoryArm,
    ValueObservatoryCapture,
    ValueObservatoryOpportunity,
    ValueObservatoryPopulationManifest,
    require_population_opportunity_completeness,
)

BENCHMARK_CAPTURE_V0_ALERT_BUDGET = 5
BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE = timedelta(minutes=30)
BENCHMARK_CAPTURE_V0_SELECTION_WINDOW = timedelta(hours=24)
BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE = ("GLOBAL",)
BENCHMARK_CAPTURE_V0_REQUIRED_ARMS = (
    ObservatoryArm.FRONTIER_NAIVE_CONTROL,
    ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
    ObservatoryArm.ORDINARY_AGGREGATION,
    ObservatoryArm.WEB_LLM_BENCHMARK,
)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class BenchmarkArmDryRunEvidence:
    """Non-authoritative proof inputs used only to validate one dry-run arm execution."""

    arm: ObservatoryArm
    started_at: datetime
    horizon_enforced: bool
    source_state_horizon: datetime | None

    def __post_init__(self) -> None:
        _require_aware(self.started_at, "dry-run arm started_at")
        if self.source_state_horizon is not None:
            _require_aware(self.source_state_horizon, "dry-run arm source_state_horizon")


@dataclass(frozen=True, slots=True)
class BenchmarkCaptureV0DryRunValidation:
    """Diagnostic validation result. This is not a scored capture or promotion receipt."""

    knowledge_horizon: datetime
    population_id: str
    opportunity_ids: tuple[str, ...]
    capture_ids: tuple[str, ...]
    complete_arms: tuple[ObservatoryArm, ...]
    failed_arms: tuple[ObservatoryArm, ...]


def validate_benchmark_capture_v0_dry_run(
    *,
    protocol_digest: Digest,
    population: ValueObservatoryPopulationManifest,
    opportunities: tuple[ValueObservatoryOpportunity, ...],
    captures: tuple[ValueObservatoryCapture, ...],
    arm_evidence: tuple[BenchmarkArmDryRunEvidence, ...],
) -> BenchmarkCaptureV0DryRunValidation:
    """Fail closed unless one boundary satisfies the frozen BENCHMARK_CAPTURE_V0 contract.

    The validator deliberately performs no network access, persistence, scheduling, scoring, or
    ranking. It proves only that already-constructed dry-run artifacts and execution evidence obey
    the frozen boundary contract strongly enough to proceed to a later executor-readiness phase.
    """

    knowledge_horizon = population.knowledge_horizon
    required_arms = set(BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)

    require_population_opportunity_completeness(population, opportunities)

    capture_by_arm = _index_captures(captures)
    evidence_by_arm = _index_arm_evidence(arm_evidence)
    if set(capture_by_arm) != required_arms:
        raise ValueError("dry-run captures must contain exactly the four frozen benchmark arms")
    if set(evidence_by_arm) != required_arms:
        raise ValueError("dry-run evidence must contain exactly the four frozen benchmark arms")

    first_arm_start = min(item.started_at for item in arm_evidence)
    if population.recorded_at > first_arm_start:
        raise ValueError("population manifest must be frozen before any benchmark arm starts")
    if any(item.recorded_at > first_arm_start for item in opportunities):
        raise ValueError("all opportunities must be preregistered before any benchmark arm starts")

    deadline = knowledge_horizon + BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE
    window_start = knowledge_horizon - BENCHMARK_CAPTURE_V0_SELECTION_WINDOW

    complete_arms: list[ObservatoryArm] = []
    failed_arms: list[ObservatoryArm] = []
    capture_ids: list[str] = []

    for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS:
        capture = capture_by_arm[arm]
        evidence = evidence_by_arm[arm]
        _validate_capture_contract(
            capture=capture,
            evidence=evidence,
            protocol_digest=protocol_digest,
            knowledge_horizon=knowledge_horizon,
            window_start=window_start,
            deadline=deadline,
        )
        capture_ids.append(capture.capture_id)
        if capture.status is CaptureStatus.COMPLETE:
            complete_arms.append(arm)
        else:
            failed_arms.append(arm)

    return BenchmarkCaptureV0DryRunValidation(
        knowledge_horizon=knowledge_horizon,
        population_id=population.population_id,
        opportunity_ids=tuple(sorted(item.opportunity_id for item in opportunities)),
        capture_ids=tuple(capture_ids),
        complete_arms=tuple(complete_arms),
        failed_arms=tuple(failed_arms),
    )


def _index_captures(
    captures: tuple[ValueObservatoryCapture, ...],
) -> dict[ObservatoryArm, ValueObservatoryCapture]:
    result: dict[ObservatoryArm, ValueObservatoryCapture] = {}
    for capture in captures:
        if capture.arm in result:
            raise ValueError("dry-run captures contain a duplicate benchmark arm")
        result[capture.arm] = capture
    return result


def _index_arm_evidence(
    evidence: tuple[BenchmarkArmDryRunEvidence, ...],
) -> dict[ObservatoryArm, BenchmarkArmDryRunEvidence]:
    result: dict[ObservatoryArm, BenchmarkArmDryRunEvidence] = {}
    for item in evidence:
        if item.arm in result:
            raise ValueError("dry-run execution evidence contains a duplicate benchmark arm")
        result[item.arm] = item
    return result


def _validate_capture_contract(
    *,
    capture: ValueObservatoryCapture,
    evidence: BenchmarkArmDryRunEvidence,
    protocol_digest: Digest,
    knowledge_horizon: datetime,
    window_start: datetime,
    deadline: datetime,
) -> None:
    if capture.arm is not evidence.arm:
        raise ValueError("dry-run capture arm does not match its execution evidence")
    if capture.knowledge_horizon != knowledge_horizon:
        raise ValueError("dry-run capture knowledge horizon does not match the frozen population")
    if capture.protocol_digest != protocol_digest:
        raise ValueError("dry-run capture protocol digest does not match BENCHMARK_CAPTURE_V0")
    if capture.alert_budget != BENCHMARK_CAPTURE_V0_ALERT_BUDGET:
        raise ValueError("dry-run capture must use the frozen K=5 alert budget")
    if capture.domain_scope != BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE:
        raise ValueError("dry-run capture must use the frozen GLOBAL domain scope")
    if capture.selection_window_start != window_start:
        raise ValueError("dry-run capture selection window start is not the frozen 24-hour boundary")
    if capture.selection_window_end != knowledge_horizon:
        raise ValueError("dry-run capture selection window must end at the knowledge horizon")
    if evidence.started_at < knowledge_horizon:
        raise ValueError("dry-run arm cannot start before the aligned knowledge horizon")
    if evidence.started_at > deadline:
        raise ValueError("dry-run arm start exceeds the frozen 30-minute capture deadline")
    if capture.captured_at < evidence.started_at:
        raise ValueError("dry-run capture cannot complete before its arm starts")
    if capture.captured_at > deadline:
        raise ValueError("dry-run capture exceeds the frozen 30-minute capture deadline")

    if capture.status is CaptureStatus.COMPLETE:
        if not evidence.horizon_enforced:
            raise ValueError("complete dry-run arm requires enforced point-in-time source state")
        if evidence.source_state_horizon != knowledge_horizon:
            raise ValueError("complete dry-run arm source state must bind the exact knowledge horizon")


__all__ = [
    "BENCHMARK_CAPTURE_V0_ALERT_BUDGET",
    "BENCHMARK_CAPTURE_V0_CAPTURE_DEADLINE",
    "BENCHMARK_CAPTURE_V0_DOMAIN_SCOPE",
    "BENCHMARK_CAPTURE_V0_REQUIRED_ARMS",
    "BENCHMARK_CAPTURE_V0_SELECTION_WINDOW",
    "BenchmarkArmDryRunEvidence",
    "BenchmarkCaptureV0DryRunValidation",
    "validate_benchmark_capture_v0_dry_run",
]
