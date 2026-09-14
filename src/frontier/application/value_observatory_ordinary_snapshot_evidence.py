from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)
from frontier.domain.canonical_json import canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_digest

BENCHMARK_ORDINARY_SNAPSHOT_ARTIFACT_REPOSITORY = "CipherCuttle/frontier"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class OrdinarySnapshotEvidenceVerdict(StrEnum):
    EVIDENCE_COMPLETE_PENDING_AUTHORITY = "EVIDENCE_COMPLETE_PENDING_AUTHORITY"
    BLOCKED = "BLOCKED"


class OrdinarySnapshotEvidenceBlockerCode(StrEnum):
    ARTIFACT_CREATED_AFTER_HORIZON = "ARTIFACT_CREATED_AFTER_HORIZON"
    SOURCE_RETRIEVAL_AFTER_HORIZON = "SOURCE_RETRIEVAL_AFTER_HORIZON"
    SOURCE_RETRIEVAL_AFTER_ARTIFACT = "SOURCE_RETRIEVAL_AFTER_ARTIFACT"


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC offset +00:00")


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotSourceClaim:
    """Caller-supplied claim for one source inside an uploadable snapshot payload."""

    source_id: str
    knowledge_horizon: datetime
    retrieval_completed_at: datetime
    source_contract_digest: Digest
    request_identity_digest: Digest
    raw_payload_digest: Digest
    normalized_collection_digest: Digest
    raw_body_retained: bool = False

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("ordinary snapshot source_id must be non-empty")
        _require_utc(self.knowledge_horizon, "ordinary snapshot knowledge_horizon")
        _require_utc(self.retrieval_completed_at, "ordinary snapshot retrieval_completed_at")
        if self.raw_body_retained:
            raise ValueError("ordinary snapshot evidence forbids raw response-body retention")


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotPayloadClaim:
    """Uploadable snapshot payload created before GitHub assigns artifact metadata."""

    snapshot_id: str
    knowledge_horizon: datetime
    benchmark_protocol_digest: Digest
    source_registry_version: Digest
    sources: tuple[OrdinarySnapshotSourceClaim, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("ordinary snapshot_id must be non-empty")
        _require_utc(self.knowledge_horizon, "ordinary snapshot payload knowledge_horizon")


def ordinary_snapshot_payload_digest_v0(payload: OrdinarySnapshotPayloadClaim) -> Digest:
    """Canonical digest of the uploadable payload, excluding post-upload metadata."""

    sources = [
        {
            "knowledge_horizon": canonical_timestamp(source.knowledge_horizon),
            "normalized_collection_digest": source.normalized_collection_digest.value,
            "raw_body_retained": source.raw_body_retained,
            "raw_payload_digest": source.raw_payload_digest.value,
            "request_identity_digest": source.request_identity_digest.value,
            "retrieval_completed_at": canonical_timestamp(source.retrieval_completed_at),
            "source_contract_digest": source.source_contract_digest.value,
            "source_id": source.source_id,
        }
        for source in sorted(payload.sources, key=lambda item: item.source_id)
    ]
    return sha256_digest(
        canonical_json_bytes(
            {
                "benchmark_protocol_digest": payload.benchmark_protocol_digest.value,
                "knowledge_horizon": canonical_timestamp(payload.knowledge_horizon),
                "schema_version": "frontier-ordinary-snapshot-payload-v0",
                "snapshot_id": payload.snapshot_id,
                "source_registry_version": payload.source_registry_version.value,
                "sources": sources,
            }
        )
    )


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotReceiptClaim:
    """Post-upload metadata claim binding one externally stored artifact to one payload digest."""

    repository_full_name: str
    artifact_id: int
    artifact_digest: Digest
    artifact_created_at: datetime
    workflow_run_id: int
    workflow_head_sha: str
    snapshot_payload_digest: Digest
    attestation_ref: str
    attestation_digest: Digest

    def __post_init__(self) -> None:
        if self.repository_full_name != BENCHMARK_ORDINARY_SNAPSHOT_ARTIFACT_REPOSITORY:
            raise ValueError("ordinary snapshot artifact repository mismatch")
        if self.artifact_id <= 0:
            raise ValueError("ordinary snapshot artifact_id must be positive")
        if self.workflow_run_id <= 0:
            raise ValueError("ordinary snapshot workflow_run_id must be positive")
        if not _GIT_SHA_RE.fullmatch(self.workflow_head_sha):
            raise ValueError("ordinary snapshot workflow_head_sha must be a 40-hex Git SHA")
        if not self.attestation_ref.strip():
            raise ValueError("ordinary snapshot attestation_ref must be non-empty")
        _require_utc(self.artifact_created_at, "ordinary snapshot artifact_created_at")


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotEvidenceBundle:
    """Uploadable payload plus a separately created post-upload receipt claim."""

    payload: OrdinarySnapshotPayloadClaim
    receipt: OrdinarySnapshotReceiptClaim


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotEvidenceBlocker:
    code: OrdinarySnapshotEvidenceBlockerCode
    detail: str
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotEvidenceAssessment:
    """Pure structural evidence result; never implementation, scoring, or activation authority."""

    verdict: OrdinarySnapshotEvidenceVerdict
    source_ids: tuple[str, ...]
    blockers: tuple[OrdinarySnapshotEvidenceBlocker, ...]


def assess_ordinary_snapshot_evidence_v0(
    bundle: OrdinarySnapshotEvidenceBundle,
) -> OrdinarySnapshotEvidenceAssessment:
    """Assess payload/receipt consistency without trusting external authority claims.

    The payload can exist before upload because it contains no server-assigned artifact metadata.
    The receipt is created afterward and carries the GitHub artifact and attestation claims plus a
    canonical digest of the payload. All receipt authority fields are still caller supplied here,
    so even a structurally complete bundle tops out at EVIDENCE_COMPLETE_PENDING_AUTHORITY. A later
    verifier must independently retrieve the artifact/attestation, verify the artifact digest, and
    verify that the sealed payload has exactly the receipt's snapshot_payload_digest.
    """

    payload = bundle.payload
    receipt = bundle.receipt

    by_source: dict[str, OrdinarySnapshotSourceClaim] = {}
    for source in payload.sources:
        if source.source_id in by_source:
            raise ValueError(f"duplicate ordinary snapshot source claim for {source.source_id}")
        by_source[source.source_id] = source

    supplied_source_ids = frozenset(by_source)
    if supplied_source_ids != BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS:
        missing = sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - supplied_source_ids)
        extra = sorted(supplied_source_ids - BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS)
        raise ValueError(
            f"ordinary snapshot source set mismatch: missing={missing!r} extra={extra!r}"
        )

    for source in by_source.values():
        if source.knowledge_horizon != payload.knowledge_horizon:
            raise ValueError("ordinary snapshot source knowledge_horizon mismatch")

    expected_payload_digest = ordinary_snapshot_payload_digest_v0(payload)
    if receipt.snapshot_payload_digest != expected_payload_digest:
        raise ValueError("ordinary snapshot receipt payload digest mismatch")

    blockers: list[OrdinarySnapshotEvidenceBlocker] = []
    if receipt.artifact_created_at > payload.knowledge_horizon:
        blockers.append(
            OrdinarySnapshotEvidenceBlocker(
                code=OrdinarySnapshotEvidenceBlockerCode.ARTIFACT_CREATED_AFTER_HORIZON,
                detail="claimed immutable artifact was created after the knowledge horizon",
            )
        )

    for source_id in sorted(by_source):
        source = by_source[source_id]
        if source.retrieval_completed_at > payload.knowledge_horizon:
            blockers.append(
                OrdinarySnapshotEvidenceBlocker(
                    code=OrdinarySnapshotEvidenceBlockerCode.SOURCE_RETRIEVAL_AFTER_HORIZON,
                    source_id=source_id,
                    detail="source retrieval completed after the benchmark knowledge horizon",
                )
            )
        if source.retrieval_completed_at > receipt.artifact_created_at:
            blockers.append(
                OrdinarySnapshotEvidenceBlocker(
                    code=OrdinarySnapshotEvidenceBlockerCode.SOURCE_RETRIEVAL_AFTER_ARTIFACT,
                    source_id=source_id,
                    detail="source retrieval completion is later than claimed artifact creation",
                )
            )

    verdict = (
        OrdinarySnapshotEvidenceVerdict.BLOCKED
        if blockers
        else OrdinarySnapshotEvidenceVerdict.EVIDENCE_COMPLETE_PENDING_AUTHORITY
    )
    return OrdinarySnapshotEvidenceAssessment(
        verdict=verdict,
        source_ids=tuple(sorted(by_source)),
        blockers=tuple(blockers),
    )


__all__ = [
    "BENCHMARK_ORDINARY_SNAPSHOT_ARTIFACT_REPOSITORY",
    "OrdinarySnapshotEvidenceAssessment",
    "OrdinarySnapshotEvidenceBlocker",
    "OrdinarySnapshotEvidenceBlockerCode",
    "OrdinarySnapshotEvidenceBundle",
    "OrdinarySnapshotEvidenceVerdict",
    "OrdinarySnapshotPayloadClaim",
    "OrdinarySnapshotReceiptClaim",
    "OrdinarySnapshotSourceClaim",
    "assess_ordinary_snapshot_evidence_v0",
    "ordinary_snapshot_payload_digest_v0",
]
