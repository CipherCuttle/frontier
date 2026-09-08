from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import frontier.application.freeze_publication as freeze_publication_module
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    confirmatory_window_end,
    derive_freeze_publication,
    first_confirmatory_boundary,
    require_confirmatory_boundary,
    require_github_main_publication,
)
from frontier.domain.candidate_freeze import FreezeInputs, build_candidate_freeze_receipt
from frontier.domain.canonical_json import canonical_json_text
from frontier.domain.digests import Digest

PUB = datetime(2026, 9, 7, 18, 17, 59, tzinfo=UTC)
START = datetime(2026, 9, 7, 18, 20, tzinfo=UTC)


def test_publication_timestamp_defines_fixed_window():
    assert first_confirmatory_boundary(PUB) == START
    assert first_confirmatory_boundary(START) == START + timedelta(minutes=5)
    assert confirmatory_window_end(PUB) == START + timedelta(seconds=2_419_200)
    require_confirmatory_boundary(as_of=START, publication_committer_at=PUB)


def test_exact_publication_merge_is_derived_from_git(tmp_path: Path):
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=tmp_path, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "frontier@example.test")
    git("config", "user.name", "Frontier Test")
    (tmp_path / "base.txt").write_text("base")
    git("add", "base.txt")
    git("commit", "-m", "implementation")
    implementation = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    receipt = build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=Digest(
                "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
            ),
            implementation_commit=implementation,
            implementation_tree_digest=tree,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    git("checkout", "-b", "freeze-publication")
    path = tmp_path / "experiments/advanced_intelligence/pef_v0/candidate_freeze_receipt_v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(canonical_json_text(receipt.to_canonical()) + "\n")
    git("add", str(path.relative_to(tmp_path)))
    git("commit", "-m", "publish receipt")
    git("checkout", "main")
    git("merge", "--no-ff", "freeze-publication", "-m", "merge durable freeze")
    publication = derive_freeze_publication(tmp_path, receipt, receipt_path=path)
    assert publication.implementation_commit == implementation
    assert publication.publication_commit == git("rev-parse", "HEAD")
    assert publication.publication_committer_at.tzinfo is not None


def test_github_main_publication_requires_canonical_remote_and_exact_remote_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    publication = CandidateFreezePublication(
        freeze_receipt_id="freezereceipt_" + "a" * 64,
        freeze_receipt_digest=Digest("sha256:" + "b" * 64),
        implementation_commit="c" * 40,
        implementation_tree_digest="d" * 40,
        publication_commit="e" * 40,
        publication_committer_at=PUB,
    )
    responses: dict[tuple[str, ...], str] = {
        ("remote", "get-url", "origin"): "https://github.com/CipherCuttle/frontier.git",
        (
            "ls-remote",
            "--exit-code",
            "origin",
            "refs/heads/main",
        ): f"{publication.publication_commit}\trefs/heads/main",
    }

    def git_text(root: Path, args: list[str]) -> str:
        assert root == tmp_path
        return responses[tuple(args)]

    monkeypatch.setattr(freeze_publication_module, "_git_text", git_text)
    require_github_main_publication(tmp_path, publication)

    responses[("ls-remote", "--exit-code", "origin", "refs/heads/main")] = (
        "f" * 40 + "\trefs/heads/main"
    )
    with pytest.raises(RuntimeError, match="not current GitHub main"):
        require_github_main_publication(tmp_path, publication)

    responses[("remote", "get-url", "origin")] = "https://github.com/attacker/fork.git"
    with pytest.raises(RuntimeError, match="not canonical GitHub repository"):
        require_github_main_publication(tmp_path, publication)
