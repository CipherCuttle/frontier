from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.domain.candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_PREREGISTRATION_PATH,
    FREEZE_SOURCE_REGISTRY_PATH,
    CandidateFreezeReceipt,
    FreezeInputs,
    RegistryEntryDigest,
    build_candidate_freeze_receipt,
    verify_candidate_freeze,
)
from frontier.domain.digests import Digest, sha256_digest

_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")


def _read_digest(path: Path) -> Digest | None:
    try:
        return sha256_digest(path.read_bytes())
    except FileNotFoundError, IsADirectoryError, PermissionError:
        return None


def _load_json_document(path: Path) -> dict[str, object] | None:
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return cast(dict[str, object], raw)


def _preregistration_config_digest(path: Path, file_digest: Digest | None) -> Digest | None:
    if file_digest is None:
        return None
    document = _load_json_document(path)
    if document is None:
        return None
    candidate = document.get("candidate")
    if not isinstance(candidate, dict):
        return None
    config_digest = cast(dict[str, object], candidate).get("configuration_digest")
    if isinstance(config_digest, str) and config_digest.startswith("sha256:"):
        try:
            return Digest(config_digest)
        except ValueError:
            return None
    return None


def _registry_entry_digests(root: Path, path: Path) -> tuple[RegistryEntryDigest, ...] | None:
    document = _load_json_document(path)
    if document is None:
        return None
    raw_paths = document.get("source_contract_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return None
    entry_paths = cast(list[object], raw_paths)
    entries: list[RegistryEntryDigest] = []
    for item in entry_paths:
        if not isinstance(item, str):
            return None
        entry_digest = _read_digest(root / item)
        if entry_digest is None:
            return None
        entries.append(RegistryEntryDigest(path=item, digest=entry_digest))
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _git_identity(root: Path) -> tuple[str | None, str | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
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


def collect_freeze_inputs(root: Path) -> FreezeInputs:
    """Collect the recomputed candidate identity components (fail-closed).

    Every unavailable component (missing lock/registry file, missing git
    metadata, unparsable preregistration) is returned as ``None`` so it can be
    recorded as explicit DRIFT in the receipt rather than guessed or fabricated
    (R8). Only the preregistration document itself must exist: it is the
    identity anchor of the freeze, so a missing one is a hard error.
    """
    preregistration_path = root / FREEZE_PREREGISTRATION_PATH
    preregistration_digest = _read_digest(preregistration_path)
    if preregistration_digest is None:
        raise FileNotFoundError(f"preregistration file missing: {FREEZE_PREREGISTRATION_PATH}")
    commit, tree = _git_identity(root)
    return FreezeInputs(
        preregistration_digest=preregistration_digest,
        preregistration_config_digest=_preregistration_config_digest(
            preregistration_path, preregistration_digest
        ),
        implementation_commit=commit,
        implementation_tree_digest=tree,
        dependency_lock_digest=_read_digest(root / FREEZE_DEPENDENCY_LOCK_PATH),
        source_registry_digest=_read_digest(root / FREEZE_SOURCE_REGISTRY_PATH),
        registry_entry_digests=_registry_entry_digests(root, root / FREEZE_SOURCE_REGISTRY_PATH),
    )


def freeze_candidate(root: Path, *, frozen_at: datetime) -> CandidateFreezeReceipt:
    """Create a candidate freeze receipt from the live repository identity."""
    inputs = collect_freeze_inputs(root)
    return build_candidate_freeze_receipt(inputs, frozen_at=frozen_at)


def verify_freeze(
    receipt: CandidateFreezeReceipt, *, root: Path, verified_at: datetime
) -> CandidateFreezeReceipt:
    """Recompute every freeze component and return an explicit drift report."""
    inputs = collect_freeze_inputs(root)
    return verify_candidate_freeze(receipt, inputs=inputs, verified_at=verified_at)
