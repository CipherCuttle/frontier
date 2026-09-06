from __future__ import annotations

import hashlib
import json
from pathlib import Path

from frontier.domain.relation import RelationType

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = ROOT / "experiments/advanced_intelligence/entity_provenance_v0/bridge_authority.json"
CORPUS_PATH = ROOT / "fixtures/entity_provenance/bridge_corpus_v0.json"

EXPECTED_PARENT = "23cf10e0d65883c7b82356cf1bd18d9c56215604"
EXPECTED_LAB_CORPUS = "sha256:04ac150abe4356ef06a6fda75429d5873d8dd519e79e29f5c5e2853f4432a386"
EXPECTED_BRIDGE_CORPUS = "sha256:9b9998be5245c7d4481652c588177c6a46ed486dd5b51902630bd36b901686ad"
EXPECTED_REGISTRY = "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"

SUPPORTED = {"pypi.updates", "cisa.kev", "github.ml-repos", "hf.models"}
UNSUPPORTED = {"arxiv.cs-ai", "gdelt.frontier", "hn.frontpage"}
ALL_SOURCES = SUPPORTED | UNSUPPORTED

EXPECTED_CASE_IDS = {f"BRV-{i:03d}" for i in range(1, 19)}

FORBIDDEN_UPGRADES = {
    "REFERENCES->DIRECT_DERIVATIVE",
    "CORRECTS->DIRECT_DERIVATIVE",
    "RETRACTS->DIRECT_DERIVATIVE",
    "github fork boolean without explicit parent target->DIRECT_DERIVATIVE",
    "same canonical URL->DIRECT_DERIVATIVE",
    "exact content mirror->DIRECT_DERIVATIVE",
    "earliest observed->true origin",
}

PERMITTED_IMPLEMENTATION_AUTHORITY = {
    "bridge_domain_adapter",
    "offline_coverage_diagnostics",
    "hostile_bridge_tests",
}


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_bridge_authority_binds_exact_lab_and_main_lineage() -> None:
    authority = _load(AUTHORITY_PATH)
    assert authority["schema_version"] == "frontier-entity-provenance-bridge-authority-v0"
    assert authority["phase_id"] == "ENTITY_PROVENANCE_BRIDGE_V0"
    assert authority["authority_state"] == "FROZEN_BRIDGE_AUTHORITY_CANDIDATE"
    assert authority["parent_main_commit"] == EXPECTED_PARENT

    lineage = authority["lab_lineage"]
    assert isinstance(lineage, dict)
    assert lineage == {
        "lab_corpus_digest": EXPECTED_LAB_CORPUS,
        "lab_id": "ENTITY_PROVENANCE_LAB_V0",
        "lab_merge_commit": EXPECTED_PARENT,
        "selected_entity_candidate": "transparent-entity-hybrid-v0",
        "selected_provenance_candidate": "explicit-reference-v0",
    }


def test_bridge_corpus_is_exact_frozen_18_case_authority() -> None:
    authority = _load(AUTHORITY_PATH)
    corpus = _load(CORPUS_PATH)

    bridge_corpus = authority["bridge_corpus"]
    assert isinstance(bridge_corpus, dict)
    assert bridge_corpus == {
        "case_count": 18,
        "digest": EXPECTED_BRIDGE_CORPUS,
        "path": "fixtures/entity_provenance/bridge_corpus_v0.json",
    }
    assert corpus["schema_version"] == "frontier-entity-provenance-bridge-corpus-v0"
    cases = corpus["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 18
    case_ids = {case["id"] for case in cases if isinstance(case, dict)}
    assert case_ids == EXPECTED_CASE_IDS
    assert len(case_ids) == len(cases)
    assert _digest(corpus) == EXPECTED_BRIDGE_CORPUS


def test_entity_mapping_partitions_exact_seven_source_registry() -> None:
    authority = _load(AUTHORITY_PATH)
    input_authority = authority["input_authority"]
    assert isinstance(input_authority, dict)
    assert input_authority["source_registry_digest"] == EXPECTED_REGISTRY

    entity_mapping = authority["entity_mapping"]
    assert isinstance(entity_mapping, dict)
    supported = entity_mapping["supported_sources"]
    unsupported = entity_mapping["unsupported_sources"]
    assert isinstance(supported, dict)
    assert isinstance(unsupported, list)

    supported_ids = set(supported)
    unsupported_ids = set(unsupported)
    assert supported_ids == SUPPORTED
    assert unsupported_ids == UNSUPPORTED
    assert supported_ids.isdisjoint(unsupported_ids)
    assert supported_ids | unsupported_ids == ALL_SOURCES


def test_provenance_mapping_cannot_upgrade_canonical_relations() -> None:
    authority = _load(AUTHORITY_PATH)
    mapping = authority["provenance_mapping"]
    assert isinstance(mapping, dict)
    assert mapping["direct_derivation_available"] is False

    canonical = mapping["canonical_relation_types"]
    assert isinstance(canonical, list)
    assert set(canonical) == {item.value for item in RelationType}
    assert set(canonical) == {"CORRECTS", "RETRACTS", "REFERENCES"}

    forbidden = mapping["forbidden_upgrades"]
    assert isinstance(forbidden, list)
    assert set(forbidden) == FORBIDDEN_UPGRADES
    assert "never factual independence" in str(mapping["zero_coverage_semantics"])


def test_authority_grants_only_offline_bridge_implementation() -> None:
    authority = _load(AUTHORITY_PATH)

    implementation = authority["implementation_authority_on_merge"]
    assert isinstance(implementation, dict)
    true_keys = {key for key, value in implementation.items() if value is True}
    false_keys = {key for key, value in implementation.items() if value is False}
    assert true_keys == PERMITTED_IMPLEMENTATION_AUTHORITY
    assert false_keys == {
        "api",
        "candidate_shadow_evaluation",
        "canonical_schema_change",
        "migration",
        "persistence",
        "terminal",
        "worker_scheduling",
    }

    output = authority["output_authority"]
    assert isinstance(output, dict)
    for key in (
        "api_authority",
        "canonical_entity_authority",
        "canonical_provenance_authority",
        "persistence_authority",
        "promotion_authority",
        "ranking_authority",
        "terminal_authority",
    ):
        assert output[key] is False
    assert output["bridge_records"] == "EXPERIMENTAL_EPHEMERAL_ONLY"
    assert output["coverage_report"] == "EXPERIMENTAL_DIAGNOSTIC_ONLY"


def test_bridge_corpus_itself_grants_no_runtime_or_truth_authority() -> None:
    corpus = _load(CORPUS_PATH)
    corpus_authority = corpus["authority"]
    assert isinstance(corpus_authority, dict)
    assert corpus_authority["runtime_authority"] is False
    assert corpus_authority["persistence_authority"] is False
    assert corpus_authority["public_authority"] is False
    assert corpus_authority["canonical_entity_authority"] is False
    assert corpus_authority["canonical_provenance_authority"] is False
