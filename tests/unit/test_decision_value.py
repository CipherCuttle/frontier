from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.decision_value import (
    DECISION_VALUE_WTP_PREREGISTRATION_PATH,
    DECISION_VALUE_WTP_PROTOCOL_DIGEST,
    CommercialOfferReceiptV0,
    CommercialOutcomeKind,
    CommercialOutcomeManifestV0,
    CommercialOutcomeReceiptV0,
    CommercialSourceEventInventoryV0,
    DecisionCaseV0,
    DecisionCohortActivationV0,
    DecisionOutcomeReceiptV0,
    DecisionOutcomeStatus,
    DecisionResponseReceiptV0,
    PacketVariant,
    ParticipantBlockAssignmentV0,
    PaymentEvidenceKind,
    PaymentEvidenceV0,
    PriceCellV0,
    PriceScheduleV0,
    RandomizationBlockV0,
    RandomizationPlanV0,
    SequentialFutilityPolicy,
    SequentialMethod,
    SequentialSidedness,
    SequentialValidityEvidenceV0,
    commercial_offer_set_digest,
    commercial_outcome_set_digest,
    decision_case_set_digest,
    expected_assignment_block,
    expected_packet_variant,
    payment_evidence_set_digest,
    qualifies_as_revealed_wtp,
    validate_case_set_against_activation,
    validate_commercial_outcome,
    validate_commercial_reporting_manifest,
    validate_decision_outcome,
    validate_decision_response,
    validate_decision_response_set,
    validate_offer_against_schedule,
    validate_payment_evidence,
    validate_unique_primary_offers,
)
from frontier.domain.digests import Digest, sha256_digest

REPO_ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 15, 12, tzinfo=UTC)


def _digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def _protocol_digest() -> Digest:
    raw = cast(
        object,
        json.loads(
            (REPO_ROOT / DECISION_VALUE_WTP_PREREGISTRATION_PATH).read_text(encoding="utf-8")
        ),
    )
    return sha256_digest(canonical_json_bytes(raw))


def _sequential(**overrides: object) -> SequentialValidityEvidenceV0:
    values: dict[str, object] = {
        "evidence_id": "seq-001",
        "frozen_at": T0 - timedelta(hours=2),
        "stopping_plan_digest": _digest("9"),
        "method": SequentialMethod.ERROR_SPENDING,
        "method_version": "lan-demets-v1",
        "max_sample_size": 100,
        "look_schedule": (25, 50, 75, 100),
        "error_target_ppm": 50_000,
        "sidedness": SequentialSidedness.TWO_SIDED,
        "boundary_specification_digest": _digest("0"),
        "operating_characteristic_validation_digest": _digest("1"),
        "futility_policy": SequentialFutilityPolicy.NONE,
    }
    values.update(overrides)
    return SequentialValidityEvidenceV0(**values)  # type: ignore[arg-type]


def _plan(**overrides: object) -> RandomizationPlanV0:
    values: dict[str, object] = {
        "plan_id": "randomization-001",
        "frozen_at": T0 - timedelta(hours=2),
        "blocks": (RandomizationBlockV0("default", 5000, 5000),),
        "participant_block_assignments": (ParticipantBlockAssignmentV0(_digest("f"), "default"),),
    }
    values.update(overrides)
    return RandomizationPlanV0(**values)  # type: ignore[arg-type]


def _activation(**overrides: object) -> DecisionCohortActivationV0:
    values: dict[str, object] = {
        "cohort_id": "decision-cohort-001",
        "activated_at": T0,
        "protocol_digest": _protocol_digest(),
        "case_set_digest": _digest("2"),
        "packet_schema_digest": _digest("3"),
        "primary_estimand_digest": _digest("4"),
        "multiplicity_policy_digest": _digest("5"),
        "randomization_plan": _plan(),
        "participant_rules_digest": _digest("6"),
        "case_order_policy_digest": _digest("7"),
        "failure_semantics_digest": _digest("8"),
        "stopping_plan_digest": _digest("9"),
    }
    values.update(overrides)
    return DecisionCohortActivationV0(**values)  # type: ignore[arg-type]


def _case(**overrides: object) -> DecisionCaseV0:
    values: dict[str, object] = {
        "cohort_id": "decision-cohort-001",
        "case_id": "case-001",
        "domain": "AI_SOFTWARE_RESEARCH_STRATEGY",
        "knowledge_horizon": T0 + timedelta(hours=1),
        "decision_question": "Ship, wait, or abstain?",
        "action_set": ("SHIP", "WAIT", "ABSTAIN"),
        "utility_rule_digest": _digest("a"),
        "maturation_rule": "Resolve after the preregistered seven-day consequence window.",
        "baseline_packet_digest": _digest("b"),
        "frontier_packet_digest": _digest("c"),
        "evidence_digests": (_digest("d"), _digest("e")),
    }
    values.update(overrides)
    return DecisionCaseV0(**values)  # type: ignore[arg-type]


def _response(
    *,
    activation: DecisionCohortActivationV0 | None = None,
    case: DecisionCaseV0 | None = None,
    **overrides: object,
) -> DecisionResponseReceiptV0:
    activation = activation or _activation()
    case = case or _case()
    participant_id_digest = cast(Digest, overrides.pop("participant_id_digest", _digest("f")))
    assignment_block_id = expected_assignment_block(
        activation.randomization_plan,
        participant_id_digest=participant_id_digest,
    )
    expected_variant = expected_packet_variant(
        activation.randomization_plan,
        participant_id_digest=participant_id_digest,
    )
    packet_digest = (
        case.baseline_packet_digest
        if expected_variant is PacketVariant.BASELINE_PACKET
        else case.frontier_packet_digest
    )
    values: dict[str, object] = {
        "cohort_id": case.cohort_id,
        "case_id": case.case_id,
        "participant_id_digest": participant_id_digest,
        "assignment_block_id": assignment_block_id,
        "assigned_variant": expected_variant,
        "presented_packet_digest": packet_digest,
        "action": "WAIT",
        "responded_at": T0 + timedelta(hours=2),
        "elapsed_ms": 15_000,
        "confidence_bps": 6_500,
    }
    values.update(overrides)
    return DecisionResponseReceiptV0(**values)  # type: ignore[arg-type]


def _schedule(**overrides: object) -> PriceScheduleV0:
    values: dict[str, object] = {
        "schedule_id": "schedule-001",
        "frozen_at": T0,
        "protocol_digest": _protocol_digest(),
        "entitlement_id": "frontier-pilot-30d",
        "entitlement_digest": _digest("a"),
        "billing_period": "30 days fixed pilot",
        "currency": "USD",
        "tax_treatment": "tax excluded; charged according to checkout jurisdiction",
        "renewal_terms": "no automatic renewal",
        "refund_terms": "refunds permitted only under the frozen pilot policy",
        "conversion_definition": "real payment authorization or settled payment within 24h",
        "conversion_window_seconds": 86_400,
        "participant_rules_digest": _digest("b"),
        "segment_assignment_rules_digest": _digest("c"),
        "primary_commercial_estimand_digest": _digest("d"),
        "stopping_plan_digest": _digest("e"),
        "target_offer_count_per_cell": 30,
        "cells": (
            PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 1000, 3334),
            PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 2500, 3333),
            PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 5000, 3333),
        ),
    }
    values.update(overrides)
    return PriceScheduleV0(**values)  # type: ignore[arg-type]


def _offer(schedule: PriceScheduleV0, **overrides: object) -> CommercialOfferReceiptV0:
    values: dict[str, object] = {
        "schedule_digest": schedule.artifact_digest,
        "participant_id_digest": _digest("f"),
        "segment_id": "AI_SOFTWARE_RESEARCH_STRATEGY",
        "entitlement_digest": schedule.entitlement_digest,
        "offered_at": T0 + timedelta(hours=1),
        "price_minor": 2500,
        "currency": "USD",
        "conversion_window_seconds": schedule.conversion_window_seconds,
    }
    values.update(overrides)
    return CommercialOfferReceiptV0(**values)  # type: ignore[arg-type]


def _outcome(
    offer: CommercialOfferReceiptV0,
    *,
    kind: CommercialOutcomeKind = CommercialOutcomeKind.PAYMENT_AUTHORIZED,
    source_char: str = "1",
    recorded_at: datetime | None = None,
    **overrides: object,
) -> CommercialOutcomeReceiptV0:
    payment_kind = kind in {
        CommercialOutcomeKind.PAYMENT_AUTHORIZED,
        CommercialOutcomeKind.PAYMENT_SETTLED,
        CommercialOutcomeKind.PAYMENT_FAILED,
        CommercialOutcomeKind.REFUND,
        CommercialOutcomeKind.CHARGEBACK,
        CommercialOutcomeKind.RENEWAL,
    }
    values: dict[str, object] = {
        "offer_receipt_digest": offer.artifact_digest,
        "source_event_digest": _digest(source_char),
        "recorded_at": recorded_at or offer.offered_at + timedelta(hours=1),
        "kind": kind,
        "amount_minor": offer.price_minor if payment_kind else None,
        "currency": offer.currency if payment_kind else None,
    }
    values.update(overrides)
    return CommercialOutcomeReceiptV0(**values)  # type: ignore[arg-type]


def _payment_evidence(
    offer: CommercialOfferReceiptV0,
    outcome: CommercialOutcomeReceiptV0,
    **overrides: object,
) -> PaymentEvidenceV0:
    values: dict[str, object] = {
        "outcome_receipt_digest": outcome.artifact_digest,
        "offer_receipt_digest": offer.artifact_digest,
        "participant_id_digest": offer.participant_id_digest,
        "processor_name": "stripe-live",
        "processor_transaction_id_digest": _digest("2"),
        "processor_receipt_digest": _digest("3"),
        "observed_at": outcome.recorded_at,
        "kind": PaymentEvidenceKind(outcome.kind.value),
        "amount_minor": offer.price_minor,
        "currency": offer.currency,
        "live_mode": True,
    }
    values.update(overrides)
    return PaymentEvidenceV0(**values)  # type: ignore[arg-type]


def _inventory(
    schedule: PriceScheduleV0,
    source_events: tuple[Digest, ...],
    *,
    cutoff: datetime | None = None,
) -> CommercialSourceEventInventoryV0:
    coverage_cutoff = cutoff or T0 + timedelta(days=3)
    return CommercialSourceEventInventoryV0(
        schedule_digest=schedule.artifact_digest,
        coverage_cutoff_at=coverage_cutoff,
        exported_at=coverage_cutoff + timedelta(minutes=5),
        source_system="stripe-live-event-export",
        source_export_digest=_digest("5"),
        source_export_attestation_digest=_digest("6"),
        complete_source_event_digests=source_events,
    )


def _manifest(
    schedule: PriceScheduleV0,
    offers: tuple[CommercialOfferReceiptV0, ...],
    outcomes: tuple[CommercialOutcomeReceiptV0, ...],
    evidence: tuple[PaymentEvidenceV0, ...],
    inventory: CommercialSourceEventInventoryV0,
) -> CommercialOutcomeManifestV0:
    return CommercialOutcomeManifestV0(
        schedule_digest=schedule.artifact_digest,
        reporting_cutoff_at=inventory.coverage_cutoff_at,
        offer_set_digest=commercial_offer_set_digest(offers),
        outcome_set_digest=commercial_outcome_set_digest(outcomes),
        payment_evidence_set_digest=payment_evidence_set_digest(evidence),
        source_event_inventory_digest=inventory.artifact_digest,
    )


def _validate_manifest(
    manifest: CommercialOutcomeManifestV0,
    inventory: CommercialSourceEventInventoryV0,
    schedule: PriceScheduleV0,
    offers: tuple[CommercialOfferReceiptV0, ...],
    outcomes: tuple[CommercialOutcomeReceiptV0, ...],
    evidence: tuple[PaymentEvidenceV0, ...],
) -> None:
    validate_commercial_reporting_manifest(
        manifest,
        source_event_inventory=inventory,
        schedule=schedule,
        offers=offers,
        outcomes=outcomes,
        payment_evidence=evidence,
    )


def test_frozen_protocol_digest_matches_merged_preregistration() -> None:
    assert _protocol_digest() == DECISION_VALUE_WTP_PROTOCOL_DIGEST


def test_activation_is_content_addressed_and_binds_frozen_protocol() -> None:
    activation = _activation()
    again = _activation()
    assert activation == again
    assert activation.protocol_digest == DECISION_VALUE_WTP_PROTOCOL_DIGEST
    assert activation.artifact_digest == again.artifact_digest
    assert activation.artifact_id.startswith("decisioncohort_")

    with pytest.raises(ValueError, match="frozen FRONTIER_DECISION_VALUE_WTP_V0"):
        _activation(protocol_digest=_digest("0"))


def test_sequential_evidence_is_structured_and_bound_to_exact_stopping_plan() -> None:
    with pytest.raises(ValueError, match="final sequential look"):
        _sequential(look_schedule=(25, 50, 75), max_sample_size=100)

    with pytest.raises(ValueError, match="validated sequential evidence"):
        _activation(sequential_monitoring=True)

    activation = _activation(
        sequential_monitoring=True,
        sequential_validity_evidence=_sequential(),
    )
    assert activation.sequential_validity_evidence is not None
    assert activation.sequential_validity_evidence.sidedness is SequentialSidedness.TWO_SIDED

    with pytest.raises(ValueError, match="activation stopping plan"):
        _activation(
            sequential_monitoring=True,
            sequential_validity_evidence=_sequential(stopping_plan_digest=_digest("0")),
        )

    with pytest.raises(ValueError, match="price stopping plan"):
        _schedule(
            sequential_monitoring=True,
            target_offer_count_per_cell=None,
            sequential_validity_evidence=_sequential(stopping_plan_digest=_digest("9")),
        )

    sequential_schedule = _schedule(
        sequential_monitoring=True,
        target_offer_count_per_cell=None,
        sequential_validity_evidence=_sequential(stopping_plan_digest=_digest("e")),
    )
    assert sequential_schedule.sequential_validity_evidence is not None


def test_sequential_futility_semantics_are_explicit_and_consistent() -> None:
    with pytest.raises(ValueError, match="no-futility"):
        _sequential(futility_rule_digest=_digest("4"))

    with pytest.raises(ValueError, match="requires futility_rule_digest"):
        _sequential(futility_policy=SequentialFutilityPolicy.BOUND_RULE)

    evidence = _sequential(
        futility_policy=SequentialFutilityPolicy.BOUND_RULE,
        futility_rule_digest=_digest("4"),
    )
    assert evidence.futility_rule_digest == _digest("4")


def test_activation_case_set_digest_recomputes_exact_cases() -> None:
    case = _case()
    digest = decision_case_set_digest((case,))
    activation = _activation(case_set_digest=digest)
    validate_case_set_against_activation((case,), activation=activation)

    changed_case = replace(case, decision_question="Ship now, wait, or abstain?")
    with pytest.raises(ValueError, match="case set digest"):
        validate_case_set_against_activation((changed_case,), activation=activation)


def test_response_rejects_case_not_in_activated_case_set() -> None:
    frozen_case = _case()
    activation = _activation(case_set_digest=decision_case_set_digest((frozen_case,)))
    forged_case = replace(
        frozen_case,
        action_set=("SHIP", "BUY", "ABSTAIN"),
        utility_rule_digest=_digest("0"),
    )
    response = _response(activation=activation, case=forged_case, action="BUY")

    with pytest.raises(ValueError, match="outside the activated case set"):
        validate_decision_response(
            response,
            case=forged_case,
            case_set=(frozen_case,),
            activation=activation,
        )


def test_decision_response_must_match_frozen_randomization_and_packet() -> None:
    case = _case()
    activation = _activation(case_set_digest=decision_case_set_digest((case,)))
    response = _response(activation=activation, case=case)
    validate_decision_response(
        response,
        case=case,
        case_set=(case,),
        activation=activation,
    )

    opposite = (
        PacketVariant.FRONTIER_PACKET
        if response.assigned_variant is PacketVariant.BASELINE_PACKET
        else PacketVariant.BASELINE_PACKET
    )
    opposite_packet = (
        case.frontier_packet_digest
        if opposite is PacketVariant.FRONTIER_PACKET
        else case.baseline_packet_digest
    )
    relabeled = replace(
        response,
        assigned_variant=opposite,
        presented_packet_digest=opposite_packet,
    )
    with pytest.raises(ValueError, match="frozen randomization plan"):
        validate_decision_response(
            relabeled,
            case=case,
            case_set=(case,),
            activation=activation,
        )

    wrong_packet = replace(response, presented_packet_digest=_digest("0"))
    with pytest.raises(ValueError, match="assigned variant"):
        validate_decision_response(
            wrong_packet,
            case=case,
            case_set=(case,),
            activation=activation,
        )


def test_randomization_block_is_derived_from_frozen_participant_mapping() -> None:
    plan = _plan(
        blocks=(
            RandomizationBlockV0("default", 5000, 5000),
            RandomizationBlockV0("alternate", 5000, 5000),
        ),
        participant_block_assignments=(
            ParticipantBlockAssignmentV0(_digest("f"), "default"),
            ParticipantBlockAssignmentV0(_digest("0"), "alternate"),
        ),
    )
    case = _case()
    activation = _activation(
        randomization_plan=plan,
        case_set_digest=decision_case_set_digest((case,)),
    )
    response = _response(activation=activation, case=case)
    forged_block = replace(response, assignment_block_id="alternate")

    with pytest.raises(ValueError, match="frozen participant assignment"):
        validate_decision_response(
            forged_block,
            case=case,
            case_set=(case,),
            activation=activation,
        )

    with pytest.raises(ValueError, match="not in frozen randomization block assignments"):
        expected_packet_variant(plan, participant_id_digest=_digest("1"))


def test_confirmatory_response_set_rejects_crossover_block_change_and_duplicate_case() -> None:
    activation = _activation()
    baseline = _response(activation=activation)
    second_case_same_arm = replace(
        baseline,
        case_id="case-002",
        responded_at=baseline.responded_at + timedelta(hours=1),
    )
    validate_decision_response_set((baseline, second_case_same_arm))

    crossover = replace(
        second_case_same_arm,
        assigned_variant=(
            PacketVariant.FRONTIER_PACKET
            if baseline.assigned_variant is PacketVariant.BASELINE_PACKET
            else PacketVariant.BASELINE_PACKET
        ),
    )
    with pytest.raises(ValueError, match="crossed packet variants"):
        validate_decision_response_set((baseline, crossover))

    changed_block = replace(second_case_same_arm, assignment_block_id="other-block")
    with pytest.raises(ValueError, match="changed randomization block"):
        validate_decision_response_set((baseline, changed_block))

    with pytest.raises(ValueError, match="duplicate response"):
        validate_decision_response_set((baseline, baseline))


def test_decision_outcome_is_bound_to_response_digest() -> None:
    response = _response()
    outcome = DecisionOutcomeReceiptV0(
        cohort_id=response.cohort_id,
        case_id=response.case_id,
        response_receipt_digest=response.artifact_digest,
        matured_at=response.responded_at + timedelta(days=7),
        status=DecisionOutcomeStatus.RESOLVED,
        outcome_label="WAIT_WAS_BETTER",
        utility_microunits=250_000,
    )
    validate_decision_outcome(outcome, response=response)

    with pytest.raises(ValueError, match="response receipt digest"):
        validate_decision_outcome(
            replace(outcome, response_receipt_digest=_digest("0")), response=response
        )


def test_unresolved_and_protocol_failure_outcomes_fail_closed() -> None:
    response = _response()
    unresolved = DecisionOutcomeReceiptV0(
        cohort_id=response.cohort_id,
        case_id=response.case_id,
        response_receipt_digest=response.artifact_digest,
        matured_at=response.responded_at + timedelta(days=7),
        status=DecisionOutcomeStatus.UNRESOLVED,
    )
    assert unresolved.utility_microunits is None

    with pytest.raises(ValueError, match="explicit reason"):
        DecisionOutcomeReceiptV0(
            cohort_id=response.cohort_id,
            case_id=response.case_id,
            response_receipt_digest=response.artifact_digest,
            matured_at=response.responded_at + timedelta(days=7),
            status=DecisionOutcomeStatus.PROTOCOL_FAILURE,
        )


def test_price_schedule_requires_three_prices_exact_mass_and_authorized_segment() -> None:
    schedule = _schedule()
    assert schedule.protocol_digest == DECISION_VALUE_WTP_PROTOCOL_DIGEST

    two_cells = (
        PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 1000, 5000),
        PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 2500, 5000),
    )
    with pytest.raises(ValueError, match="at least 3"):
        _schedule(cells=two_cells)

    exception_schedule = _schedule(
        cells=two_cells,
        two_price_exception_authority_digest=_digest("1"),
    )
    assert exception_schedule.two_price_exception_authority_digest == _digest("1")

    bad_mass = (
        PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 1000, 3000),
        PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 2500, 3000),
        PriceCellV0("AI_SOFTWARE_RESEARCH_STRATEGY", 5000, 3000),
    )
    with pytest.raises(ValueError, match="sum to 10000"):
        _schedule(cells=bad_mass)

    with pytest.raises(ValueError, match="not authorized"):
        PriceCellV0("POST_HOC_SEGMENT", 1000, 10_000)


def test_offer_must_bind_exact_frozen_schedule_terms() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    validate_offer_against_schedule(offer, schedule=schedule)

    with pytest.raises(ValueError, match="price/segment"):
        validate_offer_against_schedule(replace(offer, price_minor=9999), schedule=schedule)

    with pytest.raises(ValueError, match="entitlement"):
        validate_offer_against_schedule(
            replace(offer, entitlement_digest=_digest("1")), schedule=schedule
        )

    with pytest.raises(ValueError, match="conversion window"):
        validate_offer_against_schedule(
            replace(offer, conversion_window_seconds=172_800), schedule=schedule
        )


def test_one_primary_offer_per_participant_entitlement_schedule() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    validate_unique_primary_offers((offer,))

    second = replace(offer, offered_at=offer.offered_at + timedelta(minutes=5))
    with pytest.raises(ValueError, match="multiple primary offers"):
        validate_unique_primary_offers((offer, second))


def test_primary_payment_outside_conversion_window_is_rejected() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    late = _outcome(offer, recorded_at=offer.conversion_deadline + timedelta(seconds=1))
    with pytest.raises(ValueError, match="outside frozen conversion window"):
        validate_commercial_outcome(late, offer=offer)


def test_revealed_wtp_requires_qualifying_processor_evidence() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    outcome = _outcome(offer)
    evidence = _payment_evidence(offer, outcome)

    validate_payment_evidence(evidence, outcome=outcome, offer=offer)
    assert qualifies_as_revealed_wtp(outcome, offer=offer, evidence=evidence) is True

    for excluded in (
        replace(evidence, test_charge=True),
        replace(evidence, internal_team_payment=True),
        replace(evidence, manual_comp=True),
        replace(evidence, coupon_or_discount=True),
        replace(evidence, live_mode=False),
    ):
        assert qualifies_as_revealed_wtp(outcome, offer=offer, evidence=excluded) is False


def test_payment_evidence_must_be_observed_after_offer_and_before_outcome() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    outcome = _outcome(offer)
    evidence = _payment_evidence(offer, outcome)

    with pytest.raises(ValueError, match="predates commercial offer"):
        validate_payment_evidence(
            replace(evidence, observed_at=offer.offered_at - timedelta(seconds=1)),
            outcome=outcome,
            offer=offer,
        )

    with pytest.raises(ValueError, match="after recorded payment outcome"):
        validate_payment_evidence(
            replace(evidence, observed_at=outcome.recorded_at + timedelta(seconds=1)),
            outcome=outcome,
            offer=offer,
        )


def test_payment_evidence_must_bind_exact_offer_outcome_amount_and_participant() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    outcome = _outcome(offer)
    evidence = _payment_evidence(offer, outcome)

    with pytest.raises(ValueError, match="commercial outcome"):
        validate_payment_evidence(
            replace(evidence, outcome_receipt_digest=_digest("0")),
            outcome=outcome,
            offer=offer,
        )

    with pytest.raises(ValueError, match="participant"):
        validate_payment_evidence(
            replace(evidence, participant_id_digest=_digest("0")),
            outcome=outcome,
            offer=offer,
        )


def test_source_inventory_is_content_addressed_and_bound_to_cutoff() -> None:
    schedule = _schedule()
    cutoff = T0 + timedelta(days=3)
    inventory = _inventory(schedule, (_digest("1"),), cutoff=cutoff)
    assert inventory.artifact_id.startswith("commercialsourceinventory_")
    assert inventory.coverage_cutoff_at == cutoff

    with pytest.raises(ValueError, match="exported before coverage cutoff"):
        replace(inventory, exported_at=cutoff - timedelta(seconds=1))


def test_reporting_manifest_requires_every_matured_offer_disposition() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    cutoff = offer.conversion_deadline + timedelta(hours=1)
    inventory = _inventory(schedule, (), cutoff=cutoff)
    manifest = _manifest(schedule, (offer,), (), (), inventory)

    with pytest.raises(ValueError, match="no primary disposition"):
        _validate_manifest(manifest, inventory, schedule, (offer,), (), ())


def test_reporting_manifest_rejects_event_omitted_from_outcomes_and_manifest() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    payment = _outcome(offer, source_char="1")
    evidence = _payment_evidence(offer, payment)
    refund = _outcome(
        offer,
        kind=CommercialOutcomeKind.REFUND,
        source_char="4",
        recorded_at=offer.offered_at + timedelta(days=2),
    )
    inventory = _inventory(
        schedule,
        (payment.source_event_digest, refund.source_event_digest),
    )
    manifest = _manifest(schedule, (offer,), (payment,), (evidence,), inventory)

    with pytest.raises(ValueError, match="independently inventoried source events"):
        _validate_manifest(
            manifest,
            inventory,
            schedule,
            (offer,),
            (payment,),
            (evidence,),
        )


def test_reporting_manifest_rejects_wrong_or_mismatched_source_inventory() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    payment = _outcome(offer)
    evidence = _payment_evidence(offer, payment)
    inventory = _inventory(schedule, (payment.source_event_digest,))
    manifest = _manifest(schedule, (offer,), (payment,), (evidence,), inventory)

    wrong_inventory = replace(inventory, source_export_attestation_digest=_digest("0"))
    with pytest.raises(ValueError, match="does not bind source event inventory"):
        _validate_manifest(
            manifest,
            wrong_inventory,
            schedule,
            (offer,),
            (payment,),
            (evidence,),
        )

    wrong_cutoff = replace(
        inventory,
        coverage_cutoff_at=inventory.coverage_cutoff_at + timedelta(hours=1),
        exported_at=inventory.exported_at + timedelta(hours=1),
    )
    rebound_manifest = replace(
        manifest,
        source_event_inventory_digest=wrong_cutoff.artifact_digest,
    )
    with pytest.raises(ValueError, match="cutoff does not match reporting cutoff"):
        _validate_manifest(
            rebound_manifest,
            wrong_cutoff,
            schedule,
            (offer,),
            (payment,),
            (evidence,),
        )


def test_reporting_manifest_requires_processor_evidence_for_payment_outcome() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    payment = _outcome(offer)
    inventory = _inventory(schedule, (payment.source_event_digest,))
    manifest = _manifest(schedule, (offer,), (payment,), (), inventory)

    with pytest.raises(ValueError, match="missing processor evidence"):
        _validate_manifest(manifest, inventory, schedule, (offer,), (payment,), ())


def test_reporting_manifest_accepts_complete_payment_and_refund_history() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    payment = _outcome(offer, source_char="1")
    evidence = _payment_evidence(offer, payment)
    refund = _outcome(
        offer,
        kind=CommercialOutcomeKind.REFUND,
        source_char="4",
        recorded_at=offer.offered_at + timedelta(days=2),
    )
    outcomes = (payment, refund)
    inventory = _inventory(
        schedule,
        tuple(outcome.source_event_digest for outcome in outcomes),
    )
    manifest = _manifest(schedule, (offer,), outcomes, (evidence,), inventory)

    _validate_manifest(
        manifest,
        inventory,
        schedule,
        (offer,),
        outcomes,
        (evidence,),
    )
