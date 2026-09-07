from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from frontier.domain.entity_ground_truth_protocol_v2 import (
    ENTITY_QUALITY_STATUS,
    PROMOTION_STATUS,
    LabelStatus,
    PacketStatus,
    ProtocolV2DefinitionError,
    execute_v2_corpus,
    expand_v2_case,
    protocol_digest,
    validate_v2_packet,
)

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_protocol_builder_v2.json"
)
SCHEMA_PATH = (
    ROOT / "experiments/advanced_intelligence/entity_provenance_v0/"
    "entity_ground_truth_expanded_packet_v2.schema.json"
)
CORPUS_PATH = ROOT / "fixtures/entity_provenance/entity_ground_truth_protocol_corpus_v2.json"


def _load(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return _load(BUILDER_PATH), _load(SCHEMA_PATH), _load(CORPUS_PATH)


def test_offline_runtime_reproduces_all_24_frozen_packet_digests() -> None:
    builder, schema, corpus = _fixtures()
    runs = execute_v2_corpus(corpus=corpus, builder=builder, schema=schema)

    assert len(runs) == 24
    assert all(run.digest_matches for run in runs)
    assert len({run.packet_digest for run in runs}) == 24


def test_semantic_validator_derives_every_frozen_expected_outcome() -> None:
    builder, schema, corpus = _fixtures()
    runs = execute_v2_corpus(corpus=corpus, builder=builder, schema=schema)
    cases = cast(list[dict[str, Any]], corpus["cases"])
    expected_by_id = {
        cast(str, case["id"]): cast(dict[str, Any], case["expected"]) for case in cases
    }

    for run in runs:
        expected = expected_by_id[run.case_id]
        validation = run.validation
        assert validation.packet_status.value == expected["packet_status"]
        assert validation.label_status.value == expected["label_status"]
        assert validation.required_action == expected["required_action"]
        assert validation.headline_metric_eligible is expected["headline_metric_eligible"]
        assert validation.quality_claim is expected["quality_claim"]
        assert list(validation.forbidden_claims) == expected["forbidden_claims"]


def test_expansion_does_not_consume_expected_outcome_assertions() -> None:
    builder, schema, corpus = _fixtures()
    original = copy.deepcopy(corpus["cases"][0])
    tampered = cast(dict[str, Any], copy.deepcopy(original))
    tampered["expected"] = {
        "packet_status": "REJECT",
        "label_status": "INVALID_PACKET",
        "required_action": "SHOULD_NOT_BE_CONSUMED",
        "headline_metric_eligible": False,
        "quality_claim": "SHOULD_NOT_BE_CONSUMED",
        "forbidden_claims": ["SHOULD_NOT_BE_CONSUMED"],
    }

    original_packet = expand_v2_case(
        original,
        corpus=corpus,
        builder=builder,
        schema=schema,
    )
    tampered_packet = expand_v2_case(
        tampered,
        corpus=corpus,
        builder=builder,
        schema=schema,
    )

    assert protocol_digest(tampered_packet) == protocol_digest(original_packet)
    assert protocol_digest(original_packet) == original["expected_packet_digest"]


def test_validator_fail_closes_non_escalation_drift() -> None:
    builder, schema, corpus = _fixtures()
    case = cast(dict[str, Any], corpus["cases"][0])
    packet = expand_v2_case(case, corpus=corpus, builder=builder, schema=schema)
    tampered = copy.deepcopy(packet)
    non_escalation = cast(dict[str, Any], tampered["non_escalation"])
    non_escalation["real_label_collection_authorized"] = True

    result = validate_v2_packet(
        tampered,
        builder=builder,
        schema=schema,
        corpus=corpus,
    )

    assert result.packet_status is PacketStatus.REJECT
    assert result.label_status is LabelStatus.INVALID_PACKET
    assert result.required_action == "REJECT_PROTOCOL_DRIFT"
    assert result.quality_claim is None


def test_definition_rejects_any_real_authority_in_test_crypto() -> None:
    builder, schema, corpus = _fixtures()
    tampered_builder = copy.deepcopy(builder)
    spec = cast(dict[str, Any], tampered_builder["spec_payload"])
    test_mac = cast(dict[str, Any], spec["test_mac"])
    test_mac["real_label_authority"] = True
    tampered_builder["spec_payload_digest"] = protocol_digest(spec)
    tampered_corpus = copy.deepcopy(corpus)
    tampered_corpus["builder_spec_payload_digest"] = tampered_builder["spec_payload_digest"]

    with pytest.raises(ProtocolV2DefinitionError, match="cannot authorize real labels"):
        execute_v2_corpus(
            corpus=tampered_corpus,
            builder=tampered_builder,
            schema=schema,
        )


def test_offline_phase_preserves_scientific_state() -> None:
    builder, schema, corpus = _fixtures()
    runs = execute_v2_corpus(corpus=corpus, builder=builder, schema=schema)

    assert ENTITY_QUALITY_STATUS == "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
    assert PROMOTION_STATUS == "UNAVAILABLE"
    assert all(run.validation.quality_claim is None for run in runs)
