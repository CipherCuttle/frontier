from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Iterable

from .canonical_json import CanonicalValue
from .grouping import (
    GroupingDecision,
    GroupingInput,
    PairAssessment,
    assess_pair,
    grouping_jaccard,
    grouping_token_sequence,
    grouping_tokens,
    normalize_grouping_text,
    semantic_text,
)

SIMHASH_GROUP_DISTANCE = 8
SIMHASH_NO_GROUP_DISTANCE = 24
MINHASH_SIZE = 32
MINHASH_GROUP = 0.75
MINHASH_NO_GROUP = 0.25
TFIDF_GROUP = 0.82
TFIDF_NO_GROUP = 0.20
TOKEN_GROUP = 0.80
TOKEN_NO_GROUP = 0.20


class CandidateStrategy(StrEnum):
    CANONICAL_URL = "canonical-url-v0"
    EXACT_TEXT = "exact-text-v0"
    NORMALIZED_TITLE = "normalized-title-v0"
    TOKEN_JACCARD = "token-jaccard-v0"
    SIMHASH = "simhash-v0"
    MINHASH = "minhash-v0"
    TFIDF = "tfidf-v0"
    GUARDED_HYBRID = "guarded-hybrid-v0"


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    strategy: CandidateStrategy
    true_group: int
    false_group: int
    false_split: int
    ambiguous: int
    pair_precision: str
    group_recall: str

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "ambiguous": self.ambiguous,
            "false_group": self.false_group,
            "false_split": self.false_split,
            "group_recall": self.group_recall,
            "pair_precision": self.pair_precision,
            "strategy": self.strategy.value,
            "true_group": self.true_group,
        }


def _stable_hash(value: str) -> int:
    return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big")


def _simhash(value: str) -> int:
    token_list = grouping_token_sequence(value)
    if not token_list:
        return 0
    weights = [0] * 64
    for token in token_list:
        digest = _stable_hash(token)
        for bit in range(64):
            weights[bit] += 1 if digest & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            result |= 1 << bit
    return result


def _minhash_signature(value: str) -> tuple[int, ...]:
    token_set = grouping_tokens(value)
    if not token_set:
        return ()
    signature: list[int] = []
    for seed in range(MINHASH_SIZE):
        signature.append(min(_stable_hash(f"{seed}:{token}") for token in token_set))
    return tuple(signature)


def _minhash_similarity(left: str, right: str) -> float:
    left_sig = _minhash_signature(left)
    right_sig = _minhash_signature(right)
    if not left_sig or not right_sig:
        return 0.0
    equal = sum(
        left_value == right_value
        for left_value, right_value in zip(left_sig, right_sig, strict=True)
    )
    return equal / len(left_sig)


def _tfidf_vectors(items: Iterable[GroupingInput]) -> dict[str, dict[str, float]]:
    material = tuple(items)
    documents = {
        item.observation_id: list(grouping_token_sequence(semantic_text(item)))
        for item in material
    }
    document_frequency: dict[str, int] = {}
    for document in documents.values():
        for token in set(document):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    count = max(len(documents), 1)
    vectors: dict[str, dict[str, float]] = {}
    for observation_id, document in documents.items():
        frequency: dict[str, int] = {}
        for token in document:
            frequency[token] = frequency.get(token, 0) + 1
        vectors[observation_id] = {
            token: occurrences
            * (math.log((count + 1) / (document_frequency[token] + 1)) + 1.0)
            for token, occurrences in frequency.items()
        }
    return vectors


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def assess_candidate_pair(
    left: GroupingInput,
    right: GroupingInput,
    *,
    strategy: CandidateStrategy,
    tfidf_vectors: dict[str, dict[str, float]] | None = None,
) -> PairAssessment:
    if strategy is CandidateStrategy.GUARDED_HYBRID:
        return assess_pair(left, right)

    left_id = min(left.observation_id, right.observation_id)
    right_id = max(left.observation_id, right.observation_id)
    same_url = bool(left.canonical_url and left.canonical_url == right.canonical_url)
    left_title = normalize_grouping_text(left.title or left.artifact_name)
    right_title = normalize_grouping_text(right.title or right.artifact_name)
    exact_text = bool(semantic_text(left) and semantic_text(left) == semantic_text(right))

    if strategy is CandidateStrategy.CANONICAL_URL:
        decision = GroupingDecision.GROUP if same_url else GroupingDecision.AMBIGUOUS
        return PairAssessment(left_id, right_id, decision, ("same-url",) if same_url else ())

    if strategy is CandidateStrategy.EXACT_TEXT:
        decision = GroupingDecision.GROUP if exact_text else GroupingDecision.AMBIGUOUS
        return PairAssessment(left_id, right_id, decision, ("exact-text",) if exact_text else ())

    if strategy is CandidateStrategy.NORMALIZED_TITLE:
        title_equal = bool(left_title and left_title == right_title)
        decision = GroupingDecision.GROUP if title_equal else GroupingDecision.AMBIGUOUS
        return PairAssessment(
            left_id, right_id, decision, ("normalized-title",) if title_equal else ()
        )

    if strategy is CandidateStrategy.TOKEN_JACCARD:
        similarity = grouping_jaccard(grouping_tokens(left_title), grouping_tokens(right_title))
        if similarity >= TOKEN_GROUP:
            decision = GroupingDecision.GROUP
        elif similarity <= TOKEN_NO_GROUP:
            decision = GroupingDecision.NO_GROUP
        else:
            decision = GroupingDecision.AMBIGUOUS
        return PairAssessment(left_id, right_id, decision, (f"title-jaccard:{similarity:.3f}",))

    if strategy is CandidateStrategy.SIMHASH:
        left_text = semantic_text(left)
        right_text = semantic_text(right)
        distance = (_simhash(left_text) ^ _simhash(right_text)).bit_count()
        if left_text and right_text and distance <= SIMHASH_GROUP_DISTANCE:
            decision = GroupingDecision.GROUP
        elif not left_text or not right_text or distance < SIMHASH_NO_GROUP_DISTANCE:
            decision = GroupingDecision.AMBIGUOUS
        else:
            decision = GroupingDecision.NO_GROUP
        return PairAssessment(left_id, right_id, decision, (f"simhash-distance:{distance}",))

    if strategy is CandidateStrategy.MINHASH:
        similarity = _minhash_similarity(semantic_text(left), semantic_text(right))
        if similarity >= MINHASH_GROUP:
            decision = GroupingDecision.GROUP
        elif similarity <= MINHASH_NO_GROUP:
            decision = GroupingDecision.NO_GROUP
        else:
            decision = GroupingDecision.AMBIGUOUS
        return PairAssessment(left_id, right_id, decision, (f"minhash:{similarity:.3f}",))

    if tfidf_vectors is None:
        raise ValueError("TF-IDF strategy requires corpus vectors")
    similarity = _cosine(
        tfidf_vectors.get(left.observation_id, {}),
        tfidf_vectors.get(right.observation_id, {}),
    )
    if similarity >= TFIDF_GROUP:
        decision = GroupingDecision.GROUP
    elif similarity <= TFIDF_NO_GROUP:
        decision = GroupingDecision.NO_GROUP
    else:
        decision = GroupingDecision.AMBIGUOUS
    return PairAssessment(left_id, right_id, decision, (f"tfidf:{similarity:.3f}",))


def evaluate_strategy(
    cases: Iterable[tuple[GroupingInput, GroupingInput, GroupingDecision]],
    *,
    strategy: CandidateStrategy,
) -> EvaluationMetrics:
    material = tuple(cases)
    corpus_items: dict[str, GroupingInput] = {}
    for left, right, _ in material:
        corpus_items[left.observation_id] = left
        corpus_items[right.observation_id] = right
    vectors = _tfidf_vectors(corpus_items.values()) if strategy is CandidateStrategy.TFIDF else None

    true_group = 0
    false_group = 0
    false_split = 0
    ambiguous = 0
    expected_group_count = 0
    for left, right, expected in material:
        if expected is GroupingDecision.GROUP:
            expected_group_count += 1
        actual = assess_candidate_pair(
            left, right, strategy=strategy, tfidf_vectors=vectors
        ).decision
        if actual is GroupingDecision.AMBIGUOUS:
            ambiguous += 1
        if actual is GroupingDecision.GROUP and expected is GroupingDecision.GROUP:
            true_group += 1
        elif actual is GroupingDecision.GROUP and expected is not GroupingDecision.GROUP:
            false_group += 1
        elif actual is GroupingDecision.NO_GROUP and expected is GroupingDecision.GROUP:
            false_split += 1

    predicted_group_count = true_group + false_group
    precision = true_group / predicted_group_count if predicted_group_count else 1.0
    recall = true_group / expected_group_count if expected_group_count else 1.0
    return EvaluationMetrics(
        strategy=strategy,
        true_group=true_group,
        false_group=false_group,
        false_split=false_split,
        ambiguous=ambiguous,
        pair_precision=f"{precision:.6f}",
        group_recall=f"{recall:.6f}",
    )
