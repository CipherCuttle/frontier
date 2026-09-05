from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.domain.grouping import GROUPING_ALGORITHM_VERSION, GroupingDecision, GroupingInput
from frontier.domain.grouping_candidates import CandidateStrategy, evaluate_strategy

CORPUS = Path("fixtures/grouping/corpus_v0.json")
SELECTION = Path("fixtures/grouping/selection_v0.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def observation_id(case_id: str, side: str) -> str:
    return "obs_" + hashlib.sha256(f"{case_id}:{side}".encode()).hexdigest()


def parse_time(value: object) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), "corpus observed_at must be UTC Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def parse_input(case_id: str, side: str, value: object) -> GroupingInput:
    require(isinstance(value, dict), f"{case_id} {side} must be an object")
    source_id = value.get("source_id")
    source_item_key = value.get("source_item_key")
    require(isinstance(source_id, str), f"{case_id} {side} missing source_id")
    require(isinstance(source_item_key, str), f"{case_id} {side} missing source_item_key")
    roles = value.get("signal_roles", [])
    require(isinstance(roles, list), f"{case_id} {side} roles must be a list")
    require(all(isinstance(role, str) for role in roles), f"{case_id} {side} roles malformed")
    return GroupingInput(
        observation_id=observation_id(case_id, side),
        source_id=source_id,
        source_item_key=source_item_key,
        kind=cast(str, value.get("kind", "DOCUMENT")),
        observed_at=parse_time(value.get("observed_at")),
        canonical_url=cast(str | None, value.get("canonical_url")),
        title=cast(str | None, value.get("title")),
        text=cast(str | None, value.get("text")),
        artifact_type=cast(str | None, value.get("artifact_type")),
        artifact_name=cast(str | None, value.get("artifact_name")),
        artifact_version=cast(str | None, value.get("artifact_version")),
        signal_roles=tuple(cast(list[str], roles)),
    )


def main() -> None:
    corpus_bytes = CORPUS.read_bytes()
    corpus = json.loads(corpus_bytes)
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    require(
        selection.get("schema_version") == "frontier-grouping-selection-v0",
        "unexpected grouping selection schema",
    )
    expected_digest = "sha256:" + hashlib.sha256(corpus_bytes).hexdigest()
    require(
        selection.get("corpus_file_sha256") == expected_digest,
        "selection artifact does not bind the frozen corpus bytes",
    )

    raw_cases = corpus.get("cases")
    require(isinstance(raw_cases, list), "corpus cases must be a list")
    cases: list[tuple[GroupingInput, GroupingInput, GroupingDecision]] = []
    for raw_case in raw_cases:
        require(isinstance(raw_case, dict), "grouping case must be an object")
        case_id = raw_case.get("id")
        expected = raw_case.get("expected")
        require(isinstance(case_id, str), "grouping case missing id")
        require(isinstance(expected, str), f"{case_id} missing expected")
        cases.append(
            (
                parse_input(case_id, "left", raw_case.get("left")),
                parse_input(case_id, "right", raw_case.get("right")),
                GroupingDecision(expected),
            )
        )

    actual = [
        evaluate_strategy(cases, strategy=strategy).to_canonical()
        for strategy in CandidateStrategy
    ]
    require(
        selection.get("evaluated_candidates") == actual,
        "recorded grouping metrics do not replay from frozen corpus + implementation",
    )
    require(
        selection.get("selected_algorithm") == GROUPING_ALGORITHM_VERSION,
        "runtime grouping algorithm differs from selection authority",
    )
    selected = next(
        metrics for metrics in actual if metrics.get("strategy") == GROUPING_ALGORITHM_VERSION
    )
    require(selected.get("false_group") == 0, "selected grouping algorithm has false merges")
    require(
        selected.get("pair_precision") == "1.000000",
        "selected grouping algorithm misses precision gate",
    )
    require(
        float(cast(str, selected.get("group_recall"))) >= 0.8,
        "selected grouping algorithm misses recall gate",
    )
    survivors = [
        metrics
        for metrics in actual
        if metrics.get("false_group") == 0
        and metrics.get("pair_precision") == "1.000000"
        and float(cast(str, metrics.get("group_recall"))) >= 0.8
    ]
    require(
        [metrics.get("strategy") for metrics in survivors] == [GROUPING_ALGORITHM_VERSION],
        "selection is no longer uniquely justified by frozen gates",
    )
    print(
        "grouping-selection: PASS "
        f"{GROUPING_ALGORITHM_VERSION} precision={selected['pair_precision']} "
        f"recall={selected['group_recall']} false_group={selected['false_group']}"
    )


if __name__ == "__main__":
    main()
