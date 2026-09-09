from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.application.candidate_freeze import (
    _git_identity,
    _load_json_document,
    _read_digest,
    _registry_entry_digests,
)
from frontier.domain.candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_SOURCE_REGISTRY_PATH,
    FreezeInputs,
)
from frontier.domain.candidate_freeze_v1 import (
    FREEZE_V1_PREREGISTRATION_PATH,
    CandidateFreezeReceiptV1,
    build_candidate_freeze_receipt_v1,
    verify_candidate_freeze_v1,
)
from frontier.domain.digests import Digest
from frontier.domain.pef_v1 import PEF_V1_CANDIDATE_ID, PEF_V1_EXPERIMENT_ID


def _v1_preregistration_config_digest(path: Path, file_digest: Digest | None) -> Digest | None:
    if file_digest is None:
        return None
    document = _load_json_document(path)
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


def collect_freeze_inputs_v1(
    root: Path, *, implementation_ref: str | None = None
) -> FreezeInputs:
    """Collect the exact PEF_V1 freeze inputs without touching PEF_V0 semantics."""
    preregistration_path = root / FREEZE_V1_PREREGISTRATION_PATH
    preregistration_digest = _read_digest(preregistration_path)
    if preregistration_digest is None:
        raise FileNotFoundError(
            f"preregistration file missing: {FREEZE_V1_PREREGISTRATION_PATH}"
        )
    commit, tree = _git_identity(root, ref=implementation_ref or "HEAD")
    return FreezeInputs(
        preregistration_digest=preregistration_digest,
        preregistration_config_digest=_v1_preregistration_config_digest(
            preregistration_path, preregistration_digest
        ),
        implementation_commit=commit,
        implementation_tree_digest=tree,
        dependency_lock_digest=_read_digest(root / FREEZE_DEPENDENCY_LOCK_PATH),
        source_registry_digest=_read_digest(root / FREEZE_SOURCE_REGISTRY_PATH),
        registry_entry_digests=_registry_entry_digests(root, root / FREEZE_SOURCE_REGISTRY_PATH),
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
