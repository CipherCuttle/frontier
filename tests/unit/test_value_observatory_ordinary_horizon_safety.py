from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from frontier.application.value_observatory_ordinary_horizon_safety import (
    OrdinaryHorizonSafetyMechanism,
    OrdinaryHorizonSafetyStatus,
    OrdinaryHorizonSafetyVerdict,
    OrdinarySourceHorizonSafetyProof,
    assess_ordinary_horizon_safety_v0,
)

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "experiments/value_observatory_v0/ordinary_horizon_safety_proof_v0.json"


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{label} must be a string")
    return value


def _require_str_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AssertionError(f"{label} must be a string list")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise AssertionError(f"{label} must be a string list")
    return tuple(item for item in items if isinstance(item, str))


def _load_manifest() -> dict[str, object]:
    return cast(dict[str, object], json.loads(_MANIFEST.read_text(encoding="utf-8")))


def _proofs_from_manifest(raw: dict[str, object]) -> tuple[OrdinarySourceHorizonSafetyProof, ...]:
    rows_value = raw.get("sources")
    if not isinstance(rows_value, list):
        raise AssertionError("sources must be a list")
    rows = cast(list[object], rows_value)

    proofs: list[OrdinarySourceHorizonSafetyProof] = []
    for index, row_value in enumerate(rows):
        if not isinstance(row_value, dict):
            raise AssertionError(f"sources[{index}] must be an object")
        row = cast(dict[str, object], row_value)
        proofs.append(
            OrdinarySourceHorizonSafetyProof(
                source_id=_require_str(row.get("source_id"), f"sources[{index}].source_id"),
                status=OrdinaryHorizonSafetyStatus(
                    _require_str(row.get("status"), f"sources[{index}].status")
                ),
                mechanism=OrdinaryHorizonSafetyMechanism(
                    _require_str(row.get("mechanism"), f"sources[{index}].mechanism")
                ),
                evidence_refs=_require_str_tuple(
                    row.get("evidence_refs"), f"sources[{index}].evidence_refs"
                ),
                detail=_require_str(row.get("detail"), f"sources[{index}].detail"),
            )
        )
    return tuple(proofs)


def test_frozen_manifest_is_fail_closed_and_currently_blocks_executor_implementation() -> None:
    raw = _load_manifest()
    assert raw["schema_version"] == "frontier-ordinary-horizon-safety-proof-v0"
    assert raw["phase_id"] == "BENCHMARK_ORDINARY_HORIZON_SAFETY_PROOF_V0"
    assert raw["benchmark_protocol_id"] == "frontier-benchmark-capture-v0"
    assert raw["overall_verdict"] == "BLOCKED"
    assert raw["executor_implementation_authorized"] is False
    assert raw["evidence_complete_source_count"] == 0
    assert raw["required_source_count"] == 7

    assessment = assess_ordinary_horizon_safety_v0(_proofs_from_manifest(raw))

    assert assessment.verdict is OrdinaryHorizonSafetyVerdict.BLOCKED
    assert assessment.evidence_complete_source_ids == ()
    assert assessment.blocked_source_ids == (
        "arxiv.cs-ai",
        "cisa.kev",
        "gdelt.frontier",
        "github.ml-repos",
        "hf.models",
        "hn.frontpage",
        "pypi.updates",
    )
    assert (
        tuple(blocker.source_id for blocker in assessment.blockers) == assessment.blocked_source_ids
    )


def test_all_complete_caller_claims_remain_pending_trusted_authority() -> None:
    proofs = _proofs_from_manifest(_load_manifest())
    all_claimed_complete = tuple(
        replace(
            proof,
            status=OrdinaryHorizonSafetyStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY,
            mechanism=OrdinaryHorizonSafetyMechanism.SOURCE_NATIVE_AS_OF,
        )
        for proof in proofs
    )

    assessment = assess_ordinary_horizon_safety_v0(all_claimed_complete)

    assert assessment.verdict is OrdinaryHorizonSafetyVerdict.EVIDENCE_COMPLETE_PENDING_AUTHORITY
    assert assessment.blocked_source_ids == ()
    assert len(assessment.evidence_complete_source_ids) == 7


def test_gate_rejects_missing_extra_and_duplicate_source_proofs() -> None:
    proofs = _proofs_from_manifest(_load_manifest())

    with pytest.raises(ValueError, match="source set mismatch"):
        assess_ordinary_horizon_safety_v0(proofs[:-1])

    extra = replace(proofs[0], source_id="not.frozen")
    with pytest.raises(ValueError, match="source set mismatch"):
        assess_ordinary_horizon_safety_v0((*proofs, extra))

    with pytest.raises(ValueError, match="duplicate"):
        assess_ordinary_horizon_safety_v0((*proofs, proofs[0]))


def test_source_proof_cannot_claim_inconsistent_status_and_mechanism() -> None:
    with pytest.raises(ValueError, match="requires an explicit mechanism"):
        OrdinarySourceHorizonSafetyProof(
            source_id="cisa.kev",
            status=OrdinaryHorizonSafetyStatus.EVIDENCE_COMPLETE_PENDING_AUTHORITY,
            mechanism=OrdinaryHorizonSafetyMechanism.NONE,
            evidence_refs=("evidence",),
            detail="detail",
        )

    with pytest.raises(ValueError, match="blocked source cannot claim"):
        OrdinarySourceHorizonSafetyProof(
            source_id="hn.frontpage",
            status=OrdinaryHorizonSafetyStatus.BLOCKED_UNPROVEN,
            mechanism=OrdinaryHorizonSafetyMechanism.SOURCE_NATIVE_AS_OF,
            evidence_refs=("evidence",),
            detail="detail",
        )
