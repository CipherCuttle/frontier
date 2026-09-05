# ruff: noqa: E402
from __future__ import annotations

import os
import statistics
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import perf_counter_ns
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.api.public_read import create_public_read_app
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.application.intelligence import run_baseline_intelligence
from frontier.application.public_read import PublicReadService
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.public_read import SnapshotIntegrityError, SnapshotNotFoundError
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
REGISTRY_VERSION = Digest(
    "sha256:498b4afff3b5a0dcbfb448514a08a3e85adf7f8f2dd5d0863aebbcb353c361f8"
)


def _hex_id(prefix: str) -> str:
    return prefix + sha256(uuid4().bytes).hexdigest()


def _seed_complete_baseline() -> tuple[str, str, str]:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Public read known item</title><link>https://example.com/public-read-known</link>
        <comments>https://news.ycombinator.com/item?id=99101</comments></item>
      <item><title>Public read future item</title><link>https://example.com/public-read-future</link>
        <comments>https://news.ycombinator.com/item?id=99102</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source_id = "fixture.public.read." + uuid4().hex[:12]
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)
    source = SourceContract(
        source_id=source_id,
        display_name="Public read plane fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.ATTENTION,),
        transport=SourceTransport.FIXTURE,
    )

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(source)
        first_run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=candidates[0].retrieved_at,
        )
        evidence.start_collection_run(first_run)
        first_observation, inserted = evidence.append_observation(candidates[0], first_run.run_id)
        assert inserted
        as_of = first_observation.observed_at + timedelta(milliseconds=100)
        evidence.add_source_health(
            SourceHealthObservation(
                source_id=source_id,
                as_of=as_of,
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.DEGRADED,
                schema=HealthValue.OK,
                details={"fixture": "public-read"},
            )
        )
        result = run_baseline_intelligence(
            PostgresBaselineIntelligenceRepository(conn),
            as_of=as_of,
            generated_at=as_of + timedelta(milliseconds=1),
            source_registry_version=REGISTRY_VERSION,
        )
        episode = next(
            item
            for item in result.snapshot.episodes
            if first_observation.observation_id in item.observation_ids
        )

        second_run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=candidates[1].retrieved_at,
        )
        evidence.start_collection_run(second_run)
        second_observation, inserted = evidence.append_observation(candidates[1], second_run.run_id)
        assert inserted
        assert second_observation.observed_at > result.snapshot.as_of

    return result.snapshot.snapshot_id, episode.episode_id, second_observation.observation_id


def _insert_nonpublishable_snapshots() -> tuple[str, str]:
    assert DB_URL is not None
    failed_snapshot = _hex_id("snapshot_")
    failed_receipt = _hex_id("receipt_")
    corrupt_snapshot = _hex_id("snapshot_")
    corrupt_receipt = _hex_id("receipt_")
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    digest = "sha256:" + "9" * 64
    payload = {
        "algorithm_version": "windowed-episode-metrics-v0",
        "as_of": "2026-01-01T00:00:00.000000Z",
        "coverage_state": "UNKNOWN",
        "episodes": [],
        "freshness_state": "UNKNOWN",
        "projection_version": "baseline-intelligence-v0",
        "ranking_policy_version": "naive-episode-activity-v0",
        "schema_state": "UNKNOWN",
        "schema_version": "baseline-intelligence-snapshot-v0",
        "transport_state": "UNKNOWN",
    }
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        for receipt_id, snapshot_id, status in (
            (failed_receipt, failed_snapshot, "FAILED"),
            (corrupt_receipt, corrupt_snapshot, "COMPLETE"),
        ):
            cur.execute(
                """
                INSERT INTO projection_receipts (
                    receipt_id, receipt_schema_version, projection_name,
                    projection_version, schema_version, algorithm_version,
                    ranking_policy_version, configuration_digest,
                    source_registry_version, as_of, generated_at,
                    input_digest, output_digest, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    receipt_id,
                    "projection-receipt-v1",
                    "baseline-intelligence",
                    "baseline-intelligence-v0",
                    "baseline-intelligence-snapshot-v0",
                    "windowed-episode-metrics-v0",
                    "naive-episode-activity-v0",
                    "sha256:" + "7" * 64,
                    str(REGISTRY_VERSION),
                    as_of,
                    as_of,
                    "sha256:" + "8" * 64,
                    digest,
                    status,
                ),
            )
            cur.execute(
                """
                INSERT INTO baseline_intelligence_snapshots (
                    snapshot_id, projection_version, schema_version,
                    algorithm_version, ranking_policy_version, as_of,
                    output_digest, receipt_id, snapshot_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    snapshot_id,
                    "baseline-intelligence-v0",
                    "baseline-intelligence-snapshot-v0",
                    "windowed-episode-metrics-v0",
                    "naive-episode-activity-v0",
                    as_of,
                    digest,
                    receipt_id,
                    psycopg.types.json.Jsonb(payload),
                ),
            )
    return failed_snapshot, corrupt_snapshot


def test_public_read_plane_is_pit_safe_read_only_and_auditable() -> None:
    assert DB_URL is not None
    snapshot_id, episode_id, future_observation_id = _seed_complete_baseline()
    read_connection = psycopg.connect(DB_URL, autocommit=True)
    repository = PostgresPublicReadRepository(read_connection)
    try:
        assert repository.verify_read_only_session()
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction) as write_error:
            read_connection.execute("UPDATE sources SET enabled = enabled WHERE FALSE")
        assert write_error.value.sqlstate == "25006"

        app = create_public_read_app(PublicReadService(repository))
        methods = {
            method.upper()
            for path in app.openapi()["paths"].values()
            for method in path
        }
        assert methods == {"GET"}

        client = TestClient(app)
        radar = client.get("/v0/radar", params={"snapshot_id": snapshot_id})
        assert radar.status_code == 200
        body = radar.json()
        assert body["snapshot"]["snapshot_id"] == snapshot_id
        assert body["snapshot"]["receipt_id"].startswith("receipt_")
        assert body["snapshot"]["ranking_policy_version"] == "naive-episode-activity-v0"
        assert body["semantic_scope"] == "BASELINE_SUBSTRATE"
        assert body["items"] == sorted(body["items"], key=lambda item: item["rank"])

        drilldown = client.get(
            f"/v0/episodes/{episode_id}", params={"snapshot_id": snapshot_id}
        )
        assert drilldown.status_code == 200
        drilldown_body = drilldown.json()
        expected_ids = drilldown_body["episode"]["observation_ids"]
        assert [item["observation_id"] for item in drilldown_body["observations"]] == expected_ids

        future = client.get(
            f"/v0/observations/{future_observation_id}",
            params={"snapshot_id": snapshot_id},
        )
        assert future.status_code == 404
        assert future.json()["error"] == "OBSERVATION_NOT_FOUND"

        health = client.get("/v0/health", params={"snapshot_id": snapshot_id})
        assert health.status_code == 200
        assert health.json()["coverage_state"] == body["snapshot"].get(
            "coverage_state", health.json()["coverage_state"]
        )

        samples_ms: list[float] = []
        for _ in range(60):
            started = perf_counter_ns()
            response = client.get("/v0/radar", params={"snapshot_id": snapshot_id})
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000
            assert response.status_code == 200
            samples_ms.append(elapsed_ms)
        p95_ms = statistics.quantiles(samples_ms, n=20, method="inclusive")[18]
        print(f"public-read-plane healthy local p95_ms={p95_ms:.3f}")
        assert p95_ms < 250
    finally:
        repository.close()
        read_connection.close()


def test_failed_and_corrupt_snapshots_are_not_publishable() -> None:
    assert DB_URL is not None
    failed_snapshot, corrupt_snapshot = _insert_nonpublishable_snapshots()
    read_connection = psycopg.connect(DB_URL, autocommit=True)
    repository = PostgresPublicReadRepository(read_connection)
    try:
        with pytest.raises(SnapshotNotFoundError):
            repository.resolve_snapshot(failed_snapshot)
        with pytest.raises(SnapshotIntegrityError, match="payload digest"):
            repository.resolve_snapshot(corrupt_snapshot)
    finally:
        read_connection.close()
