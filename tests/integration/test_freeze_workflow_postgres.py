# ruff: noqa: E402
"""WP13 (G12): full candidate freeze operator workflow against the canonical DB.

Fixture-scoped ONLY: the receipts persisted here are test fixtures in the test
database. The real confirmatory candidate freeze is NOT authorized during this
sprint and is never persisted outside tests.

Sequence proven: derive (dry) -> guard refusal without override -> persist WITH
override (fixture receipt) -> durability stamped -> verify OK -> Git publication
authority persisted -> orchestrator confirmatory gate passes at the first legal
publication-derived boundary; WRONG-freeze verify prints drift;
receipt_created_at != durable_freeze_at (different clocks).
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
)
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.application.evaluation_loaders import (
    candidate_freeze_receipt_from_canonical,
)
from frontier.application.experiment_orchestration import (
    FreezeBinding,
    evaluate_confirmatory_gates,
)
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.cli.main import (
    FREEZE_PERSIST_AUTHORIZED_ENV,
    freeze_derive,
    freeze_durability,
    freeze_verify,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt
from frontier.domain.canonical_json import canonical_timestamp
from frontier.domain.digests import Digest

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

# Unique per test run (second resolution): the deterministic receipt id is a
# fixture identity, so repeated runs must not collide with prior persisted rows.
FIXED_FROZEN_AT = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=24)
FIXED_CREATED_AT_TEXT = canonical_timestamp(FIXED_FROZEN_AT)


def _derive_receipt(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    rc = freeze_derive(REPO_ROOT, persist=False, frozen_at=FIXED_FROZEN_AT)
    assert rc == 0
    return dict(json.loads(capsys.readouterr().out))


def test_full_freeze_operator_workflow(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert DB_URL is not None
    monkeypatch.delenv(FREEZE_PERSIST_AUTHORIZED_ENV, raising=False)

    # 1. Dry-run derive: deterministic, never persists.
    derived = _derive_receipt(capsys)
    again = _derive_receipt(capsys)
    assert derived["dry_run"] is True
    assert derived["receipt_id"] == again["receipt_id"]
    assert derived["status"] == "FROZEN"
    receipt_id = str(derived["receipt_id"])

    # 2. The guard refuses persistence without the explicit override.
    rc = freeze_derive(REPO_ROOT, persist=True, database_url=DB_URL, frozen_at=FIXED_FROZEN_AT)
    assert rc == 2
    refusal = json.loads(capsys.readouterr().err)
    assert refusal["error"] == "FREEZE_PERSIST_UNAUTHORIZED"
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM candidate_freeze_receipts WHERE receipt_id = %s",
            (receipt_id,),
        )
        assert cur.fetchone() == (0,), "guarded derive must never persist"

    # 3. Fixture-based persist WITH the override stamps durable_freeze_at.
    monkeypatch.setenv(FREEZE_PERSIST_AUTHORIZED_ENV, "1")
    rc = freeze_derive(REPO_ROOT, persist=True, database_url=DB_URL, frozen_at=FIXED_FROZEN_AT)
    assert rc == 0
    persisted = dict(json.loads(capsys.readouterr().out))
    assert persisted["persisted"] is True
    assert persisted["receipt_id"] == receipt_id
    durable_freeze_at = str(persisted["durable_freeze_at"])
    # receipt_created_at (wall clock) and durable_freeze_at (canonical DB
    # commit clock) are different clocks and never collapse.
    assert persisted["receipt_created_at"] == FIXED_CREATED_AT_TEXT
    assert durable_freeze_at != persisted["receipt_created_at"]
    assert durable_freeze_at > str(persisted["receipt_created_at"])

    # 4. Durability reports the canonical stamp, never a local clock.
    rc = freeze_durability(receipt_id, database_url=DB_URL)
    assert rc == 0
    durability = dict(json.loads(capsys.readouterr().out))
    assert durability["durability"] == "DURABLE"
    assert durability["durable_freeze_at"] == durable_freeze_at

    # 5. Verify against the STORED receipt recomputes OK in the live repo.
    rc = freeze_verify(REPO_ROOT, receipt_id=receipt_id, database_url=DB_URL)
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FROZEN"
    assert report["drift_reasons"] == []

    # 6. WRONG-freeze verify prints the exact drift report and exits non-zero.
    receipt = _load_receipt_from_db(receipt_id)
    wrong_receipt = replace(
        receipt,
        preregistration_digest=Digest("sha256:" + "0" * 64),
        preregistration_config_digest=Digest("sha256:" + "1" * 64),
        dependency_lock_digest=Digest("sha256:" + "2" * 64),
        source_registry_digest=Digest("sha256:" + "3" * 64),
    )
    wrong_path = tmp_path / f"tampered_freeze_{receipt_id[-8:]}.json"
    wrong_path.write_text(json.dumps(wrong_receipt.to_canonical(), sort_keys=True))
    wrong_rc = freeze_verify(REPO_ROOT, receipt_file=wrong_path, verified_at=FIXED_FROZEN_AT)
    assert wrong_rc == 1
    wrong_report = json.loads(capsys.readouterr().out)
    assert wrong_report["status"] == "DRIFTED"
    assert "preregistration file digest drifted" in wrong_report["drift_reasons"]
    assert "preregistration configuration digest drifted" in wrong_report["drift_reasons"]
    assert "dependency lock digest drifted" in wrong_report["drift_reasons"]
    assert "source registry digest drifted" in wrong_report["drift_reasons"]
    wrong_path.unlink(missing_ok=True)

    # 7. Confirmatory authority requires BOTH canonical DB durability and
    # verified Git publication. The scientific clock is the Git committer time.
    durable = datetime.fromisoformat(durable_freeze_at)
    publication_at = durable + timedelta(seconds=1)
    first_boundary = first_confirmatory_boundary(publication_at)

    unpublished = evaluate_confirmatory_gates(
        FreezeBinding(receipt=receipt, durable_freeze_at=durable),
        as_of=first_boundary,
        canonical_context=True,
    )
    assert unpublished.allowed is False
    assert "no verified Git publication" in unpublished.reason

    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit="c" * 40,
        publication_committer_at=publication_at,
    )
    with psycopg.connect(DB_URL) as conn:
        publication_repo = PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        )
        publication_repo.record_fixture_publication(publication)
        assert publication_repo.get_publication(receipt_id) == publication

    published_binding = FreezeBinding(
        receipt=receipt,
        durable_freeze_at=durable,
        publication_commit=publication.publication_commit,
        publication_committer_at=publication.publication_committer_at,
    )
    allowed = evaluate_confirmatory_gates(
        published_binding,
        as_of=first_boundary,
        canonical_context=True,
    )
    assert allowed.allowed is True

    not_durable = evaluate_confirmatory_gates(
        FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None,
            publication_commit=publication.publication_commit,
            publication_committer_at=publication.publication_committer_at,
        ),
        as_of=first_boundary,
        canonical_context=True,
    )
    assert not_durable.allowed is False
    assert "durable_freeze_at NULL" in not_durable.reason

    early = evaluate_confirmatory_gates(
        published_binding,
        as_of=first_boundary - timedelta(seconds=300),
        canonical_context=True,
    )
    assert early.allowed is False
    assert "outside the fixed preregistered ranking window" in early.reason


def _load_receipt_from_db(receipt_id: str) -> CandidateFreezeReceipt:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        stored = PostgresCandidateFreezeRepository(conn).get_receipt_json(receipt_id)
    assert stored is not None
    return candidate_freeze_receipt_from_canonical(stored)
