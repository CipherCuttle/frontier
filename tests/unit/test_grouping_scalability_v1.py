from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path

import pytest

from frontier.domain.digests import Digest
from frontier.domain.grouping import (
    EpisodeGroup,
    GroupingDecision,
    GroupingInput,
    GroupingRelationInput,
    assess_pair,
    build_grouping_projection,
)
from frontier.domain.grouping_v1 import (
    GROUPING_V1_OMITTED_PAIR_SEMANTICS,
    GROUPING_V1_ORACLE_BLOB,
    assess_pair_v1,
    build_compact_grouping_projection,
    build_compact_grouping_receipt,
    is_group_pair_v1,
)
from tests.unit.test_grouping_baseline import corpus_cases

NOW = datetime(2026, 9, 8, 20, tzinfo=UTC)
SOURCE_REGISTRY_DIGEST = Digest(
    "sha256:0e3dcd047379e500900194ed2ff47aa980a4a61172c33a7fb7b9e2f5930b696e"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode()
    return hashlib.sha1(header + payload).hexdigest()


def _partition(
    groups: tuple[EpisodeGroup, ...],
    ungrouped_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    members: list[tuple[str, ...]] = []
    for group in groups:
        members.append(tuple(sorted(group.observation_ids)))
    members.extend((observation_id,) for observation_id in ungrouped_ids)
    return tuple(sorted(members))


def _v0_partition(
    inputs: tuple[GroupingInput, ...],
    *,
    relations: tuple[GroupingRelationInput, ...] = (),
    as_of: datetime,
) -> tuple[tuple[str, ...], ...]:
    projection = build_grouping_projection(inputs, relations=relations, as_of=as_of)
    return _partition(projection.groups, projection.ungrouped_observation_ids)


def _v1_partition(
    inputs: tuple[GroupingInput, ...],
    *,
    relations: tuple[GroupingRelationInput, ...] = (),
    as_of: datetime,
) -> tuple[tuple[str, ...], ...]:
    projection = build_compact_grouping_projection(inputs, relations=relations, as_of=as_of)
    return _partition(projection.groups, projection.ungrouped_observation_ids)


def _obs(
    index: int,
    *,
    title: str,
    canonical_url: str | None = None,
    observed_at: datetime | None = None,
    source_id: str = "fixture.source",
    source_item_key: str | None = None,
    kind: str = "DOCUMENT",
    text: str | None = None,
    artifact_name: str | None = None,
    artifact_version: str | None = None,
    signal_roles: tuple[str, ...] = (),
) -> GroupingInput:
    return GroupingInput(
        observation_id="obs_" + hashlib.sha256(f"grouping-v1:{index}".encode()).hexdigest(),
        source_id=source_id,
        source_item_key=source_item_key or f"item-{index}",
        kind=kind,
        observed_at=observed_at or NOW,
        canonical_url=canonical_url,
        title=title,
        text=text,
        artifact_name=artifact_name,
        artifact_version=artifact_version,
        signal_roles=signal_roles,
    )


def test_v0_oracle_blob_is_still_the_frozen_reference() -> None:
    assert _git_blob_sha(Path("src/frontier/domain/grouping.py")) == GROUPING_V1_ORACLE_BLOB


@pytest.mark.parametrize(("left", "right", "expected"), corpus_cases())
def test_fast_group_predicate_matches_frozen_v0_pair_corpus(
    left: GroupingInput,
    right: GroupingInput,
    expected: GroupingDecision,
) -> None:
    assert is_group_pair_v1(left, right) is (expected is GroupingDecision.GROUP)
    assert assess_pair_v1(left, right).to_canonical() == assess_pair(left, right).to_canonical()


@pytest.mark.parametrize(("left", "right", "_expected"), corpus_cases())
def test_two_item_membership_matches_frozen_v0(
    left: GroupingInput,
    right: GroupingInput,
    _expected: GroupingDecision,
) -> None:
    as_of = max(left.observed_at, right.observed_at) + timedelta(seconds=1)
    inputs = (left, right)
    assert _v1_partition(inputs, as_of=as_of) == _v0_partition(inputs, as_of=as_of)


def test_exact_jaccard_threshold_pair_is_not_omitted() -> None:
    left = _obs(1, title="alpha beta gamma delta")
    right = _obs(2, title="alpha beta gamma delta epsilon")
    assert assess_pair(left, right).decision is GroupingDecision.GROUP
    projection = build_compact_grouping_projection((left, right), as_of=NOW)
    assert projection.candidate_pair_count == 1
    assert projection.group_pair_count == 1
    assert len(projection.groups) == 1


def test_explicit_relation_is_point_in_time_and_group_complete() -> None:
    left = _obs(10, title="alpha completely unrelated wording")
    right = _obs(11, title="omega different unrelated wording")
    relation = GroupingRelationInput(
        relation_type="CORRECTS",
        from_observation_id=right.observation_id,
        target_observation_id=left.observation_id,
        authority="EXPLICIT",
        created_at=NOW + timedelta(minutes=5),
    )
    before = build_compact_grouping_projection(
        (left, right),
        relations=(relation,),
        as_of=NOW,
    )
    after = build_compact_grouping_projection(
        (left, right),
        relations=(relation,),
        as_of=NOW + timedelta(minutes=5),
    )
    assert not before.groups
    assert len(after.groups) == 1
    assert after.group_pair_count == 1


def test_clique_conservative_membership_matches_v0_false_transitivity_case() -> None:
    first = _obs(
        20,
        title="Atlas runtime launches for local agents",
        canonical_url="https://alpha.example/atlas",
    )
    bridge = _obs(
        21,
        title="Atlas runtime launches for local agents",
        canonical_url="https://shared.example/atlas",
        source_id="hn.frontpage",
        signal_roles=("ATTENTION",),
    )
    ambiguous = _obs(
        22,
        title="Different discussion headline entirely",
        canonical_url="https://shared.example/atlas",
        source_id="hn.frontpage",
        signal_roles=("ATTENTION",),
    )
    inputs = (first, bridge, ambiguous)
    assert assess_pair(first, bridge).decision is GroupingDecision.GROUP
    assert assess_pair(bridge, ambiguous).decision is GroupingDecision.GROUP
    assert assess_pair(first, ambiguous).decision is GroupingDecision.AMBIGUOUS
    assert _v1_partition(inputs, as_of=NOW) == _v0_partition(inputs, as_of=NOW)


def test_compact_projection_never_materializes_exhaustive_ambiguity() -> None:
    inputs = tuple(
        _obs(
            1000 + index,
            title=f"frontier synthetic release unique{index}",
            canonical_url=f"https://example.test/{index}",
        )
        for index in range(2425)
    )
    projection = build_compact_grouping_projection(inputs, as_of=NOW)
    canonical = projection.to_canonical()
    assert projection.eligible_observation_count == 2425
    assert projection.candidate_pair_count == 0
    assert projection.group_pair_count == 0
    assert len(projection.ungrouped_observation_ids) == 2425
    assert "ambiguous_pairs" not in canonical
    assert canonical["omitted_pair_semantics"] == GROUPING_V1_OMITTED_PAIR_SEMANTICS


def test_receipt_is_deterministic_for_reversed_inputs_without_n2_output() -> None:
    inputs = tuple(
        _obs(
            4000 + index,
            title=f"frontier deterministic release unique{index}",
            canonical_url=f"https://receipt.example/{index}",
        )
        for index in range(250)
    )
    projection = build_compact_grouping_projection(inputs, as_of=NOW)
    receipt = build_compact_grouping_receipt(
        projection,
        inputs=inputs,
        relations=(),
        generated_at=NOW + timedelta(minutes=1),
        source_registry_version=SOURCE_REGISTRY_DIGEST,
    )
    replay = build_compact_grouping_receipt(
        projection,
        inputs=tuple(reversed(inputs)),
        relations=(),
        generated_at=NOW + timedelta(minutes=2),
        source_registry_version=SOURCE_REGISTRY_DIGEST,
    )
    assert receipt.receipt_id == replay.receipt_id
    assert receipt.input_digest == replay.input_digest
    assert receipt.output_digest == replay.output_digest
    assert "ambiguous_pairs" not in json.dumps(projection.to_canonical())


def test_input_digest_changes_when_membership_relevant_input_changes() -> None:
    original = _obs(5000, title="alpha beta gamma")
    changed = GroupingInput(
        observation_id=original.observation_id,
        source_id=original.source_id,
        source_item_key=original.source_item_key,
        kind=original.kind,
        observed_at=original.observed_at,
        canonical_url=original.canonical_url,
        title="alpha beta gamma changed",
        text=original.text,
        artifact_type=original.artifact_type,
        artifact_name=original.artifact_name,
        artifact_version=original.artifact_version,
        signal_roles=original.signal_roles,
    )
    original_projection = build_compact_grouping_projection((original,), as_of=NOW)
    changed_projection = build_compact_grouping_projection((changed,), as_of=NOW)
    original_receipt = build_compact_grouping_receipt(
        original_projection,
        inputs=(original,),
        relations=(),
        generated_at=NOW,
        source_registry_version=SOURCE_REGISTRY_DIGEST,
    )
    changed_receipt = build_compact_grouping_receipt(
        changed_projection,
        inputs=(changed,),
        relations=(),
        generated_at=NOW,
        source_registry_version=SOURCE_REGISTRY_DIGEST,
    )
    assert original_receipt.input_digest != changed_receipt.input_digest


def _random_universe(seed: int) -> tuple[GroupingInput, ...]:
    rng = random.Random(seed)
    roots = (
        "alpha beta gamma delta",
        "alpha beta gamma delta epsilon",
        "omega sigma theta lambda",
        "package runtime release stable",
        "model checkpoint release public",
    )
    urls = (
        None,
        "https://shared.example/a",
        "https://shared.example/b",
        "https://catalog.example/common",
    )
    values: list[GroupingInput] = []
    for index in range(8):
        base = rng.choice(roots)
        title = base if rng.random() < 0.75 else f"{base} variant{index}"
        role = ("ATTENTION",) if rng.random() < 0.2 else ()
        kind = "ARTIFACT" if rng.random() < 0.2 else "DOCUMENT"
        artifact_name = "Atlas Runtime Package" if kind == "ARTIFACT" else None
        artifact_version = rng.choice(("1.0", "2.0", "3.0")) if kind == "ARTIFACT" else None
        values.append(
            _obs(
                seed * 100 + index + 6000,
                title=title,
                canonical_url=rng.choice(urls),
                observed_at=NOW + timedelta(minutes=rng.randrange(0, 240)),
                source_id=rng.choice(("fixture.one", "fixture.two", "hn.frontpage")),
                source_item_key=f"{seed}:{index}:{rng.randrange(3)}",
                kind=kind,
                artifact_name=artifact_name,
                artifact_version=artifact_version,
                signal_roles=role,
            )
        )
    return tuple(values)


@pytest.mark.parametrize("seed", range(50))
def test_randomized_bounded_pair_and_partition_equivalence(seed: int) -> None:
    inputs = _random_universe(seed)
    as_of = NOW + timedelta(hours=6)

    for left, right in combinations(inputs, 2):
        reference = assess_pair(left, right).decision is GroupingDecision.GROUP
        assert is_group_pair_v1(left, right) is reference

    assert _v1_partition(inputs, as_of=as_of) == _v0_partition(inputs, as_of=as_of)
