from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from frontier.adapters.postgres.live_operations import (
    baseline_boundary_at,
    failure_backoff_seconds,
    resolve_failure_retry_at,
)
from frontier.adapters.postgres.readiness import DatabaseReadinessError
from frontier.application.worker import PollCycleResult
from frontier.cli.live_acquisition import (
    cycle_has_failure,
    is_transient_database_error,
    require_direct_session_database_url,
)


@pytest.mark.parametrize(
    ("failures_before", "expected"),
    [
        (0, 60),
        (1, 120),
        (2, 240),
        (3, 480),
        (4, 900),
        (5, 1800),
        (6, 3600),
        (7, 3600),
        (57, 3600),
    ],
)
def test_failure_backoff_is_bounded_and_monotonic(failures_before: int, expected: int) -> None:
    assert failure_backoff_seconds(failures_before) == expected


def test_failure_backoff_rejects_negative_state() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        failure_backoff_seconds(-1)


def test_retry_after_wins_when_later_than_circuit_floor() -> None:
    now = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
    provider_retry = now + timedelta(hours=2)
    assert (
        resolve_failure_retry_at(
            now=now,
            consecutive_failures_before=0,
            proposed_retry_at=provider_retry,
        )
        == provider_retry
    )


def test_circuit_floor_wins_when_provider_retry_is_too_early() -> None:
    now = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
    assert resolve_failure_retry_at(
        now=now,
        consecutive_failures_before=4,
        proposed_retry_at=now + timedelta(seconds=20),
    ) == now + timedelta(minutes=15)


def test_baseline_boundary_is_current_bucket_only() -> None:
    now = datetime(2026, 9, 11, 2, 9, 24, 123456, tzinfo=UTC)
    assert baseline_boundary_at(now) == datetime(2026, 9, 11, 2, 5, tzinfo=UTC)


def test_live_runtime_accepts_direct_host_and_rejects_pooler() -> None:
    direct = "postgresql://frontier:secret@ep-example.eu-central-1.aws.neon.tech/frontier"
    pooler = "postgresql://frontier:secret@ep-example-pooler.eu-central-1.aws.neon.tech/frontier"
    assert require_direct_session_database_url(direct) == "ep-example.eu-central-1.aws.neon.tech"
    with pytest.raises(ValueError, match="transaction-pooler"):
        require_direct_session_database_url(pooler)


def test_live_runtime_rejects_multi_host_connection_info() -> None:
    with pytest.raises(ValueError, match="one explicit direct database host"):
        require_direct_session_database_url(
            "host=one.example,two.example dbname=frontier user=frontier password=secret"
        )


def test_wrapped_operational_readiness_error_is_transient() -> None:
    try:
        raise DatabaseReadinessError("readiness query failed") from psycopg.OperationalError(
            "connection dropped"
        )
    except DatabaseReadinessError as error:
        assert is_transient_database_error(error) is True

    assert is_transient_database_error(DatabaseReadinessError("schema mismatch")) is False


def test_once_failure_guard_includes_isolated_source_errors() -> None:
    now = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
    clean = PollCycleResult(
        started_at=now,
        completed_at=now,
        acquired=(),
        skipped_not_due=(),
        schedules=(),
    )
    isolated = PollCycleResult(
        started_at=now,
        completed_at=now,
        acquired=(),
        skipped_not_due=(),
        schedules=(),
        errors=(("hf.models", "ValueError: broken source"),),
    )
    assert cycle_has_failure(clean) is False
    assert cycle_has_failure(isolated) is True
