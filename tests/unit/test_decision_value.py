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
    CommercialOutcomeReceiptV0,
    DecisionCaseV0,
    DecisionCohortActivationV0,
    DecisionOutcomeReceiptV0,
    DecisionOutcomeStatus,
    DecisionResponseReceiptV0,
    PacketVariant,
    PriceCellV0,
    PriceScheduleV0,
    decision_case_set_digest,
    validate_case_set_against_activation,
    validate_commercial_outcome,
    validate_decision_outcome,
    validate_decision_response,
    validate_decision_response_set,
    validate_offer_against_schedule,
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


def _activation(**overrides: object) -> DecisionCohortActivationV0:
    values: dict[str, object] = {
        "cohort_id": "decision-cohort-001",
        "activated_at": T0,
        "protocol_digest": _protocol_digest(),
        "case_set_digest": _digest("1"),
        "packet_schema_digest": _digest("2"),
        "primary_estimand_digest": _digest("3"),
        "multiplicity_policy_digest": _digest("4"),
        "randomization_plan_digest": _digest("5"),
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


def _response(**overrides: object) -> DecisionResponseReceiptV0:
    values: dict[str, object] = {
        "cohort_id": "decision-cohort-001",
        "case_id": "case-001",
        "participant_id_digest": _digest("f"),
        "assigned_variant": PacketVariant.BASELINE_PACKET,
        "presented_packet_digest": _digest("b"),
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
        "conversion_window": "24h from primary offer",
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
        "conversion_window": schedule.conversion_window,
    }
    values.update(overrides)
    return CommercialOfferReceiptV0(**values)  # type: ignore[arg-type]


def test_frozen_protocol_digest_matches_merged_preregistration() -> None:
    assert _protocol_digest() == DECISION_VALUE_WTP_PROTOCOL_DIGEST


def test_activation_is_content_addressed_and_binds_frozen_protocol() -> None:
    activation = _activation()
    again = _activation()
    assert activation == again
    assert activation.protocol_digest == DECISION_VALUE_WTP_PROTOCOL_DIGEST
    assert activation.artifact_digest == again.artifact_digest
    assert activation.artifact_id == again.artifact_id
    assert activation.artifact_id.startswith("decisioncohort_")

    with pytest.raises(ValueError, match="frozen FRONTIER_DECISION_VALUE_WTP_V0"):
        _activation(protocol_digest=_digest("0"))


def test_sequential_activation_requires_repeated_look_valid_evidence() -> None:
    with pytest.raises(ValueError, match="repeated-look-valid evidence"):
        _activation(sequential_monitoring=True)

    activation = _activation(
        sequential_monitoring=True,
        sequential_validity_evidence_digest=_digest("a"),
    )
    assert activation.sequential_monitoring is True


def test_activation_case_set_digest_recomputes_exact_cases() -> None:
    case = _case()
    digest = decision_case_set_digest((case,))
    activation = _activation(case_set_digest=digest)
    validate_case_set_against_activation((case,), activation=activation)

    changed_case = replace(case, decision_question="Ship now, wait, or abstain?")
    with pytest.raises(ValueError, match="case set digest"):
        validate_case_set_against_activation((changed_case,), activation=activation)


def test_decision_response_must_match_case_assignment_and_frozen_action_set() -> None:
    case = _case()
    activation = _activation(case_set_digest=decision_case_set_digest((case,)))
    response = _response()
    validate_decision_response(response, case=case, activation=activation)

    wrong_packet = replace(response, presented_packet_digest=case.frontier_packet_digest)
    with pytest.raises(ValueError, match="assigned variant"):
        validate_decision_response(wrong_packet, case=case, activation=activation)

    wrong_action = replace(response, action="BUY")
    with pytest.raises(ValueError, match="frozen action set"):
        validate_decision_response(wrong_action, case=case, activation=activation)


def test_confirmatory_response_set_rejects_variant_carryover_and_duplicate_case() -> None:
    baseline = _response()
    second_case_same_arm = _response(
        case_id="case-002",
        presented_packet_digest=_digest("1"),
        responded_at=T0 + timedelta(hours=3),
    )
    validate_decision_response_set((baseline, second_case_same_arm))

    crossover = replace(
        second_case_same_arm,
        assigned_variant=PacketVariant.FRONTIER_PACKET,
        presented_packet_digest=_digest("c"),
    )
    with pytest.raises(ValueError, match="crossed packet variants"):
        validate_decision_response_set((baseline, crossover))

    with pytest.raises(ValueError, match="duplicate response"):
        validate_decision_response_set((baseline, baseline))


def test_decision_outcome_is_immutable_and_bound_to_response_digest() -> None:
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
    assert outcome.artifact_id.startswith("decisionoutcome_")

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


def test_price_schedule_requires_three_prices_and_exact_assignment_mass() -> None:
    schedule = _schedule()
    assert schedule.protocol_digest == DECISION_VALUE_WTP_PROTOCOL_DIGEST
    assert schedule.artifact_id.startswith("priceschedule_")

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


def test_price_schedule_rejects_unpreregistered_segment() -> None:
    with pytest.raises(ValueError, match="not authorized"):
        PriceCellV0("POST_HOC_SEGMENT", 1000, 10_000)


def test_fixed_and_sequential_price_stopping_semantics_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="repeated-look-valid evidence"):
        _schedule(sequential_monitoring=True, target_offer_count_per_cell=None)

    sequential = _schedule(
        sequential_monitoring=True,
        target_offer_count_per_cell=None,
        sequential_validity_evidence_digest=_digest("1"),
    )
    assert sequential.sequential_monitoring is True

    with pytest.raises(ValueError, match="positive target_offer_count_per_cell"):
        _schedule(target_offer_count_per_cell=None)


def test_offer_must_bind_exact_frozen_schedule_terms() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    validate_offer_against_schedule(offer, schedule=schedule)

    with pytest.raises(ValueError, match="price/segment"):
        validate_offer_against_schedule(replace(offer, price_minor=9999), schedule=schedule)

    with pytest.raises(ValueError, match="entitlement"):
        validate_offer_against_schedule(
            replace(offer, entitlement_digest=_digest("1")),
            schedule=schedule,
        )

    with pytest.raises(ValueError, match="conversion window"):
        validate_offer_against_schedule(
            replace(offer, conversion_window="48h from primary offer"),
            schedule=schedule,
        )


def test_one_primary_offer_per_participant_entitlement_schedule() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    validate_unique_primary_offers((offer,))

    second = replace(offer, offered_at=offer.offered_at + timedelta(minutes=5))
    with pytest.raises(ValueError, match="multiple primary offers"):
        validate_unique_primary_offers((offer, second))


def test_revealed_wtp_requires_real_payment_event_and_preserves_negative_events() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    authorized = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(minutes=2),
        kind=CommercialOutcomeKind.PAYMENT_AUTHORIZED,
        amount_minor=offer.price_minor,
        currency=offer.currency,
    )
    validate_commercial_outcome(authorized, offer=offer)
    assert authorized.revealed_wtp is True

    declined = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(minutes=2),
        kind=CommercialOutcomeKind.OFFER_DECLINED,
    )
    validate_commercial_outcome(declined, offer=offer)
    assert declined.revealed_wtp is False

    refund = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(days=1),
        kind=CommercialOutcomeKind.REFUND,
        amount_minor=offer.price_minor,
        currency=offer.currency,
    )
    validate_commercial_outcome(refund, offer=offer)
    assert refund.revealed_wtp is False

    usage = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(days=2),
        kind=CommercialOutcomeKind.ACTIVE_USAGE,
        detail_code="active_day_2",
    )
    validate_commercial_outcome(usage, offer=offer)
    assert usage.revealed_wtp is False


def test_payment_outcome_must_match_frozen_offer_price_and_currency() -> None:
    schedule = _schedule()
    offer = _offer(schedule)
    wrong_amount = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(minutes=2),
        kind=CommercialOutcomeKind.PAYMENT_SETTLED,
        amount_minor=offer.price_minor + 1,
        currency=offer.currency,
    )
    with pytest.raises(ValueError, match="frozen offer price"):
        validate_commercial_outcome(wrong_amount, offer=offer)

    wrong_currency = CommercialOutcomeReceiptV0(
        offer_receipt_digest=offer.artifact_digest,
        recorded_at=offer.offered_at + timedelta(minutes=2),
        kind=CommercialOutcomeKind.PAYMENT_AUTHORIZED,
        amount_minor=offer.price_minor,
        currency="EUR",
    )
    with pytest.raises(ValueError, match="currency"):
        validate_commercial_outcome(wrong_currency, offer=offer)
