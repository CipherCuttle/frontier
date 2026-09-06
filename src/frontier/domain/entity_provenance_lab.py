"""Offline, non-authoritative ENTITY_PROVENANCE_LAB_V0 candidates."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

LAB_SCHEMA_VERSION: Final = "entity-provenance-lab-result-v0"
LAB_AUTHORITY_STATE: Final = "EXPERIMENTAL_LAB_ONLY"
CORPUS_SCHEMA_VERSION: Final = "frontier-entity-provenance-corpus-v0"

ENTITY_CANDIDATES: Final = (
    "explicit-native-id-v0",
    "canonical-entity-target-v0",
    "artifact-coordinate-v0",
    "transparent-entity-hybrid-v0",
)
PROVENANCE_CANDIDATES: Final = (
    "explicit-reference-v0",
    "exact-content-common-upstream-v0",
    "transparent-provenance-hybrid-v0",
)
_DIRECT: Final = frozenset({"COPY_OF", "REVISION_OF", "FORK_OF"})
_ALIASES: Final = frozenset({"ALIAS_OF", "RENAMED_FROM"})
_COORDINATES: Final = frozenset({"pypi", "cve", "doi", "publisher_item"})
_SPACE: Final = re.compile(r"\s+")
_TOKEN: Final = re.compile(r"[^\W_]+", flags=re.UNICODE)


class EntityDecision(StrEnum):
    SAME_ENTITY = "SAME_ENTITY"
    DIFFERENT_ENTITY = "DIFFERENT_ENTITY"
    AMBIGUOUS = "AMBIGUOUS"


class ProvenanceDecision(StrEnum):
    DIRECT_DERIVATIVE = "DIRECT_DERIVATIVE"
    SHARED_UPSTREAM_POSSIBLE = "SHARED_UPSTREAM_POSSIBLE"
    NO_LINK_EVIDENCE = "NO_LINK_EVIDENCE"


@dataclass(frozen=True, slots=True)
class LabRelation:
    relation_type: str
    target_external_ref: str
    authority: str
    created_at: datetime | None = None

    def eligible_at(self, as_of: datetime) -> bool:
        _aware(as_of, "as_of")
        return self.created_at is None or self.created_at <= as_of


@dataclass(frozen=True, slots=True)
class LabObservation:
    source_id: str
    source_item_key: str
    observed_at: datetime
    canonical_url: str | None
    entity_type: str
    entity_name: str
    native_ids: tuple[str, ...] = ()
    title: str | None = None
    text: str | None = None
    artifact_version: str | None = None
    relations: tuple[LabRelation, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        if not self.source_id or not self.source_item_key or not self.entity_type or not self.entity_name:
            raise ValueError("lab observation identity fields must be non-empty")
        for value in self.native_ids:
            _native_parts(value)


@dataclass(frozen=True, slots=True)
class LabCase:
    case_id: str
    category: str
    as_of: datetime
    left: LabObservation
    right: LabObservation
    expected_entity: EntityDecision
    expected_provenance: ProvenanceDecision
    rationale: str

    def __post_init__(self) -> None:
        _aware(self.as_of, "case as_of")
        if max(self.left.observed_at, self.right.observed_at) > self.as_of:
            raise ValueError("fixture observation leaks beyond case as_of")


@dataclass(frozen=True, slots=True)
class Assessment:
    candidate_version: str
    decision: EntityDecision | ProvenanceDecision
    reasons: tuple[str, ...]
    interpretation: str | None = None

    def to_canonical(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "authority_state": LAB_AUTHORITY_STATE,
            "candidate_version": self.candidate_version,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "schema_version": LAB_SCHEMA_VERSION,
        }
        if self.interpretation is not None:
            value["interpretation"] = self.interpretation
        return value


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    candidate_version: str
    total_cases: int
    exact_matches: int
    positive_expected: int
    positive_predictions: int
    true_positives: int
    false_positives: int
    positive_precision: str | None
    positive_recall: str
    ambiguous_forced_negative: int = 0
    expected_no_link_preserved: int = 0

    def to_canonical(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in (
                "candidate_version", "total_cases", "exact_matches",
                "positive_expected", "positive_predictions", "true_positives",
                "false_positives", "positive_precision", "positive_recall",
                "ambiguous_forced_negative", "expected_no_link_preserved",
            )
        }


@dataclass(frozen=True, slots=True)
class LabSelectionReport:
    corpus_digest: str
    entity_metrics: tuple[CandidateMetrics, ...]
    provenance_metrics: tuple[CandidateMetrics, ...]
    selected_entity_candidate: str
    selected_provenance_candidate: str

    def to_canonical(self) -> dict[str, Any]:
        return {
            "authority_state": LAB_AUTHORITY_STATE,
            "corpus_digest": self.corpus_digest,
            "entity_metrics": [x.to_canonical() for x in self.entity_metrics],
            "provenance_metrics": [x.to_canonical() for x in self.provenance_metrics],
            "schema_version": LAB_SCHEMA_VERSION,
            "selected_entity_candidate": self.selected_entity_candidate,
            "selected_provenance_candidate": self.selected_provenance_candidate,
        }

    @property
    def report_digest(self) -> str:
        raw = json.dumps(self.to_canonical(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _aware(result, "timestamp")
    return result


def _norm(value: str | None) -> str:
    return "" if value is None else _SPACE.sub(" ", unicodedata.normalize("NFC", value).casefold().strip())


def _native_parts(value: str) -> tuple[str, str]:
    namespace, separator, identity = value.partition(":")
    if not separator or not namespace or not identity:
        raise ValueError(f"malformed native id: {value}")
    return namespace.casefold(), identity


def _native_map(item: LabObservation) -> dict[str, frozenset[str]]:
    result: dict[str, set[str]] = {}
    for value in item.native_ids:
        namespace, identity = _native_parts(value)
        result.setdefault(namespace, set()).add(identity)
    return {namespace: frozenset(values) for namespace, values in result.items()}


def _native_signal(
    left: LabObservation,
    right: LabObservation,
    allowed: frozenset[str] | None = None,
) -> tuple[EntityDecision, tuple[str, ...]] | None:
    left_ids, right_ids = _native_map(left), _native_map(right)
    namespaces = set(left_ids) & set(right_ids)
    if allowed is not None:
        namespaces &= set(allowed)
    matches = {n for n in namespaces if left_ids[n] & right_ids[n]}
    conflicts = {n for n in namespaces if left_ids[n].isdisjoint(right_ids[n])}
    if matches and conflicts:
        return EntityDecision.AMBIGUOUS, ("contradictory-native-identifiers", *sorted(matches | conflicts))
    if matches:
        return EntityDecision.SAME_ENTITY, ("shared-provider-native-identifier", *sorted(matches))
    if conflicts:
        return EntityDecision.DIFFERENT_ENTITY, ("conflicting-provider-native-identifier", *sorted(conflicts))
    return None


def _relations(item: LabObservation, target: str | None, as_of: datetime) -> tuple[LabRelation, ...]:
    if target is None:
        return ()
    return tuple(r for r in item.relations if r.target_external_ref == target and r.eligible_at(as_of))


def assess_entity(
    candidate_version: str, left: LabObservation, right: LabObservation, *, as_of: datetime
) -> Assessment:
    if candidate_version not in ENTITY_CANDIDATES:
        raise ValueError(f"unknown entity candidate: {candidate_version}")
    _aware(as_of, "as_of")
    if max(left.observed_at, right.observed_at) > as_of:
        raise ValueError("entity assessment cannot use future observation")

    if candidate_version in {"explicit-native-id-v0", "transparent-entity-hybrid-v0"}:
        signal = _native_signal(left, right)
        if signal is not None:
            return Assessment(candidate_version, signal[0], signal[1])
        if candidate_version == "explicit-native-id-v0":
            return Assessment(candidate_version, EntityDecision.AMBIGUOUS, ("no-shared-native-identity",))

    if candidate_version == "artifact-coordinate-v0":
        signal = _native_signal(left, right, _COORDINATES)
        return (
            Assessment(candidate_version, signal[0], signal[1])
            if signal is not None
            else Assessment(candidate_version, EntityDecision.AMBIGUOUS, ("artifact-coordinate-insufficient",))
        )

    if candidate_version == "transparent-entity-hybrid-v0":
        relations = (*_relations(left, right.canonical_url, as_of), *_relations(right, left.canonical_url, as_of))
        if any(r.relation_type in _ALIASES for r in relations):
            return Assessment(candidate_version, EntityDecision.SAME_ENTITY, ("point-in-time-explicit-alias-or-rename",))

    same_target = (
        left.canonical_url is not None
        and left.canonical_url == right.canonical_url
        and left.entity_type == right.entity_type
        and _norm(left.entity_name) == _norm(right.entity_name)
    )
    if same_target:
        return Assessment(candidate_version, EntityDecision.SAME_ENTITY, ("same-canonical-target", "matching-entity-type-name"))

    reason = "canonical-target-insufficient" if candidate_version == "canonical-entity-target-v0" else "insufficient-stable-identity-evidence"
    return Assessment(candidate_version, EntityDecision.AMBIGUOUS, (reason,))


def _direct_relation(left: LabObservation, right: LabObservation, as_of: datetime) -> LabRelation | None:
    values = (*_relations(left, right.canonical_url, as_of), *_relations(right, left.canonical_url, as_of))
    return next((r for r in sorted(values, key=lambda x: (x.relation_type, x.authority, x.target_external_ref)) if r.relation_type in _DIRECT), None)


def _mirror(left: LabObservation, right: LabObservation) -> bool:
    a, b = _norm(left.text), _norm(right.text)
    return left.source_id != right.source_id and bool(a) and a == b and len(_TOKEN.findall(a)) >= 5


def assess_provenance(
    candidate_version: str, left: LabObservation, right: LabObservation, *, as_of: datetime
) -> Assessment:
    if candidate_version not in PROVENANCE_CANDIDATES:
        raise ValueError(f"unknown provenance candidate: {candidate_version}")
    _aware(as_of, "as_of")
    if max(left.observed_at, right.observed_at) > as_of:
        raise ValueError("provenance assessment cannot use future observation")

    if candidate_version in {"explicit-reference-v0", "transparent-provenance-hybrid-v0"}:
        relation = _direct_relation(left, right, as_of)
        if relation is not None:
            return Assessment(
                candidate_version, ProvenanceDecision.DIRECT_DERIVATIVE,
                ("point-in-time-explicit-derivation", relation.relation_type),
                "hypothesis only; direct derivation is not true-origin authority",
            )
        if candidate_version == "explicit-reference-v0":
            return Assessment(
                candidate_version, ProvenanceDecision.NO_LINK_EVIDENCE,
                ("no-qualifying-explicit-derivation",),
                "NO_LINK_EVIDENCE is not factual independence",
            )

    if candidate_version in {"exact-content-common-upstream-v0", "transparent-provenance-hybrid-v0"} and _mirror(left, right):
        return Assessment(
            candidate_version, ProvenanceDecision.SHARED_UPSTREAM_POSSIBLE,
            ("exact-substantive-cross-source-mirror", "common-upstream-possible-not-proven"),
            "hypothesis only; shared upstream is possible, not established",
        )
    return Assessment(
        candidate_version, ProvenanceDecision.NO_LINK_EVIDENCE,
        ("no-qualifying-provenance-link-evidence",),
        "NO_LINK_EVIDENCE is not factual independence",
    )


def _relation(document: dict[str, Any]) -> LabRelation:
    created = document.get("created_at")
    return LabRelation(
        str(document["relation_type"]), str(document["target_external_ref"]),
        str(document["authority"]), None if created is None else _time(str(created)),
    )


def _observation(document: dict[str, Any]) -> LabObservation:
    return LabObservation(
        source_id=str(document["source_id"]),
        source_item_key=str(document["source_item_key"]),
        observed_at=_time(str(document["observed_at"])),
        canonical_url=None if document.get("canonical_url") is None else str(document["canonical_url"]),
        entity_type=str(document["entity_type"]),
        entity_name=str(document["entity_name"]),
        native_ids=tuple(map(str, document.get("native_ids", []))),
        title=None if document.get("title") is None else str(document["title"]),
        text=None if document.get("text") is None else str(document["text"]),
        artifact_version=None if document.get("artifact_version") is None else str(document["artifact_version"]),
        relations=tuple(_relation(x) for x in document.get("relations", [])),
    )


def parse_corpus(document: dict[str, Any]) -> tuple[LabCase, ...]:
    if document.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError("unexpected entity/provenance corpus schema")
    authority = document.get("authority")
    if not isinstance(authority, dict) or any(authority.get(key) is not False for key in ("runtime_authority", "public_authority", "persistence_authority")):
        raise ValueError("lab corpus must explicitly deny runtime, public, and persistence authority")
    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("lab corpus requires cases")
    result: list[LabCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        case_id = str(raw["id"])
        if case_id in seen:
            raise ValueError(f"duplicate lab case id: {case_id}")
        seen.add(case_id)
        result.append(LabCase(
            case_id, str(raw["category"]), _time(str(raw["as_of"])),
            _observation(raw["left"]), _observation(raw["right"]),
            EntityDecision(str(raw["expected_entity"])),
            ProvenanceDecision(str(raw["expected_provenance"])),
            str(raw["rationale"]),
        ))
    return tuple(result)


def load_corpus(path: Path) -> tuple[LabCase, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("lab corpus root must be an object")
    return parse_corpus(document)


def corpus_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _ratio(a: int, b: int) -> str:
    if b <= 0:
        raise ValueError("ratio denominator must be positive")
    return f"{a / b:.6f}"


def _metrics(cases: tuple[LabCase, ...], candidate: str, entity: bool) -> CandidateMetrics:
    if entity:
        expected = [x.expected_entity for x in cases]
        predicted = [assess_entity(candidate, x.left, x.right, as_of=x.as_of).decision for x in cases]
        positive: EntityDecision | ProvenanceDecision = EntityDecision.SAME_ENTITY
        forced = sum(e is EntityDecision.AMBIGUOUS and p is EntityDecision.DIFFERENT_ENTITY for e, p in zip(expected, predicted, strict=True))
        preserved = 0
    else:
        expected = [x.expected_provenance for x in cases]
        predicted = [assess_provenance(candidate, x.left, x.right, as_of=x.as_of).decision for x in cases]
        positive = ProvenanceDecision.DIRECT_DERIVATIVE
        forced = 0
        preserved = sum(e is ProvenanceDecision.NO_LINK_EVIDENCE and p is ProvenanceDecision.NO_LINK_EVIDENCE for e, p in zip(expected, predicted, strict=True))
    positive_expected = sum(x is positive for x in expected)
    positive_predictions = sum(x is positive for x in predicted)
    true_positives = sum(e is positive and p is positive for e, p in zip(expected, predicted, strict=True))
    return CandidateMetrics(
        candidate, len(cases), sum(e is p for e, p in zip(expected, predicted, strict=True)),
        positive_expected, positive_predictions, true_positives,
        positive_predictions - true_positives,
        None if positive_predictions == 0 else _ratio(true_positives, positive_predictions),
        _ratio(true_positives, positive_expected), forced, preserved,
    )


def evaluate_entity_candidate(cases: tuple[LabCase, ...], candidate_version: str) -> CandidateMetrics:
    return _metrics(cases, candidate_version, True)


def evaluate_provenance_candidate(cases: tuple[LabCase, ...], candidate_version: str) -> CandidateMetrics:
    return _metrics(cases, candidate_version, False)


def _select(metrics: tuple[CandidateMetrics, ...], entity: bool) -> str:
    survivors = [x for x in metrics if x.false_positives == 0 and x.positive_precision == "1.000000"]
    if not survivors:
        raise ValueError("no candidate clears frozen precision gate")
    complexity = (
        {name: i for i, name in enumerate(ENTITY_CANDIDATES, start=1)}
        if entity
        else {"explicit-reference-v0": 1, "exact-content-common-upstream-v0": 1, "transparent-provenance-hybrid-v0": 2}
    )
    survivors.sort(key=lambda x: (
        -float(x.positive_recall),
        x.ambiguous_forced_negative if entity else -x.expected_no_link_preserved,
        complexity[x.candidate_version],
    ))
    return survivors[0].candidate_version


def build_selection_report(cases: tuple[LabCase, ...], *, corpus_digest_value: str) -> LabSelectionReport:
    entity = tuple(evaluate_entity_candidate(cases, x) for x in ENTITY_CANDIDATES)
    provenance = tuple(evaluate_provenance_candidate(cases, x) for x in PROVENANCE_CANDIDATES)
    return LabSelectionReport(corpus_digest_value, entity, provenance, _select(entity, True), _select(provenance, False))
