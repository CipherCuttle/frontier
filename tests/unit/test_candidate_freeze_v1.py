from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from frontier.application.candidate_freeze_v1 import (
    collect_freeze_inputs_v1,
    freeze_candidate_v1,
    verify_freeze_v1,
)
from frontier.domain.candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_SOURCE_REGISTRY_PATH,
    FreezeInputs,
    FreezeStatus,
    RegistryEntryDigest,
)
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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()


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


def test_v1_collector_binds_selected_git_tree_not_dirty_worktree(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")

    preregistration_path = tmp_path / FREEZE_V1_PREREGISTRATION_PATH
    dependency_lock_path = tmp_path / FREEZE_DEPENDENCY_LOCK_PATH
    source_registry_path = tmp_path / FREEZE_SOURCE_REGISTRY_PATH
    source_contract_relative = "sources/contracts/test-source.json"
    source_contract_path = tmp_path / source_contract_relative
    for path in (
        preregistration_path,
        dependency_lock_path,
        source_registry_path,
        source_contract_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    preregistration = {
        "experiment_id": PEF_V1_EXPERIMENT_ID,
        "candidate_id": PEF_V1_CANDIDATE_ID,
        "frozen_overrides": [
            {
                "json_pointer": "/candidate/configuration_digest",
                "value": str(PEF_V1_CONFIGURATION_DIGEST),
            }
        ],
    }
    preregistration_path.write_text(json.dumps(preregistration), encoding="utf-8")
    dependency_lock_path.write_text("locked\n", encoding="utf-8")
    source_registry_path.write_text(
        json.dumps({"source_contract_paths": [source_contract_relative]}),
        encoding="utf-8",
    )
    source_contract_path.write_text('{"version": 1}\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "frozen implementation")

    committed = collect_freeze_inputs_v1(tmp_path)

    preregistration["dirty_worktree_only"] = "dirty"
    preregistration_path.write_text(json.dumps(preregistration), encoding="utf-8")
    dependency_lock_path.write_text("dirty lock\n", encoding="utf-8")
    source_registry_path.write_text(
        json.dumps(
            {
                "source_contract_paths": [source_contract_relative],
                "dirty_worktree_only": True,
            }
        ),
        encoding="utf-8",
    )
    source_contract_path.write_text('{"version": 999}\n', encoding="utf-8")

    dirty = collect_freeze_inputs_v1(tmp_path)
    assert dirty == committed


def test_live_v1_freeze_and_verification_stay_frozen() -> None:
    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=FROZEN_AT)
    assert isinstance(receipt, CandidateFreezeReceiptV1)
    assert receipt.status is FreezeStatus.FROZEN
    verification = verify_freeze_v1(receipt, root=REPO_ROOT, verified_at=FROZEN_AT)
    assert verification.status is FreezeStatus.FROZEN
    assert verification.original_receipt_digest == receipt.receipt_digest
