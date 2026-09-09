from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.domain.candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_SOURCE_REGISTRY_PATH,
    FreezeInputs,
    RegistryEntryDigest,
)
from frontier.domain.candidate_freeze_v1 import (
    FREEZE_V1_PREREGISTRATION_PATH,
    CandidateFreezeReceiptV1,
    build_candidate_freeze_receipt_v1,
    verify_candidate_freeze_v1,
)
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.pef_v1 import PEF_V1_CANDIDATE_ID, PEF_V1_EXPERIMENT_ID

_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")


def _git_blob(root: Path, *, ref: str, path: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return result.stdout


def _load_json_blob(blob: bytes | None) -> dict[str, object] | None:
    if blob is None:
        return None
    try:
        raw = cast(object, json.loads(blob.decode("utf-8")))
    except UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return cast(dict[str, object], raw)


def _blob_digest(blob: bytes | None) -> Digest | None:
    return None if blob is None else sha256_digest(blob)


def _registry_entry_digests(
    root: Path,
    *,
    ref: str,
    registry_blob: bytes | None,
) -> tuple[RegistryEntryDigest, ...] | None:
    document = _load_json_blob(registry_blob)
    if document is None:
        return None
    raw_paths = document.get("source_contract_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return None
    entries: list[RegistryEntryDigest] = []
    for item in cast(list[object], raw_paths):
        if not isinstance(item, str):
            return None
        entry_digest = _blob_digest(_git_blob(root, ref=ref, path=item))
        if entry_digest is None:
            return None
        entries.append(RegistryEntryDigest(path=item, digest=entry_digest))
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _git_identity(root: Path, *, ref: str = "HEAD") -> tuple[str | None, str | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        tree = subprocess.run(
            ["git", "rev-parse", f"{ref}^{{tree}}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except OSError, subprocess.SubprocessError:
        return (None, None)
    commit_hash = commit.stdout.strip()
    tree_hash = tree.stdout.strip()
    if not _COMMIT_HASH_RE.fullmatch(commit_hash) or not _COMMIT_HASH_RE.fullmatch(tree_hash):
        return (None, None)
    return (commit_hash, tree_hash)


def _v1_preregistration_config_digest(document: dict[str, object] | None) -> Digest | None:
    if document is None:
        return None
    if document.get("experiment_id") != PEF_V1_EXPERIMENT_ID:
        return None
    if document.get("candidate_id") != PEF_V1_CANDIDATE_ID:
        return None
    raw_overrides = document.get("frozen_overrides")
    if not isinstance(raw_overrides, list):
        return None
    matches: list[str] = []
    for raw_override in cast(list[object], raw_overrides):
        if not isinstance(raw_override, dict):
            return None
        override = cast(dict[str, object], raw_override)
        if override.get("json_pointer") != "/candidate/configuration_digest":
            continue
        value = override.get("value")
        if not isinstance(value, str):
            return None
        matches.append(value)
    if len(matches) != 1 or not matches[0].startswith("sha256:"):
        return None
    try:
        return Digest(matches[0])
    except ValueError:
        return None


def collect_freeze_inputs_v1(root: Path, *, implementation_ref: str | None = None) -> FreezeInputs:
    """Collect exact PEF_V1 freeze inputs from the selected Git tree."""
    ref = implementation_ref or "HEAD"
    commit, tree = _git_identity(root, ref=ref)
    preregistration_blob = _git_blob(root, ref=ref, path=FREEZE_V1_PREREGISTRATION_PATH)
    if preregistration_blob is None:
        raise FileNotFoundError(f"preregistration file missing: {FREEZE_V1_PREREGISTRATION_PATH}")
    dependency_lock_blob = _git_blob(root, ref=ref, path=FREEZE_DEPENDENCY_LOCK_PATH)
    source_registry_blob = _git_blob(root, ref=ref, path=FREEZE_SOURCE_REGISTRY_PATH)
    return FreezeInputs(
        preregistration_digest=sha256_digest(preregistration_blob),
        preregistration_config_digest=_v1_preregistration_config_digest(
            _load_json_blob(preregistration_blob)
        ),
        implementation_commit=commit,
        implementation_tree_digest=tree,
        dependency_lock_digest=_blob_digest(dependency_lock_blob),
        source_registry_digest=_blob_digest(source_registry_blob),
        registry_entry_digests=_registry_entry_digests(
            root,
            ref=ref,
            registry_blob=source_registry_blob,
        ),
    )


def freeze_candidate_v1(
    root: Path,
    *,
    frozen_at: datetime,
    implementation_ref: str | None = None,
) -> CandidateFreezeReceiptV1:
    inputs = collect_freeze_inputs_v1(root, implementation_ref=implementation_ref)
    return build_candidate_freeze_receipt_v1(inputs, frozen_at=frozen_at)


def verify_freeze_v1(
    receipt: CandidateFreezeReceiptV1,
    *,
    root: Path,
    verified_at: datetime,
    implementation_ref: str | None = None,
) -> CandidateFreezeReceiptV1:
    inputs = collect_freeze_inputs_v1(root, implementation_ref=implementation_ref)
    return verify_candidate_freeze_v1(receipt, inputs=inputs, verified_at=verified_at)


__all__ = [
    "collect_freeze_inputs_v1",
    "freeze_candidate_v1",
    "verify_freeze_v1",
]
