from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.adapters.acquisition.fetcher import SecureHttpFetcher
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresFreezeBindingResolver,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.frozen_registry_intelligence import (
    PostgresFrozenRegistryBaselineIntelligenceRepository,
)
from frontier.adapters.postgres.readiness import verify_database_readiness
from frontier.adapters.postgres.worker_ops import (
    PostgresWorkerHeartbeatStore,
    PostgresWorkerLease,
    PostgresWorkerOpsProbe,
)
from frontier.application.acquisition import AcquisitionService
from frontier.application.drift_sentry import DriftSentry
from frontier.application.experiment_orchestration import (
    RUN_CLASS_CONFIRMATORY,
    ExperimentCycleAction,
    ExperimentOrchestrator,
)
from frontier.application.worker import AcquisitionWorker, WorkerLeaseHeldError

ROOT = Path("/opt/frontier/app")
WORKER_ID = "frontier-pef-v0-confirmatory-vm"
EXPECTED_COMMIT = os.environ["CANONICAL_PUBLICATION_COMMIT"]
EXPECTED_TREE = os.environ["CANONICAL_PUBLICATION_TREE"]
EXPECTED_PARENT_1 = os.environ["CANONICAL_PARENT_1"]
EXPECTED_PARENT_2 = os.environ["CANONICAL_PARENT_2"]
EXPECTED_RECEIPT = os.environ["EXPECTED_FREEZE_RECEIPT_ID"]
EXPECTED_PUBLICATION = os.environ["EXPECTED_PUBLICATION_COMMIT"]


class FatalAuthorityError(RuntimeError):
    pass


STOP = False


def _stop(signum: int, frame: object) -> None:
    global STOP
    STOP = True


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def assert_repo_identity() -> None:
    checks = (
        ("commit", _git("rev-parse", "HEAD"), EXPECTED_COMMIT),
        ("tree", _git("rev-parse", "HEAD^{tree}"), EXPECTED_TREE),
        ("parent_1", _git("rev-parse", "HEAD^1"), EXPECTED_PARENT_1),
        ("parent_2", _git("rev-parse", "HEAD^2"), EXPECTED_PARENT_2),
    )
    for label, actual, expected in checks:
        if actual != expected:
            raise FatalAuthorityError(f"canonical {label} mismatch: {actual} != {expected}")
    if _git("status", "--porcelain"):
        raise FatalAuthorityError("canonical application tree is dirty")


def database_url() -> str:
    if value := os.environ.get("FRONTIER_DATABASE_URL"):
        return value.strip()
    if credentials_dir := os.environ.get("CREDENTIALS_DIRECTORY"):
        path = Path(credentials_dir) / "frontier_database_url"
        if path.is_file() and (value := path.read_text(encoding="utf-8").strip()):
            return value
    raise FatalAuthorityError("canonical database credential is unavailable")


def assert_binding(conn: psycopg.Connection[tuple[object, ...]]) -> object:
    binding = PostgresFreezeBindingResolver(conn).latest_binding()
    if binding is None:
        raise FatalAuthorityError("no canonical freeze binding is resolvable")
    if binding.receipt.receipt_id != EXPECTED_RECEIPT:
        raise FatalAuthorityError("latest freeze receipt does not match the authorized receipt")
    if binding.publication_commit != EXPECTED_PUBLICATION:
        raise FatalAuthorityError("freeze publication commit does not match the authorized commit")
    if binding.durable_freeze_at is None or binding.publication_committer_at is None:
        raise FatalAuthorityError("freeze durability/publication binding is incomplete")
    report = DriftSentry(ROOT).check(binding.receipt, now=datetime.now(UTC))
    if report.status.value == "DRIFTED":
        raise FatalAuthorityError("DRIFTED: " + "; ".join(report.reasons))
    return binding


def preflight() -> dict[str, object]:
    assert_repo_identity()
    registry = load_source_registry(ROOT)
    load_fetch_policy(ROOT)
    with psycopg.connect(database_url()) as conn:
        readiness = verify_database_readiness(conn)
        binding = assert_binding(conn)
    return {
        "status": "READY",
        "run_class": RUN_CLASS_CONFIRMATORY,
        "canonical_context": True,
        "canonical_commit": EXPECTED_COMMIT,
        "canonical_tree": EXPECTED_TREE,
        "freeze_receipt_id": binding.receipt.receipt_id,
        "publication_commit": binding.publication_commit,
        "source_registry_version": str(registry.source_registry_version),
        "database_name": readiness.database_name,
        "migration_revision": readiness.migration_revision,
    }


def build_worker() -> tuple[psycopg.Connection[tuple[object, ...]], AcquisitionWorker]:
    assert_repo_identity()
    policy = load_fetch_policy(ROOT)
    registry = load_source_registry(ROOT)
    conn = psycopg.connect(database_url())
    try:
        verify_database_readiness(conn)
        assert_binding(conn)
        store = PostgresEvidenceStore(conn)
        resolver = PostgresFreezeBindingResolver(conn)
        worker = AcquisitionWorker(
            registry=registry,
            repository=store,
            service=AcquisitionService(
                registry=registry,
                policy=policy,
                fetcher=SecureHttpFetcher(policy),
                repository=store,
            ),
            idle_seconds=30.0,
            worker_id=WORKER_ID,
            lease=PostgresWorkerLease(conn),
            heartbeat_store=PostgresWorkerHeartbeatStore(conn),
            ops_probe=PostgresWorkerOpsProbe(conn),
            experiment_orchestrator=ExperimentOrchestrator(
                attempts=PostgresExperimentAttemptRepository(conn),
                baseline_repository=PostgresFrozenRegistryBaselineIntelligenceRepository(
                    conn, registry
                ),
                persistence=PostgresShadowRunPersister(conn),
                source_registry_version=registry.source_registry_version,
                freeze_binding=resolver,
                run_class=RUN_CLASS_CONFIRMATORY,
                canonical_context=True,
                drift_sentry=DriftSentry(ROOT),
                worker_id=WORKER_ID,
            ),
            is_transient_connection_error=lambda error: isinstance(error, psycopg.OperationalError),
        )
        return conn, worker
    except Exception:
        conn.close()
        raise


def emit_cycle(cycle: object) -> None:
    experiment = cycle.experiment
    payload = {
        "started_at": cycle.started_at.isoformat(),
        "completed_at": cycle.completed_at.isoformat(),
        "duration_seconds": round(cycle.duration_seconds, 3),
        "acquired": [
            {
                "source_id": result.source_id,
                "status": result.status.value,
                "inserted": result.inserted,
                "duplicates": result.duplicates,
                "rejected": result.rejected,
            }
            for result in cycle.acquired
        ],
        "experiment": None
        if experiment is None
        else {
            "action": experiment.action.value,
            "boundary": experiment.boundary.isoformat(),
            "attempt_status": None
            if experiment.attempt is None
            else experiment.attempt.status.value,
            "run_id": experiment.run_id,
            "detail": experiment.detail,
        },
    }
    print(json.dumps(payload, sort_keys=True), flush=True)
    if experiment is None:
        raise FatalAuthorityError("confirmatory worker produced no experiment result")
    if experiment.action is ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES:
        raise FatalAuthorityError("confirmatory authority gate was skipped")
    if experiment.detail and experiment.detail.startswith("DRIFTED:"):
        raise FatalAuthorityError(experiment.detail)


def run_service() -> int:
    global STOP
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    reconnect_failures = 0
    while not STOP:
        try:
            conn, worker = build_worker()
        except psycopg.OperationalError:
            reconnect_failures += 1
            if reconnect_failures > 5:
                return 4
            time.sleep(min(30.0, 2.0**reconnect_failures))
            continue
        try:
            reconnect_failures = 0
            while not STOP:
                try:
                    cycle = asyncio.run(worker.run_once())
                    emit_cycle(cycle)
                    remaining = worker.seconds_until_next_cycle()
                except psycopg.OperationalError:
                    break
                while remaining > 0 and not STOP:
                    sleep_for = min(1.0, remaining)
                    time.sleep(sleep_for)
                    remaining -= sleep_for
        finally:
            conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(preflight(), sort_keys=True), flush=True)
        return 0 if args.preflight else run_service()
    except WorkerLeaseHeldError:
        print(json.dumps({"error": "WORKER_LEASE_HELD"}), file=sys.stderr, flush=True)
        return 3
    except FatalAuthorityError as error:
        print(
            json.dumps({"error": "FATAL_AUTHORITY", "detail": str(error)}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
