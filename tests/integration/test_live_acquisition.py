# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.application.acquisition import AcquisitionService
from frontier.contracts.fetch import (
    BoundedFetchResult,
    FetchFailure,
    FetchOutcome,
    FetchRequest,
)
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import sha256_digest

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
ROOT = Path(".")


def pypi_body(name: str, version: str) -> bytes:
    return f"""<rss version="2.0"><channel><item>
      <title>{name} {version}</title>
      <link>https://pypi.org/project/{name}/{version}/</link>
      <description>integration release</description>
      <pubDate>Sat, 05 Sep 2026 01:00:00 GMT</pubDate>
    </item></channel></rss>""".encode()


def success(request: FetchRequest, body: bytes, content_type: str, etag: str) -> BoundedFetchResult:
    return BoundedFetchResult(
        request_id=request.request_id,
        outcome=FetchOutcome.SUCCESS,
        retrieved_at=datetime(2026, 9, 5, 1, 0, tzinfo=UTC),
        original_url=request.url,
        final_url=request.url,
        redirect_chain=(),
        http_status=200,
        content_type=content_type,
        response_headers={"Content-Type": content_type, "ETag": etag},
        compressed_bytes=len(body),
        expanded_bytes=len(body),
        body_digest=sha256_digest(body),
        body=body,
        failure=None,
    )


class ConditionalPyPiFetcher:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.requests: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        self.requests.append(request)
        if request.request_headers.get("If-None-Match") == '"fixture-etag"':
            return BoundedFetchResult(
                request_id=request.request_id,
                outcome=FetchOutcome.SUCCESS,
                retrieved_at=datetime(2026, 9, 5, 1, 1, tzinfo=UTC),
                original_url=request.url,
                final_url=request.url,
                redirect_chain=(),
                http_status=304,
                content_type=None,
                response_headers={"ETag": '"fixture-etag"'},
                compressed_bytes=0,
                expanded_bytes=0,
                body_digest=sha256_digest(b""),
                body=b"",
                failure=None,
            )
        return success(request, self._body, "application/rss+xml", '"fixture-etag"')


class Always304Fetcher:
    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=FetchOutcome.SUCCESS,
            retrieved_at=datetime(2026, 9, 5, 2, 0, tzinfo=UTC),
            original_url=request.url,
            final_url=request.url,
            redirect_chain=(),
            http_status=304,
            content_type=None,
            response_headers={"ETag": '"orphan"'},
            compressed_bytes=0,
            expanded_bytes=0,
            body_digest=sha256_digest(b""),
            body=b"",
            failure=None,
        )


class CisaFallbackFetcher:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.urls: list[str] = []

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        self.urls.append(request.url)
        if "www.cisa.gov" in request.url:
            return BoundedFetchResult(
                request_id=request.request_id,
                outcome=FetchOutcome.FAILED,
                retrieved_at=datetime(2026, 9, 5, 3, 0, tzinfo=UTC),
                original_url=request.url,
                final_url=request.url,
                redirect_chain=(),
                http_status=None,
                content_type=None,
                response_headers={},
                compressed_bytes=None,
                expanded_bytes=None,
                body_digest=None,
                body=None,
                failure=FetchFailure(
                    code="CONNECT_FAILED",
                    safe_message="fixture primary outage",
                    retryable=True,
                ),
            )
        return success(request, self._body, "application/json", '"cisa-fixture"')


def reset_fetch_state(conn: object, source_id: str) -> None:
    with conn.cursor() as cur:  # type: ignore[attr-defined]
        cur.execute("DELETE FROM source_fetch_state WHERE source_id = %s", (source_id,))
    conn.commit()  # type: ignore[attr-defined]


def service_for(
    store: PostgresEvidenceStore, fetcher: object, clock: datetime
) -> AcquisitionService:
    policy = load_fetch_policy(ROOT)
    registry = load_source_registry(ROOT)
    return AcquisitionService(
        registry=registry,
        policy=policy,
        fetcher=fetcher,  # type: ignore[arg-type]
        repository=store,
        clock=lambda: clock,
        sleep=lambda _seconds: asyncio.sleep(0),
        jitter=lambda: 0.5,
    )


def test_pypi_200_then_304_uses_trusted_state_and_does_not_manufacture_evidence() -> None:
    assert DB_URL is not None
    body = pypi_body("frontier-pr02-a", "1.0.0")
    fetcher = ConditionalPyPiFetcher(body)
    with psycopg.connect(DB_URL) as conn:
        reset_fetch_state(conn, "pypi.updates")
        store = PostgresEvidenceStore(conn)
        service = service_for(store, fetcher, datetime(2026, 9, 5, 1, 2, tzinfo=UTC))

        first = asyncio.run(service.acquire("pypi.updates"))
        second = asyncio.run(service.acquire("pypi.updates"))

        assert first.status is CollectionRunStatus.SUCCESS
        assert first.inserted == 1
        assert second.status is CollectionRunStatus.SUCCESS
        assert second.inserted == 0
        assert second.duplicates == 0
        assert fetcher.requests[1].request_headers["If-None-Match"] == '"fixture-etag"'
        state = store.get_source_fetch_state("pypi.updates")
        assert state is not None
        assert state.last_body_digest == sha256_digest(body)
        assert state.consecutive_failures == 0


def test_304_without_prior_trusted_entity_fails_closed() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        reset_fetch_state(conn, "pypi.updates")
        store = PostgresEvidenceStore(conn)
        result = asyncio.run(
            service_for(store, Always304Fetcher(), datetime(2026, 9, 5, 2, 1, tzinfo=UTC)).acquire(
                "pypi.updates"
            )
        )
        assert result.status is CollectionRunStatus.FAILED
        assert result.failure_code == "CACHE_ENTITY_MISSING"


def test_recovery_of_finite_pypi_window_degrades_completeness() -> None:
    assert DB_URL is not None
    body = pypi_body("frontier-pr02-gap", "2.0.0")
    with psycopg.connect(DB_URL) as conn:
        reset_fetch_state(conn, "pypi.updates")
        store = PostgresEvidenceStore(conn)
        registry = load_source_registry(ROOT)
        store.upsert_source(registry.require("pypi.updates").contract)
        store.record_fetch_failure("pypi.updates", next_retry_at=None)
        result = asyncio.run(
            service_for(
                store,
                ConditionalPyPiFetcher(body),
                datetime(2026, 9, 5, 2, 30, tzinfo=UTC),
            ).acquire("pypi.updates")
        )
        assert result.status is CollectionRunStatus.PARTIAL
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT completeness_health, details_json->>'recovered_after_gap'
                FROM source_health_observations
                WHERE collection_run_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (result.run_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "DEGRADED"
        assert row[1] == "true"


def test_cisa_same_authority_mirror_is_fallback_not_second_source() -> None:
    assert DB_URL is not None
    cisa = {
        "catalogVersion": "2026.09.05",
        "count": 1,
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-54321",
                "vulnerabilityName": "Fallback fixture",
                "shortDescription": "fixture",
                "requiredAction": "patch",
            }
        ],
    }
    fetcher = CisaFallbackFetcher(json.dumps(cisa).encode())
    with psycopg.connect(DB_URL) as conn:
        reset_fetch_state(conn, "cisa.kev")
        store = PostgresEvidenceStore(conn)
        result = asyncio.run(
            service_for(store, fetcher, datetime(2026, 9, 5, 3, 1, tzinfo=UTC)).acquire("cisa.kev")
        )
        assert result.status is CollectionRunStatus.SUCCESS
        assert result.inserted == 1
        assert len(fetcher.urls) == 2
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_id FROM observations WHERE observation_id = %s",
                (result.observation_ids[0],),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "cisa.kev"
