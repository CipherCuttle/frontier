from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "public_read_plane" / "corpus_v0.json"

EXPECTED_SCHEMA = "frontier-public-read-corpus-v0"
EXPECTED_API_VERSION = "public-read-api-v0"
EXPECTED_RESPONSE_SCHEMA = "public-read-response-v0"
EXPECTED_VIEW_POLICY = "baseline-read-views-v0"
EXPECTED_BASELINE = {
    "name": "baseline-intelligence",
    "version": "baseline-intelligence-v0",
    "schema_version": "baseline-intelligence-snapshot-v0",
    "algorithm_version": "windowed-episode-metrics-v0",
    "ranking_policy_version": "naive-episode-activity-v0",
}
EXPECTED_VIEW_RULES = {
    "RADAR": "all_episodes_preserve_baseline_rank",
    "NOW": "mentions_1h_gt_0_preserve_baseline_rank",
    "TRENDING": "velocity_6h_delta_gt_0_preserve_baseline_rank",
}
EXPECTED_BINDING_FIELDS = {
    "snapshot_id",
    "receipt_id",
    "receipt_schema_version",
    "projection_name",
    "projection_version",
    "schema_version",
    "algorithm_version",
    "ranking_policy_version",
    "configuration_digest",
    "source_registry_version",
    "as_of",
    "input_digest",
    "output_digest",
}
EXPECTED_CATEGORIES = {
    "publication_status",
    "availability",
    "snapshot_selection",
    "integrity",
    "view_semantics",
    "health",
    "epistemic_integrity",
    "evidence_drilldown",
    "point_in_time",
    "transport_authority",
    "mutation_boundary",
    "contract_generation",
}
EXPECTED_IDS = {
    "failed_receipt_not_publishable",
    "implicit_no_complete_snapshot",
    "latest_complete_deterministic",
    "snapshot_binding_mismatch_fail_closed",
    "snapshot_output_digest_mismatch_fail_closed",
    "radar_preserves_baseline_rank",
    "now_filters_without_rerank",
    "trending_filters_without_rerank",
    "coverage_degradation_visible",
    "source_diversity_not_confirmation",
    "episode_drilldown_membership_bounded",
    "future_observation_excluded_from_direct_read",
    "openapi_has_no_mutation_operations",
    "database_session_read_only",
    "generated_contracts_deterministic",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"public-read-plane-corpus: FAIL: {message}")


def main() -> int:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(data.get("schema_version") == EXPECTED_SCHEMA, "schema version drift")
    require(data.get("runtime_implementation_authorized") is False, "authority must predate runtime")
    require(data.get("api_version") == EXPECTED_API_VERSION, "API version drift")
    require(data.get("response_schema_family") == EXPECTED_RESPONSE_SCHEMA, "response schema drift")
    require(data.get("view_policy_version") == EXPECTED_VIEW_POLICY, "view policy drift")
    require(data.get("baseline_projection") == EXPECTED_BASELINE, "baseline identity drift")
    require(data.get("required_http_methods") == ["GET"], "only GET is authorized")
    require(
        set(data.get("forbidden_http_methods", [])) == {"POST", "PUT", "PATCH", "DELETE"},
        "forbidden method set drift",
    )
    require(data.get("view_rules") == EXPECTED_VIEW_RULES, "view rule drift")
    require(
        set(data.get("required_snapshot_binding_fields", [])) == EXPECTED_BINDING_FIELDS,
        "snapshot binding field drift",
    )
    pagination = data.get("pagination")
    require(
        pagination == {"default_limit": 50, "max_limit": 100, "default_offset": 0},
        "pagination authority drift",
    )

    scenarios = data.get("scenarios")
    require(isinstance(scenarios, list), "scenarios must be a list")
    ids: set[str] = set()
    categories: set[str] = set()
    for scenario in scenarios:
        require(isinstance(scenario, dict), "scenario must be an object")
        scenario_id = scenario.get("id")
        category = scenario.get("category")
        require(isinstance(scenario_id, str) and scenario_id, "scenario id missing")
        require(scenario_id not in ids, f"duplicate scenario id {scenario_id}")
        require(isinstance(category, str) and category, f"category missing for {scenario_id}")
        require("given" in scenario, f"given missing for {scenario_id}")
        require("expect" in scenario, f"expectation missing for {scenario_id}")
        ids.add(scenario_id)
        categories.add(category)

    require(ids == EXPECTED_IDS, "frozen scenario ID set drift")
    require(categories == EXPECTED_CATEGORIES, "required adversarial categories drift")
    require(len(scenarios) == 15, "expected exactly 15 frozen scenarios")
    print("validated 15 frozen public-read-plane scenarios across 12 categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
