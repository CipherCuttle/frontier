"""PostgreSQL operational liveness surfaces for the worker (WP9, G8).

All operations here are either mutable-liveness (``worker_heartbeats``, a WP1
mutable table) or read-only observability. The singleton cycle lease uses a
Postgres-native session advisory lock (ADR-0011: no new infrastructure); a
second worker detects the held lease and exits with ``WORKER_LEASE_HELD``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.adapters.acquisition.config import SourceRegistry

# Dedicated singleton lease key derived from a stable constant name. Session
# advisory locks are Postgres-native (D002/ADR-0011: no Redis, no Kafka).
WORKER_LEASE_NAME = "frontier-worker-lease"
WORKER_LEASE_KEY = int.from_bytes(hashlib.sha256(WORKER_LEASE_NAME.encode()).digest()[:8], "big")

ConnectionT = psycopg.Connection[tuple[object, ...]]


class PostgresWorkerLease:
    """Session-level ``pg_advisory_lock`` singleton lease for worker cycles."""

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection
        self._owner: str | None = None

    def acquire(self, *, owner: str) -> bool:
        with self._connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (WORKER_LEASE_KEY,))
            row = cur.fetchone()
        # End the implicit read transaction so the session-level lock is held
        # without pinning an open transaction for the whole cycle.
        self._connection.commit()
        acquired = bool(row is not None and row[0])
        if acquired:
            self._owner = owner
        return acquired

    def release(self, *, owner: str) -> None:
        if self._owner is not None and self._owner != owner:
            return
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_unlock(%s) WHERE pg_try_advisory_lock(%s)",
                (WORKER_LEASE_KEY, WORKER_LEASE_KEY),
            )
            row = cur.fetchone()
        self._connection.commit()
        if row is not None and not bool(row[0]):
            raise RuntimeError("worker lease release failed: lock not held")
        self._owner = None


class PostgresWorkerHeartbeatStore:
    """Upsert access to the mutable ``worker_heartbeats`` table."""

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection

    def upsert_heartbeat(
        self,
        *,
        worker_id: str,
        role: str,
        beat_at: datetime,
        metrics: dict[str, object],
    ) -> None:
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO worker_heartbeats (worker_id, role, beat_at, metrics)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (worker_id) DO UPDATE SET
                    role = EXCLUDED.role,
                    beat_at = EXCLUDED.beat_at,
                    metrics = EXCLUDED.metrics
                """,
                (worker_id, role, beat_at, Jsonb(metrics)),
            )


class PostgresWorkerOpsProbe:
    """Cheap read-only heartbeat enrichment (WP6/evaluation/drift surfaces)."""

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection

    def probe_metrics(self) -> dict[str, object]:
        with self._connection.cursor() as cur:
            cur.execute("SELECT max(as_of) FROM baseline_intelligence_snapshots")
            baseline_row = cur.fetchone()
            assert baseline_row is not None
            cur.execute("SELECT max(as_of) FROM shadow_experiment_runs")
            run_row = cur.fetchone()
            assert run_row is not None
            cur.execute("SELECT status, count(*) FROM experiment_run_attempts GROUP BY status")
            attempt_counts = {cast(str, row[0]): int(cast(int, row[1])) for row in cur.fetchall()}
            cur.execute(
                """
                SELECT status, durable_freeze_at IS NOT NULL
                FROM candidate_freeze_receipts
                ORDER BY frozen_at DESC, receipt_id DESC
                LIMIT 1
                """
            )
            freeze_row = cur.fetchone()
        metrics: dict[str, object] = {
            "latest_baseline_as_of": _iso(cast(datetime | None, baseline_row[0])),
            "latest_candidate_run_as_of": _iso(cast(datetime | None, run_row[0])),
            "attempt_state_counts": attempt_counts,
        }
        if freeze_row is None:
            metrics["drift_state"] = "UNBOUND"
        elif bool(freeze_row[1]) and cast(str, freeze_row[0]) == "FROZEN":
            metrics["drift_state"] = "OK"
        elif cast(str, freeze_row[0]) == "DRIFTED":
            metrics["drift_state"] = "DRIFTED"
        else:
            metrics["drift_state"] = "NOT_DURABLE"
        return metrics


def build_ops_status(
    connection: ConnectionT,
    registry: SourceRegistry,
    *,
    now: datetime,
) -> dict[str, object]:
    """Read-only operational status snapshot for ``frontier ops status``.

    Surfaces: heartbeat age, per-source retry backlog and freshness versus the
    registry ``poll_interval_seconds`` (FRESH/DEGRADED/STALE), attempt queue
    depth, latest snapshot/run ``as_of``, drift state, and DB artifact growth
    indicators. No mutation, no evaluation recomputation.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT worker_id, role, beat_at, metrics FROM worker_heartbeats")
        heartbeats = [
            {
                "worker_id": cast(str, row[0]),
                "role": cast(str, row[1]),
                "beat_at": _iso(cast(datetime, row[2])),
                "age_seconds": round(max(0.0, (now - cast(datetime, row[2])).total_seconds()), 3),
                "metrics": row[3],
            }
            for row in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT source_id, last_success_at, next_retry_at, consecutive_failures
            FROM source_fetch_state
            """
        )
        states = {cast(str, row[0]): row for row in cur.fetchall()}
        cur.execute(
            """
            SELECT DISTINCT ON (source_id)
                   source_id, as_of, transport_health, completeness_health, schema_health
            FROM source_health_observations
            ORDER BY source_id, as_of DESC
            """
        )
        healths = {cast(str, row[0]): row for row in cur.fetchall()}
        cur.execute("SELECT status, count(*) FROM experiment_run_attempts GROUP BY status")
        attempt_counts = {cast(str, row[0]): int(cast(int, row[1])) for row in cur.fetchall()}
        cur.execute("SELECT max(as_of) FROM baseline_intelligence_snapshots")
        baseline_row = cur.fetchone()
        assert baseline_row is not None
        latest_baseline = cast(datetime | None, baseline_row[0])
        cur.execute("SELECT max(as_of) FROM shadow_experiment_runs")
        run_row = cur.fetchone()
        assert run_row is not None
        latest_run = cast(datetime | None, run_row[0])
        cur.execute(
            """
            SELECT status, durable_freeze_at IS NOT NULL
            FROM candidate_freeze_receipts
            ORDER BY frozen_at DESC, receipt_id DESC
            LIMIT 1
            """
        )
        freeze_row = cur.fetchone()
        cur.execute(
            """
            SELECT
                (SELECT count(*) FROM observations),
                (SELECT count(*) FROM collection_runs),
                (SELECT count(*) FROM source_health_observations),
                (SELECT count(*) FROM baseline_intelligence_snapshots),
                (SELECT count(*) FROM shadow_experiment_runs),
                (SELECT count(*) FROM experiment_run_attempts),
                (SELECT count(*) FROM evaluation_receipts),
                (SELECT count(*) FROM worker_heartbeats)
            """
        )
        counts_row = cur.fetchone()
        assert counts_row is not None

    sources: list[dict[str, object]] = []
    backlog: list[dict[str, object]] = []
    for source_id in sorted(registry.sources):
        source = registry.require(source_id)
        interval = float(source.poll_interval_seconds)
        state = states.get(source_id)
        health = healths.get(source_id)
        latest_health: dict[str, object] | None = None
        age: float | None = None
        freshness = "UNKNOWN"
        if health is not None:
            age = max(0.0, (now - cast(datetime, health[1])).total_seconds())
            freshness = (
                "FRESH" if age <= interval else ("DEGRADED" if age <= 2 * interval else "STALE")
            )
            latest_health = {
                "as_of": _iso(cast(datetime, health[1])),
                "transport": cast(str, health[2]),
                "completeness": cast(str, health[3]),
                "schema": cast(str, health[4]),
            }
        next_retry_at = None if state is None else cast(datetime | None, state[2])
        entry: dict[str, object] = {
            "source_id": source_id,
            "poll_interval_seconds": source.poll_interval_seconds,
            "last_success_at": None if state is None else _iso(cast(datetime | None, state[1])),
            "next_retry_at": None if state is None else _iso(next_retry_at),
            "consecutive_failures": 0 if state is None else int(cast(int, state[3])),
            "freshness": freshness,
            "freshness_age_seconds": None if age is None else round(age, 3),
            "latest_health": latest_health,
        }
        sources.append(entry)
        if next_retry_at is not None and next_retry_at > now:
            backlog.append(
                {
                    "source_id": source_id,
                    "next_retry_at": _iso(next_retry_at),
                    "retry_in_seconds": round((next_retry_at - now).total_seconds(), 3),
                }
            )

    if freeze_row is None:
        drift_state = "UNBOUND"
    elif bool(freeze_row[1]) and cast(str, freeze_row[0]) == "FROZEN":
        drift_state = "OK"
    elif cast(str, freeze_row[0]) == "DRIFTED":
        drift_state = "DRIFTED"
    else:
        drift_state = "NOT_DURABLE"

    return {
        "now": _iso(now),
        "heartbeat": heartbeats[0] if heartbeats else None,
        "worker_count": len(heartbeats),
        "sources": sources,
        "retry_backlog": backlog,
        "attempt_state_counts": attempt_counts,
        "latest_baseline_snapshot_as_of": _iso(latest_baseline),
        "latest_candidate_run_as_of": _iso(latest_run),
        "drift_state": drift_state,
        "artifact_counts": {
            "observations": int(cast(int, counts_row[0])),
            "collection_runs": int(cast(int, counts_row[1])),
            "source_health_observations": int(cast(int, counts_row[2])),
            "baseline_intelligence_snapshots": int(cast(int, counts_row[3])),
            "shadow_experiment_runs": int(cast(int, counts_row[4])),
            "experiment_run_attempts": int(cast(int, counts_row[5])),
            "evaluation_receipts": int(cast(int, counts_row[6])),
            "worker_heartbeats": int(cast(int, counts_row[7])),
        },
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
