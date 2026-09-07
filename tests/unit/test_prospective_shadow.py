from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from frontier.application.prospective_shadow import (
    RANKING_WINDOW_SECONDS,
    confirmatory_window_end,
    due_confirmatory_boundaries,
    first_confirmatory_boundary,
    load_candidate_freeze_receipt,
    require_confirmatory_boundary,
    require_runtime_freeze_material,
)

DURABLE = datetime(2026, 9, 7, 18, 17, 59, tzinfo=UTC)
START = datetime(2026, 9, 7, 18, 20, tzinfo=UTC)


def test_first_boundary_is_strictly_after_durable_merge() -> None:
    assert first_confirmatory_boundary(DURABLE) == START
    exact_boundary = datetime(2026, 9, 7, 18, 20, tzinfo=UTC)
    assert first_confirmatory_boundary(exact_boundary) == datetime(2026, 9, 7, 18, 25, tzinfo=UTC)


def test_window_end_is_fixed_28_days_after_preregistered_start() -> None:
    assert confirmatory_window_end(DURABLE) == START + timedelta(seconds=RANKING_WINDOW_SECONDS)


def test_boundary_cannot_shift_or_extend_window() -> None:
    require_confirmatory_boundary(as_of=START, durable_freeze_at=DURABLE)
    with pytest.raises(ValueError, match="outside the fixed preregistered ranking window"):
        require_confirmatory_boundary(as_of=START - timedelta(minutes=5), durable_freeze_at=DURABLE)
    with pytest.raises(ValueError, match="outside the fixed preregistered ranking window"):
        require_confirmatory_boundary(
            as_of=confirmatory_window_end(DURABLE), durable_freeze_at=DURABLE
        )
    with pytest.raises(ValueError, match="UTC epoch multiple"):
        require_confirmatory_boundary(as_of=START + timedelta(seconds=1), durable_freeze_at=DURABLE)


def test_due_boundaries_reconstruct_missing_pit_boundaries_without_shifting_start() -> None:
    due = due_confirmatory_boundaries(
        durable_freeze_at=DURABLE,
        now=START + timedelta(minutes=12),
        existing_boundaries=(START,),
    )
    assert due == (START + timedelta(minutes=5), START + timedelta(minutes=10))


def test_duplicate_existing_boundary_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="duplicate bound shadow runs"):
        due_confirmatory_boundaries(
            durable_freeze_at=DURABLE,
            now=START,
            existing_boundaries=(START, START),
        )


def test_published_v0_receipt_round_trips_but_is_stale_after_implementation_change() -> None:
    root = Path(".")
    receipt_path = root / "experiments/advanced_intelligence/pef_v0/candidate_freeze_receipt_v0.json"
    receipt = load_candidate_freeze_receipt(receipt_path)
    assert receipt.receipt_id == (
        "freezereceipt_6e6c54a1c065e5afa8a83df92a1c88ee7e1343be7c5f65030924b10b41ff4626"
    )
    with pytest.raises(RuntimeError):
        require_runtime_freeze_material(root, receipt, receipt_path=receipt_path)
