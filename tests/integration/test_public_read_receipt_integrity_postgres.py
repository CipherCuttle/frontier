from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import sha256_digest
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_RECEIPT_SCHEMA_VERSION,
    BASELINE_SCHEMA_VERSION,
)
from frontier.domain.public_read import SnapshotIntegrityError

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _hex_id(prefix: str) -> str:
    return prefix + sha256(uuid4().bytes).hexdigest()


def _valid_payload(as_of: datetime) -> dict[str, CanonicalValue]:
    return {
        "algorithm_version": BASELINE_ALGORITHM_VERSION,
        "as_of": as_of.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "coverage_state": "UNKNOWN",
        "episodes": [],
        "freshness_state": "UNKNOWN",
        "projection_version": BASELINE_PROJECTION_VERSION,
        "ranking_policy_version": BASELINE_RANKING_POLICY_VERSION,
        "schema_state": "UNKNOWN",
        "schema_version": BASELINE_SCHEMA_VERSION,
        "transport_state": "UNKNOWN",
    }


def _insert_candidate(*, receipt_schema_version: str) -> tuple[str, str]:
    assert DB_URL is not None
    snapshot_id = _hex_id("snapshot_")
    receipt_id = _hex_id("receipt_")
    as_of = datetime(2026, 9, 5, 12, tzinfo=UTC)
    payload = _valid_payload(as_of)
    output_digest = str(sha256_digest(canonical_json_bytes(payload)))

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO projection_receipts (
                receipt_id, receipt_schema_version, projection_name,
                projection_version, schema_version, algorithm_version,
                ranking_policy_version, configuration_digest,
                source_registry_version, as_of, generated_at,
                input_digest, output_digest, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'COMPLETE')
            """,
            (
                receipt_id,
                receipt_schema_version,
                BASELINE_PROJECTION_NAME,
                BASELINE_PROJECTION_VERSION,
                BASELINE_SCHEMA_VERSION,
                BASELINE_ALGORITHM_VERSION,
                BASELINE_RANKING_POLICY_VERSION,
                "sha256:" + "7" * 64,
                "sha256:" + "6" * 64,
                as_of,
                as_of,
                "sha256:" + "8" * 64,
                output_digest,
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
                BASELINE_PROJECTION_VERSION,
                BASELINE_SCHEMA_VERSION,
                BASELINE_ALGORITHM_VERSION,
                BASELINE_RANKING_POLICY_VERSION,
                as_of,
                output_digest,
                receipt_id,
                Jsonb(payload),
            ),
        )
    return snapshot_id, receipt_id


def test_receipt_schema_drift_fails_closed() -> None:
    assert DB_URL is not None
    snapshot_id, _ = _insert_candidate(receipt_schema_version="projection-receipt-v999")
    read_connection = psycopg.connect(DB_URL, autocommit=True)
    repository = PostgresPublicReadRepository(read_connection)
    try:
        with pytest.raises(SnapshotIntegrityError, match="receipt schema version identity"):
            repository.resolve_snapshot(snapshot_id)
    finally:
        read_connection.close()


def test_receipt_id_drift_fails_closed() -> None:
    assert DB_URL is not None
    snapshot_id, stored_receipt_id = _insert_candidate(
        receipt_schema_version=BASELINE_RECEIPT_SCHEMA_VERSION
    )
    read_connection = psycopg.connect(DB_URL, autocommit=True)
    repository = PostgresPublicReadRepository(read_connection)
    try:
        with pytest.raises(SnapshotIntegrityError, match="receipt deterministic identity"):
            repository.resolve_snapshot(snapshot_id)
        assert stored_receipt_id.startswith("receipt_")
    finally:
        read_connection.close()
