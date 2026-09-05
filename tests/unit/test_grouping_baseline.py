from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from frontier.domain.digests import Digest
from frontier.domain.grouping import (
    GROUPING_ALGORITHM_VERSION,
    GroupingDecision,
    GroupingInput,
    GroupingRelationInput,
    assess_pair,
    build_grouping_projection,
    build_grouping_receipt,
)
from frontier.domain.grouping_candidates import CandidateStrategy, evaluate_strategy

CORPUS = Path("fixtures/grouping/corpus_v0.json")
SELECTION = Path("fixtures/grouping/selection_v0.json")
NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)


def observation_id(case_id: str, side: str) -> str:
    return "obs_" + hashlib.sha256(f"{case_id}:{side}".encode()).hexdigest()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def parse_input(case_id: str, side: str, value: dict[str, object]) -> GroupingInput:
    roles_value = value.get("signal_roles", [])
    assert isinstance(roles_value, list)
    return GroupingInput(
        observation_id=observation_id(case_id, side),
        source_id=cast(str, value["source_id"]),
        source_item_key=cast(str, value["source_item_key"]),
        kind=cast(str, value.get("kind", "DOCUMENT")),
        observed_at=parse_time(cast(str, value["observed_at"])),
        canonical_url=cast(str | None, value.get("canonical_url")),
        title=cast(str | None, value.get("title")),
        text=cast(str | None, value.get("text")),
        artifact_type=cast(str | None, value.get("artifact_type")),
        artifact_name=cast(str | None, value.get("artifact_name")),
        artifact_version=cast(str | None, value.get("artifact_version")),
        signal_roles=tuple(cast(list[str], roles_value)),
    )


def corpus_cases() -> list[tuple[GroupingInput, GroupingInput, GroupingDecision]]:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    raw_cases = cast(list[dict[str, object]], document["cases"])
    result: list[tuple[GroupingInput, GroupingInput, GroupingDecision]] = []
    for case in raw_cases:
        case_id = cast(str, case["id"])
        left = parse_input(case_id, "left", cast(dict[str, object], case["left"]))
        right = parse_input(case_id, "right", cast(dict[str, object], case["right"]))
        result.append((left, right, GroupingDecision(cast(str, case["expected"]))))
    return result


def test_frozen_candidate_selection_recomputes_exactly() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    expected_metrics = cast(list[dict[str, object]], selection["evaluated_candidates"])
    actual_metrics = [
        evaluate_strategy(corpus_cases(), strategy=strategy).to_canonical()
        for strategy in CandidateStrategy
    ]
    assert actual_metrics == expected_metrics
    assert selection["selected_algorithm"] == GROUPING_ALGORITHM_VERSION
    selected = next(
        metrics for metrics in actual_metrics if metrics["strategy"] == GROUPING_ALGORITHM_VERSION
    )
    assert selected["false_group"] == 0
    assert selected["pair_precision"] == "1.000000"
    assert selected["group_recall"] == "0.900000"


def test_shared_catalog_and_attention_guards_preserve_uncertainty() -> None:
    cases = corpus_cases()
    first_left, first_right, _ = cases[0]
    second_left, second_right, _ = cases[1]
    catalog_left, catalog_right, _ = cases[17]
    assert assess_pair(first_left, first_right).decision is GroupingDecision.GROUP
    assert assess_pair(second_left, second_right).decision is GroupingDecision.NO_GROUP
    assert assess_pair(catalog_left, catalog_right).decision is GroupingDecision.AMBIGUOUS


def test_projection_is_deterministic_and_filters_future_observations() -> None:
    first, second, _ = corpus_cases()[0]
    future = GroupingInput(
        observation_id="obs_" + "f" * 64,
        source_id="future.source",
        source_item_key="future",
        kind="DOCUMENT",
        observed_at=NOW + timedelta(hours=1),
        canonical_url=first.canonical_url,
        title=first.title,
        text=None,
        signal_roles=("ATTENTION",),
    )
    forward = build_grouping_projection((first, second, future), as_of=NOW + timedelta(minutes=10))
    reverse = build_grouping_projection((future, second, first), as_of=NOW + timedelta(minutes=10))
    assert forward.to_canonical() == reverse.to_canonical()
    assert len(forward.groups) == 1
    assert forward.groups[0].observation_ids == tuple(
        sorted((first.observation_id, second.observation_id))
    )
    assert future.observation_id not in json.dumps(forward.to_canonical())


def test_explicit_correction_is_point_in_time_and_does_not_rewrite_history() -> None:
    left = GroupingInput(
        observation_id="obs_" + "a" * 64,
        source_id="publisher.one",
        source_item_key="old",
        kind="DOCUMENT",
        observed_at=NOW,
        canonical_url="https://one.example/old",
        title="Old unrelated wording",
        text=None,
    )
    right = GroupingInput(
        observation_id="obs_" + "b" * 64,
        source_id="publisher.one",
        source_item_key="new",
        kind="DOCUMENT",
        observed_at=NOW,
        canonical_url="https://one.example/new",
        title="Completely different correction wording",
        text=None,
    )
    relation = GroupingRelationInput(
        relation_type="CORRECTS",
        from_observation_id=right.observation_id,
        target_observation_id=left.observation_id,
        authority="EXPLICIT",
        created_at=NOW + timedelta(minutes=5),
    )
    before = build_grouping_projection((left, right), relations=(relation,), as_of=NOW)
    after = build_grouping_projection(
        (left, right), relations=(relation,), as_of=NOW + timedelta(minutes=5)
    )
    assert not before.groups
    assert len(after.groups) == 1
    assert {left.observation_id, right.observation_id} == set(after.groups[0].observation_ids)


def test_projection_receipt_is_replayable_and_contains_no_provenance_claim() -> None:
    first, second, _ = corpus_cases()[0]
    projection = build_grouping_projection((first, second), as_of=NOW + timedelta(minutes=10))
    receipt = build_grouping_receipt(
        projection,
        inputs=(first, second),
        relations=(),
        generated_at=NOW + timedelta(minutes=11),
        source_registry_version=Digest(
            "sha256:498b4afff3b5a0dcbfb448514a08a3e85adf7f8f2dd5d0863aebbcb353c361f8"
        ),
    )
    replay = build_grouping_receipt(
        projection,
        inputs=(second, first),
        relations=(),
        generated_at=NOW + timedelta(minutes=12),
        source_registry_version=receipt.source_registry_version,
    )
    assert receipt.receipt_id == replay.receipt_id
    canonical = json.dumps(projection.to_canonical())
    assert "provenance" not in canonical
    assert "root" not in canonical
    assert "entity" not in canonical


def test_duplicate_grouping_input_fails_closed() -> None:
    first, _, _ = corpus_cases()[0]
    with pytest.raises(ValueError, match="duplicate observation_id"):
        build_grouping_projection((first, first), as_of=NOW + timedelta(minutes=10))


def test_projection_does_not_bridge_no_group_or_ambiguous_pairs() -> None:
    artifact_v1 = GroupingInput(
        observation_id="obs_" + "1" * 64,
        source_id="pypi.fixture",
        source_item_key="atlas/1.0",
        kind="ARTIFACT",
        observed_at=NOW,
        canonical_url="https://pypi.example/atlas/1.0",
        title=None,
        text=None,
        artifact_type="python-package-release",
        artifact_name="Atlas Runtime Package",
        artifact_version="1.0",
    )
    artifact_bridge = GroupingInput(
        observation_id="obs_" + "2" * 64,
        source_id="publisher.fixture",
        source_item_key="atlas-release",
        kind="DOCUMENT",
        observed_at=NOW + timedelta(minutes=1),
        canonical_url="https://publisher.example/atlas",
        title="Atlas Runtime Package",
        text=None,
    )
    artifact_v2 = GroupingInput(
        observation_id="obs_" + "3" * 64,
        source_id="pypi.fixture",
        source_item_key="atlas/2.0",
        kind="ARTIFACT",
        observed_at=NOW + timedelta(minutes=2),
        canonical_url="https://pypi.example/atlas/2.0",
        title=None,
        text=None,
        artifact_type="python-package-release",
        artifact_name="Atlas Runtime Package",
        artifact_version="2.0",
    )
    assert assess_pair(artifact_v1, artifact_bridge).decision is GroupingDecision.GROUP
    assert assess_pair(artifact_bridge, artifact_v2).decision is GroupingDecision.GROUP
    assert assess_pair(artifact_v1, artifact_v2).decision is GroupingDecision.NO_GROUP

    artifact_projection = build_grouping_projection(
        (artifact_v1, artifact_bridge, artifact_v2),
        as_of=NOW + timedelta(minutes=10),
    )
    assert not any(
        {artifact_v1.observation_id, artifact_v2.observation_id} <= set(group.observation_ids)
        for group in artifact_projection.groups
    )

    first = GroupingInput(
        observation_id="obs_" + "4" * 64,
        source_id="publisher.alpha",
        source_item_key="atlas-a",
        kind="DOCUMENT",
        observed_at=NOW,
        canonical_url="https://alpha.example/atlas",
        title="Atlas runtime launches for local agents",
        text=None,
    )
    bridge = GroupingInput(
        observation_id="obs_" + "5" * 64,
        source_id="hn.frontpage",
        source_item_key="hn:500",
        kind="DOCUMENT",
        observed_at=NOW + timedelta(minutes=1),
        canonical_url="https://shared.example/atlas",
        title="Atlas runtime launches for local agents",
        text=None,
        signal_roles=("ATTENTION",),
    )
    ambiguous = GroupingInput(
        observation_id="obs_" + "6" * 64,
        source_id="hn.frontpage",
        source_item_key="hn:501",
        kind="DOCUMENT",
        observed_at=NOW + timedelta(minutes=2),
        canonical_url="https://shared.example/atlas",
        title="Different discussion headline entirely",
        text=None,
        signal_roles=("ATTENTION",),
    )
    assert assess_pair(first, bridge).decision is GroupingDecision.GROUP
    assert assess_pair(bridge, ambiguous).decision is GroupingDecision.GROUP
    assert assess_pair(first, ambiguous).decision is GroupingDecision.AMBIGUOUS

    ambiguous_projection = build_grouping_projection(
        (first, bridge, ambiguous),
        as_of=NOW + timedelta(minutes=10),
    )
    assert not any(
        {first.observation_id, ambiguous.observation_id} <= set(group.observation_ids)
        for group in ambiguous_projection.groups
    )
    assert any(
        pair.left_observation_id == first.observation_id
        and pair.right_observation_id == ambiguous.observation_id
        for pair in ambiguous_projection.ambiguous_pairs
    )
