from __future__ import annotations

import json
from pathlib import Path

AUTHORITY_PATH = Path("docs/FRONTIER_DECISION_VALUE_WTP_V0.md")
PREREG_PATH = Path("experiments/value_observatory_v0/decision_value_wtp_v0.json")


def _prereg() -> dict[str, object]:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def test_decision_value_wtp_preregistration_preserves_scientific_authority() -> None:
    prereg = _prereg()

    assert prereg["phase_id"] == "FRONTIER_DECISION_VALUE_WTP_V0"
    assert prereg["status"] == "CANDIDATE_SUBORDINATE_AUTHORITY_UNTIL_MERGE"
    assert prereg["parent_authority"] == "FRONTIER_VALUE_OBSERVATORY_V0"
    assert prereg["scientific_benchmark_authority"] == "BENCHMARK_CAPTURE_V0"

    scientific_separation = prereg["scientific_separation"]
    assert isinstance(scientific_separation, dict)
    assert (
        scientific_separation["active_scored_alerts_may_be_exposed_before_longest_outcome_horizon"]
        is False
    )
    assert scientific_separation["historical_cases_confirmatory"] is False
    assert scientific_separation["user_reaction_as_scientific_outcome_label"] is False

    forbidden = set(prereg["not_authorized"])
    assert {
        "PEF_V1_MUTATION",
        "PERMANENT_NAIVE_BASELINE_MUTATION",
        "BENCHMARK_CAPTURE_V0_MUTATION",
        "CANONICAL_PUBLIC_RANKING_CHANGE",
        "USER_REACTION_AS_SCIENTIFIC_OUTCOME_LABEL",
        "OUTCOME_DEPENDENT_EARLY_STOPPING_WITHOUT_PREREGISTERED_SEQUENTIAL_RULE",
    } <= forbidden


def test_decision_study_is_randomized_equal_horizon_and_intention_to_treat() -> None:
    prereg = _prereg()
    decision = prereg["decision_loop"]
    assert isinstance(decision, dict)

    assert decision["packet_variants"] == ["BASELINE_PACKET", "FRONTIER_PACKET"]
    assert decision["assignment"] == "RANDOMIZED_BLOCKED_CASE_LEVEL"
    assert decision["same_case_seen_twice_by_participant"] is False
    assert decision["primary_analysis"] == "INTENTION_TO_TREAT"
    assert decision["packet_equal_knowledge_horizon_required"] is True
    assert decision["primary_utility_metric_must_be_frozen_before_enrollment"] is True
    assert (
        decision["sample_size_or_sequential_precision_rule_must_be_frozen_before_enrollment"]
        is True
    )
    assert (
        decision["outcome_dependent_early_stopping_without_preregistered_sequential_rule"] is False
    )


def test_revealed_wtp_requires_real_payment_and_frozen_randomized_prices() -> None:
    prereg = _prereg()
    market = prereg["market_loop"]
    assert isinstance(market, dict)

    assert market["revealed_wtp_requires_real_payment_commitment"] is True
    assert market["stated_wtp_is_diagnostic_only"] is True
    assert market["price_schedule_must_be_frozen_before_first_offer"] is True
    assert market["price_schedule_minimum_nonzero_points_per_segment"] >= 3
    assert market["price_assignment"] == "RANDOMIZED_WITHIN_PREREGISTERED_SEGMENT"
    assert (
        market["target_offer_count_or_sequential_precision_rule_must_be_frozen_before_first_offer"]
        is True
    )
    assert (
        market["outcome_dependent_price_cell_stopping_without_preregistered_sequential_rule"]
        is False
    )
    assert market["participant_level_renegotiation_before_primary_conversion_outcome"] is False
    assert market["personalized_pricing_using_participant_attributes_or_prior_response"] is False
    assert market["refunds_and_chargebacks_must_remain_visible"] is True


def test_protocol_keeps_prediction_decision_and_market_evidence_distinct() -> None:
    prereg = _prereg()
    assert prereg["evidence_loops"] == ["SCIENTIFIC", "DECISION", "MARKET"]

    negative_results = set(prereg["valid_negative_interpretations"])
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
