from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.acquisition.fetcher import SecureHttpFetcher
from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.application.acquisition import AcquisitionService
from frontier.application.worker import AcquisitionWorker, PollCycleResult
from frontier.domain.canonical_json import canonical_json_text
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.observation import Observation
from frontier.domain.source import (
    AcquisitionClass,
    SignalRole,
    SourceContract,
    SourceTransport,
)


def _source() -> SourceContract:
    return SourceContract(
        source_id="fixture.hostile_document",
        display_name="Hostile document fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def replay_fixture(path: Path) -> int:
    candidate, observed_at = load_fixture_candidate(path)
    observation = Observation(candidate=candidate, observed_at=observed_at)
    print(canonical_json_text(observation.to_canonical()))
    return 0


def ingest_fixture(path: Path, database_url: str) -> int:
    import psycopg

    from frontier.adapters.postgres import PostgresEvidenceStore
    from frontier.adapters.postgres.readiness import verify_database_readiness

    candidate, _ = load_fixture_candidate(path)
    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        store = PostgresEvidenceStore(conn)
        source = _source()
        store.upsert_source(source)
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source.source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=candidate.retrieved_at,
        )
        store.start_collection_run(run)
        observation, inserted = store.append_observation(candidate, run.run_id)
    print(json.dumps({"inserted": inserted, "observation_id": observation.observation_id}))
    return 0


def acquire_source(source_id: str, database_url: str, config_root: Path) -> int:
    import psycopg

    from frontier.adapters.postgres import PostgresEvidenceStore
    from frontier.adapters.postgres.readiness import verify_database_readiness

    policy = load_fetch_policy(config_root)
    registry = load_source_registry(config_root)
    fetcher = SecureHttpFetcher(policy)
    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        store = PostgresEvidenceStore(conn)
        service = AcquisitionService(
            registry=registry,
            policy=policy,
            fetcher=fetcher,
            repository=store,
        )
        result = asyncio.run(service.acquire(source_id))
    print(
        json.dumps(
            {
                "duplicates": result.duplicates,
                "failure_code": result.failure_code,
                "inserted": result.inserted,
                "observations": len(result.observation_ids),
                "rejected": result.rejected,
                "run_id": str(result.run_id),
                "source_id": result.source_id,
                "status": result.status.value,
            },
            sort_keys=True,
        )
    )
    return 0 if result.status in (CollectionRunStatus.SUCCESS, CollectionRunStatus.PARTIAL) else 2


def doctor_database(database_url: str, config_root: Path) -> int:
    import psycopg

    from frontier.adapters.postgres.readiness import verify_database_readiness

    _ = load_fetch_policy(config_root)
    registry = load_source_registry(config_root)
    with psycopg.connect(database_url) as conn:
        readiness = verify_database_readiness(conn)
    payload = readiness.to_dict()
    payload["configured_sources"] = sorted(registry.sources)
    payload["source_registry_version"] = str(registry.source_registry_version)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _cycle_payload(cycle: PollCycleResult) -> dict[str, object]:
    return {
        "acquired": [
            {
                "failure_code": result.failure_code,
                "inserted": result.inserted,
                "source_id": result.source_id,
                "status": result.status.value,
            }
            for result in cycle.acquired
        ],
        "completed_at": _timestamp(cycle.completed_at),
        "duration_ms": round(cycle.duration_seconds * 1000, 3),
        "schedule": [
            {
                "cadence_slo": schedule.cadence_slo.value,
                "consecutive_failures": schedule.consecutive_failures,
                "due": schedule.due,
                "due_at": _timestamp(schedule.due_at),
                "last_success_at": _timestamp(schedule.last_success_at),
                "lateness_seconds": schedule.lateness_seconds,
                "next_retry_at": _timestamp(schedule.next_retry_at),
                "source_id": schedule.source_id,
            }
            for schedule in cycle.schedules
        ],
        "skipped_not_due": list(cycle.skipped_not_due),
        "started_at": _timestamp(cycle.started_at),
    }


def run_worker(database_url: str, config_root: Path, *, once: bool, idle_seconds: float) -> int:
    import psycopg

    from frontier.adapters.postgres import PostgresEvidenceStore
    from frontier.adapters.postgres.readiness import verify_database_readiness

    policy = load_fetch_policy(config_root)
    registry = load_source_registry(config_root)
    fetcher = SecureHttpFetcher(policy)
    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        store = PostgresEvidenceStore(conn)
        service = AcquisitionService(
            registry=registry,
            policy=policy,
            fetcher=fetcher,
            repository=store,
        )
        worker = AcquisitionWorker(
            registry=registry,
            repository=store,
            service=service,
            idle_seconds=idle_seconds,
        )
        if once:
            cycle = asyncio.run(worker.run_once())
            print(json.dumps(_cycle_payload(cycle), sort_keys=True))
            return (
                2
                if any(result.status is CollectionRunStatus.FAILED for result in cycle.acquired)
                else 0
            )
        try:
            asyncio.run(
                worker.run_forever(
                    observer=lambda cycle: print(json.dumps(_cycle_payload(cycle), sort_keys=True))
                )
            )
        except KeyboardInterrupt:
            return 0
    return 0


def _database_url(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    value = (
        args.database_url
        or os.getenv("FRONTIER_DATABASE_URL")
        or os.getenv("FRONTIER_TEST_DATABASE_URL")
    )
    if not value:
        parser.error("--database-url or FRONTIER_DATABASE_URL is required")
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(prog="frontier")
    sub = parser.add_subparsers(dest="command", required=True)

    replay = sub.add_parser("replay-fixture")
    replay.add_argument("fixture", type=Path)

    ingest = sub.add_parser("ingest-fixture")
    ingest.add_argument("fixture", type=Path)
    ingest.add_argument("--database-url")

    acquire = sub.add_parser("acquire")
    acquire.add_argument("source_id")
    acquire.add_argument("--database-url")
    acquire.add_argument("--config-root", type=Path, default=Path("."))

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--database-url")
    doctor.add_argument("--config-root", type=Path, default=Path("."))

    worker = sub.add_parser("worker")
    worker.add_argument("--database-url")
    worker.add_argument("--config-root", type=Path, default=Path("."))
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--idle-seconds", type=float, default=30.0)

    args = parser.parse_args()
    if args.command == "replay-fixture":
        return replay_fixture(args.fixture)
    database_url = _database_url(args, parser)
    if args.command == "ingest-fixture":
        return ingest_fixture(args.fixture, database_url)
    if args.command == "acquire":
        return acquire_source(args.source_id, database_url, args.config_root)
    if args.command == "doctor":
        return doctor_database(database_url, args.config_root)
    return run_worker(
        database_url,
        args.config_root,
        once=args.once,
        idle_seconds=args.idle_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
