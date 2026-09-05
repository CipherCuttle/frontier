# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
)
from frontier.application.candidate_freeze import freeze_candidate
from frontier.domain.candidate_freeze import (
    FREEZE_RECEIPT_ID_PREFIX,
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def _entry_jsonb(receipt: CandidateFreezeReceipt) -> Jsonb:
    assert receipt.registry_entry_digests is not None
    return Jsonb(
        [{"digest": str(e.digest), "path": e.path} for e in receipt.registry_entry_digests]
    )


def test_postgres_candidate_freeze_receipt_persists_and_is_append_only() -> None:
    assert DB_URL is not None
    frozen_at = datetime.now(UTC)
    receipt = freeze_candidate(REPO_ROOT, frozen_at=frozen_at)
    assert receipt.status is FreezeStatus.FROZEN

    with psycopg.connect(DB_URL) as conn:
        repository = PostgresCandidateFreezeRepository(conn)
        repository.record_receipt(receipt)
        assert repository.latest_receipt_id() == receipt.receipt_id
        retained = repository.get_receipt_json(receipt.receipt_id)
        assert retained == receipt.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, configuration_digest, preregistration_path,
                       preregistration_digest, implementation_commit,
                       implementation_tree_digest, dependency_lock_digest,
                       source_registry_digest, receipt_digest
                FROM candidate_freeze_receipts
                WHERE receipt_id = %s
                """,
                (receipt.receipt_id,),
            )
            row = cur.fetchone()
        assert row == (
            "FROZEN",
            str(receipt.configuration_digest),
            receipt.preregistration_path,
            str(receipt.preregistration_digest),
            receipt.implementation_commit,
            receipt.implementation_tree_digest,
            str(receipt.dependency_lock_digest),
            str(receipt.source_registry_digest),
            str(receipt.receipt_digest),
        )

        # Re-recording the identical receipt is an append-only no-op.
        repository.record_receipt(receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt.receipt_id,),
            )
            assert cur.fetchone() == (1,)

        # A conflicting identity with a different digest must never be stored.
        with (
            pytest.raises(psycopg.errors.UniqueViolation),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                INSERT INTO candidate_freeze_receipts (
                    receipt_id, schema_version, candidate_id, experiment_id,
                    algorithm_version, configuration_digest, status,
                    preregistration_path, preregistration_digest,
                    preregistration_config_digest, implementation_commit,
                    implementation_tree_digest, dependency_lock_digest,
                    source_registry_digest, registry_entry_digests,
                    drift_reasons, receipt_digest, frozen_at, verified_at,
                    original_receipt_digest, receipt_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    receipt.receipt_id,
                    receipt.schema_version,
                    receipt.candidate_id,
                    receipt.experiment_id,
                    receipt.algorithm_version,
                    str(receipt.configuration_digest),
                    "DRIFTED",
                    receipt.preregistration_path,
                    str(receipt.preregistration_digest),
                    str(receipt.preregistration_config_digest),
                    receipt.implementation_commit,
                    receipt.implementation_tree_digest,
                    str(receipt.dependency_lock_digest),
                    str(receipt.source_registry_digest),
                    _entry_jsonb(receipt),
                    Jsonb(["dependency lock digest drifted"]),
                    "sha256:" + "e" * 64,
                    receipt.frozen_at,
                    frozen_at,
                    str(receipt.receipt_digest),
                    Jsonb(receipt.to_canonical()),
                ),
            )


def test_postgres_candidate_freeze_receipt_stores_drifted_explicitly() -> None:
    assert DB_URL is not None
    frozen_at = datetime.now(UTC)
    healthy = freeze_candidate(REPO_ROOT, frozen_at=frozen_at)
    receipt = build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=healthy.preregistration_digest,
            preregistration_config_digest=None,
            implementation_commit=None,
            implementation_tree_digest=None,
            dependency_lock_digest=None,
            source_registry_digest=None,
            registry_entry_digests=None,
        ),
        frozen_at=frozen_at,
    )
    assert receipt.status is FreezeStatus.DRIFTED
    assert receipt.drift_reasons

    with psycopg.connect(DB_URL) as conn:
        repository = PostgresCandidateFreezeRepository(conn)
        repository.record_receipt(receipt)
        assert repository.latest_receipt_id() == receipt.receipt_id
        assert receipt.receipt_id.startswith(FREEZE_RECEIPT_ID_PREFIX)
        retained = repository.get_receipt_json(receipt.receipt_id)
        assert retained == receipt.to_canonical()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, drift_reasons FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt.receipt_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "DRIFTED"
        assert list(row[1]) == list(receipt.drift_reasons)
