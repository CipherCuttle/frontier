from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
REPAIR_AUTHORITY_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_builder_reproducibility_repair_authority.json"
)
V1_AUTHORITY_PATH = (
    ROOT
    / "experiments/advanced_intelligence/entity_provenance_v0/entity_ground_truth_authority.json"
)
V1_CORPUS_PATH = ROOT / "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v0.json"

EXPECTED_PARENT = "0d30b076cde0439bbd70f1d9390b6d7c5dff5c03"
EXPECTED_V1_AUTHORITY_BLOB = "4aa25903a9f8ee6d016111bbe48483661f327a79"
EXPECTED_V1_CORPUS_BLOB = "664a86962b73bd1aae11feea25e41adbfbf5899a"


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{name} must be object")
    return cast(dict[str, object], value)


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"{name} must be array")
    return cast(list[object], value)


def _load(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _object(raw, path.name)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def test_repair_authority_binds_existing_v1_without_rewriting_it() -> None:
    repair = _load(REPAIR_AUTHORITY_PATH)
    lineage = _object(repair["lineage"], "lineage")
    preservation = _object(repair["v1_preservation"], "v1_preservation")

    assert repair["schema_version"] == (
        "frontier-entity-ground-truth-builder-reproducibility-repair-authority-v0"
    )
    assert repair["phase_id"] == "ENTITY_GROUND_TRUTH_BUILDER_REPRODUCIBILITY_REPAIR_V0"
    assert repair["authority_state"] == "FROZEN_REPRODUCIBILITY_REPAIR_AUTHORITY_CANDIDATE"
    assert repair["parent_main_commit"] == EXPECTED_PARENT

    assert lineage["v1_authority_git_blob_sha1"] == EXPECTED_V1_AUTHORITY_BLOB
    assert lineage["v1_corpus_git_blob_sha1"] == EXPECTED_V1_CORPUS_BLOB
    assert _git_blob_sha1(V1_AUTHORITY_PATH) == EXPECTED_V1_AUTHORITY_BLOB
    assert _git_blob_sha1(V1_CORPUS_PATH) == EXPECTED_V1_CORPUS_BLOB

    assert preservation == {
        "edit_v1_corpus_in_place": False,
        "reinterpret_v1_expected_packet_digests": False,
        "claim_v1_builder_reproduced_without_evidence": False,
        "historical_v1_artifacts_remain_immutable": True,
    }


def test_missing_builder_defect_is_explicit_and_fail_closed() -> None:
    repair = _load(REPAIR_AUTHORITY_PATH)
    defect = _object(repair["defect"], "defect")
    gate = _object(repair["implementation_gate"], "implementation_gate")

    assert defect["status"] == "BLOCKED_MISSING_FROZEN_BUILDER"
    missing = set(_array(defect["missing_frozen_elements"], "missing_frozen_elements"))
    assert {
        "complete expanded packet schema",
        "deterministic base-vector-to-packet construction algorithm",
        "synthetic signature construction and verification algorithm",
        "exact mutation application semantics against the expanded packet",
        "a content identity for the builder/specification itself",
    }.issubset(missing)

    assert gate and all(value is False for value in gate.values())


def test_v1_corpus_references_unpersisted_builder_contract() -> None:
    corpus = _load(V1_CORPUS_PATH)
    resolver = _object(corpus["resolver_contract"], "resolver_contract")
    expansion = resolver["expansion"]
    assert isinstance(expansion, str)
    assert "frozen governance builder" in expansion
    assert "expected_packet_digest binds the complete expanded packet" in expansion

    # The v1 corpus freezes base vectors, mutation descriptions and digests, but no
    # embedded complete builder/schema object capable of constructing those packets.
    assert "builder" not in corpus
    assert "packet_schema" not in corpus
    assert "expanded_packet_schema" not in corpus
    assert "signature_algorithm" not in corpus


def test_repair_requires_versioned_v2_freeze_before_conformance() -> None:
    repair = _load(REPAIR_AUTHORITY_PATH)
    required = _object(repair["required_repair"], "required_repair")
    allowed = _object(repair["allowed_after_repair_authority_merge"], "allowed")

    assert required["strategy"] == "VERSIONED_V2_PROTOCOL_FREEZE"
    requirements = set(_array(required["requirements"], "requirements"))
    assert {
        "preserve the v1 authority/corpus/blob identities unchanged as historical artifacts",
        "freeze a v2 builder or complete declarative builder specification with its own immutable content identity",
        "independently recompute every v2 expected packet digest from the frozen builder/specification in CI",
        "leave entity quality exactly INSUFFICIENT_INDEPENDENT_GROUND_TRUTH",
    }.issubset(requirements)

    assert allowed == {
        "prepare_v2_builder_specification_candidate": True,
        "prepare_v2_synthetic_corpus_candidate": True,
        "prepare_v2_reproducibility_tests": True,
        "runtime_validator_conformance_claim": False,
        "real_world_label_collection": False,
        "candidate_quality_evaluation": False,
    }
