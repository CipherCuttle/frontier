"""WP13 (G12): candidate freeze operator CLI discipline (unit level).

Covers the dry-run derive determinism, the absolute ``--persist`` guard
refusal, the verify OK path, per-component drift reporting, and the
NOT_DURABLE durability semantics. Persistence WITH the override is covered by
the Postgres integration test (fixture-scoped only; a real freeze is never
authorized during this sprint).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from frontier.application.candidate_freeze import collect_freeze_inputs
from frontier.cli.main import (
    FREEZE_PERSIST_AUTHORIZED_ENV,
    FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV,
    durability_payload,
    freeze_derive,
    freeze_publish,
    freeze_verify,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeStatus,
    build_candidate_freeze_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXED_FROZEN_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _derive_payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    return dict(json.loads(captured.out))


def test_derive_dry_run_is_deterministic_and_never_persists(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(FREEZE_PERSIST_AUTHORIZED_ENV, raising=False)
    first = freeze_derive(REPO_ROOT, persist=False, frozen_at=FIXED_FROZEN_AT)
    assert first == 0
    payload_one = _derive_payload(capsys)

    second = freeze_derive(REPO_ROOT, persist=False, frozen_at=FIXED_FROZEN_AT)
    assert second == 0
    payload_two = _derive_payload(capsys)

    assert payload_one["dry_run"] is True
    assert payload_one["receipt_id"] == payload_two["receipt_id"]
    assert payload_one["status"] == "FROZEN"
    assert payload_one["verify_status"] == "FROZEN"
    assert payload_one["receipt_created_at"] == "2026-01-01T12:00:00.000000Z"
    receipt = payload_one["receipt"]
    assert isinstance(receipt, dict)
    assert receipt["frozen_at"] == "2026-01-01T12:00:00.000000Z"
    # The expected components are printed alongside the receipt.
    components = payload_one["expected_components"]
    assert isinstance(components, dict)
    assert components["dependency_lock_digest"] == receipt["dependency_lock_digest"]
    assert components["source_registry_digest"] == receipt["source_registry_digest"]
    assert components["implementation_commit"] == receipt["implementation_commit"]


def test_derive_persist_guard_refuses_without_explicit_override(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(FREEZE_PERSIST_AUTHORIZED_ENV, raising=False)
    rc = freeze_derive(REPO_ROOT, persist=True, database_url="postgresql://invalid.invalid/db")
    assert rc == 2
    captured = capsys.readouterr()
    refusal = json.loads(captured.err)
    assert refusal["error"] == "FREEZE_PERSIST_UNAUTHORIZED"
    assert "NOT authorized during this sprint" in refusal["message"]
    assert captured.out == ""


def test_verify_ok_from_receipt_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    rc = freeze_derive(REPO_ROOT, persist=False, frozen_at=FIXED_FROZEN_AT)
    assert rc == 0
    payload = _derive_payload(capsys)
    receipt_file = tmp_path / "freeze.json"
    receipt_file.write_text(json.dumps(payload["receipt"]), encoding="utf-8")

    rc = freeze_verify(REPO_ROOT, receipt_file=receipt_file, verified_at=FIXED_FROZEN_AT)
    assert rc == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "FROZEN"
    assert report["drift_reasons"] == []


def _tampered_receipt(*, field: str, value: object) -> CandidateFreezeReceipt:
    inputs = collect_freeze_inputs(REPO_ROOT)
    base = build_candidate_freeze_receipt(inputs, frozen_at=FIXED_FROZEN_AT)
    assert base.status is FreezeStatus.FROZEN
    return replace(base, **{field: value})


def _verify_tampered(
    capsys: pytest.CaptureFixture[str], receipt: CandidateFreezeReceipt, tmp_path: Path
) -> tuple[int, str]:
    receipt_file = tmp_path / "tampered.json"
    receipt_file.write_text(json.dumps(receipt.to_canonical(), sort_keys=True))
    rc = freeze_verify(REPO_ROOT, receipt_file=receipt_file, verified_at=FIXED_FROZEN_AT)
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "DRIFTED"
    return rc, captured.out


def test_verify_reports_each_drift_component_reason(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from frontier.domain.digests import Digest

    cases: tuple[tuple[str, object, str], ...] = (
        (
            "preregistration_digest",
            Digest("sha256:" + "0" * 64),
            "preregistration file digest drifted",
        ),
        (
            "preregistration_config_digest",
            Digest("sha256:" + "1" * 64),
            "preregistration configuration digest drifted",
        ),
        ("implementation_commit", "a" * 40, "implementation commit drifted"),
        ("implementation_tree_digest", "b" * 40, "implementation tree digest drifted"),
        (
            "dependency_lock_digest",
            Digest("sha256:" + "2" * 64),
            "dependency lock digest drifted",
        ),
        (
            "source_registry_digest",
            Digest("sha256:" + "3" * 64),
            "source registry digest drifted",
        ),
        ("registry_entry_digests", (), "source registry entry digests drifted"),
    )
    for field, value, expected_reason in cases:
        receipt = _tampered_receipt(field=field, value=value)
        rc, out = _verify_tampered(capsys, receipt, tmp_path)
        assert rc == 1, f"{field} should exit 1 with drift"
        report = json.loads(out)
        assert expected_reason in report["drift_reasons"], report["drift_reasons"]


def test_durability_payload_null_is_not_durable() -> None:
    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    payload = durability_payload(
        "freezereceipt_" + "a" * 64,
        status="FROZEN",
        receipt_created_at=created_at,
        durable_freeze_at=None,
    )
    assert payload["durability"] == "NOT_DURABLE"
    assert payload["durable_freeze_at"] is None
    assert "cannot gate confirmatory runs" in str(payload["note"])


def test_durability_payload_stamped_is_durable() -> None:
    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    durable = datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC)
    payload = durability_payload(
        "freezereceipt_" + "a" * 64,
        status="FROZEN",
        receipt_created_at=created_at,
        durable_freeze_at=durable,
    )
    assert payload["durability"] == "DURABLE"
    assert payload["durable_freeze_at"] == "2026-01-01T12:00:05.000000Z"
    assert payload["receipt_created_at"] == "2026-01-01T12:00:00.000000Z"
    # The two clocks are never collapsed.
    assert payload["durable_freeze_at"] != payload["receipt_created_at"]


def test_persist_guard_env_is_documented_name() -> None:
    # The guard name is a stable operator contract; the safe default is absolute.
    assert FREEZE_PERSIST_AUTHORIZED_ENV == "FRONTIER_FREEZE_PERSIST_AUTHORIZED"


def test_publication_persist_guard_refuses_before_db_or_git_access(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV, raising=False)
    rc = freeze_publish(
        REPO_ROOT,
        receipt_id="freezereceipt_" + "a" * 64,
        database_url="postgresql://invalid.invalid/db",
    )
    assert rc == 2
    captured = capsys.readouterr()
    refusal = json.loads(captured.err)
    assert refusal["error"] == "FREEZE_PUBLICATION_PERSIST_UNAUTHORIZED"
    assert captured.out == ""


def test_publication_persist_guard_env_is_documented_name() -> None:
    assert (
        FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV
        == "FRONTIER_FREEZE_PUBLICATION_PERSIST_AUTHORIZED"
    )
