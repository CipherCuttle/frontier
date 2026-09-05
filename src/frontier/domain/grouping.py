from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import combinations
from typing import Iterable

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .receipt import ProjectionReceipt, ProjectionStatus

GROUPING_SCHEMA_VERSION = "grouping-projection-v0"
GROUPING_PROJECTION_NAME = "episode-grouping"
GROUPING_PROJECTION_VERSION = "grouping-baseline-v0"
GROUPING_ALGORITHM_VERSION = "guarded-hybrid-v0"
GROUPING_RECEIPT_SCHEMA_VERSION = "projection-receipt-v1"

TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
SPACE_RE = re.compile(r"\s+")
NEAR_WINDOW = timedelta(hours=72)
FAR_WINDOW = timedelta(days=30)
TITLE_GROUP_JACCARD = 0.80
TITLE_NO_GROUP_JACCARD = 0.20

GROUPING_CONFIGURATION: dict[str, CanonicalValue] = {
    "far_window_seconds": int(FAR_WINDOW.total_seconds()),
    "near_window_seconds": int(NEAR_WINDOW.total_seconds()),
    "title_group_jaccard": "0.80",
    "title_no_group_jaccard": "0.20",
}
GROUPING_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(GROUPING_CONFIGURATION))


class GroupingDecision(StrEnum):
    GROUP = "GROUP"
    NO_GROUP = "NO_GROUP"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class GroupingInput:
    observation_id: str
    source_id: str
    source_item_key: str
    kind: str
    observed_at: datetime
    canonical_url: str | None
    title: str | None
    text: str | None
    artifact_type: str | None = None
    artifact_name: str | None = None
    artifact_version: str | None = None
    signal_roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.startswith("obs_"):
            raise ValueError("grouping input requires canonical observation_id")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "canonical_url": self.canonical_url,
            "kind": self.kind,
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "signal_roles": sorted(self.signal_roles),
            "source_id": self.source_id,
            "source_item_key": self.source_item_key,
            "text": self.text,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class GroupingRelationInput:
    relation_type: str
    from_observation_id: str
    target_observation_id: str
    authority: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("relation created_at must be timezone-aware")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "authority": self.authority,
            "created_at": canonical_timestamp(self.created_at),
            "from_observation_id": self.from_observation_id,
            "relation_type": self.relation_type,
            "target_observation_id": self.target_observation_id,
        }


@dataclass(frozen=True, slots=True)
class PairAssessment:
    left_observation_id: str
    right_observation_id: str
    decision: GroupingDecision
    reasons: tuple[str, ...]

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "decision": self.decision.value,
            "left_observation_id": self.left_observation_id,
            "reasons": list(self.reasons),
            "right_observation_id": self.right_observation_id,
        }


@dataclass(frozen=True, slots=True)
class EpisodeGroup:
    group_id: str
    observation_ids: tuple[str, ...]

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {"group_id": self.group_id, "observation_ids": list(self.observation_ids)}


@dataclass(frozen=True, slots=True)
class GroupingProjection:
    as_of: datetime
    groups: tuple[EpisodeGroup, ...]
    ambiguous_pairs: tuple[PairAssessment, ...]
    ungrouped_observation_ids: tuple[str, ...]
    schema_version: str = GROUPING_SCHEMA_VERSION
    projection_version: str = GROUPING_PROJECTION_VERSION
    algorithm_version: str = GROUPING_ALGORITHM_VERSION

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "algorithm_version": self.algorithm_version,
            "ambiguous_pairs": [pair.to_canonical() for pair in self.ambiguous_pairs],
            "as_of": canonical_timestamp(self.as_of),
            "groups": [group.to_canonical() for group in self.groups],
            "projection_version": self.projection_version,
            "schema_version": self.schema_version,
            "ungrouped_observation_ids": list(self.ungrouped_observation_ids),
        }


def normalize_grouping_text(value: str | None) -> str:
    if value is None:
        return ""
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", value).casefold().strip())


def grouping_token_sequence(value: str | None) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(normalize_grouping_text(value)))


def grouping_tokens(value: str | None) -> frozenset[str]:
    return frozenset(grouping_token_sequence(value))


def grouping_jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def semantic_text(item: GroupingInput) -> str:
    parts = (
        item.title or "",
        item.text or "",
        item.artifact_name or "",
        item.artifact_version or "",
    )
    return normalize_grouping_text(" ".join(part for part in parts if part))


def ordered_pair(left_id: str, right_id: str) -> tuple[str, str]:
    if left_id <= right_id:
        return (left_id, right_id)
    return (right_id, left_id)


def _same_artifact_different_version(left: GroupingInput, right: GroupingInput) -> bool:
    return (
        left.kind == "ARTIFACT"
        and right.kind == "ARTIFACT"
        and left.artifact_name is not None
        and right.artifact_name is not None
        and normalize_grouping_text(left.artifact_name)
        == normalize_grouping_text(right.artifact_name)
        and left.artifact_version is not None
        and right.artifact_version is not None
        and left.artifact_version != right.artifact_version
    )


def _punctuation_sensitive_conflict(left_title: str, right_title: str) -> bool:
    left_tokens = grouping_token_sequence(left_title)
    return (
        left_title != right_title
        and bool(left_tokens)
        and left_tokens == grouping_token_sequence(right_title)
    )


def assess_pair(
    left: GroupingInput,
    right: GroupingInput,
    *,
    explicit_episode_relations: frozenset[tuple[str, str]] = frozenset(),
) -> PairAssessment:
    left_id, right_id = ordered_pair(left.observation_id, right.observation_id)
    if (left_id, right_id) in explicit_episode_relations:
        return PairAssessment(
            left_id, right_id, GroupingDecision.GROUP, ("explicit-correction-retraction",)
        )

    distance = abs(left.observed_at - right.observed_at)
    if _same_artifact_different_version(left, right):
        return PairAssessment(
            left_id, right_id, GroupingDecision.NO_GROUP, ("same-artifact-different-version",)
        )
    if distance > FAR_WINDOW:
        return PairAssessment(left_id, right_id, GroupingDecision.NO_GROUP, ("outside-far-window",))

    same_url = bool(left.canonical_url and left.canonical_url == right.canonical_url)
    left_title = normalize_grouping_text(left.title or left.artifact_name)
    right_title = normalize_grouping_text(right.title or right.artifact_name)
    title_tokens_left = grouping_token_sequence(left_title)
    title_tokens_right = grouping_token_sequence(right_title)
    title_substantive = min(len(title_tokens_left), len(title_tokens_right)) >= 3
    title_equal = bool(left_title and left_title == right_title)
    title_jaccard = grouping_jaccard(frozenset(title_tokens_left), frozenset(title_tokens_right))
    punctuation_conflict = _punctuation_sensitive_conflict(left_title, right_title)
    exact_text = bool(semantic_text(left) and semantic_text(left) == semantic_text(right))

    if same_url:
        both_attention = "ATTENTION" in left.signal_roles and "ATTENTION" in right.signal_roles
        if both_attention:
            return PairAssessment(
                left_id, right_id, GroupingDecision.GROUP, ("same-url", "attention-target")
            )
        if (
            left.source_id == right.source_id
            and left.source_item_key != right.source_item_key
            and title_jaccard <= TITLE_NO_GROUP_JACCARD
        ):
            return PairAssessment(
                left_id,
                right_id,
                GroupingDecision.NO_GROUP,
                ("same-url", "distinct-source-items", "low-title-overlap"),
            )
        if punctuation_conflict:
            return PairAssessment(
                left_id,
                right_id,
                GroupingDecision.AMBIGUOUS,
                ("same-url", "punctuation-sensitive-title-conflict"),
            )
        if exact_text or (title_substantive and title_equal) or (
            title_substantive and title_jaccard >= TITLE_GROUP_JACCARD
        ):
            return PairAssessment(
                left_id, right_id, GroupingDecision.GROUP, ("same-url", "semantic-match")
            )
        return PairAssessment(
            left_id, right_id, GroupingDecision.AMBIGUOUS, ("same-url", "semantic-conflict")
        )

    if punctuation_conflict:
        return PairAssessment(
            left_id,
            right_id,
            GroupingDecision.AMBIGUOUS,
            ("punctuation-sensitive-title-conflict",),
        )
    if exact_text and title_substantive and distance <= NEAR_WINDOW:
        return PairAssessment(
            left_id, right_id, GroupingDecision.GROUP, ("exact-text", "near-time")
        )
    if title_equal and title_substantive and distance <= NEAR_WINDOW:
        return PairAssessment(
            left_id, right_id, GroupingDecision.GROUP, ("normalized-title", "near-time")
        )
    if (
        title_substantive
        and title_jaccard >= TITLE_GROUP_JACCARD
        and distance <= NEAR_WINDOW
    ):
        return PairAssessment(
            left_id, right_id, GroupingDecision.GROUP, ("high-title-overlap", "near-time")
        )
    if title_jaccard <= TITLE_NO_GROUP_JACCARD:
        return PairAssessment(
            left_id,
            right_id,
            GroupingDecision.AMBIGUOUS,
            ("low-title-overlap", "no-negative-evidence"),
        )
    return PairAssessment(
        left_id, right_id, GroupingDecision.AMBIGUOUS, ("insufficient-evidence",)
    )


def _explicit_pairs(
    relations: Iterable[GroupingRelationInput],
    *,
    as_of: datetime,
    allowed_ids: frozenset[str],
) -> frozenset[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for relation in relations:
        if relation.created_at > as_of:
            continue
        if relation.authority != "EXPLICIT":
            continue
        if relation.relation_type not in {"CORRECTS", "RETRACTS"}:
            continue
        if (
            relation.from_observation_id not in allowed_ids
            or relation.target_observation_id not in allowed_ids
        ):
            continue
        pairs.add(ordered_pair(relation.from_observation_id, relation.target_observation_id))
    return frozenset(pairs)


def build_grouping_projection(
    inputs: Iterable[GroupingInput],
    *,
    relations: Iterable[GroupingRelationInput] = (),
    as_of: datetime,
) -> GroupingProjection:
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

    parents = {observation_id: observation_id for observation_id in ids}

    def find(observation_id: str) -> str:
        current = observation_id
        while parents[current] != current:
            parents[current] = parents[parents[current]]
            current = parents[current]
        return current

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        first, second = ordered_pair(left_root, right_root)
        parents[second] = first

    explicit_pairs = _explicit_pairs(relations, as_of=as_of, allowed_ids=frozenset(ids))
    ambiguous: list[PairAssessment] = []
    for left, right in combinations(eligible, 2):
        assessment = assess_pair(
            left, right, explicit_episode_relations=explicit_pairs
        )
        if assessment.decision is GroupingDecision.GROUP:
            union(left.observation_id, right.observation_id)
        elif assessment.decision is GroupingDecision.AMBIGUOUS:
            ambiguous.append(assessment)

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
            "algorithm_version": GROUPING_ALGORITHM_VERSION,
            "observation_ids": list(ordered_ids),
        }
        groups.append(
            EpisodeGroup(
                group_id="grp_" + sha256_hex(canonical_json_bytes(material)),
                observation_ids=ordered_ids,
            )
        )
    groups.sort(key=lambda group: group.group_id)
    ambiguous.sort(key=lambda pair: (pair.left_observation_id, pair.right_observation_id))
    return GroupingProjection(
        as_of=as_of,
        groups=tuple(groups),
        ambiguous_pairs=tuple(ambiguous),
        ungrouped_observation_ids=tuple(sorted(ungrouped)),
    )


def grouping_input_digest(
    inputs: Iterable[GroupingInput],
    relations: Iterable[GroupingRelationInput],
    *,
    as_of: datetime,
) -> Digest:
    input_values = [item.to_canonical() for item in inputs if item.observed_at <= as_of]
    input_values.sort(key=lambda value: str(value["observation_id"]))
    relation_values = [
        relation.to_canonical() for relation in relations if relation.created_at <= as_of
    ]
    relation_values.sort(
        key=lambda value: (
            str(value["from_observation_id"]),
            str(value["target_observation_id"]),
            str(value["relation_type"]),
        )
    )
    return sha256_digest(
        canonical_json_bytes(
            {
                "as_of": canonical_timestamp(as_of),
                "inputs": input_values,
                "relations": relation_values,
            }
        )
    )


def build_grouping_receipt(
    projection: GroupingProjection,
    *,
    inputs: Iterable[GroupingInput],
    relations: Iterable[GroupingRelationInput],
    generated_at: datetime,
    source_registry_version: Digest,
) -> ProjectionReceipt:
    input_values = tuple(inputs)
    relation_values = tuple(relations)
    return ProjectionReceipt(
        receipt_schema_version=GROUPING_RECEIPT_SCHEMA_VERSION,
        projection_name=GROUPING_PROJECTION_NAME,
        projection_version=GROUPING_PROJECTION_VERSION,
        schema_version=GROUPING_SCHEMA_VERSION,
        algorithm_version=GROUPING_ALGORITHM_VERSION,
        ranking_policy_version=None,
        configuration_digest=GROUPING_CONFIGURATION_DIGEST,
        source_registry_version=source_registry_version,
        as_of=projection.as_of,
        generated_at=generated_at,
        input_digest=grouping_input_digest(
            input_values, relation_values, as_of=projection.as_of
        ),
        output_digest=sha256_digest(canonical_json_bytes(projection.to_canonical())),
        status=ProjectionStatus.COMPLETE,
    )
