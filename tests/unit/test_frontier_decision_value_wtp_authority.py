from __future__ import annotations

import json
from pathlib import Path
from typing import cast

AUTHORITY_PATH = Path("docs/FRONTIER_DECISION_VALUE_WTP_V0.md")
PREREG_PATH = Path("experiments/value_observatory_v0/decision_value_wtp_v0.json")


def _prereg() -> dict[str, object]:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def _object_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _string_list(value: object) -> list[str]:
    assert isinstance(value, list)
    items = cast(list[object], value)
    result: list[str] = []
    for item in items:
        assert isinstance(item, str)
        result.append(item)
    return result


def _int_value(value: object) -> int:
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def test_decision_value_wtp_preregistration_preserves_scientific_authority() -> None:
    prereg = _prereg()

    assert prereg["phase_id"] == "FRONTIER_DECISION_VALUE_WTP_V0"
    assert prereg["status"] == "CANDIDATE_SUBORDINATE_AUTHORITY_UNTIL_MERGE"
    assert prereg["parent_authority"] == "FRONTIER_VALUE_OBSERVATORY_V0"
    assert prereg["scientific_benchmark_authority"] == "BENCHMARK_CAPTURE_V0"

    scientific_separation = _object_dict(prereg["scientific_separation"])
    assert (
        scientific_separation["active_scored_alerts_may_be_exposed_before_longest_outcome_horizon"]
        is False
    )
    assert scientific_separation["historical_cases_confirmatory"] is False
    assert scientific_separation["user_reaction_as_scientific_outcome_label"] is False

    forbidden = set(_string_list(prereg["not_authorized"]))
    assert {
        "PEF_V1_MUTATION",
        "PERMANENT_NAIVE_BASELINE_MUTATION",
        "BENCHMARK_CAPTURE_V0_MUTATION",
        "CANONICAL_PUBLIC_RANKING_CHANGE",
        "USER_REACTION_AS_SCIENTIFIC_OUTCOME_LABEL",
        "CONFIRMATORY_WITHIN_PARTICIPANT_PACKET_CROSSOVER",
        "REPEAT_OR_NEGOTIATED_PRIMARY_WTP_OFFER_BEFORE_OUTCOME",
        "REPEATED_FIXED_SAMPLE_PEEKING_AS_SEQUENTIAL_VALIDITY",
        "POST_HOC_PRIMARY_ESTIMAND_OR_MULTIPLICITY_SELECTION",
    } <= forbidden


def test_decision_study_prevents_treatment_carryover() -> None:
    prereg = _prereg()
    decision = _object_dict(prereg["decision_loop"])

    assert decision["treatment_assignment_unit"] == "participant"
    assert decision["packet_variants"] == ["BASELINE_PACKET", "FRONTIER_PACKET"]
    assert decision["assignment"] == "RANDOMIZED_BLOCKED_PARTICIPANT_LEVEL"
    assert (
        decision["participant_exposure_to_both_packet_variants_within_confirmatory_cohort"] is False
    )
    assert decision["same_case_seen_twice_by_participant"] is False
    assert decision["case_set_policy_equal_across_arms"] is True
    assert decision["case_order_policy_must_be_frozen_or_treatment_independent"] is True
    assert decision["primary_analysis"] == "INTENTION_TO_TREAT_BY_PARTICIPANT_ASSIGNMENT"
    assert decision["analysis_must_account_for_repeated_cases_per_participant"] is True
    assert decision["packet_equal_knowledge_horizon_required"] is True


def test_decision_confirmatory_estimand_and_multiplicity_are_frozen() -> None:
    prereg = _prereg()
    decision = _object_dict(prereg["decision_loop"])
    multiplicity = _object_dict(prereg["multiplicity"])

    assert decision["primary_estimand_contract_required_before_enrollment"] is True
    required_estimand = set(_string_list(decision["primary_estimand_required_fields"]))
    assert {
        "target_population_or_segment",
        "eligible_domain_or_case_population",
        "analysis_unit",
        "primary_outcome_or_utility_metric",
        "treatment_contrast",
        "direction_or_sidedness",
        "analysis_model_or_estimator",
        "participant_clustering_treatment",
        "material_effect_threshold",
        "uncertainty_method_and_nominal_error_level",
        "confirmatory_multiplicity_family",
        "multiplicity_adjustment_or_gatekeeping_policy",
    } <= required_estimand

    assert multiplicity["one_primary_confirmatory_estimand_per_cohort"] is True
    assert (
        multiplicity["confirmatory_family_must_be_frozen_before_enrollment_or_first_offer"] is True
    )
    assert multiplicity["unadjusted_secondary_results_are_exploratory"] is True
    assert multiplicity["post_hoc_primary_claim_selection"] is False
    family_scope = set(_string_list(multiplicity["family_scope_must_cover_if_claimed"]))
    assert {
        "domain",
        "segment",
        "cohort",
        "pooled",
        "direction",
        "alternate_metric",
    } <= family_scope


def test_sequential_design_requires_repeated_look_valid_error_control() -> None:
    prereg = _prereg()
    decision = _object_dict(prereg["decision_loop"])
    market = _object_dict(prereg["market_loop"])

    assert decision["fixed_sample_default"] is True
    assert (
        decision["sequential_rule_if_used_requires_repeated_look_valid_error_or_coverage_control"]
        is True
    )
    assert decision["repeated_fixed_sample_interval_peeking_allowed"] is False
    sequential_fields = set(_string_list(decision["sequential_design_required_fields"]))
    assert {
        "maximum_sample_size",
        "look_schedule_or_anytime_valid_rule",
        "error_or_coverage_target",
        "error_spending_boundary_confidence_sequence_or_equivalent",
        "offline_operating_characteristic_validation",
    } <= sequential_fields

    assert market["fixed_offer_count_default"] is True
    assert (
        market["sequential_price_monitoring_requires_repeated_look_valid_error_or_coverage_control"]
        is True
    )
    assert market["repeated_fixed_sample_conversion_interval_peeking_allowed"] is False


def test_revealed_wtp_binds_one_offer_and_full_price_schedule_contract() -> None:
    prereg = _prereg()
    market = _object_dict(prereg["market_loop"])

    assert market["revealed_wtp_requires_real_payment_commitment"] is True
    assert market["stated_wtp_is_diagnostic_only"] is True
    assert market["price_schedule_must_be_content_addressed_and_frozen_before_first_offer"] is True
    assert _int_value(market["price_schedule_minimum_nonzero_points_per_segment"]) >= 3
    assert market["same_entitlement_and_terms_across_price_arms"] is True
    assert market["offers_per_participant_per_entitlement_per_schedule"] == 1
    assert market["repeat_or_negotiated_offer_before_primary_conversion_outcome"] is False
    assert market["price_assignment"] == "RANDOMIZED_WITHIN_PREREGISTERED_SEGMENT"
    assert market["participant_level_renegotiation_before_primary_conversion_outcome"] is False
    assert market["personalized_pricing_using_participant_attributes_or_prior_response"] is False
    assert market["refunds_and_chargebacks_must_remain_visible"] is True

    schedule_fields = set(_string_list(market["price_schedule_required_fields"]))
    assert {
        "schedule_id",
        "schedule_digest",
        "exact_product_entitlement",
        "billing_period_or_fixed_pilot_duration",
        "currency",
        "tax_inclusion_and_treatment",
        "price_points_by_segment",
        "assignment_probabilities",
        "refund_and_cancellation_terms",
        "renewal_or_continuation_terms",
        "primary_conversion_definition",
        "primary_conversion_observation_window",
    } <= schedule_fields

    offer_fields = set(_string_list(market["commercial_offer_receipt_required_fields"]))
    assert {
        "participant_pseudonymous_id",
        "segment",
        "assigned_price",
        "entitlement_identity",
        "price_schedule_digest",
        "offer_time",
        "conversion_observation_window",
    } <= offer_fields


def test_protocol_keeps_prediction_decision_and_market_evidence_distinct() -> None:
    prereg = _prereg()
    assert prereg["evidence_loops"] == ["SCIENTIFIC", "DECISION", "MARKET"]

    negative_results = set(_string_list(prereg["valid_negative_interpretations"]))
    assert {
        "PREDICTIVE_VALUE_WITHOUT_DECISION_VALUE",
        "DECISION_VALUE_WITHOUT_REVEALED_WTP",
        "REVEALED_WTP_WITHOUT_SCIENTIFIC_SUPERIORITY",
        "NO_MATERIAL_VALUE_OBSERVED",
    } <= negative_results

    text = AUTHORITY_PATH.read_text(encoding="utf-8")
    assert (
        "A scientific win with no decision impact is not automatically commercially valuable."
        in text
    )
    assert "Merge proves only that the decision/WTP experiment is preregistered." in text
