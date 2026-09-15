from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex

DECISION_VALUE_WTP_PREREGISTRATION_PATH = (
    "experiments/value_observatory_v0/decision_value_wtp_v0.json"
)
DECISION_VALUE_WTP_PROTOCOL_DIGEST = Digest(
    "sha256:58887a83812b54248c5c7e7aa03684757719199804a2c08fefc1d830f56301c3"
)
INITIAL_MARKET_SEGMENTS = frozenset(
    {
        "AI_SOFTWARE_RESEARCH_STRATEGY",
        "TECHNICAL_DILIGENCE_INVESTMENT_RESEARCH",
        "DEVELOPER_SECURITY_ECOSYSTEM_MONITORING",
    }
)

_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class PacketVariant(StrEnum):
    BASELINE_PACKET = "BASELINE_PACKET"
    FRONTIER_PACKET = "FRONTIER_PACKET"


class DecisionOutcomeStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    PROTOCOL_FAILURE = "PROTOCOL_FAILURE"


class SequentialMethod(StrEnum):
    ERROR_SPENDING = "ERROR_SPENDING"
    CONFIDENCE_SEQUENCE = "CONFIDENCE_SEQUENCE"
    OTHER_REPEATED_LOOK_VALID = "OTHER_REPEATED_LOOK_VALID"


class SequentialSidedness(StrEnum):
    TWO_SIDED = "TWO_SIDED"
    UPPER = "UPPER"
    LOWER = "LOWER"


class SequentialFutilityPolicy(StrEnum):
    NONE = "NONE"
    BOUND_RULE = "BOUND_RULE"


class CommercialOutcomeKind(StrEnum):
    OFFER_DECLINED = "OFFER_DECLINED"
    OFFER_EXPIRED = "OFFER_EXPIRED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_SETTLED = "PAYMENT_SETTLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    REFUND = "REFUND"
    CHARGEBACK = "CHARGEBACK"
    ACTIVE_USAGE = "ACTIVE_USAGE"
    SUPPORT_INTERVENTION = "SUPPORT_INTERVENTION"
    CANCELLATION = "CANCELLATION"
    RENEWAL = "RENEWAL"
    NONRENEWAL = "NONRENEWAL"


class PaymentEvidenceKind(StrEnum):
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_SETTLED = "PAYMENT_SETTLED"


_PRIMARY_WINDOW_KINDS = {
    CommercialOutcomeKind.OFFER_DECLINED,
    CommercialOutcomeKind.PAYMENT_AUTHORIZED,
    CommercialOutcomeKind.PAYMENT_SETTLED,
    CommercialOutcomeKind.PAYMENT_FAILED,
}
_PAYMENT_AMOUNT_KINDS = {
    CommercialOutcomeKind.PAYMENT_AUTHORIZED,
    CommercialOutcomeKind.PAYMENT_SETTLED,
    CommercialOutcomeKind.PAYMENT_FAILED,
    CommercialOutcomeKind.REFUND,
    CommercialOutcomeKind.CHARGEBACK,
    CommercialOutcomeKind.RENEWAL,
}
_REVEALED_WTP_OUTCOME_KINDS = {
    CommercialOutcomeKind.PAYMENT_AUTHORIZED,
    CommercialOutcomeKind.PAYMENT_SETTLED,
}


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_stable_id(value: str, field: str) -> None:
    if not _STABLE_ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a stable non-empty identifier")


def _require_text(value: str, field: str) -> None:
    if not value.strip():
        raise ValueError(f"{field} must be non-empty")


def _require_protocol_digest(value: Digest) -> None:
    if value != DECISION_VALUE_WTP_PROTOCOL_DIGEST:
        raise ValueError(
            "artifact does not bind the frozen FRONTIER_DECISION_VALUE_WTP_V0 protocol"
        )


def _artifact_digest(canonical: dict[str, CanonicalValue]) -> Digest:
    return sha256_digest(canonical_json_bytes(canonical))


def _artifact_id(prefix: str, canonical: dict[str, CanonicalValue]) -> str:
    return prefix + sha256_hex(canonical_json_bytes(canonical))


def _digest_set(values: tuple[Digest, ...], *, field: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicate digests")
    return tuple(sorted(str(value) for value in values))


@dataclass(frozen=True, slots=True)
class SequentialValidityEvidenceV0:
    evidence_id: str
    frozen_at: datetime
    stopping_plan_digest: Digest
    method: SequentialMethod
    method_version: str
    max_sample_size: int
    look_schedule: tuple[int, ...]
    error_target_ppm: int
    sidedness: SequentialSidedness
    boundary_specification_digest: Digest
    operating_characteristic_validation_digest: Digest
    futility_policy: SequentialFutilityPolicy = SequentialFutilityPolicy.NONE
    futility_rule_digest: Digest | None = None
    schema_version: str = "sequential-validity-evidence-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.evidence_id, "evidence_id")
        _require_aware(self.frozen_at, "frozen_at")
        _require_text(self.method_version, "method_version")
        if self.max_sample_size <= 0:
            raise ValueError("max_sample_size must be positive")
        if not self.look_schedule:
            raise ValueError("sequential evidence requires at least one planned look")
        if any(look <= 0 for look in self.look_schedule):
            raise ValueError("sequential look sizes must be positive")
        if tuple(sorted(set(self.look_schedule))) != self.look_schedule:
            raise ValueError("sequential look schedule must be strictly increasing and unique")
        if self.look_schedule[-1] != self.max_sample_size:
            raise ValueError("final sequential look must equal max_sample_size")
        if not 1 <= self.error_target_ppm < 1_000_000:
            raise ValueError("error_target_ppm must be between 1 and 999999")
        if self.futility_policy is SequentialFutilityPolicy.NONE:
            if self.futility_rule_digest is not None:
                raise ValueError("no-futility policy cannot carry futility_rule_digest")
        elif self.futility_rule_digest is None:
            raise ValueError("bound futility policy requires futility_rule_digest")
        if self.schema_version != "sequential-validity-evidence-v0":
            raise ValueError("sequential validity evidence schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("sequentialvalidity_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "boundary_specification_digest": str(self.boundary_specification_digest),
            "error_target_ppm": self.error_target_ppm,
            "evidence_id": self.evidence_id,
            "frozen_at": canonical_timestamp(self.frozen_at),
            "futility_policy": self.futility_policy.value,
            "futility_rule_digest": (
                None if self.futility_rule_digest is None else str(self.futility_rule_digest)
            ),
            "look_schedule": list(self.look_schedule),
            "max_sample_size": self.max_sample_size,
            "method": self.method.value,
            "method_version": self.method_version,
            "operating_characteristic_validation_digest": str(
                self.operating_characteristic_validation_digest
            ),
            "schema_version": self.schema_version,
            "sidedness": self.sidedness.value,
            "stopping_plan_digest": str(self.stopping_plan_digest),
        }


@dataclass(frozen=True, slots=True)
class RandomizationBlockV0:
    block_id: str
    baseline_weight_bps: int
    frontier_weight_bps: int

    def __post_init__(self) -> None:
        _require_stable_id(self.block_id, "block_id")
        if self.baseline_weight_bps <= 0 or self.frontier_weight_bps <= 0:
            raise ValueError("both randomization arms require positive weight")
        if self.baseline_weight_bps + self.frontier_weight_bps != 10_000:
            raise ValueError("randomization arm weights must sum to 10000 bps")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "baseline_weight_bps": self.baseline_weight_bps,
            "block_id": self.block_id,
            "frontier_weight_bps": self.frontier_weight_bps,
        }


@dataclass(frozen=True, slots=True)
class ParticipantBlockAssignmentV0:
    participant_id_digest: Digest
    block_id: str

    def __post_init__(self) -> None:
        _require_stable_id(self.block_id, "block_id")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "block_id": self.block_id,
            "participant_id_digest": str(self.participant_id_digest),
        }


@dataclass(frozen=True, slots=True)
class RandomizationPlanV0:
    plan_id: str
    frozen_at: datetime
    blocks: tuple[RandomizationBlockV0, ...]
    participant_block_assignments: tuple[ParticipantBlockAssignmentV0, ...]
    algorithm: str = "SHA256_THRESHOLD_V0"
    schema_version: str = "randomization-plan-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.plan_id, "plan_id")
        _require_aware(self.frozen_at, "frozen_at")
        if not self.blocks:
            raise ValueError("randomization plan requires at least one block")
        block_ids = [block.block_id for block in self.blocks]
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("randomization plan block IDs must be unique")
        if not self.participant_block_assignments:
            raise ValueError("randomization plan requires frozen participant block assignments")
        participant_ids = [
            assignment.participant_id_digest for assignment in self.participant_block_assignments
        ]
        if len(set(participant_ids)) != len(participant_ids):
            raise ValueError("participant block assignments must be unique by participant")
        authorized_blocks = set(block_ids)
        if any(
            assignment.block_id not in authorized_blocks
            for assignment in self.participant_block_assignments
        ):
            raise ValueError("participant block assignment references unknown block")
        if self.algorithm != "SHA256_THRESHOLD_V0":
            raise ValueError("unsupported randomization algorithm")
        if self.schema_version != "randomization-plan-v0":
            raise ValueError("randomization plan schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("randomizationplan_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        ordered_blocks = sorted(self.blocks, key=lambda block: block.block_id)
        ordered_assignments = sorted(
            self.participant_block_assignments,
            key=lambda assignment: str(assignment.participant_id_digest),
        )
        return {
            "algorithm": self.algorithm,
            "blocks": [block.to_canonical() for block in ordered_blocks],
            "frozen_at": canonical_timestamp(self.frozen_at),
            "participant_block_assignments": [
                assignment.to_canonical() for assignment in ordered_assignments
            ],
            "plan_id": self.plan_id,
            "schema_version": self.schema_version,
        }


def expected_assignment_block(
    plan: RandomizationPlanV0,
    *,
    participant_id_digest: Digest,
) -> str:
    assignment = next(
        (
            item
            for item in plan.participant_block_assignments
            if item.participant_id_digest == participant_id_digest
        ),
        None,
    )
    if assignment is None:
        raise ValueError("participant is not in frozen randomization block assignments")
    return assignment.block_id


def expected_packet_variant(
    plan: RandomizationPlanV0,
    *,
    participant_id_digest: Digest,
) -> PacketVariant:
    block_id = expected_assignment_block(
        plan,
        participant_id_digest=participant_id_digest,
    )
    block = next(item for item in plan.blocks if item.block_id == block_id)
    draw_input: dict[str, CanonicalValue] = {
        "block_id": block_id,
        "participant_id_digest": str(participant_id_digest),
        "plan_digest": str(plan.artifact_digest),
    }
    draw = int(sha256_hex(canonical_json_bytes(draw_input))[:16], 16) % 10_000
    if draw < block.baseline_weight_bps:
        return PacketVariant.BASELINE_PACKET
    return PacketVariant.FRONTIER_PACKET


@dataclass(frozen=True, slots=True)
class DecisionCohortActivationV0:
    cohort_id: str
    activated_at: datetime
    protocol_digest: Digest
    case_set_digest: Digest
    packet_schema_digest: Digest
    primary_estimand_digest: Digest
    multiplicity_policy_digest: Digest
    randomization_plan: RandomizationPlanV0
    participant_rules_digest: Digest
    case_order_policy_digest: Digest
    failure_semantics_digest: Digest
    stopping_plan_digest: Digest
    sequential_monitoring: bool = False
    sequential_validity_evidence: SequentialValidityEvidenceV0 | None = None
    assignment: str = "RANDOMIZED_BLOCKED_PARTICIPANT_LEVEL"
    primary_analysis: str = "INTENTION_TO_TREAT_BY_PARTICIPANT_ASSIGNMENT"
    participant_exposure_to_both_variants: bool = False
    schema_version: str = "decision-cohort-activation-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.cohort_id, "cohort_id")
        _require_aware(self.activated_at, "activated_at")
        _require_protocol_digest(self.protocol_digest)
        if self.randomization_plan.frozen_at > self.activated_at:
            raise ValueError("randomization plan must be frozen before cohort activation")
        if self.assignment != "RANDOMIZED_BLOCKED_PARTICIPANT_LEVEL":
            raise ValueError("confirmatory decision cohorts require participant-level assignment")
        if self.primary_analysis != "INTENTION_TO_TREAT_BY_PARTICIPANT_ASSIGNMENT":
            raise ValueError(
                "confirmatory decision cohorts require participant-level intention-to-treat"
            )
        if self.participant_exposure_to_both_variants:
            raise ValueError(
                "confirmatory participants may not cross packet variants within a cohort"
            )
        if self.sequential_monitoring:
            if self.sequential_validity_evidence is None:
                raise ValueError("sequential monitoring requires validated sequential evidence")
            if self.sequential_validity_evidence.frozen_at > self.activated_at:
                raise ValueError("sequential evidence must be frozen before cohort activation")
            if self.sequential_validity_evidence.stopping_plan_digest != self.stopping_plan_digest:
                raise ValueError("sequential evidence does not bind activation stopping plan")
        elif self.sequential_validity_evidence is not None:
            raise ValueError("fixed-sample activation cannot carry sequential validity evidence")
        if self.schema_version != "decision-cohort-activation-v0":
            raise ValueError("decision cohort activation schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("decisioncohort_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "activated_at": canonical_timestamp(self.activated_at),
            "assignment": self.assignment,
            "case_order_policy_digest": str(self.case_order_policy_digest),
            "case_set_digest": str(self.case_set_digest),
            "cohort_id": self.cohort_id,
            "failure_semantics_digest": str(self.failure_semantics_digest),
            "multiplicity_policy_digest": str(self.multiplicity_policy_digest),
            "packet_schema_digest": str(self.packet_schema_digest),
            "participant_exposure_to_both_variants": self.participant_exposure_to_both_variants,
            "participant_rules_digest": str(self.participant_rules_digest),
            "primary_analysis": self.primary_analysis,
            "primary_estimand_digest": str(self.primary_estimand_digest),
            "protocol_digest": str(self.protocol_digest),
            "randomization_plan_digest": str(self.randomization_plan.artifact_digest),
            "schema_version": self.schema_version,
            "sequential_monitoring": self.sequential_monitoring,
            "sequential_validity_evidence_digest": (
                None
                if self.sequential_validity_evidence is None
                else str(self.sequential_validity_evidence.artifact_digest)
            ),
            "stopping_plan_digest": str(self.stopping_plan_digest),
        }


@dataclass(frozen=True, slots=True)
class DecisionCaseV0:
    cohort_id: str
    case_id: str
    domain: str
    knowledge_horizon: datetime
    decision_question: str
    action_set: tuple[str, ...]
    utility_rule_digest: Digest
    maturation_rule: str
    baseline_packet_digest: Digest
    frontier_packet_digest: Digest
    evidence_digests: tuple[Digest, ...]
    schema_version: str = "decision-case-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.cohort_id, "cohort_id")
        _require_stable_id(self.case_id, "case_id")
        _require_text(self.domain, "domain")
        _require_aware(self.knowledge_horizon, "knowledge_horizon")
        _require_text(self.decision_question, "decision_question")
        _require_text(self.maturation_rule, "maturation_rule")
        if not self.action_set:
            raise ValueError("decision case requires a non-empty action set")
        if any(not action.strip() for action in self.action_set):
            raise ValueError("decision case actions must be non-empty")
        if len(set(self.action_set)) != len(self.action_set):
            raise ValueError("decision case action set must not contain duplicates")
        if self.baseline_packet_digest == self.frontier_packet_digest:
            raise ValueError("baseline and FRONTIER packet digests must be distinct")
        if not self.evidence_digests:
            raise ValueError("decision case requires at least one immutable evidence digest")
        if len(set(self.evidence_digests)) != len(self.evidence_digests):
            raise ValueError("decision case evidence digests must not contain duplicates")
        if self.schema_version != "decision-case-v0":
            raise ValueError("decision case schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("decisioncase_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "action_set": list(self.action_set),
            "baseline_packet_digest": str(self.baseline_packet_digest),
            "case_id": self.case_id,
            "cohort_id": self.cohort_id,
            "decision_question": self.decision_question,
            "domain": self.domain,
            "evidence_digests": [str(value) for value in self.evidence_digests],
            "frontier_packet_digest": str(self.frontier_packet_digest),
            "knowledge_horizon": canonical_timestamp(self.knowledge_horizon),
            "maturation_rule": self.maturation_rule,
            "schema_version": self.schema_version,
            "utility_rule_digest": str(self.utility_rule_digest),
        }


def decision_case_set_digest(cases: tuple[DecisionCaseV0, ...]) -> Digest:
    if not cases:
        raise ValueError("decision case set cannot be empty")
    ordered = sorted(cases, key=lambda case: (case.cohort_id, case.case_id))
    identities = [(case.cohort_id, case.case_id) for case in ordered]
    if len(set(identities)) != len(identities):
        raise ValueError("decision case set contains duplicate cohort/case identity")
    return sha256_digest(canonical_json_bytes([str(case.artifact_digest) for case in ordered]))


def validate_case_set_against_activation(
    cases: tuple[DecisionCaseV0, ...],
    *,
    activation: DecisionCohortActivationV0,
) -> None:
    if any(case.cohort_id != activation.cohort_id for case in cases):
        raise ValueError("decision case set contains case from another cohort")
    if decision_case_set_digest(cases) != activation.case_set_digest:
        raise ValueError("decision case set digest does not match cohort activation")


@dataclass(frozen=True, slots=True)
class DecisionResponseReceiptV0:
    cohort_id: str
    case_id: str
    participant_id_digest: Digest
    assignment_block_id: str
    assigned_variant: PacketVariant
    presented_packet_digest: Digest
    action: str
    responded_at: datetime
    elapsed_ms: int
    confidence_bps: int | None = None
    schema_version: str = "decision-response-receipt-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.cohort_id, "cohort_id")
        _require_stable_id(self.case_id, "case_id")
        _require_stable_id(self.assignment_block_id, "assignment_block_id")
        _require_text(self.action, "action")
        _require_aware(self.responded_at, "responded_at")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms cannot be negative")
        if self.confidence_bps is not None and not 0 <= self.confidence_bps <= 10_000:
            raise ValueError("confidence_bps must be between 0 and 10000")
        if self.schema_version != "decision-response-receipt-v0":
            raise ValueError("decision response receipt schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("decisionresponse_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "action": self.action,
            "assigned_variant": self.assigned_variant.value,
            "assignment_block_id": self.assignment_block_id,
            "case_id": self.case_id,
            "cohort_id": self.cohort_id,
            "confidence_bps": self.confidence_bps,
            "elapsed_ms": self.elapsed_ms,
            "participant_id_digest": str(self.participant_id_digest),
            "presented_packet_digest": str(self.presented_packet_digest),
            "responded_at": canonical_timestamp(self.responded_at),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DecisionOutcomeReceiptV0:
    cohort_id: str
    case_id: str
    response_receipt_digest: Digest
    matured_at: datetime
    status: DecisionOutcomeStatus
    outcome_label: str | None = None
    utility_microunits: int | None = None
    protocol_failure_reason: str | None = None
    schema_version: str = "decision-outcome-receipt-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.cohort_id, "cohort_id")
        _require_stable_id(self.case_id, "case_id")
        _require_aware(self.matured_at, "matured_at")
        if self.status is DecisionOutcomeStatus.RESOLVED:
            if self.outcome_label is None or not self.outcome_label.strip():
                raise ValueError("resolved decision outcome requires an outcome label")
            if self.utility_microunits is None:
                raise ValueError("resolved decision outcome requires utility_microunits")
            if self.protocol_failure_reason is not None:
                raise ValueError("resolved decision outcome cannot carry a protocol failure reason")
        elif self.status is DecisionOutcomeStatus.UNRESOLVED:
            if self.outcome_label is not None or self.utility_microunits is not None:
                raise ValueError("unresolved decision outcome cannot carry resolved outcome values")
            if self.protocol_failure_reason is not None:
                raise ValueError(
                    "unresolved decision outcome cannot carry a protocol failure reason"
                )
        else:
            if self.protocol_failure_reason is None or not self.protocol_failure_reason.strip():
                raise ValueError("protocol failure outcome requires an explicit reason")
            if self.outcome_label is not None or self.utility_microunits is not None:
                raise ValueError("protocol failure outcome cannot carry resolved outcome values")
        if self.schema_version != "decision-outcome-receipt-v0":
            raise ValueError("decision outcome receipt schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("decisionoutcome_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "case_id": self.case_id,
            "cohort_id": self.cohort_id,
            "matured_at": canonical_timestamp(self.matured_at),
            "outcome_label": self.outcome_label,
            "protocol_failure_reason": self.protocol_failure_reason,
            "response_receipt_digest": str(self.response_receipt_digest),
            "schema_version": self.schema_version,
            "status": self.status.value,
            "utility_microunits": self.utility_microunits,
        }


@dataclass(frozen=True, slots=True)
class PriceCellV0:
    segment_id: str
    price_minor: int
    assignment_weight_bps: int

    def __post_init__(self) -> None:
        _require_stable_id(self.segment_id, "segment_id")
        if self.segment_id not in INITIAL_MARKET_SEGMENTS:
            raise ValueError("price cell segment is not authorized by V0 market authority")
        if self.price_minor <= 0:
            raise ValueError("price_minor must be positive")
        if not 1 <= self.assignment_weight_bps <= 10_000:
            raise ValueError("assignment_weight_bps must be between 1 and 10000")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "assignment_weight_bps": self.assignment_weight_bps,
            "price_minor": self.price_minor,
            "segment_id": self.segment_id,
        }


@dataclass(frozen=True, slots=True)
class PriceScheduleV0:
    schedule_id: str
    frozen_at: datetime
    protocol_digest: Digest
    entitlement_id: str
    entitlement_digest: Digest
    billing_period: str
    currency: str
    tax_treatment: str
    renewal_terms: str
    refund_terms: str
    conversion_definition: str
    conversion_window_seconds: int
    participant_rules_digest: Digest
    segment_assignment_rules_digest: Digest
    primary_commercial_estimand_digest: Digest
    stopping_plan_digest: Digest
    cells: tuple[PriceCellV0, ...]
    target_offer_count_per_cell: int | None = None
    two_price_exception_authority_digest: Digest | None = None
    sequential_monitoring: bool = False
    sequential_validity_evidence: SequentialValidityEvidenceV0 | None = None
    schema_version: str = "price-schedule-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.schedule_id, "schedule_id")
        _require_stable_id(self.entitlement_id, "entitlement_id")
        _require_aware(self.frozen_at, "frozen_at")
        _require_protocol_digest(self.protocol_digest)
        if not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("currency must be an uppercase ISO-style three-letter code")
        for field_name, value in (
            ("billing_period", self.billing_period),
            ("tax_treatment", self.tax_treatment),
            ("renewal_terms", self.renewal_terms),
            ("refund_terms", self.refund_terms),
            ("conversion_definition", self.conversion_definition),
        ):
            _require_text(value, field_name)
        if self.conversion_window_seconds <= 0:
            raise ValueError("conversion_window_seconds must be positive")
        if not self.cells:
            raise ValueError("price schedule requires price cells")
        grouped: dict[str, list[PriceCellV0]] = {}
        for cell in self.cells:
            grouped.setdefault(cell.segment_id, []).append(cell)
        for segment_id, cells in grouped.items():
            prices = {cell.price_minor for cell in cells}
            if len(prices) != len(cells):
                raise ValueError(f"duplicate price point in segment {segment_id}")
            minimum = 2 if self.two_price_exception_authority_digest is not None else 3
            if len(prices) < minimum:
                raise ValueError(
                    f"segment {segment_id} requires at least {minimum} distinct non-zero prices"
                )
            if sum(cell.assignment_weight_bps for cell in cells) != 10_000:
                raise ValueError(f"segment {segment_id} assignment weights must sum to 10000 bps")
        if self.sequential_monitoring:
            if self.sequential_validity_evidence is None:
                raise ValueError(
                    "sequential price monitoring requires validated sequential evidence"
                )
            if self.sequential_validity_evidence.frozen_at > self.frozen_at:
                raise ValueError("sequential evidence must be frozen before price schedule")
            if self.sequential_validity_evidence.stopping_plan_digest != self.stopping_plan_digest:
                raise ValueError("sequential evidence does not bind price stopping plan")
            if self.target_offer_count_per_cell is not None:
                raise ValueError("sequential schedule cannot also declare fixed target offer count")
        else:
            if self.sequential_validity_evidence is not None:
                raise ValueError("fixed-offer schedule cannot carry sequential validity evidence")
            if self.target_offer_count_per_cell is None or self.target_offer_count_per_cell <= 0:
                raise ValueError(
                    "fixed-offer schedule requires positive target_offer_count_per_cell"
                )
        if self.schema_version != "price-schedule-v0":
            raise ValueError("price schedule schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("priceschedule_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        ordered_cells = sorted(
            self.cells,
            key=lambda cell: (cell.segment_id, cell.price_minor, cell.assignment_weight_bps),
        )
        return {
            "billing_period": self.billing_period,
            "cells": [cell.to_canonical() for cell in ordered_cells],
            "conversion_definition": self.conversion_definition,
            "conversion_window_seconds": self.conversion_window_seconds,
            "currency": self.currency,
            "entitlement_digest": str(self.entitlement_digest),
            "entitlement_id": self.entitlement_id,
            "frozen_at": canonical_timestamp(self.frozen_at),
            "participant_rules_digest": str(self.participant_rules_digest),
            "primary_commercial_estimand_digest": str(self.primary_commercial_estimand_digest),
            "protocol_digest": str(self.protocol_digest),
            "refund_terms": self.refund_terms,
            "renewal_terms": self.renewal_terms,
            "schedule_id": self.schedule_id,
            "schema_version": self.schema_version,
            "segment_assignment_rules_digest": str(self.segment_assignment_rules_digest),
            "sequential_monitoring": self.sequential_monitoring,
            "sequential_validity_evidence_digest": (
                None
                if self.sequential_validity_evidence is None
                else str(self.sequential_validity_evidence.artifact_digest)
            ),
            "stopping_plan_digest": str(self.stopping_plan_digest),
            "target_offer_count_per_cell": self.target_offer_count_per_cell,
            "tax_treatment": self.tax_treatment,
            "two_price_exception_authority_digest": (
                None
                if self.two_price_exception_authority_digest is None
                else str(self.two_price_exception_authority_digest)
            ),
        }


@dataclass(frozen=True, slots=True)
class CommercialOfferReceiptV0:
    schedule_digest: Digest
    participant_id_digest: Digest
    segment_id: str
    entitlement_digest: Digest
    offered_at: datetime
    price_minor: int
    currency: str
    conversion_window_seconds: int
    schema_version: str = "commercial-offer-receipt-v0"

    def __post_init__(self) -> None:
        _require_stable_id(self.segment_id, "segment_id")
        _require_aware(self.offered_at, "offered_at")
        if self.price_minor <= 0:
            raise ValueError("commercial offer price_minor must be positive")
        if not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("commercial offer currency must be uppercase three-letter code")
        if self.conversion_window_seconds <= 0:
            raise ValueError("commercial offer conversion window must be positive")
        if self.schema_version != "commercial-offer-receipt-v0":
            raise ValueError("commercial offer receipt schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("commercialoffer_", self.to_canonical())

    @property
    def conversion_deadline(self) -> datetime:
        return self.offered_at + timedelta(seconds=self.conversion_window_seconds)

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "conversion_window_seconds": self.conversion_window_seconds,
            "currency": self.currency,
            "entitlement_digest": str(self.entitlement_digest),
            "offered_at": canonical_timestamp(self.offered_at),
            "participant_id_digest": str(self.participant_id_digest),
            "price_minor": self.price_minor,
            "schedule_digest": str(self.schedule_digest),
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
        }


@dataclass(frozen=True, slots=True)
class CommercialOutcomeReceiptV0:
    offer_receipt_digest: Digest
    source_event_digest: Digest
    recorded_at: datetime
    kind: CommercialOutcomeKind
    amount_minor: int | None = None
    currency: str | None = None
    detail_code: str | None = None
    schema_version: str = "commercial-outcome-receipt-v0"

    def __post_init__(self) -> None:
        _require_aware(self.recorded_at, "recorded_at")
        if self.detail_code is not None:
            _require_stable_id(self.detail_code, "detail_code")
        if self.kind in _PAYMENT_AMOUNT_KINDS:
            if self.amount_minor is None or self.amount_minor <= 0:
                raise ValueError(
                    "payment-related commercial outcome requires positive amount_minor"
                )
            if self.currency is None or not _CURRENCY_RE.fullmatch(self.currency):
                raise ValueError("payment-related commercial outcome requires valid currency")
        elif self.amount_minor is not None or self.currency is not None:
            raise ValueError("non-payment commercial outcome cannot carry amount/currency")
        if self.schema_version != "commercial-outcome-receipt-v0":
            raise ValueError("commercial outcome receipt schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("commercialoutcome_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "detail_code": self.detail_code,
            "kind": self.kind.value,
            "offer_receipt_digest": str(self.offer_receipt_digest),
            "recorded_at": canonical_timestamp(self.recorded_at),
            "schema_version": self.schema_version,
            "source_event_digest": str(self.source_event_digest),
        }


@dataclass(frozen=True, slots=True)
class PaymentEvidenceV0:
    outcome_receipt_digest: Digest
    offer_receipt_digest: Digest
    participant_id_digest: Digest
    processor_name: str
    processor_transaction_id_digest: Digest
    processor_receipt_digest: Digest
    observed_at: datetime
    kind: PaymentEvidenceKind
    amount_minor: int
    currency: str
    live_mode: bool
    test_charge: bool = False
    internal_team_payment: bool = False
    manual_comp: bool = False
    barter_or_credit: bool = False
    coupon_or_discount: bool = False
    founder_favor: bool = False
    schema_version: str = "payment-evidence-v0"

    def __post_init__(self) -> None:
        _require_text(self.processor_name, "processor_name")
        _require_aware(self.observed_at, "observed_at")
        if self.amount_minor <= 0:
            raise ValueError("payment evidence amount_minor must be positive")
        if not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("payment evidence currency must be uppercase three-letter code")
        if self.schema_version != "payment-evidence-v0":
            raise ValueError("payment evidence schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("paymentevidence_", self.to_canonical())

    @property
    def excluded_from_revealed_wtp(self) -> bool:
        return (
            not self.live_mode
            or self.test_charge
            or self.internal_team_payment
            or self.manual_comp
            or self.barter_or_credit
            or self.coupon_or_discount
            or self.founder_favor
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "amount_minor": self.amount_minor,
            "barter_or_credit": self.barter_or_credit,
            "coupon_or_discount": self.coupon_or_discount,
            "currency": self.currency,
            "founder_favor": self.founder_favor,
            "internal_team_payment": self.internal_team_payment,
            "kind": self.kind.value,
            "live_mode": self.live_mode,
            "manual_comp": self.manual_comp,
            "observed_at": canonical_timestamp(self.observed_at),
            "offer_receipt_digest": str(self.offer_receipt_digest),
            "outcome_receipt_digest": str(self.outcome_receipt_digest),
            "participant_id_digest": str(self.participant_id_digest),
            "processor_name": self.processor_name,
            "processor_receipt_digest": str(self.processor_receipt_digest),
            "processor_transaction_id_digest": str(self.processor_transaction_id_digest),
            "schema_version": self.schema_version,
            "test_charge": self.test_charge,
        }


def commercial_offer_set_digest(offers: tuple[CommercialOfferReceiptV0, ...]) -> Digest:
    if not offers:
        raise ValueError("commercial offer set cannot be empty")
    return sha256_digest(
        canonical_json_bytes(sorted(str(offer.artifact_digest) for offer in offers))
    )


def commercial_outcome_set_digest(outcomes: tuple[CommercialOutcomeReceiptV0, ...]) -> Digest:
    return sha256_digest(
        canonical_json_bytes(sorted(str(outcome.artifact_digest) for outcome in outcomes))
    )


def payment_evidence_set_digest(evidence: tuple[PaymentEvidenceV0, ...]) -> Digest:
    return sha256_digest(
        canonical_json_bytes(sorted(str(item.artifact_digest) for item in evidence))
    )


@dataclass(frozen=True, slots=True)
class CommercialSourceEventInventoryV0:
    schedule_digest: Digest
    coverage_cutoff_at: datetime
    exported_at: datetime
    source_system: str
    source_export_digest: Digest
    source_export_attestation_digest: Digest
    complete_source_event_digests: tuple[Digest, ...]
    schema_version: str = "commercial-source-event-inventory-v0"

    def __post_init__(self) -> None:
        _require_aware(self.coverage_cutoff_at, "coverage_cutoff_at")
        _require_aware(self.exported_at, "exported_at")
        _require_text(self.source_system, "source_system")
        if self.exported_at < self.coverage_cutoff_at:
            raise ValueError("source event inventory cannot be exported before coverage cutoff")
        _digest_set(self.complete_source_event_digests, field="complete_source_event_digests")
        if self.schema_version != "commercial-source-event-inventory-v0":
            raise ValueError("commercial source event inventory schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("commercialsourceinventory_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "complete_source_event_digests": list(
                _digest_set(
                    self.complete_source_event_digests,
                    field="complete_source_event_digests",
                )
            ),
            "coverage_cutoff_at": canonical_timestamp(self.coverage_cutoff_at),
            "exported_at": canonical_timestamp(self.exported_at),
            "schedule_digest": str(self.schedule_digest),
            "schema_version": self.schema_version,
            "source_export_attestation_digest": str(self.source_export_attestation_digest),
            "source_export_digest": str(self.source_export_digest),
            "source_system": self.source_system,
        }


@dataclass(frozen=True, slots=True)
class CommercialOutcomeManifestV0:
    schedule_digest: Digest
    reporting_cutoff_at: datetime
    offer_set_digest: Digest
    outcome_set_digest: Digest
    payment_evidence_set_digest: Digest
    source_event_inventory_digest: Digest
    schema_version: str = "commercial-outcome-manifest-v0"

    def __post_init__(self) -> None:
        _require_aware(self.reporting_cutoff_at, "reporting_cutoff_at")
        if self.schema_version != "commercial-outcome-manifest-v0":
            raise ValueError("commercial outcome manifest schema mismatch")

    @property
    def artifact_digest(self) -> Digest:
        return _artifact_digest(self.to_canonical())

    @property
    def artifact_id(self) -> str:
        return _artifact_id("commercialmanifest_", self.to_canonical())

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "offer_set_digest": str(self.offer_set_digest),
            "outcome_set_digest": str(self.outcome_set_digest),
            "payment_evidence_set_digest": str(self.payment_evidence_set_digest),
            "reporting_cutoff_at": canonical_timestamp(self.reporting_cutoff_at),
            "schedule_digest": str(self.schedule_digest),
            "schema_version": self.schema_version,
            "source_event_inventory_digest": str(self.source_event_inventory_digest),
        }


def validate_decision_response(
    response: DecisionResponseReceiptV0,
    *,
    case: DecisionCaseV0,
    case_set: tuple[DecisionCaseV0, ...],
    activation: DecisionCohortActivationV0,
) -> None:
    validate_case_set_against_activation(case_set, activation=activation)
    case_digests = {item.artifact_digest for item in case_set}
    if case.artifact_digest not in case_digests:
        raise ValueError("decision response case is outside the activated case set")
    if response.cohort_id != activation.cohort_id or case.cohort_id != activation.cohort_id:
        raise ValueError("decision response/case does not bind to activation cohort")
    if response.case_id != case.case_id:
        raise ValueError("decision response does not bind to decision case")
    if response.action not in case.action_set:
        raise ValueError("decision response action is outside frozen action set")
    expected_block = expected_assignment_block(
        activation.randomization_plan,
        participant_id_digest=response.participant_id_digest,
    )
    if response.assignment_block_id != expected_block:
        raise ValueError("decision response block does not match frozen participant assignment")
    expected_variant = expected_packet_variant(
        activation.randomization_plan,
        participant_id_digest=response.participant_id_digest,
    )
    if response.assigned_variant is not expected_variant:
        raise ValueError("decision response variant does not match frozen randomization plan")
    expected_packet = (
        case.baseline_packet_digest
        if expected_variant is PacketVariant.BASELINE_PACKET
        else case.frontier_packet_digest
    )
    if response.presented_packet_digest != expected_packet:
        raise ValueError("decision response presented packet does not match assigned variant")
    if response.responded_at < case.knowledge_horizon:
        raise ValueError("decision response predates frozen case knowledge horizon")
    if response.responded_at < activation.activated_at:
        raise ValueError("decision response predates cohort activation")


def validate_decision_response_set(responses: tuple[DecisionResponseReceiptV0, ...]) -> None:
    participant_variants: dict[tuple[str, Digest], PacketVariant] = {}
    participant_blocks: dict[tuple[str, Digest], str] = {}
    participant_cases: set[tuple[str, Digest, str]] = set()
    for response in responses:
        participant_key = (response.cohort_id, response.participant_id_digest)
        previous_variant = participant_variants.setdefault(
            participant_key, response.assigned_variant
        )
        if previous_variant is not response.assigned_variant:
            raise ValueError("participant crossed packet variants within confirmatory cohort")
        previous_block = participant_blocks.setdefault(
            participant_key, response.assignment_block_id
        )
        if previous_block != response.assignment_block_id:
            raise ValueError("participant changed randomization block within confirmatory cohort")
        case_key = (response.cohort_id, response.participant_id_digest, response.case_id)
        if case_key in participant_cases:
            raise ValueError("participant has duplicate response for the same decision case")
        participant_cases.add(case_key)


def validate_decision_outcome(
    outcome: DecisionOutcomeReceiptV0,
    *,
    response: DecisionResponseReceiptV0,
) -> None:
    if outcome.cohort_id != response.cohort_id or outcome.case_id != response.case_id:
        raise ValueError("decision outcome does not bind to response cohort/case")
    if outcome.response_receipt_digest != response.artifact_digest:
        raise ValueError("decision outcome does not bind to response receipt digest")
    if outcome.matured_at < response.responded_at:
        raise ValueError("decision outcome cannot mature before participant response")


def validate_offer_against_schedule(
    offer: CommercialOfferReceiptV0,
    *,
    schedule: PriceScheduleV0,
) -> None:
    if offer.schedule_digest != schedule.artifact_digest:
        raise ValueError("commercial offer does not bind to frozen price schedule")
    if offer.entitlement_digest != schedule.entitlement_digest:
        raise ValueError("commercial offer entitlement does not match frozen schedule")
    if offer.currency != schedule.currency:
        raise ValueError("commercial offer currency does not match frozen schedule")
    if offer.conversion_window_seconds != schedule.conversion_window_seconds:
        raise ValueError("commercial offer conversion window does not match frozen schedule")
    if offer.offered_at < schedule.frozen_at:
        raise ValueError("commercial offer predates frozen schedule")
    matching_cell = any(
        cell.segment_id == offer.segment_id and cell.price_minor == offer.price_minor
        for cell in schedule.cells
    )
    if not matching_cell:
        raise ValueError("commercial offer price/segment is outside frozen schedule")


def validate_unique_primary_offers(offers: tuple[CommercialOfferReceiptV0, ...]) -> None:
    seen: set[tuple[Digest, Digest, Digest]] = set()
    for offer in offers:
        key = (offer.schedule_digest, offer.participant_id_digest, offer.entitlement_digest)
        if key in seen:
            raise ValueError(
                "participant received multiple primary offers for one entitlement/schedule"
            )
        seen.add(key)


def validate_commercial_outcome(
    outcome: CommercialOutcomeReceiptV0,
    *,
    offer: CommercialOfferReceiptV0,
) -> None:
    if outcome.offer_receipt_digest != offer.artifact_digest:
        raise ValueError("commercial outcome does not bind to offer receipt digest")
    if outcome.recorded_at < offer.offered_at:
        raise ValueError("commercial outcome predates offer")
    if outcome.kind in _PRIMARY_WINDOW_KINDS and outcome.recorded_at > offer.conversion_deadline:
        raise ValueError("primary commercial outcome is outside frozen conversion window")
    if (
        outcome.kind is CommercialOutcomeKind.OFFER_EXPIRED
        and outcome.recorded_at < offer.conversion_deadline
    ):
        raise ValueError("offer cannot expire before frozen conversion deadline")
    if outcome.kind in _PAYMENT_AMOUNT_KINDS:
        if outcome.currency != offer.currency:
            raise ValueError("commercial outcome currency does not match offer")
        assert outcome.amount_minor is not None
        if (
            outcome.kind
            in {
                CommercialOutcomeKind.PAYMENT_AUTHORIZED,
                CommercialOutcomeKind.PAYMENT_SETTLED,
                CommercialOutcomeKind.PAYMENT_FAILED,
            }
            and outcome.amount_minor != offer.price_minor
        ):
            raise ValueError("primary payment outcome amount does not match frozen offer price")
        if (
            outcome.kind
            in {
                CommercialOutcomeKind.REFUND,
                CommercialOutcomeKind.CHARGEBACK,
            }
            and outcome.amount_minor > offer.price_minor
        ):
            raise ValueError("refund/chargeback cannot exceed frozen offer price")


def validate_payment_evidence(
    evidence: PaymentEvidenceV0,
    *,
    outcome: CommercialOutcomeReceiptV0,
    offer: CommercialOfferReceiptV0,
) -> None:
    if evidence.outcome_receipt_digest != outcome.artifact_digest:
        raise ValueError("payment evidence does not bind to commercial outcome")
    if evidence.offer_receipt_digest != offer.artifact_digest:
        raise ValueError("payment evidence does not bind to commercial offer")
    if evidence.participant_id_digest != offer.participant_id_digest:
        raise ValueError("payment evidence participant does not match commercial offer")
    expected_kind = PaymentEvidenceKind(outcome.kind.value)
    if evidence.kind is not expected_kind:
        raise ValueError("payment evidence kind does not match commercial outcome")
    if evidence.amount_minor != outcome.amount_minor or evidence.amount_minor != offer.price_minor:
        raise ValueError("payment evidence amount does not match frozen offer/outcome")
    if evidence.currency != outcome.currency or evidence.currency != offer.currency:
        raise ValueError("payment evidence currency does not match frozen offer/outcome")
    if evidence.observed_at < offer.offered_at:
        raise ValueError("payment evidence predates commercial offer")
    if evidence.observed_at > outcome.recorded_at:
        raise ValueError("payment evidence cannot be observed after recorded payment outcome")


def qualifies_as_revealed_wtp(
    outcome: CommercialOutcomeReceiptV0,
    *,
    offer: CommercialOfferReceiptV0,
    evidence: PaymentEvidenceV0,
) -> bool:
    if outcome.kind not in _REVEALED_WTP_OUTCOME_KINDS:
        return False
    validate_commercial_outcome(outcome, offer=offer)
    validate_payment_evidence(evidence, outcome=outcome, offer=offer)
    if evidence.observed_at > offer.conversion_deadline:
        return False
    return not evidence.excluded_from_revealed_wtp


def validate_commercial_reporting_manifest(
    manifest: CommercialOutcomeManifestV0,
    *,
    source_event_inventory: CommercialSourceEventInventoryV0,
    schedule: PriceScheduleV0,
    offers: tuple[CommercialOfferReceiptV0, ...],
    outcomes: tuple[CommercialOutcomeReceiptV0, ...],
    payment_evidence: tuple[PaymentEvidenceV0, ...],
) -> None:
    if manifest.schedule_digest != schedule.artifact_digest:
        raise ValueError("commercial manifest does not bind to frozen price schedule")
    if source_event_inventory.schedule_digest != schedule.artifact_digest:
        raise ValueError("source event inventory does not bind to frozen price schedule")
    if manifest.source_event_inventory_digest != source_event_inventory.artifact_digest:
        raise ValueError("commercial manifest does not bind source event inventory")
    if source_event_inventory.coverage_cutoff_at != manifest.reporting_cutoff_at:
        raise ValueError("source event inventory cutoff does not match reporting cutoff")
    if manifest.offer_set_digest != commercial_offer_set_digest(offers):
        raise ValueError("commercial manifest offer set digest mismatch")
    if manifest.outcome_set_digest != commercial_outcome_set_digest(outcomes):
        raise ValueError("commercial manifest outcome set digest mismatch")
    if manifest.payment_evidence_set_digest != payment_evidence_set_digest(payment_evidence):
        raise ValueError("commercial manifest payment evidence set digest mismatch")
    outcome_source_events = tuple(outcome.source_event_digest for outcome in outcomes)
    if _digest_set(
        outcome_source_events,
        field="outcome source event digests",
    ) != _digest_set(
        source_event_inventory.complete_source_event_digests,
        field="complete_source_event_digests",
    ):
        raise ValueError("commercial reporting omits or adds independently inventoried source events")

    validate_unique_primary_offers(offers)
    offer_by_digest = {offer.artifact_digest: offer for offer in offers}
    for offer in offers:
        validate_offer_against_schedule(offer, schedule=schedule)
        if offer.offered_at > manifest.reporting_cutoff_at:
            raise ValueError("commercial manifest includes offer after reporting cutoff")

    outcome_by_digest = {outcome.artifact_digest: outcome for outcome in outcomes}
    if len(outcome_by_digest) != len(outcomes):
        raise ValueError("commercial manifest contains duplicate outcome receipts")
    outcomes_by_offer: dict[Digest, list[CommercialOutcomeReceiptV0]] = {}
    for outcome in outcomes:
        offer = offer_by_digest.get(outcome.offer_receipt_digest)
        if offer is None:
            raise ValueError("commercial manifest outcome references unlisted offer")
        if outcome.recorded_at > manifest.reporting_cutoff_at:
            raise ValueError("commercial manifest includes outcome after reporting cutoff")
        validate_commercial_outcome(outcome, offer=offer)
        outcomes_by_offer.setdefault(offer.artifact_digest, []).append(outcome)

    evidence_by_outcome: dict[Digest, PaymentEvidenceV0] = {}
    for evidence in payment_evidence:
        outcome = outcome_by_digest.get(evidence.outcome_receipt_digest)
        if outcome is None:
            raise ValueError("payment evidence references unlisted commercial outcome")
        offer = offer_by_digest[outcome.offer_receipt_digest]
        if evidence.observed_at > manifest.reporting_cutoff_at:
            raise ValueError("commercial manifest includes payment evidence after reporting cutoff")
        if evidence.outcome_receipt_digest in evidence_by_outcome:
            raise ValueError("commercial outcome has duplicate payment evidence")
        validate_payment_evidence(evidence, outcome=outcome, offer=offer)
        evidence_by_outcome[evidence.outcome_receipt_digest] = evidence

    for outcome in outcomes:
        if (
            outcome.kind in _REVEALED_WTP_OUTCOME_KINDS
            and outcome.artifact_digest not in evidence_by_outcome
        ):
            raise ValueError("payment outcome is missing processor evidence")

    for offer in offers:
        history = sorted(
            outcomes_by_offer.get(offer.artifact_digest, []),
            key=lambda outcome: outcome.recorded_at,
        )
        if offer.conversion_deadline <= manifest.reporting_cutoff_at:
            primary = [
                outcome
                for outcome in history
                if outcome.kind in _PRIMARY_WINDOW_KINDS
                or outcome.kind is CommercialOutcomeKind.OFFER_EXPIRED
            ]
            if not primary:
                raise ValueError("matured commercial offer has no primary disposition")
        paid_at = [
            outcome.recorded_at
            for outcome in history
            if outcome.kind in _REVEALED_WTP_OUTCOME_KINDS
        ]
        for outcome in history:
            if outcome.kind in {
                CommercialOutcomeKind.REFUND,
                CommercialOutcomeKind.CHARGEBACK,
            } and not any(payment_time <= outcome.recorded_at for payment_time in paid_at):
                raise ValueError("refund/chargeback has no preceding payment outcome")
