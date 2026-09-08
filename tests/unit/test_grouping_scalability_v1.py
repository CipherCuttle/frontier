from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_grouping_baseline import corpus_cases

import frontier.domain.grouping_v1 as grouping_v1
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

NOW = datetime(2026, 9, 8, 20, tzinfo=UTC)
SOURCE_REGISTRY_DIGEST = Digest(
    "sha256:0e3dcd047379e500900194ed2ff47aa980a4a61172c33a7fb7b9e2f5930b696e"
)
FROZEN_CORPUS_BLOB = "909586dc99fe3c84ccf02f09aebe6f5ea2224b6a"
BOUNDED_ORACLE_CASE_COUNT = 2047
BOUNDED_ORACLE_PARTITION_SHA256 = (
    "2184f17bfcdd1a0c6ed8df824078a55eb585b47651d493cfca61b056cde4a3ea"
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


def _oracle_obs(
    index: int,
    *,
    title: str | None,
    url: str,
    observed_at: datetime | None = None,
    source_id: str = "fixture.source",
    source_item_key: str | None = None,
    kind: str = "DOCUMENT",
    artifact_name: str | None = None,
    artifact_version: str | None = None,
    signal_roles: tuple[str, ...] = (),
) -> GroupingInput:
    return GroupingInput(
        observation_id=f"obs_{index:064x}",
        source_id=source_id,
        source_item_key=source_item_key or f"item-{index}",
        kind=kind,
        observed_at=observed_at or NOW,
        canonical_url=url,
        title=title,
        text=None,
        artifact_name=artifact_name,
        artifact_version=artifact_version,
        signal_roles=signal_roles,
    )


def _bounded_oracle_basis() -> tuple[GroupingInput, ...]:
    return (
        _oracle_obs(
            1,
            title="Atlas runtime launches for local agents",
            url="https://alpha.example/atlas",
        ),
        _oracle_obs(
            2,
            title="Atlas runtime launches for local agents",
            url="https://shared.example/atlas",
            source_id="hn.frontpage",
            signal_roles=("ATTENTION",),
        ),
        _oracle_obs(
            3,
            title="Different discussion headline entirely",
            url="https://shared.example/atlas",
            source_id="hn.frontpage",
            signal_roles=("ATTENTION",),
        ),
        _oracle_obs(4, title="alpha beta gamma delta", url="https://jaccard.example/a"),
        _oracle_obs(
            5,
            title="alpha beta gamma delta epsilon",
            url="https://jaccard.example/b",
        ),
        _oracle_obs(
            6,
            title=None,
            url="https://artifact.example/v1",
            kind="ARTIFACT",
            artifact_name="Atlas Runtime Package",
            artifact_version="1.0",
        ),
        _oracle_obs(
            7,
            title=None,
            url="https://artifact.example/v2",
            kind="ARTIFACT",
            artifact_name="Atlas Runtime Package",
            artifact_version="2.0",
        ),
        _oracle_obs(8, title="Alpha: beta gamma", url="https://punct.example/shared"),
        _oracle_obs(9, title="Alpha beta gamma", url="https://punct.example/shared"),
        _oracle_obs(
            10,
            title="Far window stable release",
            url="https://far.example/shared",
            observed_at=NOW - timedelta(days=31),
        ),
        _oracle_obs(11, title="Far window stable release", url="https://far.example/shared"),
    )


def _partition_json(partition: tuple[tuple[str, ...], ...]) -> list[list[str]]:
    return [list(members) for members in partition]


def test_immutable_v0_oracle_artifacts_are_exactly_pinned() -> None:
    assert (
        _git_blob_sha(Path("fixtures/grouping/oracle_guarded_hybrid_v0.txt"))
        == GROUPING_V1_ORACLE_BLOB
    )
    assert _git_blob_sha(Path("fixtures/grouping/corpus_v0.json")) == FROZEN_CORPUS_BLOB


@pytest.mark.parametrize(("left", "right", "_expected"), corpus_cases())
def test_fast_group_predicate_matches_frozen_v0_pair_corpus(
    left: GroupingInput,
    right: GroupingInput,
    _expected: GroupingDecision,
) -> None:
    reference = assess_pair(left, right).decision
    assert is_group_pair_v1(left, right) is (reference is GroupingDecision.GROUP)
    assert assess_pair_v1(left, right).decision is reference


@pytest.mark.parametrize(("left", "right", "_expected"), corpus_cases())
def test_two_item_membership_matches_frozen_v0_pair_corpus(
    left: GroupingInput,
    right: GroupingInput,
    _expected: GroupingDecision,
) -> None:
    as_of = max(left.observed_at, right.observed_at) + timedelta(seconds=1)
    reference = assess_pair(left, right).decision
    if reference is GroupingDecision.GROUP:
        expected_partition = (tuple(sorted((left.observation_id, right.observation_id))),)
    else:
        expected_partition = tuple(sorted(((left.observation_id,), (right.observation_id,))))
    assert _v1_partition((left, right), as_of=as_of) == expected_partition


def test_exhaustive_bounded_membership_matches_pinned_v0_artifact_digest() -> None:
    basis = _bounded_oracle_basis()
    records: list[dict[str, object]] = []
    for mask in range(1, 1 << len(basis)):
        inputs = tuple(item for index, item in enumerate(basis) if mask & (1 << index))
        records.append(
            {
                "mask": mask,
                "partition": _partition_json(_v1_partition(inputs, as_of=NOW)),
            }
        )

    assert len(records) == BOUNDED_ORACLE_CASE_COUNT
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == BOUNDED_ORACLE_PARTITION_SHA256


def test_exact_jaccard_threshold_pair_is_not_omitted() -> None:
    left = _obs(1, title="alpha beta gamma delta")
    right = _obs(2, title="alpha beta gamma delta epsilon")
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


def test_explicit_self_relation_is_excluded_from_v0_pair_diagnostics() -> None:
    item = _obs(12, title="self relation must remain a singleton")
    relation = GroupingRelationInput(
        relation_type="CORRECTS",
        from_observation_id=item.observation_id,
        target_observation_id=item.observation_id,
        authority="EXPLICIT",
        created_at=NOW,
    )
    reference = build_grouping_projection((item,), relations=(relation,), as_of=NOW)
    projection = build_compact_grouping_projection((item,), relations=(relation,), as_of=NOW)

    assert projection.candidate_pair_count == 0
    assert projection.group_pair_count == 0
    assert _partition(projection.groups, projection.ungrouped_observation_ids) == _partition(
        reference.groups,
        reference.ungrouped_observation_ids,
    )
    assert _partition(reference.groups, reference.ungrouped_observation_ids) == (
        (item.observation_id,),
    )


def test_clique_conservative_membership_matches_pinned_false_transitivity_case() -> None:
    first, bridge, ambiguous = _bounded_oracle_basis()[:3]
    expected = tuple(
        sorted(
            (
                tuple(sorted((first.observation_id, bridge.observation_id))),
                (ambiguous.observation_id,),
            )
        )
    )
    assert _v1_partition((first, bridge, ambiguous), as_of=NOW) == expected


def test_candidate_omission_attack_fails_equivalence_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left, right = _bounded_oracle_basis()[3:5]
    expected = (tuple(sorted((left.observation_id, right.observation_id))),)
    monkeypatch.setattr(
        grouping_v1._CandidateIndex,
        "candidate_right_ids",
        lambda _self, _left: (),
    )
    with pytest.raises(AssertionError):
        assert _v1_partition((left, right), as_of=NOW) == expected


def test_false_group_injection_attack_fails_equivalence_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left, right = _bounded_oracle_basis()[7:9]
    expected = tuple(sorted(((left.observation_id,), (right.observation_id,))))
    monkeypatch.setattr(grouping_v1, "_is_group_fast", lambda *_args, **_kwargs: True)
    with pytest.raises(AssertionError):
        assert _v1_partition((left, right), as_of=NOW) == expected


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
