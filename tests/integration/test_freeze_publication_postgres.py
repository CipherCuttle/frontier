# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

psycopg = pytest.importorskip("psycopg")
from frontier.adapters.postgres.advanced_intelligence import PostgresCandidateFreezeRepository
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.application.freeze_publication import CandidateFreezePublication
from frontier.domain.candidate_freeze import FreezeInputs, build_candidate_freeze_receipt
from frontier.domain.digests import Digest
from tests.integration.freeze_publication_fixture import record_fixture_publication

DB = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_publication_requires_authority_and_binds_durable_receipt():
    assert DB
    with psycopg.connect(DB) as conn:
        receipt = build_candidate_freeze_receipt(
            FreezeInputs(
                preregistration_digest=Digest("sha256:" + "1" * 64),
                preregistration_config_digest=Digest(
                    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
                ),
                implementation_commit="a" * 40,
                implementation_tree_digest="b" * 40,
                dependency_lock_digest=Digest("sha256:" + "2" * 64),
                source_registry_digest=Digest("sha256:" + "3" * 64),
                registry_entry_digests=(),
            ),
            frozen_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        row = conn.execute(
            "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id=%s",
            (receipt.receipt_id,),
        ).fetchone()
        assert row and row[0]
        publication = CandidateFreezePublication(
            freeze_receipt_id=receipt.receipt_id,
            freeze_receipt_digest=receipt.receipt_digest,
            implementation_commit=receipt.implementation_commit or "",
            implementation_tree_digest=receipt.implementation_tree_digest or "",
            publication_commit="c" * 40,
            publication_committer_at=row[0] + timedelta(seconds=1),
        )
        repo = PostgresCandidateFreezePublicationRepository(conn)
        with pytest.raises(PermissionError):
            repo.record_publication(publication)
        authorized_repo = PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        )
        with pytest.raises(PermissionError):
            authorized_repo.record_publication(publication)
        record_fixture_publication(conn, publication)
        loaded = repo.get_publication(receipt.receipt_id)
        assert loaded == publication
