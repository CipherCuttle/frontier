from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from frontier.adapters.acquisition.frozen_config import load_source_registry_from_git_ref

ROOT = Path(".")


def _init_registry_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "sources", repo / "sources")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "frontier@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Frontier Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "sources"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "freeze registry"], cwd=repo, check=True, capture_output=True
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, commit


def test_frozen_registry_loader_ignores_later_worktree_contract_drift(tmp_path: Path) -> None:
    repo, frozen_commit = _init_registry_repo(tmp_path)
    frozen = load_source_registry_from_git_ref(repo, frozen_commit)
    original_endpoint = frozen.require("hf.models").endpoint_url

    contract_path = repo / "sources/registry/hf.models.v0.json"
    raw = json.loads(contract_path.read_text(encoding="utf-8"))
    raw["endpoint"]["url"] = "https://example.invalid/drifted"
    contract_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    replayed = load_source_registry_from_git_ref(repo, frozen_commit)
    assert replayed.source_registry_version == frozen.source_registry_version
    assert replayed.require("hf.models").endpoint_url == original_endpoint
    assert replayed.require("hf.models").endpoint_url != "https://example.invalid/drifted"


def test_frozen_registry_loader_fails_closed_for_missing_ref(tmp_path: Path) -> None:
    repo, _frozen_commit = _init_registry_repo(tmp_path)
    with pytest.raises(ValueError, match="frozen source registry blob unavailable"):
        load_source_registry_from_git_ref(repo, "0" * 40)


def test_frozen_registry_loader_rejects_contract_path_escape(tmp_path: Path) -> None:
    repo, _frozen_commit = _init_registry_repo(tmp_path)
    registry_path = repo / "sources/registry/registry_v0.json"
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    raw["source_contract_paths"] = ["../outside.json"]
    registry_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    subprocess.run(["git", "add", str(registry_path.relative_to(repo))], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "hostile registry"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    hostile_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(ValueError, match="escapes sources/registry"):
        load_source_registry_from_git_ref(repo, hostile_commit)
