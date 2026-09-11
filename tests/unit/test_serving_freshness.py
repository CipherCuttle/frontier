from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.ops.serving_freshness import (
    BASELINE_CADENCE_SECONDS,
    LAGGING_MAX_HEARTBEAT_AGE_SECONDS,
    LAGGING_MAX_SNAPSHOT_LAG_SECONDS,
    LIVE_MAX_HEARTBEAT_AGE_SECONDS,
    LIVE_MAX_SNAPSHOT_LAG_SECONDS,
    ServingFreshnessState,
    classify_serving_freshness,
    current_boundary_at,
)

NOW = datetime(2026, 9, 11, 20, 4, tzinfo=UTC)
BOUNDARY = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)


def test_current_boundary_uses_five_minute_utc_cadence() -> None:
    assert BASELINE_CADENCE_SECONDS == 300
    assert current_boundary_at(NOW) == BOUNDARY


def test_serving_freshness_live_allows_one_snapshot_boundary_and_two_worker_cadences() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY - timedelta(seconds=LIVE_MAX_SNAPSHOT_LAG_SECONDS),
        latest_baseline_freshness="OK",
        latest_worker_beat_at=NOW - timedelta(seconds=LIVE_MAX_HEARTBEAT_AGE_SECONDS),
    )

    assert status.state is ServingFreshnessState.LIVE
    assert status.reasons == ()


def test_canonical_degraded_freshness_caps_timely_serving_at_lagging() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY,
        latest_baseline_freshness="DEGRADED",
        latest_worker_beat_at=NOW,
    )

    assert status.state is ServingFreshnessState.LAGGING
    assert status.reasons == ("BASELINE_FRESHNESS_DEGRADED",)


@pytest.mark.parametrize(
    ("freshness", "reason"),
    [
        ("FAILED", "BASELINE_FRESHNESS_FAILED"),
        ("UNKNOWN", "BASELINE_FRESHNESS_UNKNOWN"),
        (None, "BASELINE_FRESHNESS_MISSING"),
        ("FRESH", "BASELINE_FRESHNESS_INVALID"),
    ],
)
def test_non_usable_canonical_freshness_fails_closed(
    freshness: str | None,
    reason: str,
) -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY,
        latest_baseline_freshness=freshness,
        latest_worker_beat_at=NOW,
    )

    assert status.state is ServingFreshnessState.STALE
    assert status.reasons == (reason,)


def test_serving_freshness_lagging_identifies_each_lagging_dimension() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY - timedelta(seconds=LIVE_MAX_SNAPSHOT_LAG_SECONDS + 300),
        latest_baseline_freshness="OK",
        latest_worker_beat_at=NOW - timedelta(seconds=LIVE_MAX_HEARTBEAT_AGE_SECONDS + 1),
    )

    assert status.state is ServingFreshnessState.LAGGING
    assert status.reasons == ("SNAPSHOT_LAGGING", "HEARTBEAT_LAGGING")


def test_serving_freshness_stale_after_bounded_lag_window() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY
        - timedelta(seconds=LAGGING_MAX_SNAPSHOT_LAG_SECONDS + 300),
        latest_baseline_freshness="OK",
        latest_worker_beat_at=NOW - timedelta(seconds=LAGGING_MAX_HEARTBEAT_AGE_SECONDS + 1),
    )

    assert status.state is ServingFreshnessState.STALE
    assert status.reasons == ("SNAPSHOT_STALE", "HEARTBEAT_STALE")


def test_serving_freshness_fails_closed_when_evidence_is_missing() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=None,
        latest_baseline_freshness=None,
        latest_worker_beat_at=None,
    )

    assert status.state is ServingFreshnessState.STALE
    assert status.reasons == ("NO_BASELINE_SNAPSHOT", "NO_WORKER_HEARTBEAT")


def test_serving_freshness_fails_closed_on_future_or_misaligned_evidence() -> None:
    status = classify_serving_freshness(
        now=NOW,
        latest_baseline_as_of=BOUNDARY + timedelta(seconds=1),
        latest_baseline_freshness="OK",
        latest_worker_beat_at=NOW + timedelta(seconds=1),
    )

    assert status.state is ServingFreshnessState.STALE
    assert status.reasons == (
        "SNAPSHOT_BOUNDARY_INVALID",
        "SNAPSHOT_FROM_FUTURE",
        "HEARTBEAT_FROM_FUTURE",
    )


def test_serving_freshness_rejects_naive_clocks() -> None:
    naive = datetime(2026, 9, 11, 20, 4)
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        classify_serving_freshness(
            now=naive,
            latest_baseline_as_of=BOUNDARY,
            latest_baseline_freshness="OK",
            latest_worker_beat_at=NOW,
        )
