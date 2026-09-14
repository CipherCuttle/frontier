from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import frontier.application.value_observatory_ordinary_snapshot_probe as probe_module
from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.acquisition.normalizers import NormalizedBatch
from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)
from frontier.application.value_observatory_ordinary_snapshot_probe import (
    OrdinarySnapshotProbeResult,
    OrdinarySnapshotProbeStatus,
    ordinary_snapshot_probe_artifact_v0,
    run_ordinary_snapshot_probe_v0,
)
from frontier.contracts.fetch import BoundedFetchResult, FetchFailure, FetchOutcome, FetchRequest
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.observation import DocumentPayload, ObservationCandidate, ObservationKind

ROOT = Path(__file__).resolve().parents[2]
HORIZON = datetime(2026, 9, 14, 6, tzinfo=UTC)
RAW_SENTINEL = b"RAW_RESPONSE_BODY_SENTINEL_DO_NOT_PERSIST"


class StubFetcher:
    def __init__(self, *, fail_source_id: str | None = None) -> None:
        self.fail_source_id = fail_source_id
        self.requests: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        self.requests.append(request)
        retrieved_at = HORIZON - timedelta(minutes=2)
        if request.source_id == self.fail_source_id:
            return BoundedFetchResult(
                request_id=request.request_id,
                outcome=FetchOutcome.FAILED,
                retrieved_at=retrieved_at,
                original_url=request.url,
                final_url=request.url,
                redirect_chain=(),
                http_status=503,
                content_type=None,
                response_headers={},
                compressed_bytes=None,
                expanded_bytes=None,
                body_digest=None,
                body=None,
                failure=FetchFailure(
                    code="HTTP_503",
                    safe_message="stub failure",
                    retryable=True,
                ),
            )
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=FetchOutcome.SUCCESS,
            retrieved_at=retrieved_at,
            original_url=request.url,
            final_url=request.url,
            redirect_chain=(),
            http_status=200,
            content_type=request.accepted_content_types[0],
            response_headers={},
            compressed_bytes=len(RAW_SENTINEL),
            expanded_bytes=len(RAW_SENTINEL),
            body_digest=sha256_digest(RAW_SENTINEL),
            body=RAW_SENTINEL,
            failure=None,
        )


def _normalized_batch(
    source_id: str,
    body: bytes,
    *,
    retrieved_at: datetime,
    fetch_digest: Digest,
) -> NormalizedBatch:
    assert body == RAW_SENTINEL
    return NormalizedBatch(
        candidates=(
            ObservationCandidate(
                source_id=source_id,
                source_item_key=f"{source_id}:item-1",
                kind=ObservationKind.DOCUMENT,
                payload=DocumentPayload(
                    canonical_url=f"https://example.com/{source_id}",
                    title=f"item from {source_id}",
                    excerpt=None,
                ),
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=retrieved_at - timedelta(minutes=1),
            ),
        ),
        records_received=1,
        records_rejected=0,
        schema_health=HealthValue.OK,
        details={"parser": "stub-v0"},
        completeness_health=HealthValue.OK,
    )


def _run(monkeypatch: pytest.MonkeyPatch, fetcher: StubFetcher) -> OrdinarySnapshotProbeResult:
    monkeypatch.setattr(probe_module, "normalize_source", _normalized_batch)
    registry = load_source_registry(ROOT)
    policy = load_fetch_policy(ROOT)
    return asyncio.run(
        run_ordinary_snapshot_probe_v0(
            registry=registry,
            policy=policy,
            fetcher=fetcher,
            snapshot_id="manual-probe-001",
            authority_ref="a" * 40,
            knowledge_horizon=HORIZON,
            benchmark_protocol_digest=sha256_digest(b"benchmark-protocol"),
        )
    )


def test_probe_builds_seven_source_replayable_artifact_without_raw_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = StubFetcher()
    result = _run(monkeypatch, fetcher)

    assert result.status is OrdinarySnapshotProbeStatus.COMPLETE
    assert result.payload is not None
    assert {source.source_id for source in result.sources} == BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS
    assert len(fetcher.requests) == 7
    assert len({request.source_id for request in fetcher.requests}) == 7

    artifact = ordinary_snapshot_probe_artifact_v0(result)
    encoded = canonical_json_bytes(artifact)
    assert RAW_SENTINEL not in encoded
    collections = artifact["normalized_collections"]
    assert isinstance(collections, list)
    assert len(collections) == 7
    for source in result.sources:
        assert source.normalized_collection is not None
        assert source.normalized_collection_digest == sha256_digest(
            canonical_json_bytes(source.normalized_collection)
        )


def test_probe_fails_closed_when_one_frozen_source_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_source = "github.ml-repos"
    result = _run(monkeypatch, StubFetcher(fail_source_id=failed_source))

    assert result.status is OrdinarySnapshotProbeStatus.FAILED
    assert result.payload is None
    failed = next(source for source in result.sources if source.source_id == failed_source)
    assert failed.failure_code == "HTTP_503"
    with pytest.raises(ValueError, match="no uploadable snapshot payload"):
        ordinary_snapshot_probe_artifact_v0(result)
