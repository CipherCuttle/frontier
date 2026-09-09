# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from frontier.adapters.postgres import candidate_freeze_v1 as postgres_v1
from frontier.application.candidate_freeze_v1 import freeze_candidate_v1
from frontier.application.freeze_publication import CandidateFreezePublication
from frontier.domain.candidate_freeze import FreezeStatus
from frontier.domain.candidate_freeze_v1 import CandidateFreezeReceiptV1
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_v1_freeze_persistence_is_authorized_and_db_durable() -> None:
    assert DB_URL is not None
    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=datetime.now(UTC) - timedelta(minutes=1))
    assert receipt.status is FreezeStatus.FROZEN

    with psycopg.connect(DB_URL) as conn:
        unauthorized = postgres_v1.PostgresCandidateFreezeV1Repository(conn)
        with pytest.raises(PermissionError, match="PEF_V1 candidate freeze persistence"):
            unauthorized.record_receipt(receipt)

        repository = postgres_v1.PostgresCandidateFreezeV1Repository(
            conn, persistence_authorized=True
        )
        repository.record_receipt(receipt)
        assert repository.get_receipt_json(receipt.receipt_id) == receipt.to_canonical()
        durable_freeze_at = repository.get_durable_freeze_at(receipt.receipt_id)
        assert durable_freeze_at is not None
        assert durable_freeze_at >= receipt.frozen_at

        row = conn.execute(
            """SELECT candidate_id, experiment_id, configuration_digest,
                      preregistration_path, status
                 FROM candidate_freeze_receipts WHERE receipt_id=%s""",
            (receipt.receipt_id,),
        ).fetchone()
        assert row == (
            PEF_V1_CANDIDATE_ID,
            PEF_V1_EXPERIMENT_ID,
            str(PEF_V1_CONFIGURATION_DIGEST),
            receipt.preregistration_path,
            "FROZEN",
        )


def test_v1_freeze_persistence_rejects_drifted_and_forged_frozen_receipts() -> None:
    assert DB_URL is not None
    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=datetime.now(UTC) - timedelta(minutes=1))
    assert receipt.status is FreezeStatus.FROZEN
    drifted = replace(receipt, status=FreezeStatus.DRIFTED, drift_reasons=("test drift",))
    forged = replace(
        receipt,
        preregistration_config_digest=None,
        implementation_commit=None,
        implementation_tree_digest=None,
        dependency_lock_digest=None,
        source_registry_digest=None,
        registry_entry_digests=(),
    )

    with psycopg.connect(DB_URL) as conn:
        repository = postgres_v1.PostgresCandidateFreezeV1Repository(
            conn, persistence_authorized=True
        )
        with pytest.raises(ValueError, match="requires a FROZEN receipt"):
            repository.record_receipt(drifted)
        with pytest.raises(ValueError, match="does not exactly bind deployed Git HEAD"):
            repository.record_receipt(forged)
        count = conn.execute(
            "SELECT COUNT(*) FROM candidate_freeze_receipts WHERE receipt_id IN (%s, %s)",
            (drifted.receipt_id, forged.receipt_id),
        ).fetchone()
        assert count == (0,)


def test_v1_publication_repository_routes_through_deployed_v1_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DB_URL is not None
    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=datetime.now(UTC) - timedelta(minutes=1))
    assert receipt.status is FreezeStatus.FROZEN

    with psycopg.connect(DB_URL) as conn:
        receipt_repository = postgres_v1.PostgresCandidateFreezeV1Repository(
            conn, persistence_authorized=True
        )
        receipt_repository.record_receipt(receipt)
        durable_freeze_at = receipt_repository.get_durable_freeze_at(receipt.receipt_id)
        assert durable_freeze_at is not None
        assert receipt.implementation_commit is not None
        assert receipt.implementation_tree_digest is not None
        publication = CandidateFreezePublication(
            freeze_receipt_id=receipt.receipt_id,
            freeze_receipt_digest=receipt.receipt_digest,
            implementation_commit=receipt.implementation_commit,
            implementation_tree_digest=receipt.implementation_tree_digest,
            publication_commit="c" * 40,
            publication_committer_at=durable_freeze_at + timedelta(seconds=1),
        )

        def derive_v1(
            root: Path,
            bound_receipt: CandidateFreezeReceiptV1,
            *,
            receipt_path: Path | None = None,
        ) -> CandidateFreezePublication:
            del receipt_path
            assert root == REPO_ROOT
            assert bound_receipt == receipt
            return publication

        monkeypatch.setattr(
            postgres_v1,
            "derive_github_main_freeze_publication_v1",
            derive_v1,
        )
        repository = postgres_v1.PostgresCandidateFreezePublicationV1Repository(conn)
        with pytest.raises(PermissionError, match="publication persistence is not authorized"):
            repository.record_verified_publication(receipt)
        with pytest.raises(PermissionError, match="raw PEF_V1"):
            repository.record_publication(publication)

        authorized = postgres_v1.PostgresCandidateFreezePublicationV1Repository(
            conn, persistence_authorized=True
        )
        assert authorized.record_verified_publication(receipt) == publication
        assert authorized.get_publication(receipt.receipt_id) == publication
