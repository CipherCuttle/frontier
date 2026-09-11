"""Bounded production launcher for the frozen acquisition-only runtime.

The canonical live acquisition CLI currently opens a non-autocommit psycopg
session. Read probes can therefore leave an implicit transaction open while
network acquisition runs for many minutes, which can trip PostgreSQL's
idle_in_transaction_session_timeout before baseline publication.

This additive ops launcher intentionally leaves the frozen runtime untouched.
It opens the direct session with autocommit enabled, then delegates the actual
cycle to the frozen acquisition loop. Explicit write transaction contexts in
the runtime remain transactional; standalone reads no longer pin an outer
implicit transaction across network I/O.

This launcher is deliberately one-shot only. It is an operational bridge while
PEF_V1 freeze compatibility forbids editing the canonical runtime paths.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
from contextlib import suppress
from pathlib import Path

import psycopg

from frontier.adapters.postgres.readiness import verify_database_readiness
from frontier.adapters.postgres.worker_ops import PostgresWorkerLease
from frontier.cli.live_acquisition import (
    ShutdownRequest,
    _run_connected,  # pyright: ignore[reportPrivateUsage]  # frozen runtime delegation
    require_direct_session_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="scripts/ops/live_acquisition_once_autocommit.py")
    parser.add_argument("--config-root", type=Path, default=Path("."))
    parser.add_argument("--idle-seconds", type=float, default=15.0)
    parser.add_argument(
        "--worker-id",
        default=os.getenv(
            "FRONTIER_WORKER_ID",
            f"frontier-live-once-autocommit-{socket.gethostname()}",
        ),
    )
    args = parser.parse_args()

    database_url = os.getenv("FRONTIER_DATABASE_URL_DIRECT")
    if not database_url:
        print(
            json.dumps(
                {
                    "error": "LIVE_ACQUISITION_CONFIGURATION_INVALID",
                    "detail": "FRONTIER_DATABASE_URL_DIRECT is required",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        require_direct_session_database_url(database_url)
        if args.idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
    except ValueError as error:
        print(
            json.dumps(
                {
                    "error": "LIVE_ACQUISITION_CONFIGURATION_INVALID",
                    "detail": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    connection: psycopg.Connection[tuple[object, ...]] | None = None
    lease: PostgresWorkerLease | None = None
    lease_acquired = False
    try:
        connection = psycopg.connect(database_url, autocommit=True)
        verify_database_readiness(connection)
        lease = PostgresWorkerLease(connection)
        lease_acquired = lease.acquire(owner=args.worker_id)
        if not lease_acquired:
            print(
                json.dumps(
                    {"error": "WORKER_LEASE_HELD", "worker_id": args.worker_id},
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 3

        shutdown = ShutdownRequest()
        return asyncio.run(
            _run_connected(
                connection,
                config_root=args.config_root,
                worker_id=args.worker_id,
                idle_seconds=args.idle_seconds,
                once=True,
                shutdown=shutdown,
                on_successful_cycle=lambda: None,
            )
        )
    finally:
        if lease is not None and lease_acquired and connection is not None:
            with suppress(psycopg.Error, RuntimeError):
                lease.release(owner=args.worker_id)
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
