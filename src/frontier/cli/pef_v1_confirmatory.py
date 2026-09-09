from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

_OPERATOR_LEASE_NAME = "frontier-pef-v1-confirmatory-lease"
_OPERATOR_LEASE_KEY = int.from_bytes(
    hashlib.sha256(_OPERATOR_LEASE_NAME.encode()).digest()[:8], "big"
) & ((1 << 63) - 1)


def require_direct_session_database_url(database_url: str) -> str:
    """Reject Neon transaction-pooler endpoints for session-lock operation."""
    try:
        params = conninfo_to_dict(database_url)
    except psycopg.ProgrammingError as error:
        raise ValueError("database URL is not valid Postgres connection information") from error
    host_value = params.get("host")
    if not isinstance(host_value, str) or not host_value or "," in host_value:
        raise ValueError("PEF_V1 confirmatory operation requires one explicit direct database host")
    normalized = host_value.strip().lower()
    if "-pooler" in normalized:
        raise ValueError(
            "PEF_V1 confirmatory operation forbids transaction-pooler hosts; "
            "use the direct/session Neon endpoint"
        )
    return normalized


def require_clean_repository_tree(root: Path) -> None:
    """Fail closed when live confirmatory code or inputs differ from committed Git bytes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            "PEF_V1 confirmatory operation requires a readable Git worktree"
        ) from error
    if result.stdout:
        raise ValueError("PEF_V1 confirmatory operation forbids a dirty Git worktree")


def _acquire_operator_lease(conn: psycopg.Connection[tuple[object, ...]]) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_OPERATOR_LEASE_KEY,))
        row = cur.fetchone()
    conn.commit()
    return bool(row is not None and row[0])


def _release_operator_lease(conn: psycopg.Connection[tuple[object, ...]]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (_OPERATOR_LEASE_KEY,))
        row = cur.fetchone()
    conn.commit()
    if row is None or not bool(row[0]):
        raise RuntimeError("PEF_V1 confirmatory operator lease release failed")


def run_once(
    *,
    database_url: str,
    root: Path,
    worker_id: str,
    now: datetime | None = None,
) -> int:
    require_direct_session_database_url(database_url)
    require_clean_repository_tree(root)

    # Project/runtime imports are intentionally delayed until the Git worktree
    # is proven clean. Dirty candidate code or registry-loader code therefore
    # cannot execute before the confirmatory contamination gate.
    from frontier.adapters.acquisition.config import load_source_registry
    from frontier.adapters.postgres.experiment_attempts import PostgresExperimentAttemptRepository
    from frontier.adapters.postgres.frozen_registry_intelligence import (
        PostgresFrozenRegistryBaselineIntelligenceRepository,
    )
    from frontier.adapters.postgres.pef_v1_confirmatory import (
        PostgresPefV1ConfirmatoryPersistence,
        PostgresPefV1FreezeBindingResolver,
    )
    from frontier.adapters.postgres.readiness import verify_database_readiness
    from frontier.application.experiment_orchestration import ExperimentCycleAction
    from frontier.application.pef_v1_confirmatory import PefV1ConfirmatoryOrchestrator

    registry = load_source_registry(root)
    at = now or datetime.now(UTC)
    with psycopg.connect(database_url) as conn:
        verify_database_readiness(conn)
        if not _acquire_operator_lease(conn):
            print(
                json.dumps(
                    {
                        "error": "PEF_V1_CONFIRMATORY_LEASE_HELD",
                        "worker_id": worker_id,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 3
        try:
            repository = PostgresFrozenRegistryBaselineIntelligenceRepository(conn, registry)
            orchestrator = PefV1ConfirmatoryOrchestrator(
                attempts=PostgresExperimentAttemptRepository(conn),
                baseline_repository=repository,
                persistence=PostgresPefV1ConfirmatoryPersistence(conn),
                freeze_binding=PostgresPefV1FreezeBindingResolver(conn),
                source_registry_version=registry.source_registry_version,
                repository_root=root,
                canonical_context=True,
                worker_id=worker_id,
            )
            result = orchestrator.run_cycle(now=at)
        finally:
            _release_operator_lease(conn)

    payload: dict[str, object] = {
        "action": result.action.value,
        "boundary": result.boundary.isoformat(),
        "detail": result.detail,
        "run_id": result.run_id,
        "worker_id": worker_id,
    }
    if result.attempt is not None:
        payload["attempt_id"] = result.attempt.attempt_id
        payload["attempt_no"] = result.attempt.attempt_no
        payload["attempt_status"] = result.attempt.status.value
    print(json.dumps(payload, sort_keys=True))
    if result.action in (
        ExperimentCycleAction.RAN,
        ExperimentCycleAction.ALREADY_COMPLETE,
        ExperimentCycleAction.DEFERRED_ACTIVE_OWNER,
    ):
        return 0
    return 2


def _database_url(value: str | None, parser: argparse.ArgumentParser) -> str:
    resolved = value or os.getenv("FRONTIER_DATABASE_URL")
    if not resolved:
        parser.error("--database-url or FRONTIER_DATABASE_URL is required")
    return str(resolved)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m frontier.cli.pef_v1_confirmatory")
    parser.add_argument("--database-url")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--worker-id",
        default=os.getenv("FRONTIER_WORKER_ID", "frontier-pef-v1-confirmatory"),
    )
    args = parser.parse_args()
    database_url = _database_url(args.database_url, parser)
    try:
        return run_once(
            database_url=database_url,
            root=args.root,
            worker_id=args.worker_id,
        )
    except ValueError as error:
        print(
            json.dumps(
                {"error": "PEF_V1_CONFIRMATORY_CONFIGURATION_INVALID", "detail": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
