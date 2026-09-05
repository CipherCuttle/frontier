from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.application.acquisition import AcquisitionService
from frontier.contracts.fetch import BoundedFetchResult, FetchOutcome, FetchRequest
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import sha256_digest

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
ROOT = Path(".")
NOW = datetime(2026, 9, 5, 2, 40, tzinfo=UTC)


class StaticJsonFetcher:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=FetchOutcome.SUCCESS,
            retrieved_at=NOW,
            original_url=request.url,
            final_url=request.url,
            redirect_chain=(),
            http_status=200,
            content_type="application/json",
            response_headers={"Content-Type": "application/json"},
            compressed_bytes=len(self.body),
            expanded_bytes=len(self.body),
            body_digest=sha256_digest(self.body),
            body=self.body,
            failure=None,
        )


def test_gdelt_saturated_window_propagates_partial_coverage_without_fake_freshness() -> None:
    assert DB_URL is not None
    articles = [
        {
            "url": f"https://frontier-source-diversity-{index}.invalid/story",
            "title": f"Discovery story {index}",
            "seendate": "20260905T023900Z",
            "domain": f"frontier-source-diversity-{index}.invalid",
            "language": "English",
            "sourcecountry": "United States",
        }
        for index in range(250)
    ]
    body = json.dumps({"articles": articles}).encode()

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM source_fetch_state WHERE source_id = %s", ("gdelt.frontier",))
        conn.commit()
        store = PostgresEvidenceStore(conn)
        service = AcquisitionService(
            registry=load_source_registry(ROOT),
            policy=load_fetch_policy(ROOT),
            fetcher=StaticJsonFetcher(body),
            repository=store,
            clock=lambda: NOW,
            sleep=lambda _seconds: asyncio.sleep(0),
            jitter=lambda: 0.5,
        )

        result = asyncio.run(service.acquire("gdelt.frontier"))

        assert result.status is CollectionRunStatus.PARTIAL
        assert result.rejected == 0
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT freshness_health, completeness_health, schema_health,
                       details_json->>'window_saturated'
                FROM source_health_observations
                WHERE collection_run_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (result.run_id,),
            )
            health = cur.fetchone()
        assert health == ("UNKNOWN", "DEGRADED", "OK", "true")
