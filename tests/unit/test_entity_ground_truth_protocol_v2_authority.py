from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT
    / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_protocol_v2_authority.json"
)

EXPECTED_PARENT = "bee2b5a74a7d4df630c72330ea6c576571ffa305"
EXPECTED_BUILDER_BLOB = "fca9669c08396de9bb49a218e26a59e47fb87c8e"
EXPECTED_SCHEMA_BLOB = "8ed77a799070dd9e4720069c09a16bb4437e34b2"
EXPECTED_CORPUS_BLOB = "e61330b6ac94ccb52817fbe4078f63bfcd242732"
EXPECTED_RECOMPUTE_TEST_BLOB = "572eedd2022e8b3fe76ea339baf79c6f5d406774"


def _load(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def test_v2_authority_binds_exact_frozen_repository_bytes() -> None:
    authority = _load(AUTHORITY_PATH)
    frozen = authority["frozen_v2_artifacts"]

    assert authority["phase_id"] == "ENTITY_GROUND_TRUTH_PROTOCOL_V2_FREEZE"
    assert authority["authority_state"] == "FROZEN_PROTOCOL_V2_CANDIDATE"
    assert authority["parent_main_commit"] == EXPECTED_PARENT

    expected = {
        "builder_spec": EXPECTED_BUILDER_BLOB,
        "expanded_packet_schema": EXPECTED_SCHEMA_BLOB,
        "hostile_corpus": EXPECTED_CORPUS_BLOB,
        "independent_recomputation_test": EXPECTED_RECOMPUTE_TEST_BLOB,
    }
    for name, blob_sha in expected.items():
        artifact = frozen[name]
        path = ROOT / artifact["path"]
        assert artifact["git_blob_sha1"] == blob_sha
        assert _git_blob_sha1(path) == blob_sha


def test_v2_authority_preserves_v1_and_quality_fail_closed_state() -> None:
    authority = _load(AUTHORITY_PATH)
    lineage = authority["repair_lineage"]
    state = authority["scientific_state"]
    allowed = authority["authorized_after_this_freeze_merges"]

    assert lineage["v1_reinterpretation_authorized"] is False
    assert state["entity_quality"] == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert state["quality_claim"] is None
    assert state["promotion_status"] == "UNAVAILABLE"

    assert allowed["offline_packet_expander_validator"] is True
    assert allowed["offline_blinding_redaction_validator"] is True
    assert allowed["offline_adjudication_receipt_validator"] is True
    assert allowed["protocol_hostile_tests"] is True
    assert allowed["in_memory_only"] is True
    assert allowed["v2_exact_digest_conformance_required"] is True

    forbidden = [
        "real_label_collection",
        "candidate_quality_metrics",
        "candidate_quality_pass_fail",
        "candidate_promotion",
        "canonical_entity_truth",
        "persistence",
        "migrations",
        "workers_or_schedulers",
        "api",
        "terminal",
        "source_registry_changes",
        "provenance_production_truth",
        "ranking_changes",
    ]
    assert all(allowed[name] is False for name in forbidden)


def test_v2_test_crypto_is_explicitly_non_authoritative() -> None:
    authority = _load(AUTHORITY_PATH)
    boundary = authority["synthetic_trust_boundary"]

    assert boundary["security_status"] == "TEST_ONLY_NOT_A_REAL_SIGNATURE_SCHEME"
    assert boundary["all_key_ids_must_begin_with"] == "TEST_ONLY_"
    assert boundary["fixture_secrets_are_public_test_material"] is True
    assert boundary["real_identity_or_origin_authentication"] is False
    assert boundary["real_label_authority"] is False
    assert boundary["real_trust_roots_must_be_separately_frozen_before_real_collection"] is True
