from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "advanced_intelligence" / "corpus_v0.json"
EXPECTED_IDS = tuple(f"A{index:03d}" for index in range(1, 21))
EXPECTED_CATEGORIES = {
    "backfill-recovered-contamination",
    "configuration-drift",
    "coverage-coercion",
    "denominator-gaming",
    "domain-cherry-picking",
    "emit-nothing-precision",
    "failed-artifact-as-signal",
    "future-observation-leakage",
    "future-operational-metadata",
    "label-leakage",
    "merge-is-not-promotion",
    "multiple-comparison-selection",
    "nonindependent-domains",
    "operating-point-mismatch",
    "posthoc-threshold-selection",
    "retrospective-tuning",
    "semantic-escalation",
    "source-count-confirmation",
    "stochastic-replay-drift",
    "universe-mismatch",
}


def fail(message: str) -> int:
    print(f"advanced-intelligence-corpus: FAIL: {message}")
    return 1


def main() -> int:
    document = cast(dict[str, Any], json.loads(CORPUS.read_text(encoding="utf-8")))
    if document.get("schema_version") != "advanced-intelligence-hostile-corpus-v0":
        return fail("unexpected schema_version")
    if document.get("authority") != "docs/ADVANCED_INTELLIGENCE_EXPERIMENTS.md":
        return fail("unexpected authority")
    if document.get("parent") != "e54c36f538e0f28535b853c49d62d2d6c35f5e2c":
        return fail("unexpected frozen parent")
    if document.get("runtime_implementation_authorized") is not False:
        return fail("authority freeze must not authorize runtime implementation")

    control = document.get("control")
    if not isinstance(control, dict):
        return fail("control must be an object")
    if control.get("projection_name") != "baseline-intelligence":
        return fail("unexpected control projection")
    if control.get("projection_version") != "baseline-intelligence-v0":
        return fail("unexpected control projection version")
    if control.get("ranking_policy_version") != "naive-episode-activity-v0":
        return fail("unexpected control ranking policy")

    promotion = document.get("promotion_contract")
    if not isinstance(promotion, dict):
        return fail("promotion_contract must be an object")
    expected_promotion = {
        "shadow_authority_state": "EXPERIMENTAL_SHADOW",
        "experiment_class": "RANKING_EMERGENCE_EXISTING_EPISODE_UNIVERSE",
        "qualifying_domain_ids": [
            "AI_MODELS",
            "SECURITY_VULNERABILITIES",
            "SOFTWARE_PACKAGES",
        ],
        "minimum_qualifying_domains": 2,
        "operating_point_contract": "same_preregistered_positive_global_rank_cutoff_k_both_arms",
        "point_precision_floor": "candidate_gte_control_each_qualifying_domain",
        "lead_time_floor": "median_positive_each_qualifying_domain_and_pooled",
        "requires_preregistration_before_confirmatory_window": True,
        "requires_hostile_preregistration_review": True,
        "historical_development_counts_as_confirmatory": False,
        "public_promotion_requires_separate_authority_change": True,
    }
    if promotion != expected_promotion:
        return fail("promotion contract drifted")

    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 20:
        return fail("expected exactly 20 frozen scenarios")

    ids: list[str] = []
    categories: set[str] = set()
    for raw in scenarios:
        if not isinstance(raw, dict):
            return fail("scenario must be an object")
        scenario = cast(dict[str, Any], raw)
        scenario_id = scenario.get("id")
        category = scenario.get("category")
        requirement = scenario.get("requirement")
        forbidden = scenario.get("forbidden")
        if not isinstance(scenario_id, str):
            return fail("scenario id must be a string")
        if not isinstance(category, str):
            return fail(f"{scenario_id}: category must be a string")
        if not isinstance(requirement, str) or not requirement.strip():
            return fail(f"{scenario_id}: requirement must be non-empty")
        if not isinstance(forbidden, str) or not forbidden.strip():
            return fail(f"{scenario_id}: forbidden must be non-empty")
        ids.append(scenario_id)
        categories.add(category)

    if tuple(ids) != EXPECTED_IDS:
        return fail("scenario IDs/order drifted")
    if categories != EXPECTED_CATEGORIES:
        return fail("scenario category set drifted")
    if len(categories) != len(scenarios):
        return fail("scenario categories must be unique in V0")

    print("advanced-intelligence-corpus: PASS 20 frozen hostile scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
