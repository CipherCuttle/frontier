from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

if TYPE_CHECKING:
    from psycopg import Connection

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.acquisition.fetcher import SecureHttpFetcher
from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.application.acquisition import AcquisitionService
from frontier.application.candidate_freeze import collect_freeze_inputs, verify_freeze
from frontier.application.worker import (
    AcquisitionWorker,
    PollCycleResult,
    WorkerLeaseHeldError,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.canonical_json import canonical_json_text, canonical_timestamp
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
        "errors": [{"error": error, "source_id": source_id} for source_id, error in cycle.errors],
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


class ShutdownRequest:
    """Cooperative shutdown flag set by SIGTERM/SIGINT handlers (WP9)."""

    def __init__(self) -> None:
        self.stop = False

    def __call__(self) -> bool:
        return self.stop


def _install_signal_handlers(shutdown: ShutdownRequest) -> None:
    def handler(signum: int, frame: object) -> None:
        shutdown.stop = True

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _worker_cycle_observer(cycle: PollCycleResult) -> None:
    print(json.dumps(_cycle_payload(cycle), sort_keys=True), flush=True)


def _build_worker_components(
    database_url: str,
    config_root: Path,
    *,
    worker_id: str,
    idle_seconds: float,
) -> tuple[Connection[tuple[object, ...]], AcquisitionWorker]:
    import psycopg

    from frontier.adapters.postgres import PostgresEvidenceStore
    from frontier.adapters.postgres.readiness import verify_database_readiness
    from frontier.adapters.postgres.worker_ops import (
        PostgresWorkerHeartbeatStore,
        PostgresWorkerLease,
        PostgresWorkerOpsProbe,
    )

    policy = load_fetch_policy(config_root)
    registry = load_source_registry(config_root)
    fetcher = SecureHttpFetcher(policy)
    conn = psycopg.connect(database_url)
    verify_database_readiness(conn)
    store = PostgresEvidenceStore(conn)
    service = AcquisitionService(
        registry=registry,
        policy=policy,
        fetcher=fetcher,
        repository=store,
    )
    # WP2 operational wiring: the shipped worker drives one prospective
    # experiment boundary per cycle via the canonical PG repositories (the
    # same objects every other canonical-DB path builds). DEV run-class is
    # the default; the CONFIRMATORY path stays gated (canonical_context is
    # False here, and the four binding gates fail closed regardless). This
    # wiring is always present because the worker requires the canonical DB
    # store to exist at all.
    from frontier.adapters.postgres.experiment_attempts import (
        PostgresExperimentAttemptRepository,
        PostgresFreezeBindingResolver,
        PostgresShadowRunPersister,
    )
    from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
    from frontier.application.experiment_orchestration import (
        RUN_CLASS_DEV,
        ExperimentOrchestrator,
    )

    orchestrator = ExperimentOrchestrator(
        attempts=PostgresExperimentAttemptRepository(conn),
        baseline_repository=PostgresBaselineIntelligenceRepository(conn),
        persistence=PostgresShadowRunPersister(conn),
        source_registry_version=registry.source_registry_version,
        freeze_binding=PostgresFreezeBindingResolver(conn),
        run_class=RUN_CLASS_DEV,
        canonical_context=False,
        worker_id=worker_id,
    )
    worker = AcquisitionWorker(
        registry=registry,
        repository=store,
        service=service,
        idle_seconds=idle_seconds,
        worker_id=worker_id,
        lease=PostgresWorkerLease(conn),
        heartbeat_store=PostgresWorkerHeartbeatStore(conn),
        ops_probe=PostgresWorkerOpsProbe(conn),
        experiment_orchestrator=orchestrator,
        is_transient_connection_error=lambda error: isinstance(error, psycopg.OperationalError),
    )
    return conn, worker


def _lease_held_payload(worker_id: str) -> dict[str, str]:
    return {"error": "WORKER_LEASE_HELD", "worker_id": worker_id}


def run_worker(
    database_url: str,
    config_root: Path,
    *,
    once: bool,
    idle_seconds: float,
    worker_id: str = "frontier-worker",
) -> int:
    import psycopg

    if once:
        conn, worker = _build_worker_components(
            database_url, config_root, worker_id=worker_id, idle_seconds=idle_seconds
        )
        try:
            cycle = asyncio.run(worker.run_once())
        except WorkerLeaseHeldError:
            conn.close()
            print(json.dumps(_lease_held_payload(worker_id), sort_keys=True), file=sys.stderr)
            return 3
        print(json.dumps(_cycle_payload(cycle), sort_keys=True))
        conn.close()
        return (
            2
            if any(result.status is CollectionRunStatus.FAILED for result in cycle.acquired)
            else 0
        )

    # Continuous operation (WP9): graceful SIGTERM/SIGINT shutdown, singleton
    # advisory-lock lease (a second worker exits 3 with WORKER_LEASE_HELD), and
    # bounded reconnect backoff on transient Postgres connection failures.
    shutdown = ShutdownRequest()
    _install_signal_handlers(shutdown)
    reconnect_failures = 0
    while True:
        try:
            conn, worker = _build_worker_components(
                database_url, config_root, worker_id=worker_id, idle_seconds=idle_seconds
            )
        except psycopg.OperationalError as error:
            reconnect_failures += 1
            if reconnect_failures > _MAX_RECONNECT_FAILURES:
                print(
                    json.dumps(
                        {"error": "WORKER_DB_UNREACHABLE", "attempts": reconnect_failures},
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 4
            delay = min(30.0, 2.0**reconnect_failures)
            print(
                json.dumps(
                    {
                        "warning": "WORKER_DB_RECONNECT",
                        "attempt": reconnect_failures,
                        "delay_seconds": delay,
                        "error": str(error),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
            continue
        try:
            asyncio.run(worker.run_forever(observer=_worker_cycle_observer, should_stop=shutdown))
            # Graceful stop (or a clean loop exit): the final cycle completed
            # and its publish transactions are committed; the cycle lease was
            # released inside run_once.
            return 0
        except WorkerLeaseHeldError:
            print(json.dumps(_lease_held_payload(worker_id), sort_keys=True), file=sys.stderr)
            return 3
        except KeyboardInterrupt:
            return 0
        except psycopg.OperationalError as error:
            if shutdown.stop:
                # Signal arrived mid-failure: treat as a graceful stop.
                return 0
            reconnect_failures += 1
            if reconnect_failures > _MAX_RECONNECT_FAILURES:
                print(
                    json.dumps(
                        {"error": "WORKER_DB_UNREACHABLE", "attempts": reconnect_failures},
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 4
            delay = min(30.0, 2.0**reconnect_failures)
            print(
                json.dumps(
                    {
                        "warning": "WORKER_DB_RECONNECT",
                        "attempt": reconnect_failures,
                        "delay_seconds": delay,
                        "error": str(error),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
            continue
        finally:
            conn.close()


_MAX_RECONNECT_FAILURES = 5


def ops_status_command(database_url: str, config_root: Path) -> int:
    import psycopg

    from frontier.adapters.postgres.readiness import verify_database_readiness
    from frontier.adapters.postgres.worker_ops import build_ops_status

    registry = load_source_registry(config_root)
    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        payload = build_ops_status(conn, registry, now=datetime.now(UTC))
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0


# --- Candidate freeze operator workflow (WP13, G12) -------------------------
# Doctrine: receipt creation time (``frozen_at`` / ``receipt_created_at``) is a
# local wall clock; durability (``durable_freeze_at``) is stamped ONLY by the
# canonical DB insert transaction. Confirmatory eligibility uses durable time
# exclusively. The real (confirmatory) candidate freeze is NOT authorized to be
# persisted during this sprint: ``--persist`` refuses unless the explicit
# environment override below is present.
FREEZE_PERSIST_AUTHORIZED_ENV = "FRONTIER_FREEZE_PERSIST_AUTHORIZED"


def _freeze_persist_refusal_payload() -> dict[str, str]:
    return {
        "error": "FREEZE_PERSIST_UNAUTHORIZED",
        "message": (
            "Refusing to persist a real candidate freeze receipt: persistence is "
            "NOT authorized during this sprint. The final freeze happens only "
            f"after the GIGASPRINT branch merges AND a human sets "
            f"{FREEZE_PERSIST_AUTHORIZED_ENV}=1 explicitly. Dry-run only."
        ),
    }


def _freeze_components_payload(inputs: FreezeInputs) -> dict[str, object]:
    entries: list[dict[str, str]] | None = None
    if inputs.registry_entry_digests is not None:
        entries = [
            {"digest": str(entry.digest), "path": entry.path}
            for entry in inputs.registry_entry_digests
        ]
    return {
        "dependency_lock_digest": (
            None if inputs.dependency_lock_digest is None else str(inputs.dependency_lock_digest)
        ),
        "implementation_commit": inputs.implementation_commit,
        "implementation_tree_digest": inputs.implementation_tree_digest,
        "preregistration_config_digest": (
            None
            if inputs.preregistration_config_digest is None
            else str(inputs.preregistration_config_digest)
        ),
        "preregistration_digest": str(inputs.preregistration_digest),
        "registry_entry_digests": entries,
        "source_registry_digest": (
            None if inputs.source_registry_digest is None else str(inputs.source_registry_digest)
        ),
    }


def durability_payload(
    receipt_id: str,
    *,
    status: str,
    receipt_created_at: datetime,
    durable_freeze_at: datetime | None,
) -> dict[str, object]:
    """Report canonical-DB durability for a stored freeze receipt.

    Durability truth comes from the canonical DB commit (``durable_freeze_at``),
    never from any local clock. ``NULL`` means NOT_DURABLE: the freeze cannot
    gate confirmatory runs.
    """
    durable = durable_freeze_at is not None
    return {
        "durability": "DURABLE" if durable else "NOT_DURABLE",
        "durable_freeze_at": (
            None if durable_freeze_at is None else canonical_timestamp(durable_freeze_at)
        ),
        "note": (
            "durability truth comes from the canonical DB commit "
            "(durable_freeze_at), never from local clocks"
            + ("" if durable else "; NOT_DURABLE freezes cannot gate confirmatory runs")
        ),
        "receipt_created_at": canonical_timestamp(receipt_created_at),
        "receipt_id": receipt_id,
        "status": status,
    }


def freeze_derive(
    root: Path,
    *,
    persist: bool = False,
    database_url: str | None = None,
    frozen_at: datetime | None = None,
) -> int:
    """Derive the candidate freeze receipt from the CURRENT repo state.

    DEFAULT: dry-run. The receipt is built from freshly collected freeze
    inputs, verified against the same inputs, and printed with its wall-clock
    ``receipt_created_at`` and the expected identity components. NOTHING is
    persisted unless ``--persist`` is passed AND the explicit environment
    override ``FRONTIER_FREEZE_PERSIST_AUTHORIZED=1`` is present (a guard that
    must never be weakened: real freezes require separate human authorization).
    """
    created_at = frozen_at if frozen_at is not None else datetime.now(UTC)
    inputs = collect_freeze_inputs(root)
    receipt = build_candidate_freeze_receipt(inputs, frozen_at=created_at)
    verification = verify_freeze(receipt, root=root, verified_at=created_at)
    payload: dict[str, object] = {
        "dry_run": not persist,
        "expected_components": _freeze_components_payload(inputs),
        "receipt": receipt.to_canonical(),
        "receipt_created_at": canonical_timestamp(created_at),
        "receipt_id": receipt.receipt_id,
        "status": receipt.status.value,
        "verify_status": verification.status.value,
    }
    if not persist:
        # Dry-run is always a pure report; `freeze verify` is the drift gate.
        print(json.dumps(payload, sort_keys=True))
        return 0
    if receipt.status is not FreezeStatus.FROZEN:
        print(
            json.dumps(
                {"error": "FREEZE_PERSIST_DRIFTED", "drift_reasons": list(receipt.drift_reasons)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if os.getenv(FREEZE_PERSIST_AUTHORIZED_ENV) != "1":
        print(json.dumps(_freeze_persist_refusal_payload(), sort_keys=True), file=sys.stderr)
        return 2
    if not database_url:
        print(
            json.dumps({"error": "FREEZE_PERSIST_DATABASE_URL_REQUIRED"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    import psycopg

    from frontier.adapters.postgres.advanced_intelligence import PostgresCandidateFreezeRepository
    from frontier.adapters.postgres.readiness import verify_database_readiness

    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt.receipt_id,),
            )
            row = cur.fetchone()
    if row is None or row[0] is None:
        print(
            json.dumps({"error": "FREEZE_PERSIST_DURABILITY_STAMP_MISSING"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    payload["durable_freeze_at"] = canonical_timestamp(cast("datetime", row[0]))
    payload["persisted"] = True
    print(json.dumps(payload, sort_keys=True))
    return 0


def freeze_verify(
    root: Path,
    *,
    receipt_file: Path | None = None,
    receipt_id: str | None = None,
    database_url: str | None = None,
    verified_at: datetime | None = None,
) -> int:
    """Recompute every freeze component against current state; print the report.

    Exit 0 with ``FROZEN`` when every component matches; exit 1 with the exact
    drift reasons (WP5 semantics) otherwise; exit 2 when the receipt cannot be
    loaded.
    """
    try:
        receipt = _load_freeze_receipt(receipt_file, receipt_id, database_url)
    except ValueError as error:
        print(
            json.dumps({"error": "FREEZE_RECEIPT_UNLOADABLE", "detail": str(error)}),
            file=sys.stderr,
        )
        return 2
    if receipt is None:
        print(
            json.dumps({"error": "FREEZE_RECEIPT_NOT_FOUND", "receipt_id": receipt_id}),
            file=sys.stderr,
        )
        return 2
    at = verified_at if verified_at is not None else datetime.now(UTC)
    verification = verify_freeze(receipt, root=root, verified_at=at)
    print(
        json.dumps(
            {
                "drift_reasons": list(verification.drift_reasons),
                "receipt_id": receipt.receipt_id,
                "status": verification.status.value,
                "verified_at": canonical_timestamp(at),
                "verification_receipt_digest": str(verification.receipt_digest),
            },
            sort_keys=True,
        )
    )
    return 0 if verification.status is FreezeStatus.FROZEN else 1


def freeze_durability(receipt_id: str, *, database_url: str) -> int:
    """Report whether a stored receipt is durable in the canonical DB."""
    import psycopg

    from frontier.adapters.postgres.readiness import verify_database_readiness

    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, frozen_at, durable_freeze_at
                FROM candidate_freeze_receipts
                WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
    if row is None:
        print(
            json.dumps({"error": "FREEZE_RECEIPT_NOT_FOUND", "receipt_id": receipt_id}),
            file=sys.stderr,
        )
        return 2
    payload = durability_payload(
        receipt_id,
        status=cast("str", row[0]),
        receipt_created_at=cast("datetime", row[1]),
        durable_freeze_at=cast("datetime | None", row[2]),
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


def _load_freeze_receipt(
    receipt_file: Path | None,
    receipt_id: str | None,
    database_url: str | None,
) -> CandidateFreezeReceipt | None:
    if (receipt_file is None) == (receipt_id is None):
        raise ValueError("exactly one of --receipt-file or --receipt-id is required")
    if receipt_file is not None:
        document = json.loads(receipt_file.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("receipt file is not a JSON object")
        raw = cast("dict[str, object]", document)
        canonical = raw.get("receipt") if "receipt" in raw else raw
        from frontier.application.evaluation_loaders import candidate_freeze_receipt_from_canonical

        return candidate_freeze_receipt_from_canonical(cast("dict[str, object]", canonical))
    if not database_url:
        raise ValueError("a stored receipt id requires --database-url or FRONTIER_DATABASE_URL")
    import psycopg

    from frontier.adapters.postgres.advanced_intelligence import PostgresCandidateFreezeRepository

    with psycopg.connect(database_url) as conn:
        stored = PostgresCandidateFreezeRepository(conn).get_receipt_json(cast("str", receipt_id))
    if stored is None:
        return None
    from frontier.application.evaluation_loaders import candidate_freeze_receipt_from_canonical

    return candidate_freeze_receipt_from_canonical(stored)


def _dispatch_freeze(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.freeze_command == "derive":
        url = _freeze_database_url(args.database_url, parser) if args.persist else None
        return freeze_derive(args.root, persist=args.persist, database_url=url)
    if args.freeze_command == "verify":
        url = _freeze_database_url(args.database_url, parser) if args.receipt_id else None
        return freeze_verify(
            args.root,
            receipt_file=args.receipt_file,
            receipt_id=args.receipt_id,
            database_url=url,
        )
    return freeze_durability(
        args.receipt_id, database_url=_freeze_database_url(args.database_url, parser)
    )


def _freeze_database_url(value: str | None, parser: argparse.ArgumentParser) -> str:
    resolved = (
        value or os.getenv("FRONTIER_DATABASE_URL") or os.getenv("FRONTIER_TEST_DATABASE_URL")
    )
    if not resolved:
        parser.error("--database-url or FRONTIER_DATABASE_URL is required")
    return str(resolved)


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
    worker.add_argument("--worker-id", default=os.getenv("FRONTIER_WORKER_ID", "frontier-worker"))

    ops = sub.add_parser("ops")
    ops_sub = ops.add_subparsers(dest="ops_command", required=True)
    ops_status = ops_sub.add_parser("status")
    ops_status.add_argument("--database-url")
    ops_status.add_argument("--config-root", type=Path, default=Path("."))

    freeze = sub.add_parser("freeze")
    freeze_sub = freeze.add_subparsers(dest="freeze_command", required=True)
    freeze_derive_parser = freeze_sub.add_parser(
        "derive", help="derive the candidate freeze receipt from the current repo state (dry-run)"
    )
    freeze_derive_parser.add_argument("--root", type=Path, default=Path("."))
    freeze_derive_parser.add_argument(
        "--persist",
        action="store_true",
        help=(
            "persist the receipt (NOT authorized during this sprint unless "
            f"{FREEZE_PERSIST_AUTHORIZED_ENV}=1 is set explicitly)"
        ),
    )
    freeze_derive_parser.add_argument("--database-url")

    freeze_verify_parser = freeze_sub.add_parser(
        "verify", help="recompute every freeze component against current state"
    )
    freeze_verify_parser.add_argument("--root", type=Path, default=Path("."))
    freeze_verify_source = freeze_verify_parser.add_mutually_exclusive_group(required=True)
    freeze_verify_source.add_argument("--receipt-file", type=Path)
    freeze_verify_source.add_argument("--receipt-id")
    freeze_verify_parser.add_argument("--database-url")

    freeze_durability_parser = freeze_sub.add_parser(
        "durability", help="report durable_freeze_at for a stored receipt id"
    )
    freeze_durability_parser.add_argument("--receipt-id", required=True)
    freeze_durability_parser.add_argument("--database-url")

    args = parser.parse_args()
    if args.command == "replay-fixture":
        return replay_fixture(args.fixture)
    if args.command == "freeze":
        return _dispatch_freeze(args, parser)
    database_url = _database_url(args, parser)
    if args.command == "ingest-fixture":
        return ingest_fixture(args.fixture, database_url)
    if args.command == "acquire":
        return acquire_source(args.source_id, database_url, args.config_root)
    if args.command == "doctor":
        return doctor_database(database_url, args.config_root)
    if args.command == "ops":
        return ops_status_command(database_url, args.config_root)
    return run_worker(
        database_url,
        args.config_root,
        once=args.once,
        idle_seconds=args.idle_seconds,
        worker_id=args.worker_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
