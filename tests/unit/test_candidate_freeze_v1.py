from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from frontier.application.candidate_freeze_v1 import (
    collect_freeze_inputs_v1,
    freeze_candidate_v1,
    verify_freeze_v1,
)
from frontier.domain.candidate_freeze import FreezeInputs, FreezeStatus, RegistryEntryDigest
from frontier.domain.candidate_freeze_v1 import (
    FREEZE_V1_PREREGISTRATION_PATH,
    CandidateFreezeReceiptV1,
    build_candidate_freeze_receipt_v1,
    verify_candidate_freeze_v1,
)
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_AT = datetime(2026, 9, 9, 16, 50, tzinfo=UTC)
FAKE_COMMIT = "a" * 40
FAKE_TREE = "b" * 40


def _healthy_inputs() -> FreezeInputs:
    return FreezeInputs(
        preregistration_digest=sha256_digest(
            (REPO_ROOT / FREEZE_V1_PREREGISTRATION_PATH).read_bytes()
        ),
        preregistration_config_digest=PEF_V1_CONFIGURATION_DIGEST,
        implementation_commit=FAKE_COMMIT,
        implementation_tree_digest=FAKE_TREE,
        dependency_lock_digest=Digest("sha256:" + "1" * 64),
        source_registry_digest=Digest("sha256:" + "2" * 64),
        registry_entry_digests=(
            RegistryEntryDigest(
                path="sources/registry/cisa.kev.v0.json",
                digest=Digest("sha256:" + "3" * 64),
            ),
        ),
    )


def test_v1_freeze_receipt_binds_successor_identity() -> None:
    receipt = build_candidate_freeze_receipt_v1(_healthy_inputs(), frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.FROZEN
    assert receipt.candidate_id == PEF_V1_CANDIDATE_ID
    assert receipt.experiment_id == PEF_V1_EXPERIMENT_ID
    assert receipt.configuration_digest == PEF_V1_CONFIGURATION_DIGEST
    assert receipt.preregistration_path == FREEZE_V1_PREREGISTRATION_PATH
    assert receipt.receipt_id.startswith("freezereceipt_")


def test_v1_freeze_fails_closed_on_preregistered_configuration_drift() -> None:
    inputs = replace(
        _healthy_inputs(),
        preregistration_config_digest=Digest("sha256:" + "0" * 64),
    )
    receipt = build_candidate_freeze_receipt_v1(inputs, frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.DRIFTED
    assert any("PEF_V1 configuration" in reason for reason in receipt.drift_reasons)


def test_v1_verification_detects_implementation_drift() -> None:
    receipt = build_candidate_freeze_receipt_v1(_healthy_inputs(), frozen_at=FROZEN_AT)
    verification = verify_candidate_freeze_v1(
        receipt,
        inputs=replace(_healthy_inputs(), implementation_commit="f" * 40),
        verified_at=FROZEN_AT,
    )
    assert verification.status is FreezeStatus.DRIFTED
    assert any("implementation commit drifted" in reason for reason in verification.drift_reasons)


def test_live_v1_collector_extracts_successor_override_and_git_identity() -> None:
    inputs = collect_freeze_inputs_v1(REPO_ROOT)
    assert inputs.preregistration_config_digest == PEF_V1_CONFIGURATION_DIGEST
    assert inputs.preregistration_digest == sha256_digest(
        (REPO_ROOT / FREEZE_V1_PREREGISTRATION_PATH).read_bytes()
    )
    assert inputs.implementation_commit is not None
    assert inputs.implementation_tree_digest is not None
    assert inputs.dependency_lock_digest is not None
    assert inputs.source_registry_digest is not None
    assert inputs.registry_entry_digests


def test_live_v1_freeze_and_verification_stay_frozen() -> None:
    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=FROZEN_AT)
    assert isinstance(receipt, CandidateFreezeReceiptV1)
    assert receipt.status is FreezeStatus.FROZEN
    verification = verify_freeze_v1(receipt, root=REPO_ROOT, verified_at=FROZEN_AT)
    assert verification.status is FreezeStatus.FROZEN
    assert verification.original_receipt_digest == receipt.receipt_digest
