from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from .advanced_intelligence import PEF_ALGORITHM_VERSION
from .candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_RECEIPT_ID_PREFIX,
    FREEZE_SCHEMA_VERSION,
    FREEZE_SOURCE_REGISTRY_PATH,
    FreezeInputs,
    FreezeStatus,
    RegistryEntryDigest,
)
from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    require_pef_v1_configuration_identity,
)

FREEZE_V1_PREREGISTRATION_PATH = "experiments/advanced_intelligence/pef_v1/preregistration.json"
_IMPLEMENTATION_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass(frozen=True, slots=True)
class CandidateFreezeReceiptV1:
    """Durable freeze receipt binding the PEF_V1 candidate identity."""

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
    candidate_id: str = PEF_V1_CANDIDATE_ID
    experiment_id: str = PEF_V1_EXPERIMENT_ID
    algorithm_version: str = PEF_ALGORITHM_VERSION
    configuration_digest: Digest = PEF_V1_CONFIGURATION_DIGEST
    preregistration_path: str = FREEZE_V1_PREREGISTRATION_PATH
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
        if self.candidate_id != PEF_V1_CANDIDATE_ID:
            raise ValueError("PEF_V1 candidate freeze candidate id mismatch")
        if self.experiment_id != PEF_V1_EXPERIMENT_ID:
            raise ValueError("PEF_V1 candidate freeze experiment id mismatch")
        if self.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("PEF_V1 candidate freeze algorithm version mismatch")
        if self.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
            raise ValueError("PEF_V1 candidate freeze configuration digest mismatch")
        if self.preregistration_path != FREEZE_V1_PREREGISTRATION_PATH:
            raise ValueError("PEF_V1 candidate freeze preregistration path mismatch")
        if self.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("PEF_V1 candidate freeze schema version mismatch")
        if self.status is FreezeStatus.FROZEN and self.drift_reasons:
            raise ValueError("FROZEN freeze receipt cannot carry drift reasons")
        if self.status is FreezeStatus.FROZEN and self.registry_entry_digests is None:
            raise ValueError("FROZEN freeze receipt requires source registry entry digests")
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


def _drift_reasons(inputs: FreezeInputs) -> list[str]:
    reasons: list[str] = []
    if inputs.preregistration_config_digest is None:
        reasons.append("preregistration configuration digest unavailable")
    elif inputs.preregistration_config_digest != PEF_V1_CONFIGURATION_DIGEST:
        reasons.append(
            "preregistration configuration digest drifted from frozen PEF_V1 configuration"
        )
    if inputs.implementation_commit is None or inputs.implementation_tree_digest is None:
        reasons.append("implementation commit/tree digest unavailable")
    if inputs.dependency_lock_digest is None:
        reasons.append("dependency lock digest unavailable")
    if inputs.source_registry_digest is None:
        reasons.append("source registry digest unavailable")
    if inputs.registry_entry_digests is None:
        reasons.append("source registry entry digests unavailable")
    return reasons


def build_candidate_freeze_receipt_v1(
    inputs: FreezeInputs, *, frozen_at: datetime
) -> CandidateFreezeReceiptV1:
    require_pef_v1_configuration_identity()
    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        raise ValueError("freeze frozen_at must be timezone-aware")
    reasons = _drift_reasons(inputs)
    return CandidateFreezeReceiptV1(
        frozen_at=frozen_at,
        status=FreezeStatus.DRIFTED if reasons else FreezeStatus.FROZEN,
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


def verify_candidate_freeze_v1(
    receipt: CandidateFreezeReceiptV1,
    *,
    inputs: FreezeInputs,
    verified_at: datetime,
) -> CandidateFreezeReceiptV1:
    require_pef_v1_configuration_identity()
    if verified_at.tzinfo is None or verified_at.utcoffset() is None:
        raise ValueError("freeze verified_at must be timezone-aware")
    reasons: list[str] = []
    if receipt.status is FreezeStatus.DRIFTED:
        reasons.append("original freeze receipt recorded DRIFTED")
    reasons.extend(_drift_reasons(inputs))
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
    return replace(
        receipt,
        status=FreezeStatus.DRIFTED if reasons else FreezeStatus.FROZEN,
        drift_reasons=tuple(reasons),
        verified_at=verified_at,
        original_receipt_digest=receipt.receipt_digest,
    )


__all__ = [
    "FREEZE_DEPENDENCY_LOCK_PATH",
    "FREEZE_SOURCE_REGISTRY_PATH",
    "FREEZE_V1_PREREGISTRATION_PATH",
    "CandidateFreezeReceiptV1",
    "build_candidate_freeze_receipt_v1",
    "verify_candidate_freeze_v1",
]
