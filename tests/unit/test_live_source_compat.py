from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from frontier.adapters.acquisition.live_compat import (
    CISA_MIRROR_URL,
    HF_FROZEN_URL,
    HF_LIVE_URL,
    LiveSourceCompatibilityFetcher,
    live_wire_request,
    live_wire_result,
)
from frontier.contracts.fetch import BoundedFetchResult, FetchOutcome, FetchRequest


def _request(*, source_id: str, url: str) -> FetchRequest:
    return FetchRequest(
        request_id="fixture:1",
        source_id=source_id,
        url=url,
        policy_profile="structured-public-v0",
        credential_ref=None,
        accepted_content_types=("application/json", "text/json"),
        deadline_ms=5000,
        max_response_bytes=1024 * 1024,
        max_redirects=3,
        request_headers={"Accept": "application/json, text/json"},
    )


def _success(*, url: str, content_type: str, body: bytes) -> BoundedFetchResult:
    return BoundedFetchResult(
        request_id="fixture:1",
        outcome=FetchOutcome.SUCCESS,
        retrieved_at=datetime(2026, 9, 11, 2, 30, tzinfo=UTC),
        original_url=url,
        final_url=url,
        redirect_chain=(),
        http_status=200,
        content_type=content_type,
        response_headers={"Content-Type": content_type},
        compressed_bytes=len(body),
        expanded_bytes=len(body),
        body_digest=None,
        body=body,
        failure=None,
    )


def test_hf_live_wire_rewrites_only_exact_frozen_request() -> None:
    request = _request(source_id="hf.models", url=HF_FROZEN_URL)
    rewritten = live_wire_request(request)
    assert rewritten.url == HF_LIVE_URL
    assert request.url == HF_FROZEN_URL

    other_source = _request(source_id="not.hf", url=HF_FROZEN_URL)
    assert live_wire_request(other_source) is other_source

    other_url = _request(source_id="hf.models", url="https://huggingface.co/api/models?limit=1")
    assert live_wire_request(other_url) is other_url


def test_cisa_live_wire_accepts_text_plain_only_for_exact_json_mirror() -> None:
    request = _request(source_id="cisa.kev", url=CISA_MIRROR_URL)
    result = _success(
        url=CISA_MIRROR_URL,
        content_type="text/plain",
        body=b'{"catalogVersion":"fixture","vulnerabilities":[]}',
    )
    repaired = live_wire_result(request, result)
    assert repaired.content_type == "application/json"
    assert repaired.response_headers["Content-Type"] == "text/plain"

    invalid_json = _success(url=CISA_MIRROR_URL, content_type="text/plain", body=b"not-json")
    assert live_wire_result(request, invalid_json).content_type == "text/plain"

    primary = _request(
        source_id="cisa.kev",
        url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    )
    assert live_wire_result(primary, result).content_type == "text/plain"

    other_source = _request(source_id="other.source", url=CISA_MIRROR_URL)
    assert live_wire_result(other_source, result).content_type == "text/plain"


class _RecordingFetcher:
    def __init__(self, result: BoundedFetchResult) -> None:
        self.result = result
        self.requests: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        self.requests.append(request)
        return self.result


def test_live_compatibility_fetcher_sends_hf_repaired_wire_url() -> None:
    inner = _RecordingFetcher(
        _success(url=HF_LIVE_URL, content_type="application/json", body=b"[]")
    )
    fetcher = LiveSourceCompatibilityFetcher(inner)

    result = asyncio.run(fetcher.fetch(_request(source_id="hf.models", url=HF_FROZEN_URL)))

    assert result.outcome is FetchOutcome.SUCCESS
    assert [request.url for request in inner.requests] == [HF_LIVE_URL]
