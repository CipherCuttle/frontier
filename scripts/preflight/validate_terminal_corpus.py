from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "terminal" / "corpus_v0.json"
EXPECTED_IDS = tuple(f"T{index:03d}" for index in range(1, 22))
EXPECTED_CATEGORIES = {
    "aggregate-health",
    "api-failure",
    "audit-reachability",
    "confirmation-unavailable",
    "coverage-unknown",
    "editable-target-guard",
    "empty-view",
    "experimental-lens",
    "generated-client-authority",
    "get-only-transport",
    "keyboard-contract",
    "large-fixture-order",
    "local-filter",
    "multidimensional-health",
    "non-color-only-health",
    "provenance-root-unavailable",
    "rank-preservation",
    "snapshot-bound-drilldown",
    "snapshot-change-invalidation",
    "source-count-not-confirmation",
    "unauthorized-semantics",
}


def fail(message: str) -> int:
    print(f"terminal-corpus: FAIL: {message}")
    return 1


def main() -> int:
    document = cast(dict[str, Any], json.loads(CORPUS.read_text(encoding="utf-8")))
    if document.get("schema_version") != "terminal-hostile-corpus-v0":
        return fail("unexpected schema_version")
    if document.get("authority") != "docs/TERMINAL_V0.md":
        return fail("authority must be docs/TERMINAL_V0.md")
    if document.get("parent") != "641cca5f0001e5e5b644f574aa09765a9d797589":
        return fail("unexpected frozen parent")

    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 21:
        return fail("expected exactly 21 frozen scenarios")

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

    print("terminal-corpus: PASS 21 frozen hostile scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
