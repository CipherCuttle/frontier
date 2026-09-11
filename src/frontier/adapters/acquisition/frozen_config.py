from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import cast

from .config import SourceRegistry, load_source_registry

_REGISTRY_PATH = "sources/registry/registry_v0.json"


def _git_blob(root: Path, *, ref: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"frozen source registry blob unavailable: {path}") from error
    return result.stdout


def _contract_paths(registry_blob: bytes) -> tuple[str, ...]:
    try:
        raw = cast(object, json.loads(registry_blob.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("frozen source registry is not valid UTF-8 JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("frozen source registry must be a JSON object")
    paths = cast(dict[str, object], raw).get("source_contract_paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("frozen source registry has no source_contract_paths")

    result: list[str] = []
    for value in cast(list[object], paths):
        if not isinstance(value, str) or not value:
            raise ValueError("frozen source registry contains an invalid contract path")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("sources", "registry"):
            raise ValueError("frozen source registry contract path escapes sources/registry")
        result.append(value)
    return tuple(result)


def load_source_registry_from_git_ref(root: Path, ref: str) -> SourceRegistry:
    """Load the exact source registry and contracts stored at ``ref``.

    Confirmatory callers use this instead of the mutable worktree so later
    operational source-contract repairs cannot silently alter a frozen
    experiment's source membership, roles, cadence, or registry identity.
    The ordinary registry loader performs the canonical schema/digest checks on
    the materialized Git blobs before any SourceRegistry is returned.
    """
    if not ref:
        raise ValueError("frozen source registry requires a non-empty Git ref")

    registry_blob = _git_blob(root, ref=ref, path=_REGISTRY_PATH)
    contract_paths = _contract_paths(registry_blob)
    blobs = {path: _git_blob(root, ref=ref, path=path) for path in contract_paths}

    with TemporaryDirectory(prefix="frontier-frozen-registry-") as directory:
        frozen_root = Path(directory)
        registry_target = frozen_root / _REGISTRY_PATH
        registry_target.parent.mkdir(parents=True, exist_ok=True)
        registry_target.write_bytes(registry_blob)
        for path, blob in blobs.items():
            target = frozen_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        return load_source_registry(frozen_root)


__all__ = ["load_source_registry_from_git_ref"]
