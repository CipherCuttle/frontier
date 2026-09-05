from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DATABASE_NAME = "frontier_capacity_probe"
DATABASE_URL_ENV = "FRONTIER_CAPACITY_DATABASE_URL"
ALLOW_ENV = "FRONTIER_CAPACITY_MEASURE_ALLOW"
COUNT_ENV = "FRONTIER_CAPACITY_OBSERVATIONS"
DEFAULT_COUNT = 1000
MAX_COUNT = 10000
SOURCE_ID = "ops.capacity-fixture"
FIXTURE = Path("fixtures/sources/hostile_document_v1")


def _database_url(base_url: str, database: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise RuntimeError("capacity measurement requires a PostgreSQL URL")
    if parsed.hostname is None or parsed.username is None:
        raise RuntimeError("capacity database URL must include host and user")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database}",
            parsed.query,
            parsed.fragment,
        )
    )


def _sqlalchemy_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = "postgresql+psycopg" if parsed.scheme in {"postgres", "postgresql"} else parsed.scheme
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _reset_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(DATABASE_NAME)
            )
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE_NAME)))


def _drop_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(DATABASE_NAME)
            )
        )


def _migrate(database_url: str) -> None:
    import subprocess

    environment = os.environ.copy()
    environment["FRONTIER_DATABASE_URL"] = _sqlalchemy_url(database_url)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=environment)


def _observation_count() -> int:
    raw = os.environ.get(COUNT_ENV, str(DEFAULT_COUNT))
    try:
        count = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{COUNT_ENV} must be an integer") from exc
    if not 1 <= count <= MAX_COUNT:
        raise RuntimeError(f"{COUNT_ENV} must be between 1 and {MAX_COUNT}")
    return count


def _source_contract() -> SourceContract:
    return SourceContract(
        source_id=SOURCE_ID,
        display_name="Capacity measurement fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
        enabled=False,
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise RuntimeError("cannot calculate percentile for an empty sample")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))
    return ordered[index]


def _measure(database_url: str, count: int) -> dict[str, object]:
    base_candidate, _ = load_fixture_candidate(FIXTURE)
    started_at = datetime.now(UTC)
    latencies_ms: list[float] = []

    with psycopg.connect(database_url) as connection:
        store = PostgresEvidenceStore(connection)
        store.upsert_source(_source_contract())
        run = CollectionRun(
            run_id=uuid4(),
            source_id=SOURCE_ID,
            reason=CollectionReason.BACKFILL,
            started_at=started_at,
        )
        store.start_collection_run(run)

        insert_started = perf_counter()
        for index in range(count):
            candidate = replace(
                base_candidate,
                source_id=SOURCE_ID,
                source_item_key=f"capacity:{index:05d}",
            )
            item_started = perf_counter()
            _, inserted = store.append_observation(candidate, run.run_id)
            latencies_ms.append((perf_counter() - item_started) * 1000.0)
            if not inserted:
                raise RuntimeError(f"capacity candidate {index} was unexpectedly a duplicate")
        insert_elapsed = perf_counter() - insert_started

        store.complete_collection_run(
            run.run_id,
            status=CollectionRunStatus.SUCCESS,
            records_received=count,
            records_accepted=count,
            records_rejected=0,
            duplicates=0,
            failure_code=None,
        )

        read_started = perf_counter()
        observation_ids = store.list_observation_ids_as_of(datetime.now(UTC))
        read_elapsed = perf_counter() - read_started
        if len(observation_ids) != count:
            raise RuntimeError(
                f"capacity readback expected {count} observations, got {len(observation_ids)}"
            )

        row = connection.execute(
            "SELECT pg_database_size(current_database()), current_setting('server_version')"
        ).fetchone()
        if row is None:
            raise RuntimeError("capacity database metadata query returned no row")
        database_size_bytes = cast(int, row[0])
        postgres_version = cast(str, row[1])

    insert_rate = count / insert_elapsed if insert_elapsed > 0 else 0.0
    return {
        "database_size_bytes": database_size_bytes,
        "insert_elapsed_seconds": round(insert_elapsed, 6),
        "insert_latency_ms_max": round(max(latencies_ms), 6),
        "insert_latency_ms_p50": round(_percentile(latencies_ms, 0.50), 6),
        "insert_latency_ms_p95": round(_percentile(latencies_ms, 0.95), 6),
        "insert_observations_per_second": round(insert_rate, 3),
        "measurement_kind": "APPLICATION_STORE_ROUND_TRIP",
        "observation_count": count,
        "postgres_version": postgres_version,
        "read_all_elapsed_ms": round(read_elapsed * 1000.0, 6),
        "read_all_rows": len(observation_ids),
        "schema_version": "capacity-measurement-v0",
        "threshold_verdict": None,
    }


def main() -> int:
    if os.environ.get(ALLOW_ENV) != "1":
        raise RuntimeError(f"set {ALLOW_ENV}=1 to run the destructive scratch-database measurement")
    admin_url = os.environ.get(DATABASE_URL_ENV)
    if admin_url is None or not admin_url.strip():
        raise RuntimeError(f"{DATABASE_URL_ENV} is required")

    count = _observation_count()
    database_url = _database_url(admin_url, DATABASE_NAME)
    _drop_database(admin_url)
    try:
        _reset_database(admin_url)
        _migrate(database_url)
        receipt = _measure(database_url, count)
        print(json.dumps(receipt, sort_keys=True))
    finally:
        _drop_database(admin_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
