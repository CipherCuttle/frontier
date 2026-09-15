from __future__ import annotations

import pytest

from frontier.application.value_observatory_ordinary_snapshot_trigger import (
    REQUEST_SCHEMA_V0,
    parse_repository_request_v0,
    select_new_repository_request_v0,
)


def request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": REQUEST_SCHEMA_V0,
        "snapshot_id": "ordinary-prehorizon-probe-20260916t0600z-01",
        "knowledge_horizon": "2026-09-16T06:00:00Z",
        "non_scored": True,
    }
    value.update(changes)
    return value


def test_request_accepts_exact_manual_non_scored_boundary() -> None:
    resolved = parse_repository_request_v0(request())
    assert resolved.snapshot_id == "ordinary-prehorizon-probe-20260916t0600z-01"
    assert resolved.knowledge_horizon == "2026-09-16T06:00:00Z"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "other", "unsupported probe request schema"),
        ("non_scored", False, "explicitly non-scored"),
        ("snapshot_id", "UPPERCASE", "lowercase stable identifier"),
        ("knowledge_horizon", "2026-09-16T05:00:00Z", "frozen 00/06/12/18"),
        ("knowledge_horizon", "2026-09-16T06:00:01Z", "frozen 00/06/12/18"),
        ("knowledge_horizon", "2026-09-16T06:00:00+00:00", "exact UTC Z timestamp"),
    ],
)
def test_request_rejects_contract_drift(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_repository_request_v0(request(**{field: value}))


def test_request_rejects_extra_or_missing_fields() -> None:
    with pytest.raises(ValueError, match="exactly the frozen V0 keys"):
        parse_repository_request_v0({**request(), "extra": "no"})
    missing = request()
    del missing["snapshot_id"]
    with pytest.raises(ValueError, match="exactly the frozen V0 keys"):
        parse_repository_request_v0(missing)


def test_selector_requires_exactly_one_new_request_file() -> None:
    path = ".github/probe-requests/ordinary-prehorizon-v0/request.json"
    assert select_new_repository_request_v0((("A", path),)) == path

    with pytest.raises(ValueError, match="exactly one changed request file"):
        select_new_repository_request_v0(())
    with pytest.raises(ValueError, match="exactly one changed request file"):
        select_new_repository_request_v0((("A", path), ("A", path.replace("request", "other"))))


@pytest.mark.parametrize("status", ["M", "D", "T"])
def test_selector_rejects_existing_request_mutation(status: str) -> None:
    path = ".github/probe-requests/ordinary-prehorizon-v0/request.json"
    with pytest.raises(ValueError, match="newly added immutable request file"):
        select_new_repository_request_v0(((status, path),))


def test_selector_ignores_unrelated_files_but_fails_on_any_second_request_change() -> None:
    path = ".github/probe-requests/ordinary-prehorizon-v0/request.json"
    assert (
        select_new_repository_request_v0((("M", "README.md"), ("A", path)))
        == path
    )
    with pytest.raises(ValueError, match="exactly one changed request file"):
        select_new_repository_request_v0(
            (
                ("A", path),
                ("M", ".github/probe-requests/ordinary-prehorizon-v0/old.json"),
            )
        )
