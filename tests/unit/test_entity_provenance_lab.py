from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from frontier.domain.entity_provenance_lab import (
    ENTITY_CANDIDATES,
    PROVENANCE_CANDIDATES,
    EntityDecision,
    ProvenanceDecision,
    assess_entity,
    assess_provenance,
    build_selection_report,
    corpus_digest,
    load_corpus,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures/entity_provenance/corpus_v0.json"
PREREG = (
    ROOT / "experiments" / "advanced_intelligence" / "entity_provenance_v0" / "preregistration.json"
)


def _case(case_id: str):
    return next(case for case in load_corpus(CORPUS) if case.case_id == case_id)


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def test_frozen_corpus_digest_matches_preregistration() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert corpus_digest(CORPUS) == prereg["corpus_digest"]
    assert prereg["runtime_authority"] is False
    assert prereg["public_authority"] is False
    assert prereg["persistence_authority"] is False
    assert prereg["promotion_authority"] is False


def test_corpus_is_frozen_18_case_hostile_set() -> None:
    cases = load_corpus(CORPUS)
    assert len(cases) == 18
    assert len({case.case_id for case in cases}) == 18
    assert {case.case_id for case in cases} == {f"EPV-{index:03d}" for index in range(1, 19)}


def test_transparent_entity_hybrid_matches_all_frozen_labels() -> None:
    for case in load_corpus(CORPUS):
        result = assess_entity(
            "transparent-entity-hybrid-v0", case.left, case.right, as_of=case.as_of
        )
        assert result.decision is case.expected_entity, case.case_id


def test_transparent_provenance_hybrid_matches_all_frozen_labels() -> None:
    for case in load_corpus(CORPUS):
        result = assess_provenance(
            "transparent-provenance-hybrid-v0",
            case.left,
            case.right,
            as_of=case.as_of,
        )
        assert result.decision is case.expected_provenance, case.case_id


def test_selection_report_follows_frozen_precision_rules() -> None:
    cases = load_corpus(CORPUS)
    report = build_selection_report(cases, corpus_digest_value=corpus_digest(CORPUS))

    assert report.selected_entity_candidate == "transparent-entity-hybrid-v0"
    # The frozen rule optimizes DIRECT_DERIVATIVE recall and then lower complexity,
    # so the conservative explicit-reference candidate wins; the richer hybrid is
    # still measured and remains available for falsification.
    assert report.selected_provenance_candidate == "explicit-reference-v0"

    entity = {item.candidate_version: item for item in report.entity_metrics}
    assert entity["transparent-entity-hybrid-v0"].positive_precision == "1.000000"
    assert entity["transparent-entity-hybrid-v0"].positive_recall == "1.000000"

    provenance = {item.candidate_version: item for item in report.provenance_metrics}
    assert provenance["explicit-reference-v0"].positive_precision == "1.000000"
    assert provenance["explicit-reference-v0"].positive_recall == "1.000000"


def test_future_alias_relation_does_not_leak_into_case_horizon() -> None:
    case = _case("EPV-018")
    before = assess_entity("transparent-entity-hybrid-v0", case.left, case.right, as_of=case.as_of)
    after = assess_entity(
        "transparent-entity-hybrid-v0",
        case.left,
        case.right,
        as_of=case.as_of + timedelta(minutes=21),
    )

    assert before.decision is EntityDecision.AMBIGUOUS
    assert after.decision is EntityDecision.SAME_ENTITY


def test_fork_keeps_entity_and_provenance_dimensions_separate() -> None:
    case = _case("EPV-006")
    entity = assess_entity("transparent-entity-hybrid-v0", case.left, case.right, as_of=case.as_of)
    provenance = assess_provenance(
        "transparent-provenance-hybrid-v0", case.left, case.right, as_of=case.as_of
    )

    assert entity.decision is EntityDecision.DIFFERENT_ENTITY
    assert provenance.decision is ProvenanceDecision.DIRECT_DERIVATIVE


def test_same_name_without_stable_evidence_stays_ambiguous() -> None:
    case = _case("EPV-014")
    result = assess_entity("transparent-entity-hybrid-v0", case.left, case.right, as_of=case.as_of)
    assert result.decision is EntityDecision.AMBIGUOUS


def test_exact_mirror_is_not_promoted_to_direct_derivative() -> None:
    case = _case("EPV-001")
    result = assess_provenance(
        "transparent-provenance-hybrid-v0", case.left, case.right, as_of=case.as_of
    )
    assert result.decision is ProvenanceDecision.SHARED_UPSTREAM_POSSIBLE


def test_lab_outputs_contain_no_truth_escalation_keys() -> None:
    forbidden = {
        "confirmation",
        "confirmation_count",
        "independent_confirmation",
        "entity_certainty",
        "factual_confidence",
        "true_origin",
        "origin_verdict",
        "manipulation_verdict",
        "truth_probability",
    }
    case = _case("EPV-002")
    values = [
        assess_entity(
            "transparent-entity-hybrid-v0", case.left, case.right, as_of=case.as_of
        ).to_canonical(),
        assess_provenance(
            "transparent-provenance-hybrid-v0",
            case.left,
            case.right,
            as_of=case.as_of,
        ).to_canonical(),
    ]
    for value in values:
        assert not (_all_keys(value) & forbidden)


def test_selection_report_replays_deterministically() -> None:
    cases = load_corpus(CORPUS)
    first = build_selection_report(cases, corpus_digest_value=corpus_digest(CORPUS))
    second = build_selection_report(cases, corpus_digest_value=corpus_digest(CORPUS))
    assert first.to_canonical() == second.to_canonical()
    assert first.report_digest == second.report_digest
    assert first.report_digest.startswith("sha256:")
    assert len(first.report_digest) == len("sha256:") + hashlib.sha256().digest_size * 2


def test_all_preregistered_candidates_are_executable() -> None:
    cases = load_corpus(CORPUS)
    for candidate in ENTITY_CANDIDATES:
        for case in cases:
            assess_entity(candidate, case.left, case.right, as_of=case.as_of)
    for candidate in PROVENANCE_CANDIDATES:
        for case in cases:
            assess_provenance(candidate, case.left, case.right, as_of=case.as_of)
