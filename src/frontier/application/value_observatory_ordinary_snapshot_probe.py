from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from frontier.adapters.acquisition.config import FetchPolicy, RegisteredSource, SourceRegistry
from frontier.adapters.acquisition.normalizers import (
    NormalizationError,
    NormalizedBatch,
    normalize_source,
)
from frontier.application.ports.fetcher import FetcherPort
from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)
from frontier.application.value_observatory_ordinary_snapshot_evidence import (
    OrdinarySnapshotPayloadClaim,
    OrdinarySnapshotSourceClaim,
    ordinary_snapshot_payload_digest_v0,
)
from frontier.contracts.fetch import FetchOutcome, FetchRequest
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.observation import ObservationCandidate

ORDINARY_SNAPSHOT_PROBE_ARTIFACT_SCHEMA = "frontier-ordinary-snapshot-probe-artifact-v0"
ORDINARY_SNAPSHOT_PROBE_REPORT_SCHEMA = "frontier-ordinary-snapshot-probe-report-v0"


class OrdinarySnapshotProbeStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotProbeSourceResult:
    source_id: str
    status: OrdinarySnapshotProbeStatus
    retrieval_completed_at: datetime
    request_identity_digest: Digest
    raw_payload_digest: Digest | None
    normalized_collection_digest: Digest | None
    source_contract_digest: Digest
    normalized_collection: dict[str, CanonicalValue] | None
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotProbeResult:
    snapshot_id: str
    authority_ref: str
    knowledge_horizon: datetime
    source_registry_version: Digest
    benchmark_protocol_digest: Digest
    sources: tuple[OrdinarySnapshotProbeSourceResult, ...]
    payload: OrdinarySnapshotPayloadClaim | None

    @property
    def status(self) -> OrdinarySnapshotProbeStatus:
        return (
            OrdinarySnapshotProbeStatus.COMPLETE
            if self.payload is not None
            else OrdinarySnapshotProbeStatus.FAILED
        )


def _source_contract_digest(source: RegisteredSource) -> Digest:
    return sha256_digest(canonical_json_bytes(source.raw_contract))


def _request_for_probe(
    source: RegisteredSource,
    policy: FetchPolicy,
    *,
    snapshot_id: str,
) -> FetchRequest:
    if source.policy_profile != policy.policy_profile:
        raise ValueError("source policy profile does not match loaded fetch policy")
    headers = {
        "Accept": ", ".join(source.accepted_content_types),
        "User-Agent": "FRONTIER/0.1 (+https://github.com/CipherCuttle/frontier)",
    }
    return FetchRequest(
        request_id=f"{snapshot_id}:{source.contract.source_id}",
        source_id=source.contract.source_id,
        url=source.endpoint_url,
        policy_profile=source.policy_profile,
        credential_ref=source.credential_ref,
        accepted_content_types=source.accepted_content_types,
        deadline_ms=policy.deadline_ms,
        max_response_bytes=policy.max_response_bytes,
        max_redirects=policy.max_redirects,
        request_headers=headers,
    )


def request_identity_digest_v0(request: FetchRequest) -> Digest:
    return sha256_digest(
        canonical_json_bytes(
            {
                "accepted_content_types": list(request.accepted_content_types),
                "deadline_ms": request.deadline_ms,
                "max_redirects": request.max_redirects,
                "max_response_bytes": request.max_response_bytes,
                "policy_profile": request.policy_profile,
                "request_headers": {
                    key: request.request_headers[key] for key in sorted(request.request_headers)
                },
                "schema_version": "frontier-ordinary-snapshot-request-v0",
                "source_id": request.source_id,
                "url": request.url,
            }
        )
    )


def _candidate_material(candidate: ObservationCandidate, ordinal: int) -> dict[str, CanonicalValue]:
    return {
        "identity": candidate.identity_material(),
        "observation_id": candidate.observation_id,
        "ordinal": ordinal,
    }


def normalized_collection_material_v0(
    *,
    source_id: str,
    retrieval_completed_at: datetime,
    batch: NormalizedBatch,
) -> dict[str, CanonicalValue]:
    return {
        "completeness_health": batch.completeness_health.value,
        "details": batch.details,
        "items": [
            _candidate_material(candidate, ordinal)
            for ordinal, candidate in enumerate(batch.candidates)
        ],
        "records_received": batch.records_received,
        "records_rejected": batch.records_rejected,
        "retrieval_completed_at": canonical_timestamp(retrieval_completed_at),
        "schema_health": batch.schema_health.value,
        "schema_version": "frontier-ordinary-normalized-collection-v0",
        "source_id": source_id,
    }


def payload_claim_material_v0(payload: OrdinarySnapshotPayloadClaim) -> dict[str, CanonicalValue]:
    return {
        "benchmark_protocol_digest": payload.benchmark_protocol_digest.value,
        "knowledge_horizon": canonical_timestamp(payload.knowledge_horizon),
        "snapshot_id": payload.snapshot_id,
        "source_registry_version": payload.source_registry_version.value,
        "sources": [
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
        ],
    }


def ordinary_snapshot_probe_artifact_v0(
    result: OrdinarySnapshotProbeResult,
) -> dict[str, CanonicalValue]:
    if result.payload is None:
        raise ValueError("failed ordinary snapshot probe has no uploadable snapshot payload")
    collections: list[CanonicalValue] = []
    for source in sorted(result.sources, key=lambda item: item.source_id):
        if source.normalized_collection is None:
            raise ValueError("complete ordinary snapshot probe is missing normalized collection")
        if source.normalized_collection_digest != sha256_digest(
            canonical_json_bytes(source.normalized_collection)
        ):
            raise ValueError("ordinary snapshot normalized collection digest mismatch")
        collections.append(source.normalized_collection)
    return {
        "authority_ref": result.authority_ref,
        "normalized_collections": collections,
        "payload_claim": payload_claim_material_v0(result.payload),
        "schema_version": ORDINARY_SNAPSHOT_PROBE_ARTIFACT_SCHEMA,
        "snapshot_payload_digest": ordinary_snapshot_payload_digest_v0(result.payload).value,
    }


def ordinary_snapshot_probe_report_v0(
    result: OrdinarySnapshotProbeResult,
) -> dict[str, CanonicalValue]:
    return {
        "authority_ref": result.authority_ref,
        "benchmark_protocol_digest": result.benchmark_protocol_digest.value,
        "knowledge_horizon": canonical_timestamp(result.knowledge_horizon),
        "schema_version": ORDINARY_SNAPSHOT_PROBE_REPORT_SCHEMA,
        "snapshot_id": result.snapshot_id,
        "snapshot_payload_digest": (
            ordinary_snapshot_payload_digest_v0(result.payload).value
            if result.payload is not None
            else None
        ),
        "source_registry_version": result.source_registry_version.value,
        "sources": [
            {
                "failure_code": source.failure_code,
                "normalized_collection_digest": (
                    source.normalized_collection_digest.value
                    if source.normalized_collection_digest is not None
                    else None
                ),
                "raw_payload_digest": (
                    source.raw_payload_digest.value
                    if source.raw_payload_digest is not None
                    else None
                ),
                "request_identity_digest": source.request_identity_digest.value,
                "retrieval_completed_at": canonical_timestamp(source.retrieval_completed_at),
                "source_contract_digest": source.source_contract_digest.value,
                "source_id": source.source_id,
                "status": source.status.value,
            }
            for source in sorted(result.sources, key=lambda item: item.source_id)
        ],
        "status": result.status.value,
    }


async def _probe_source(
    *,
    source: RegisteredSource,
    policy: FetchPolicy,
    fetcher: FetcherPort,
    snapshot_id: str,
) -> OrdinarySnapshotProbeSourceResult:
    request = _request_for_probe(source, policy, snapshot_id=snapshot_id)
    request_digest = request_identity_digest_v0(request)
    contract_digest = _source_contract_digest(source)
    result = await fetcher.fetch(request)
    retrieved_at = result.retrieved_at

    if result.outcome is not FetchOutcome.SUCCESS:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=result.body_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code=result.failure.code if result.failure is not None else "FETCH_FAILED",
        )
    if result.http_status != 200:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=result.body_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code="UNEXPECTED_SUCCESS_STATUS",
        )
    if result.body is None:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=result.body_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code="FETCH_BODY_MISSING",
        )

    trusted_digest = sha256_digest(result.body)
    if result.body_digest != trusted_digest:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=trusted_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code="FETCH_DIGEST_MISMATCH",
        )
    actual_type = (result.content_type or "").lower()
    if actual_type not in {value.lower() for value in source.accepted_content_types}:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=trusted_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code="CONTENT_TYPE_UNEXPECTED",
        )
    try:
        batch = normalize_source(
            source.contract.source_id,
            result.body,
            retrieved_at=retrieved_at,
            fetch_digest=trusted_digest,
        )
    except NormalizationError as exc:
        return OrdinarySnapshotProbeSourceResult(
            source_id=source.contract.source_id,
            status=OrdinarySnapshotProbeStatus.FAILED,
            retrieval_completed_at=retrieved_at,
            request_identity_digest=request_digest,
            raw_payload_digest=trusted_digest,
            normalized_collection_digest=None,
            source_contract_digest=contract_digest,
            normalized_collection=None,
            failure_code=exc.code,
        )

    normalized = normalized_collection_material_v0(
        source_id=source.contract.source_id,
        retrieval_completed_at=retrieved_at,
        batch=batch,
    )
    normalized_digest = sha256_digest(canonical_json_bytes(normalized))
    return OrdinarySnapshotProbeSourceResult(
        source_id=source.contract.source_id,
        status=OrdinarySnapshotProbeStatus.COMPLETE,
        retrieval_completed_at=retrieved_at,
        request_identity_digest=request_digest,
        raw_payload_digest=trusted_digest,
        normalized_collection_digest=normalized_digest,
        source_contract_digest=contract_digest,
        normalized_collection=normalized,
        failure_code=None,
    )


async def run_ordinary_snapshot_probe_v0(
    *,
    registry: SourceRegistry,
    policy: FetchPolicy,
    fetcher: FetcherPort,
    snapshot_id: str,
    authority_ref: str,
    knowledge_horizon: datetime,
    benchmark_protocol_digest: Digest,
) -> OrdinarySnapshotProbeResult:
    if not snapshot_id.strip():
        raise ValueError("ordinary snapshot probe snapshot_id must be non-empty")
    if len(authority_ref) != 40 or any(
        character not in "0123456789abcdef" for character in authority_ref
    ):
        raise ValueError("ordinary snapshot probe authority_ref must be a 40-hex Git SHA")
    offset = knowledge_horizon.utcoffset()
    if knowledge_horizon.tzinfo is None or offset is None:
        raise ValueError("ordinary snapshot probe knowledge_horizon must be timezone-aware")
    if offset.total_seconds() != 0:
        raise ValueError("ordinary snapshot probe knowledge_horizon must use UTC offset +00:00")

    source_ids = frozenset(registry.sources)
    if source_ids != BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS:
        raise ValueError(
            "ordinary snapshot probe registry source set differs from frozen benchmark arm"
        )

    ordered_ids = tuple(sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS))
    source_results = tuple(
        await asyncio.gather(
            *(
                _probe_source(
                    source=registry.require(source_id),
                    policy=policy,
                    fetcher=fetcher,
                    snapshot_id=snapshot_id,
                )
                for source_id in ordered_ids
            )
        )
    )

    complete = all(
        source.status is OrdinarySnapshotProbeStatus.COMPLETE for source in source_results
    )
    payload: OrdinarySnapshotPayloadClaim | None = None
    if complete:
        claims = []
        for source in source_results:
            assert source.raw_payload_digest is not None
            assert source.normalized_collection_digest is not None
            claims.append(
                OrdinarySnapshotSourceClaim(
                    source_id=source.source_id,
                    knowledge_horizon=knowledge_horizon,
                    retrieval_completed_at=source.retrieval_completed_at,
                    source_contract_digest=source.source_contract_digest,
                    request_identity_digest=source.request_identity_digest,
                    raw_payload_digest=source.raw_payload_digest,
                    normalized_collection_digest=source.normalized_collection_digest,
                    raw_body_retained=False,
                )
            )
        payload = OrdinarySnapshotPayloadClaim(
            snapshot_id=snapshot_id,
            knowledge_horizon=knowledge_horizon,
            benchmark_protocol_digest=benchmark_protocol_digest,
            source_registry_version=registry.source_registry_version,
            sources=tuple(claims),
        )

    return OrdinarySnapshotProbeResult(
        snapshot_id=snapshot_id,
        authority_ref=authority_ref,
        knowledge_horizon=knowledge_horizon,
        source_registry_version=registry.source_registry_version,
        benchmark_protocol_digest=benchmark_protocol_digest,
        sources=source_results,
        payload=payload,
    )


__all__ = [
    "ORDINARY_SNAPSHOT_PROBE_ARTIFACT_SCHEMA",
    "ORDINARY_SNAPSHOT_PROBE_REPORT_SCHEMA",
    "OrdinarySnapshotProbeResult",
    "OrdinarySnapshotProbeSourceResult",
    "OrdinarySnapshotProbeStatus",
    "normalized_collection_material_v0",
    "ordinary_snapshot_probe_artifact_v0",
    "ordinary_snapshot_probe_report_v0",
    "payload_claim_material_v0",
    "request_identity_digest_v0",
    "run_ordinary_snapshot_probe_v0",
]
