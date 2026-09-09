from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from frontier.application.freeze_publication_v1 import derive_freeze_publication_v1
from frontier.domain.candidate_freeze import FreezeInputs, FreezeStatus
from frontier.domain.candidate_freeze_v1 import (
    CandidateFreezeReceiptV1,
    build_candidate_freeze_receipt_v1,
)
from frontier.domain.canonical_json import canonical_json_text
from frontier.domain.digests import Digest
from frontier.domain.pef_v1 import PEF_V1_CONFIGURATION_DIGEST


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()


def _frozen_receipt(root: Path) -> CandidateFreezeReceiptV1:
    implementation = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    receipt = build_candidate_freeze_receipt_v1(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=PEF_V1_CONFIGURATION_DIGEST,
            implementation_commit=implementation,
            implementation_tree_digest=tree,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    return receipt


def _publish_receipt_merge(root: Path, receipt: CandidateFreezeReceiptV1) -> Path:
    _git(root, "checkout", "-b", "freeze-publication")
    path = root / "experiments/advanced_intelligence/pef_v1/candidate_freeze_receipt_v0.json"
    path.parent.mkdir(parents=True)
    path.write_text(canonical_json_text(receipt.to_canonical()) + "\n", encoding="utf-8")
    _git(root, "add", str(path.relative_to(root)))
    _git(root, "commit", "-m", "publish receipt")
    _git(root, "checkout", "main")
    _git(root, "merge", "--no-ff", "freeze-publication", "-m", "merge durable freeze")
    return path


def test_exact_v1_publication_merge_is_derived_from_git(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")
    (tmp_path / "base.txt").write_text("base", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "implementation")
    receipt = _frozen_receipt(tmp_path)
    path = _publish_receipt_merge(tmp_path, receipt)

    publication = derive_freeze_publication_v1(tmp_path, receipt, receipt_path=path)
    assert publication.implementation_commit == receipt.implementation_commit
    assert publication.implementation_tree_digest == receipt.implementation_tree_digest
    assert publication.publication_commit == _git(tmp_path, "rev-parse", "HEAD")
    assert publication.publication_committer_at.tzinfo is not None


def test_v1_publication_rejects_non_v1_receipt_path(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")
    (tmp_path / "base.txt").write_text("base", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "implementation")
    receipt = _frozen_receipt(tmp_path)
    path = tmp_path / "experiments/advanced_intelligence/pef_v0/candidate_freeze_receipt_v99.json"
    path.parent.mkdir(parents=True)
    path.write_text(canonical_json_text(receipt.to_canonical()) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="canonical versioned publication path"):
        derive_freeze_publication_v1(tmp_path, receipt, receipt_path=path)


def test_v1_publication_rejects_drifted_receipt(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")
    (tmp_path / "base.txt").write_text("base", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "implementation")
    receipt = _frozen_receipt(tmp_path)
    drifted = replace(
        receipt,
        status=FreezeStatus.DRIFTED,
        drift_reasons=("test drift",),
    )
    path = tmp_path / "experiments/advanced_intelligence/pef_v1/candidate_freeze_receipt_v0.json"

    with pytest.raises(RuntimeError, match="requires a FROZEN receipt"):
        derive_freeze_publication_v1(tmp_path, drifted, receipt_path=path)


def test_v1_publication_verifies_receipt_bytes_from_head(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")
    (tmp_path / "base.txt").write_text("base", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "implementation")
    receipt = _frozen_receipt(tmp_path)
    path = _publish_receipt_merge(tmp_path, receipt)

    spoofed = replace(
        receipt,
        source_registry_digest=Digest("sha256:" + "4" * 64),
    )
    path.write_text(canonical_json_text(spoofed.to_canonical()) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="committed freeze publication does not equal"):
        derive_freeze_publication_v1(tmp_path, spoofed, receipt_path=path)
