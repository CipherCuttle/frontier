from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

import psycopg

DATABASE_URL_ENV = "FRONTIER_DATABASE_URL"
SCHEMA_VERSION = "serving-freshness-v0"
BASELINE_CADENCE_SECONDS = 300
LIVE_MAX_SNAPSHOT_LAG_SECONDS = BASELINE_CADENCE_SECONDS
LIVE_MAX_HEARTBEAT_AGE_SECONDS = BASELINE_CADENCE_SECONDS * 2
LAGGING_MAX_SNAPSHOT_LAG_SECONDS = BASELINE_CADENCE_SECONDS * 6
LAGGING_MAX_HEARTBEAT_AGE_SECONDS = BASELINE_CADENCE_SECONDS * 6
_CANONICAL_FRESHNESS_STATES = frozenset({"OK", "DEGRADED", "FAILED", "UNKNOWN"})


class ServingFreshnessState(StrEnum):
    LIVE = "LIVE"
    LAGGING = "LAGGING"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class ServingFreshnessStatus:
    state: ServingFreshnessState
    now: datetime
    current_boundary: datetime
    latest_baseline_as_of: datetime | None
    latest_baseline_freshness: str | None
    latest_worker_beat_at: datetime | None
    snapshot_lag_seconds: float | None
    heartbeat_age_seconds: float | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "state": self.state.value,
            "now": _iso(self.now),
            "current_boundary": _iso(self.current_boundary),
            "latest_baseline_as_of": _iso(self.latest_baseline_as_of),
            "latest_baseline_freshness": self.latest_baseline_freshness,
            "latest_worker_beat_at": _iso(self.latest_worker_beat_at),
            "snapshot_lag_seconds": self.snapshot_lag_seconds,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "reasons": list(self.reasons),
            "thresholds": {
                "live_max_snapshot_lag_seconds": LIVE_MAX_SNAPSHOT_LAG_SECONDS,
                "live_max_heartbeat_age_seconds": LIVE_MAX_HEARTBEAT_AGE_SECONDS,
                "lagging_max_snapshot_lag_seconds": LAGGING_MAX_SNAPSHOT_LAG_SECONDS,
                "lagging_max_heartbeat_age_seconds": LAGGING_MAX_HEARTBEAT_AGE_SECONDS,
            },
        }


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def current_boundary_at(now: datetime) -> datetime:
    """Return the current five-minute UTC serving boundary."""
    _require_aware("now", now)
    utc_now = now.astimezone(UTC)
    epoch_seconds = int(utc_now.timestamp())
    boundary_seconds = epoch_seconds - (epoch_seconds % BASELINE_CADENCE_SECONDS)
    return datetime.fromtimestamp(boundary_seconds, tz=UTC)


def classify_serving_freshness(
    *,
    now: datetime,
    latest_baseline_as_of: datetime | None,
    latest_baseline_freshness: str | None,
    latest_worker_beat_at: datetime | None,
) -> ServingFreshnessStatus:
    """Classify read-plane serving freshness without mutating canonical state.

    LIVE tolerates one missed baseline boundary and up to two worker cadences,
    but only when the latest COMPLETE baseline's canonical freshness aggregate
    is OK. DEGRADED caps serving at LAGGING. FAILED, UNKNOWN, absent, invalid,
    future-dated, misaligned, or older evidence fails closed to STALE.
    """
    _require_aware("now", now)
    utc_now = now.astimezone(UTC)
    current_boundary = current_boundary_at(utc_now)
    reasons: list[str] = []
    snapshot_lag_seconds: float | None = None
    heartbeat_age_seconds: float | None = None

    if latest_baseline_as_of is None:
        reasons.append("NO_BASELINE_SNAPSHOT")
    else:
        _require_aware("latest_baseline_as_of", latest_baseline_as_of)
        baseline = latest_baseline_as_of.astimezone(UTC)
        if int(baseline.timestamp()) % BASELINE_CADENCE_SECONDS != 0:
            reasons.append("SNAPSHOT_BOUNDARY_INVALID")
        snapshot_lag_seconds = (current_boundary - baseline).total_seconds()
        if snapshot_lag_seconds < 0:
            reasons.append("SNAPSHOT_FROM_FUTURE")

        if latest_baseline_freshness is None:
            reasons.append("BASELINE_FRESHNESS_MISSING")
        elif latest_baseline_freshness not in _CANONICAL_FRESHNESS_STATES:
            reasons.append("BASELINE_FRESHNESS_INVALID")
        elif latest_baseline_freshness == "FAILED":
            reasons.append("BASELINE_FRESHNESS_FAILED")
        elif latest_baseline_freshness == "UNKNOWN":
            reasons.append("BASELINE_FRESHNESS_UNKNOWN")

    if latest_worker_beat_at is None:
        reasons.append("NO_WORKER_HEARTBEAT")
    else:
        _require_aware("latest_worker_beat_at", latest_worker_beat_at)
        heartbeat = latest_worker_beat_at.astimezone(UTC)
        heartbeat_age_seconds = (utc_now - heartbeat).total_seconds()
        if heartbeat_age_seconds < 0:
            reasons.append("HEARTBEAT_FROM_FUTURE")

    if reasons:
        state = ServingFreshnessState.STALE
    else:
        assert snapshot_lag_seconds is not None
        assert heartbeat_age_seconds is not None
        if (
            snapshot_lag_seconds <= LIVE_MAX_SNAPSHOT_LAG_SECONDS
            and heartbeat_age_seconds <= LIVE_MAX_HEARTBEAT_AGE_SECONDS
            and latest_baseline_freshness == "OK"
        ):
            state = ServingFreshnessState.LIVE
        elif (
            snapshot_lag_seconds <= LAGGING_MAX_SNAPSHOT_LAG_SECONDS
            and heartbeat_age_seconds <= LAGGING_MAX_HEARTBEAT_AGE_SECONDS
        ):
            state = ServingFreshnessState.LAGGING
            if latest_baseline_freshness == "DEGRADED":
                reasons.append("BASELINE_FRESHNESS_DEGRADED")
            if snapshot_lag_seconds > LIVE_MAX_SNAPSHOT_LAG_SECONDS:
                reasons.append("SNAPSHOT_LAGGING")
            if heartbeat_age_seconds > LIVE_MAX_HEARTBEAT_AGE_SECONDS:
                reasons.append("HEARTBEAT_LAGGING")
        else:
            state = ServingFreshnessState.STALE
            if latest_baseline_freshness == "DEGRADED":
                reasons.append("BASELINE_FRESHNESS_DEGRADED")
            if snapshot_lag_seconds > LAGGING_MAX_SNAPSHOT_LAG_SECONDS:
                reasons.append("SNAPSHOT_STALE")
            if heartbeat_age_seconds > LAGGING_MAX_HEARTBEAT_AGE_SECONDS:
                reasons.append("HEARTBEAT_STALE")

    return ServingFreshnessStatus(
        state=state,
        now=utc_now,
        current_boundary=current_boundary,
        latest_baseline_as_of=(
            None if latest_baseline_as_of is None else latest_baseline_as_of.astimezone(UTC)
        ),
        latest_baseline_freshness=latest_baseline_freshness,
        latest_worker_beat_at=(
            None if latest_worker_beat_at is None else latest_worker_beat_at.astimezone(UTC)
        ),
        snapshot_lag_seconds=snapshot_lag_seconds,
        heartbeat_age_seconds=heartbeat_age_seconds,
        reasons=tuple(reasons),
    )


def read_serving_freshness(database_url: str) -> ServingFreshnessStatus:
    """Read canonical liveness evidence through a forced read-only session."""
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute("SHOW transaction_read_only")
            read_only_row = cur.fetchone()
            if read_only_row is None or cast(str, read_only_row[0]) != "on":
                raise RuntimeError("serving freshness database session is not read-only")

            cur.execute("SELECT clock_timestamp()")
            now_row = cur.fetchone()
            if now_row is None or not isinstance(now_row[0], datetime):
                raise RuntimeError("database clock unavailable")
            now = cast(datetime, now_row[0])
            _require_aware("database clock", now)

            cur.execute(
                """
                SELECT b.as_of, b.snapshot_json ->> 'freshness_state'
                FROM baseline_intelligence_snapshots b
                JOIN projection_receipts r ON r.receipt_id = b.receipt_id
                WHERE r.status = 'COMPLETE'
                  AND r.projection_name = 'baseline-intelligence'
                ORDER BY b.as_of DESC, b.snapshot_id DESC
                LIMIT 1
                """
            )
            baseline_row = cur.fetchone()
            latest_baseline = None if baseline_row is None else cast(datetime, baseline_row[0])
            latest_baseline_freshness = (
                None if baseline_row is None else cast(str | None, baseline_row[1])
            )

            cur.execute("SELECT max(beat_at) FROM worker_heartbeats")
            heartbeat_row = cur.fetchone()
            if heartbeat_row is None:
                raise RuntimeError("worker heartbeat query returned no row")
            latest_heartbeat = cast(datetime | None, heartbeat_row[0])

    return classify_serving_freshness(
        now=now,
        latest_baseline_as_of=latest_baseline,
        latest_baseline_freshness=latest_baseline_freshness,
        latest_worker_beat_at=latest_heartbeat,
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    _require_aware("timestamp", value)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    database_url = os.environ.get(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is required")
    status = read_serving_freshness(database_url)
    print(json.dumps(status.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
