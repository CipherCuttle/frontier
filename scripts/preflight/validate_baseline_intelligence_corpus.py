from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "baseline_intelligence" / "corpus_v0.json"

EXPECTED_SCHEMA = "frontier-baseline-intelligence-corpus-v0"
EXPECTED_PROJECTION = {
    "name": "baseline-intelligence",
    "version": "baseline-intelligence-v0",
    "schema_version": "baseline-intelligence-snapshot-v0",
    "algorithm_version": "windowed-episode-metrics-v0",
    "ranking_policy_version": "naive-episode-activity-v0",
}
EXPECTED_WINDOWS = {
    "mentions_1h": 3600,
    "mentions_6h": 21600,
    "mentions_24h": 86400,
    "previous_6h_start": 43200,
    "preprevious_6h_start": 64800,
}
EXPECTED_RANKING = [
    "mentions_1h_desc",
    "mentions_6h_desc",
    "velocity_6h_delta_desc",
    "acceleration_6h_desc",
    "mentions_24h_desc",
    "source_role_diversity_desc",
    "last_observed_at_desc",
    "evidence_count_total_desc",
    "episode_id_asc",
]
REQUIRED_PROPERTIES = {
    "deterministic_replay",
    "point_in_time_no_lookahead",
    "observed_at_is_knowledge_clock",
    "backfill_not_live_activity",
    "recovered_backlog_not_live_activity",
    "duplicate_collection_not_duplicate_mentions",
    "coverage_not_zero_activity",
    "attention_not_confirmation",
    "source_count_not_provenance_root_count",
    "assertion_state_orthogonal_to_activity",
    "complete_snapshot_and_receipt_atomic",
    "failed_candidate_preserves_prior_complete",
}
REQUIRED_CATEGORIES = {
    "fresh_primary",
    "attention_propagation",
    "window_math",
    "prospective_eligibility",
    "knowledge_clock",
    "point_in_time",
    "collection_deduplication",
    "assertion_trend_separation",
    "coverage_health",
    "coverage_unknown",
    "ranking_tie",
    "atomic_publication",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"baseline-intelligence-corpus: FAIL: {message}")


def main() -> int:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(data.get("schema_version") == EXPECTED_SCHEMA, "schema version drift")
    require(data.get("runtime_implementation_authorized") is False, "authority must predate runtime")
    require(data.get("projection") == EXPECTED_PROJECTION, "projection identity drift")
    require(data.get("windows_seconds") == EXPECTED_WINDOWS, "window authority drift")
    require(data.get("ranking_order") == EXPECTED_RANKING, "ranking policy drift")
    require(set(data.get("required_properties", [])) == REQUIRED_PROPERTIES, "property set drift")

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
        require("expect" in scenario, f"expectation missing for {scenario_id}")
        ids.add(scenario_id)
        categories.add(category)

    require(categories == REQUIRED_CATEGORIES, "required adversarial categories drift")
    require(len(scenarios) == 12, "expected exactly 12 frozen scenarios")
    print("validated 12 frozen baseline-intelligence scenarios across 12 categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
