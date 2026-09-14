from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)
from frontier.domain.digests import Digest

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
    """Caller-supplied claim for one source inside a prospective comparator snapshot."""

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
class OrdinarySnapshotArtifactClaim:
    """Unverified external-artifact metadata claim; not trusted publication authority."""

    repository_full_name: str
    artifact_id: int
    artifact_digest: Digest
    artifact_created_at: datetime
    workflow_run_id: int
    workflow_head_sha: str
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
    """One caller-supplied candidate snapshot bundle targeting one exact benchmark horizon."""

    snapshot_id: str
    knowledge_horizon: datetime
    benchmark_protocol_digest: Digest
    source_registry_version: Digest
    artifact: OrdinarySnapshotArtifactClaim
    sources: tuple[OrdinarySnapshotSourceClaim, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("ordinary snapshot_id must be non-empty")
        _require_utc(self.knowledge_horizon, "ordinary snapshot bundle knowledge_horizon")


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
    """Assess a claimed pre-horizon snapshot without trusting caller-supplied authority metadata.

    This function can establish only internal evidence completeness. GitHub artifact timestamps,
    digests, workflow identity, attestations, protocol identity, and source-contract identity are
    still caller supplied here. Even a structurally complete bundle therefore tops out at
    EVIDENCE_COMPLETE_PENDING_AUTHORITY. A later independently reviewed verifier must retrieve and
    bind the external authority material before any executor implementation or scored use is
    authorized.
    """

    by_source: dict[str, OrdinarySnapshotSourceClaim] = {}
    for source in bundle.sources:
        if source.source_id in by_source:
            raise ValueError(f"duplicate ordinary snapshot source claim for {source.source_id}")
        by_source[source.source_id] = source

    supplied_source_ids = frozenset(by_source)
    if supplied_source_ids != BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS:
        missing = sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS - supplied_source_ids)
        extra = sorted(supplied_source_ids - BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS)
        raise ValueError(
            "ordinary snapshot source set mismatch: "
            f"missing={missing!r} extra={extra!r}"
        )

    for source in by_source.values():
        if source.knowledge_horizon != bundle.knowledge_horizon:
            raise ValueError("ordinary snapshot source knowledge_horizon mismatch")

    blockers: list[OrdinarySnapshotEvidenceBlocker] = []
    if bundle.artifact.artifact_created_at > bundle.knowledge_horizon:
        blockers.append(
            OrdinarySnapshotEvidenceBlocker(
                code=OrdinarySnapshotEvidenceBlockerCode.ARTIFACT_CREATED_AFTER_HORIZON,
                detail="claimed immutable artifact was created after the benchmark knowledge horizon",
            )
        )

    for source_id in sorted(by_source):
        source = by_source[source_id]
        if source.retrieval_completed_at > bundle.knowledge_horizon:
            blockers.append(
                OrdinarySnapshotEvidenceBlocker(
                    code=OrdinarySnapshotEvidenceBlockerCode.SOURCE_RETRIEVAL_AFTER_HORIZON,
                    source_id=source_id,
                    detail="source retrieval completed after the benchmark knowledge horizon",
                )
            )
        if source.retrieval_completed_at > bundle.artifact.artifact_created_at:
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
    "OrdinarySnapshotArtifactClaim",
    "OrdinarySnapshotEvidenceAssessment",
    "OrdinarySnapshotEvidenceBlocker",
    "OrdinarySnapshotEvidenceBlockerCode",
    "OrdinarySnapshotEvidenceBundle",
    "OrdinarySnapshotEvidenceVerdict",
    "OrdinarySnapshotSourceClaim",
    "assess_ordinary_snapshot_evidence_v0",
]
