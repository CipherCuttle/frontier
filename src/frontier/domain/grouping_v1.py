from __future__ import annotations

import hashlib
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .grouping import (
    FAR_WINDOW,
    NEAR_WINDOW,
    TITLE_GROUP_JACCARD,
    TITLE_NO_GROUP_JACCARD,
    EpisodeGroup,
    GroupingInput,
    GroupingRelationInput,
    PairAssessment,
    _explicit_pairs,
    assess_pair,
    grouping_jaccard,
    grouping_token_sequence,
    normalize_grouping_text,
    ordered_pair,
    semantic_text,
)
from .receipt import ProjectionReceipt, ProjectionStatus

GROUPING_V1_SCHEMA_VERSION: Final = "grouping-projection-v1"
GROUPING_V1_PROJECTION_NAME: Final = "episode-grouping"
GROUPING_V1_PROJECTION_VERSION: Final = "grouping-scalable-v1"
GROUPING_V1_ALGORITHM_VERSION: Final = "guarded-hybrid-group-complete-blocking-v1"
GROUPING_V1_RECEIPT_SCHEMA_VERSION: Final = "projection-receipt-v1"
GROUPING_V1_PAIR_SEMANTICS_VERSION: Final = (
    "guarded-hybrid-v0@db206cda7eed92b62c706a10089c2571b4381d66"
)
GROUPING_V1_ORACLE_BLOB: Final = "943affde20b08f500f8dba2716ffedfc428f58e1"
GROUPING_V1_OMITTED_PAIR_SEMANTICS: Final = "OMITTED_PAIRS_HAVE_NO_NEGATIVE_OR_INDEPENDENCE_MEANING"

_JACCARD_NUMERATOR: Final = 4
_JACCARD_DENOMINATOR: Final = 5

GROUPING_V1_CONFIGURATION: dict[str, CanonicalValue] = {
    "candidate_generation": "deterministic-group-complete-blocking-v1",
    "far_window_seconds": int(FAR_WINDOW.total_seconds()),
    "near_window_seconds": int(NEAR_WINDOW.total_seconds()),
    "omitted_pair_semantics": GROUPING_V1_OMITTED_PAIR_SEMANTICS,
    "pair_oracle_blob": GROUPING_V1_ORACLE_BLOB,
    "pair_semantics_version": GROUPING_V1_PAIR_SEMANTICS_VERSION,
    "title_group_jaccard": "0.80",
    "title_no_group_jaccard": "0.20",
}
GROUPING_V1_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(GROUPING_V1_CONFIGURATION))


@dataclass(frozen=True, slots=True)
class CompactGroupingProjection:
    as_of: datetime
    groups: tuple[EpisodeGroup, ...]
    ungrouped_observation_ids: tuple[str, ...]
    eligible_observation_count: int
    candidate_pair_count: int
    group_pair_count: int
    schema_version: str = GROUPING_V1_SCHEMA_VERSION
    projection_version: str = GROUPING_V1_PROJECTION_VERSION
    algorithm_version: str = GROUPING_V1_ALGORITHM_VERSION
    pair_semantics_version: str = GROUPING_V1_PAIR_SEMANTICS_VERSION
    omitted_pair_semantics: str = GROUPING_V1_OMITTED_PAIR_SEMANTICS

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "candidate_pair_count": self.candidate_pair_count,
            "eligible_observation_count": self.eligible_observation_count,
            "group_pair_count": self.group_pair_count,
            "groups": [group.to_canonical() for group in self.groups],
            "omitted_pair_semantics": self.omitted_pair_semantics,
            "pair_semantics_version": self.pair_semantics_version,
            "projection_version": self.projection_version,
            "schema_version": self.schema_version,
            "ungrouped_observation_ids": list(self.ungrouped_observation_ids),
        }


@dataclass(frozen=True, slots=True)
class _PreparedInput:
    item: GroupingInput
    title_normalized: str
    title_tokens: tuple[str, ...]
    title_token_set: frozenset[str]
    title_substantive: bool
    semantic: str
    artifact_name_normalized: str
    signal_roles: frozenset[str]


def _prepare(item: GroupingInput) -> _PreparedInput:
    title_normalized = normalize_grouping_text(item.title or item.artifact_name)
    title_tokens = grouping_token_sequence(title_normalized)
    return _PreparedInput(
        item=item,
        title_normalized=title_normalized,
        title_tokens=title_tokens,
        title_token_set=frozenset(title_tokens),
        title_substantive=len(title_tokens) >= 3,
        semantic=semantic_text(item),
        artifact_name_normalized=normalize_grouping_text(item.artifact_name),
        signal_roles=frozenset(item.signal_roles),
    )


def _same_artifact_different_version(left: _PreparedInput, right: _PreparedInput) -> bool:
    return (
        left.item.kind == "ARTIFACT"
        and right.item.kind == "ARTIFACT"
        and left.item.artifact_name is not None
        and right.item.artifact_name is not None
        and left.artifact_name_normalized == right.artifact_name_normalized
        and left.item.artifact_version is not None
        and right.item.artifact_version is not None
        and left.item.artifact_version != right.item.artifact_version
    )


def _punctuation_sensitive_conflict(left: _PreparedInput, right: _PreparedInput) -> bool:
    return (
        left.title_normalized != right.title_normalized
        and bool(left.title_tokens)
        and left.title_tokens == right.title_tokens
    )


def _is_group_fast(
    left: _PreparedInput,
    right: _PreparedInput,
    *,
    explicit_episode_relations: frozenset[tuple[str, str]],
) -> bool:
    pair = ordered_pair(left.item.observation_id, right.item.observation_id)
    if pair in explicit_episode_relations:
        return True

    distance = abs(left.item.observed_at - right.item.observed_at)
    if _same_artifact_different_version(left, right) or distance > FAR_WINDOW:
        return False

    same_url = bool(left.item.canonical_url and left.item.canonical_url == right.item.canonical_url)
    title_jaccard = grouping_jaccard(left.title_token_set, right.title_token_set)
    title_substantive = left.title_substantive and right.title_substantive
    title_equal = bool(left.title_normalized and left.title_normalized == right.title_normalized)
    punctuation_conflict = _punctuation_sensitive_conflict(left, right)
    exact_text = bool(left.semantic and left.semantic == right.semantic)

    if same_url:
        if "ATTENTION" in left.signal_roles and "ATTENTION" in right.signal_roles:
            return True
        if (
            left.item.source_id == right.item.source_id
            and left.item.source_item_key != right.item.source_item_key
            and title_jaccard <= TITLE_NO_GROUP_JACCARD
        ):
            return False
        if punctuation_conflict:
            return False
        return bool(
            exact_text
            or (title_substantive and title_equal)
            or (title_substantive and title_jaccard >= TITLE_GROUP_JACCARD)
        )

    if punctuation_conflict:
        return False
    if distance > NEAR_WINDOW:
        return False
    return bool(
        (exact_text and title_substantive)
        or (title_equal and title_substantive)
        or (title_substantive and title_jaccard >= TITLE_GROUP_JACCARD)
    )


def is_group_pair_v1(
    left: GroupingInput,
    right: GroupingInput,
    *,
    explicit_episode_relations: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """Hot-path GROUP predicate; equivalence to the frozen oracle is mandatory."""
    return _is_group_fast(
        _prepare(left),
        _prepare(right),
        explicit_episode_relations=explicit_episode_relations,
    )


def assess_pair_v1(
    left: GroupingInput,
    right: GroupingInput,
    *,
    explicit_episode_relations: frozenset[tuple[str, str]] = frozenset(),
) -> PairAssessment:
    """Diagnostic pair path: delegate directly to the frozen V0 pair semantics."""
    return assess_pair(
        left,
        right,
        explicit_episode_relations=explicit_episode_relations,
    )


def _ceil_ratio(value: int, numerator: int, denominator: int) -> int:
    return (value * numerator + denominator - 1) // denominator


def _jaccard_prefix_length(token_count: int) -> int:
    if token_count <= 0:
        return 0
    required_overlap = _ceil_ratio(
        token_count,
        _JACCARD_NUMERATOR,
        _JACCARD_DENOMINATOR,
    )
    return token_count - required_overlap + 1


def _jaccard_prefix(
    token_set: frozenset[str],
    token_frequency: Counter[str],
) -> tuple[str, ...]:
    ordered = sorted(token_set, key=lambda token: (token_frequency[token], token))
    return tuple(ordered[: _jaccard_prefix_length(len(ordered))])


def _jaccard_length_bounds(token_count: int) -> tuple[int, int]:
    lower = _ceil_ratio(token_count, _JACCARD_NUMERATOR, _JACCARD_DENOMINATOR)
    upper = token_count * _JACCARD_DENOMINATOR // _JACCARD_NUMERATOR
    return lower, upper


_TimeBucket = list[tuple[datetime, str]]


def _ids_within_window(
    bucket: _TimeBucket,
    *,
    center: datetime,
    window: timedelta,
) -> Iterator[str]:
    lower = bisect_left(bucket, (center - window, ""))
    upper = bisect_right(bucket, (center + window, "\U0010ffff"))
    for index in range(lower, upper):
        yield bucket[index][1]


@dataclass(slots=True)
class _CandidateIndex:
    by_id: dict[str, _PreparedInput]
    explicit_by_left: dict[str, tuple[str, ...]]
    same_url: dict[str, _TimeBucket]
    semantic: dict[str, _TimeBucket]
    title_equal: dict[str, _TimeBucket]
    jaccard_prefix_by_id: dict[str, tuple[str, ...]]
    jaccard_postings: dict[str, dict[int, tuple[str, ...]]]

    @classmethod
    def build(
        cls,
        prepared: tuple[_PreparedInput, ...],
        *,
        explicit_pairs: frozenset[tuple[str, str]],
    ) -> _CandidateIndex:
        by_id = {value.item.observation_id: value for value in prepared}

        explicit_lists: dict[str, list[str]] = defaultdict(list)
        for left_id, right_id in sorted(explicit_pairs):
            explicit_lists[left_id].append(right_id)

        same_url: dict[str, _TimeBucket] = defaultdict(list)
        semantic: dict[str, _TimeBucket] = defaultdict(list)
        title_equal: dict[str, _TimeBucket] = defaultdict(list)
        token_frequency: Counter[str] = Counter()

        for value in prepared:
            item = value.item
            if item.canonical_url:
                same_url[item.canonical_url].append((item.observed_at, item.observation_id))
            if value.title_substantive and value.semantic:
                semantic[value.semantic].append((item.observed_at, item.observation_id))
            if value.title_substantive and value.title_normalized:
                title_equal[value.title_normalized].append((item.observed_at, item.observation_id))
                token_frequency.update(value.title_token_set)

        for buckets in (same_url, semantic, title_equal):
            for values in buckets.values():
                values.sort()

        jaccard_prefix_by_id: dict[str, tuple[str, ...]] = {}
        mutable_postings: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
        for value in prepared:
            if not value.title_substantive:
                continue
            prefix = _jaccard_prefix(value.title_token_set, token_frequency)
            jaccard_prefix_by_id[value.item.observation_id] = prefix
            token_count = len(value.title_token_set)
            for token in prefix:
                mutable_postings[token][token_count].append(value.item.observation_id)

        jaccard_postings: dict[str, dict[int, tuple[str, ...]]] = {}
        for token, by_length in mutable_postings.items():
            jaccard_postings[token] = {
                length: tuple(sorted(ids)) for length, ids in by_length.items()
            }

        return cls(
            by_id=by_id,
            explicit_by_left={
                left_id: tuple(sorted(right_ids)) for left_id, right_ids in explicit_lists.items()
            },
            same_url=dict(same_url),
            semantic=dict(semantic),
            title_equal=dict(title_equal),
            jaccard_prefix_by_id=jaccard_prefix_by_id,
            jaccard_postings=jaccard_postings,
        )

    def candidate_right_ids(self, left: _PreparedInput) -> tuple[str, ...]:
        left_id = left.item.observation_id
        candidates: set[str] = set(self.explicit_by_left.get(left_id, ()))

        if left.item.canonical_url:
            bucket = self.same_url.get(left.item.canonical_url, [])
            for candidate_id in _ids_within_window(
                bucket,
                center=left.item.observed_at,
                window=FAR_WINDOW,
            ):
                if candidate_id > left_id:
                    candidates.add(candidate_id)

        if left.title_substantive and left.semantic:
            bucket = self.semantic.get(left.semantic, [])
            for candidate_id in _ids_within_window(
                bucket,
                center=left.item.observed_at,
                window=NEAR_WINDOW,
            ):
                if candidate_id > left_id:
                    candidates.add(candidate_id)

        if left.title_substantive and left.title_normalized:
            bucket = self.title_equal.get(left.title_normalized, [])
            for candidate_id in _ids_within_window(
                bucket,
                center=left.item.observed_at,
                window=NEAR_WINDOW,
            ):
                if candidate_id > left_id:
                    candidates.add(candidate_id)

        prefix = self.jaccard_prefix_by_id.get(left_id, ())
        if prefix:
            lower_length, upper_length = _jaccard_length_bounds(len(left.title_token_set))
            for token in prefix:
                by_length = self.jaccard_postings.get(token, {})
                for token_count in range(lower_length, upper_length + 1):
                    for candidate_id in by_length.get(token_count, ()):
                        if candidate_id <= left_id:
                            continue
                        candidate = self.by_id[candidate_id]
                        if abs(left.item.observed_at - candidate.item.observed_at) <= NEAR_WINDOW:
                            candidates.add(candidate_id)

        return tuple(sorted(candidates))


def _eligible_inputs(
    inputs: Iterable[GroupingInput],
    *,
    as_of: datetime,
) -> tuple[GroupingInput, ...]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    eligible = tuple(
        sorted(
            (item for item in inputs if item.observed_at <= as_of),
            key=lambda item: item.observation_id,
        )
    )
    ids = tuple(item.observation_id for item in eligible)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate observation_id in grouping inputs")
    return eligible


def build_compact_grouping_projection(
    inputs: Iterable[GroupingInput],
    *,
    relations: Iterable[GroupingRelationInput] = (),
    as_of: datetime,
) -> CompactGroupingProjection:
    eligible = _eligible_inputs(inputs, as_of=as_of)
    relation_values = tuple(relations)
    ids = tuple(item.observation_id for item in eligible)
    explicit_pairs = _explicit_pairs(
        relation_values,
        as_of=as_of,
        allowed_ids=frozenset(ids),
    )
    prepared = tuple(_prepare(item) for item in eligible)
    index = _CandidateIndex.build(prepared, explicit_pairs=explicit_pairs)

    parents = {observation_id: observation_id for observation_id in ids}
    component_members = {observation_id: {observation_id} for observation_id in ids}

    def find(observation_id: str) -> str:
        current = observation_id
        while parents[current] != current:
            parents[current] = parents[parents[current]]
            current = parents[current]
        return current

    def union_if_pairwise_group(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        left_members = component_members[left_root]
        right_members = component_members[right_root]
        for left_member in left_members:
            prepared_left = index.by_id[left_member]
            for right_member in right_members:
                if not _is_group_fast(
                    prepared_left,
                    index.by_id[right_member],
                    explicit_episode_relations=explicit_pairs,
                ):
                    return
        first, second = ordered_pair(left_root, right_root)
        merged_members = left_members | right_members
        parents[second] = first
        component_members[first] = merged_members
        del component_members[second]

    candidate_pair_count = 0
    group_pair_count = 0
    for left in prepared:
        left_id = left.item.observation_id
        for right_id in index.candidate_right_ids(left):
            candidate_pair_count += 1
            right = index.by_id[right_id]
            if not _is_group_fast(
                left,
                right,
                explicit_episode_relations=explicit_pairs,
            ):
                continue
            group_pair_count += 1
            union_if_pairwise_group(left_id, right_id)

    members: dict[str, list[str]] = {}
    for observation_id in ids:
        members.setdefault(find(observation_id), []).append(observation_id)

    groups: list[EpisodeGroup] = []
    ungrouped: list[str] = []
    for member_ids in members.values():
        ordered_ids = tuple(sorted(member_ids))
        if len(ordered_ids) == 1:
            ungrouped.append(ordered_ids[0])
            continue
        material = {
            "algorithm_version": GROUPING_V1_ALGORITHM_VERSION,
            "observation_ids": list(ordered_ids),
        }
        groups.append(
            EpisodeGroup(
                group_id="grp_" + sha256_hex(canonical_json_bytes(material)),
                observation_ids=ordered_ids,
            )
        )

    groups.sort(key=lambda group: group.group_id)
    return CompactGroupingProjection(
        as_of=as_of,
        groups=tuple(groups),
        ungrouped_observation_ids=tuple(sorted(ungrouped)),
        eligible_observation_count=len(eligible),
        candidate_pair_count=candidate_pair_count,
        group_pair_count=group_pair_count,
    )


class _HashLike(Protocol):
    def update(self, data: bytes, /) -> None: ...


def _update_length_prefixed(hasher: _HashLike, marker: bytes, payload: bytes) -> None:
    hasher.update(marker)
    hasher.update(len(payload).to_bytes(8, byteorder="big", signed=False))
    hasher.update(payload)


def grouping_v1_input_digest(
    inputs: Iterable[GroupingInput],
    relations: Iterable[GroupingRelationInput],
    *,
    as_of: datetime,
) -> Digest:
    eligible = _eligible_inputs(inputs, as_of=as_of)
    allowed_ids = frozenset(item.observation_id for item in eligible)
    eligible_relations = tuple(
        sorted(
            (
                relation
                for relation in relations
                if relation.created_at <= as_of
                and relation.authority == "EXPLICIT"
                and relation.relation_type in {"CORRECTS", "RETRACTS"}
                and relation.from_observation_id in allowed_ids
                and relation.target_observation_id in allowed_ids
            ),
            key=lambda relation: (
                relation.from_observation_id,
                relation.target_observation_id,
                relation.relation_type,
                relation.authority,
                relation.created_at,
            ),
        )
    )

    hasher = hashlib.sha256()
    header = canonical_json_bytes(
        {
            "as_of": canonical_timestamp(as_of),
            "digest_schema": "grouping-input-stream-v1",
            "pair_semantics_version": GROUPING_V1_PAIR_SEMANTICS_VERSION,
        }
    )
    _update_length_prefixed(hasher, b"H", header)
    for item in eligible:
        _update_length_prefixed(hasher, b"I", canonical_json_bytes(item.to_canonical()))
    for relation in eligible_relations:
        _update_length_prefixed(
            hasher,
            b"R",
            canonical_json_bytes(relation.to_canonical()),
        )
    return Digest("sha256:" + hasher.hexdigest())


def build_compact_grouping_receipt(
    projection: CompactGroupingProjection,
    *,
    inputs: Iterable[GroupingInput],
    relations: Iterable[GroupingRelationInput],
    generated_at: datetime,
    source_registry_version: Digest,
) -> ProjectionReceipt:
    return ProjectionReceipt(
        receipt_schema_version=GROUPING_V1_RECEIPT_SCHEMA_VERSION,
        projection_name=GROUPING_V1_PROJECTION_NAME,
        projection_version=GROUPING_V1_PROJECTION_VERSION,
        schema_version=GROUPING_V1_SCHEMA_VERSION,
        algorithm_version=GROUPING_V1_ALGORITHM_VERSION,
        ranking_policy_version=None,
        configuration_digest=GROUPING_V1_CONFIGURATION_DIGEST,
        source_registry_version=source_registry_version,
        as_of=projection.as_of,
        generated_at=generated_at,
        input_digest=grouping_v1_input_digest(
            inputs,
            relations,
            as_of=projection.as_of,
        ),
        output_digest=sha256_digest(canonical_json_bytes(projection.to_canonical())),
        status=ProjectionStatus.COMPLETE,
    )
