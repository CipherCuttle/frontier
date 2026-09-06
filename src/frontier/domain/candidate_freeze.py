from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from .advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    require_pef_configuration_identity,
)
from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex

FREEZE_SCHEMA_VERSION = "candidate-freeze-receipt-v0"
FREEZE_RECEIPT_ID_PREFIX = "freezereceipt_"
FREEZE_PREREGISTRATION_PATH = "experiments/advanced_intelligence/pef_v0/preregistration.json"
FREEZE_DEPENDENCY_LOCK_PATH = "uv.lock"
FREEZE_SOURCE_REGISTRY_PATH = "sources/registry/registry_v0.json"

_FREEZE_RECEIPT_ID_RE = re.compile(r"^freezereceipt_[0-9a-f]{64}$")
_IMPLEMENTATION_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")


class FreezeStatus(StrEnum):
    """Freeze lifecycle status (R8).

    FROZEN means every bound identity component was available and consistent at
    freeze time. DRIFTED means at least one component was missing, inconsistent,
    or later drifted: drift is always explicit in the receipt and never silently
    accepted, so confirmatory evidence can be invalidated on any drift.
    """

    FROZEN = "FROZEN"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True, slots=True)
class RegistryEntryDigest:
    """Digest of a single source-registry contract entry file."""

    path: str
    digest: Digest

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {"digest": str(self.digest), "path": self.path}


@dataclass(frozen=True, slots=True)
class FreezeInputs:
    """Recomputed identity components of the PEF_V0 candidate.

    ``None`` marks a component that could not be collected in this environment
    (missing file, missing git metadata): it is never guessed or fabricated and
    always yields an explicit DRIFTED freeze (R8 fail-closed).
    """

    preregistration_digest: Digest
    preregistration_config_digest: Digest | None
    implementation_commit: str | None
    implementation_tree_digest: str | None
    dependency_lock_digest: Digest | None
    source_registry_digest: Digest | None
    registry_entry_digests: tuple[RegistryEntryDigest, ...] | None


@dataclass(frozen=True, slots=True)
class CandidateFreezeReceipt:
    """Durable freeze receipt binding the PEF_V0 candidate identity (R8).

    The receipt binds candidate identity (candidate id, algorithm version,
    experiment id, configuration digest), preregistration identity (path, file
    digest, embedded configuration digest), implementation identity (git commit
    and tree digest), dependency lock digest, and source registry version. A
    verification receipt re-binds the same structure against recomputed inputs
    and records ``verified_at`` plus the digest of the receipt it verified.
    """

    frozen_at: datetime
    status: FreezeStatus
    drift_reasons: tuple[str, ...]
    preregistration_digest: Digest
    preregistration_config_digest: Digest | None
    implementation_commit: str | None
    implementation_tree_digest: str | None
    dependency_lock_digest: Digest | None
    source_registry_digest: Digest | None
    registry_entry_digests: tuple[RegistryEntryDigest, ...] | None
    candidate_id: str = PEF_CANDIDATE_ID
    experiment_id: str = PEF_EXPERIMENT_ID
    algorithm_version: str = PEF_ALGORITHM_VERSION
    configuration_digest: Digest = PEF_CONFIGURATION_DIGEST
    preregistration_path: str = FREEZE_PREREGISTRATION_PATH
    schema_version: str = FREEZE_SCHEMA_VERSION
    verified_at: datetime | None = None
    original_receipt_digest: Digest | None = None

    def __post_init__(self) -> None:
        if self.frozen_at.tzinfo is None or self.frozen_at.utcoffset() is None:
            raise ValueError("freeze frozen_at must be timezone-aware")
        if self.verified_at is not None and (
            self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None
        ):
            raise ValueError("freeze verified_at must be timezone-aware")
        if self.candidate_id != PEF_CANDIDATE_ID:
            raise ValueError("candidate freeze candidate id mismatch")
        if self.experiment_id != PEF_EXPERIMENT_ID:
            raise ValueError("candidate freeze experiment id mismatch")
        if self.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("candidate freeze algorithm version mismatch")
        if self.configuration_digest != PEF_CONFIGURATION_DIGEST:
            raise ValueError("candidate freeze configuration digest mismatch")
        if self.preregistration_path != FREEZE_PREREGISTRATION_PATH:
            raise ValueError("candidate freeze preregistration path mismatch")
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("candidate freeze schema version mismatch")
        if self.status is FreezeStatus.FROZEN and self.drift_reasons:
            raise ValueError("FROZEN freeze receipt cannot carry drift reasons")
        if self.status is FreezeStatus.DRIFTED and not self.drift_reasons:
            raise ValueError("DRIFTED freeze receipt requires explicit drift reasons")
        if self.original_receipt_digest is not None and self.verified_at is None:
            raise ValueError("original receipt binding requires a verification timestamp")
        if self.implementation_commit is not None and not _IMPLEMENTATION_HASH_RE.fullmatch(
            self.implementation_commit
        ):
            raise ValueError("implementation commit is not a git commit hash")
        if self.implementation_tree_digest is not None and not _IMPLEMENTATION_HASH_RE.fullmatch(
            self.implementation_tree_digest
        ):
            raise ValueError("implementation tree digest is not a git tree hash")

    @property
    def receipt_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    @property
    def receipt_id(self) -> str:
        return FREEZE_RECEIPT_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        entries: list[CanonicalValue] | None = None
        if self.registry_entry_digests is not None:
            entries = [entry.to_canonical() for entry in self.registry_entry_digests]
        return {
            "algorithm_version": self.algorithm_version,
            "candidate_id": self.candidate_id,
            "configuration_digest": str(self.configuration_digest),
            "dependency_lock_digest": (
                None if self.dependency_lock_digest is None else str(self.dependency_lock_digest)
            ),
            "drift_reasons": list(self.drift_reasons),
            "experiment_id": self.experiment_id,
            "frozen_at": canonical_timestamp(self.frozen_at),
            "implementation_commit": self.implementation_commit,
            "implementation_tree_digest": self.implementation_tree_digest,
            "original_receipt_digest": (
                None if self.original_receipt_digest is None else str(self.original_receipt_digest)
            ),
            "preregistration_config_digest": (
                None
                if self.preregistration_config_digest is None
                else str(self.preregistration_config_digest)
            ),
            "preregistration_digest": str(self.preregistration_digest),
            "preregistration_path": self.preregistration_path,
            "registry_entry_digests": entries,
            "schema_version": self.schema_version,
            "source_registry_digest": (
                None if self.source_registry_digest is None else str(self.source_registry_digest)
            ),
            "status": self.status.value,
            "verified_at": (
                None if self.verified_at is None else canonical_timestamp(self.verified_at)
            ),
        }


def _preregistration_drift_reasons(inputs: FreezeInputs) -> list[str]:
    reasons: list[str] = []
    if inputs.preregistration_config_digest is None:
        reasons.append("preregistration configuration digest unavailable")
    elif inputs.preregistration_config_digest != PEF_CONFIGURATION_DIGEST:
        reasons.append("preregistration configuration digest drifted from frozen PEF configuration")
    return reasons


def build_candidate_freeze_receipt(
    inputs: FreezeInputs, *, frozen_at: datetime
) -> CandidateFreezeReceipt:
    """Freeze the candidate identity; any missing/inconsistent component drifts.

    Fail-closed (R8): a component that cannot be collected is recorded as an
    explicit DRIFTED freeze with a concrete reason, never as a guessed value.
    """
    require_pef_configuration_identity()
    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        raise ValueError("freeze frozen_at must be timezone-aware")

    reasons: list[str] = []
    reasons.extend(_preregistration_drift_reasons(inputs))
    if inputs.implementation_commit is None or inputs.implementation_tree_digest is None:
        reasons.append("implementation commit/tree digest unavailable")
    if inputs.dependency_lock_digest is None:
        reasons.append("dependency lock digest unavailable")
    if inputs.source_registry_digest is None:
        reasons.append("source registry digest unavailable")
    status = FreezeStatus.DRIFTED if reasons else FreezeStatus.FROZEN
    return CandidateFreezeReceipt(
        frozen_at=frozen_at,
        status=status,
        drift_reasons=tuple(reasons),
        preregistration_digest=inputs.preregistration_digest,
        preregistration_config_digest=inputs.preregistration_config_digest,
        implementation_commit=inputs.implementation_commit,
        implementation_tree_digest=inputs.implementation_tree_digest,
        dependency_lock_digest=inputs.dependency_lock_digest,
        source_registry_digest=inputs.source_registry_digest,
        registry_entry_digests=inputs.registry_entry_digests,
    )


def _mismatch(reasons: list[str], *, label: str, frozen: object, recomputed: object) -> None:
    if frozen is None:
        reasons.append(f"{label} was not bound in the original freeze receipt")
    elif recomputed is None:
        reasons.append(f"{label} unavailable at verification time")
    elif frozen != recomputed:
        reasons.append(f"{label} drifted")


def verify_candidate_freeze(
    receipt: CandidateFreezeReceipt,
    *,
    inputs: FreezeInputs,
    verified_at: datetime,
) -> CandidateFreezeReceipt:
    """Recompute each freeze component and produce an explicit drift report.

    ANY drift (configuration digest, preregistration digest, dependency lock,
    registry, implementation commit/tree) yields a DRIFTED verification receipt;
    drift is never silently accepted (R8). A previously DRIFTED freeze stays
    DRIFTED even when the live inputs now match, because the freeze itself was
    taken with drift.
    """
    require_pef_configuration_identity()
    if verified_at.tzinfo is None or verified_at.utcoffset() is None:
        raise ValueError("freeze verified_at must be timezone-aware")

    reasons: list[str] = []
    if receipt.status is FreezeStatus.DRIFTED:
        reasons.append("original freeze receipt recorded DRIFTED")
    reasons.extend(_preregistration_drift_reasons(inputs))
    _mismatch(
        reasons,
        label="preregistration file digest",
        frozen=receipt.preregistration_digest,
        recomputed=inputs.preregistration_digest,
    )
    _mismatch(
        reasons,
        label="preregistration configuration digest",
        frozen=receipt.preregistration_config_digest,
        recomputed=inputs.preregistration_config_digest,
    )
    _mismatch(
        reasons,
        label="implementation commit",
        frozen=receipt.implementation_commit,
        recomputed=inputs.implementation_commit,
    )
    _mismatch(
        reasons,
        label="implementation tree digest",
        frozen=receipt.implementation_tree_digest,
        recomputed=inputs.implementation_tree_digest,
    )
    _mismatch(
        reasons,
        label="dependency lock digest",
        frozen=receipt.dependency_lock_digest,
        recomputed=inputs.dependency_lock_digest,
    )
    _mismatch(
        reasons,
        label="source registry digest",
        frozen=receipt.source_registry_digest,
        recomputed=inputs.source_registry_digest,
    )
    _mismatch(
        reasons,
        label="source registry entry digests",
        frozen=receipt.registry_entry_digests,
        recomputed=inputs.registry_entry_digests,
    )
    status = FreezeStatus.DRIFTED if reasons else FreezeStatus.FROZEN
    return replace(
        receipt,
        status=status,
        drift_reasons=tuple(reasons),
        verified_at=verified_at,
        original_receipt_digest=receipt.receipt_digest,
    )


def freeze_receipt_id(receipt_digest: Digest) -> str:
    """Derive the receipt id from a receipt digest."""
    text = receipt_digest.value
    if not text.startswith("sha256:"):
        raise ValueError("freeze receipt digest must be a sha256 digest")
    return FREEZE_RECEIPT_ID_PREFIX + text.removeprefix("sha256:")


def canonical_freeze_components(
    candidate_freeze_receipt_id: str | None,
) -> str | None:
    """Normalize an optional freeze-receipt binding for shadow runs (R8)."""
    if candidate_freeze_receipt_id is None:
        return None
    if not _FREEZE_RECEIPT_ID_RE.fullmatch(candidate_freeze_receipt_id):
        raise ValueError("invalid candidate freeze receipt id binding")
    return candidate_freeze_receipt_id


__all__ = [
    "FREEZE_DEPENDENCY_LOCK_PATH",
    "FREEZE_PREREGISTRATION_PATH",
    "FREEZE_RECEIPT_ID_PREFIX",
    "FREEZE_SCHEMA_VERSION",
    "FREEZE_SOURCE_REGISTRY_PATH",
    "FreezeInputs",
    "FreezeStatus",
    "RegistryEntryDigest",
    "build_candidate_freeze_receipt",
    "canonical_freeze_components",
    "freeze_receipt_id",
    "verify_candidate_freeze",
]
