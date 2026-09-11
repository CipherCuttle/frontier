from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from frontier.cli.pef_v1_confirmatory import require_pinned_operator_commit


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> str:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "frontier@example.test")
    _git(tmp_path, "config", "user.name", "Frontier Test")
    (tmp_path / "operator.txt").write_text("reviewed\n", encoding="utf-8")
    _git(tmp_path, "add", "operator.txt")
    _git(tmp_path, "commit", "-m", "reviewed operator")
    return _git(tmp_path, "rev-parse", "HEAD")


def test_operator_commit_requires_authority_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    monkeypatch.delenv("FRONTIER_PEF_V1_OPERATOR_COMMIT", raising=False)

    with pytest.raises(ValueError, match="requires FRONTIER_PEF_V1_OPERATOR_COMMIT"):
        require_pinned_operator_commit(tmp_path)


def test_operator_commit_rejects_descendant_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewed = _repo(tmp_path)
    monkeypatch.setenv("FRONTIER_PEF_V1_OPERATOR_COMMIT", reviewed)
    (tmp_path / "later.txt").write_text("descendant\n", encoding="utf-8")
    _git(tmp_path, "add", "later.txt")
    _git(tmp_path, "commit", "-m", "later runtime")

    with pytest.raises(ValueError, match="does not match pinned operator commit"):
        require_pinned_operator_commit(tmp_path)


def test_operator_commit_accepts_exact_reviewed_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewed = _repo(tmp_path)
    monkeypatch.setenv("FRONTIER_PEF_V1_OPERATOR_COMMIT", reviewed)

    assert require_pinned_operator_commit(tmp_path) == reviewed
