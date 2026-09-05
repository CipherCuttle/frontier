# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresEvaluationRepository,
)
from frontier.domain.advanced_intelligence import PEF_CONFIGURATION_DIGEST
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import (
    EvaluationReceipt,
    EvaluationStatus,
    ShadowRunBinding,
    build_evaluation_receipt,
)

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

FROZEN_AT = datetime(2026, 9, 1, tzinfo=UTC)
AS_OF = FROZEN_AT + timedelta(days=1)


def _freeze_receipt(status: FreezeStatus) -> CandidateFreezeReceipt:
    frozen = status is FreezeStatus.FROZEN
    inputs = FreezeInputs(
        preregistration_digest=Digest("sha256:" + "2" * 64),
        preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
        implementation_commit="a" * 64 if frozen else None,
        implementation_tree_digest="b" * 64 if frozen else None,
        dependency_lock_digest=Digest("sha256:" + "3" * 64) if frozen else None,
        source_registry_digest=Digest("sha256:" + "4" * 64) if frozen else None,
        registry_entry_digests=() if frozen else None,
    )
    return build_candidate_freeze_receipt(inputs, frozen_at=FROZEN_AT)


def _evaluation_receipt(freeze_receipt: CandidateFreezeReceipt) -> EvaluationReceipt:
    return build_evaluation_receipt(
        as_of=AS_OF,
        generated_at=AS_OF,
        shadow_runs=(
            ShadowRunBinding(
                run_id="shadowrun_" + "9" * 64, run_digest=Digest("sha256:" + "8" * 64)
            ),
        ),
        candidate_freeze_receipt_id=freeze_receipt.receipt_id,
        freeze_receipt_digest=freeze_receipt.receipt_digest,
        preregistration_digest=freeze_receipt.preregistration_digest,
        freeze_status=freeze_receipt.status,
        opportunities=(),
        tracking_by_anchor={},
        domain_evaluations=(),
        pooled_median=Decimal("0"),
        status=EvaluationStatus.INSUFFICIENT_SAMPLE,
        status_reason="fewer than two adequately sampled domains: 0 qualifying of 0",
    )


def test_postgres_evaluation_receipt_persists_and_is_append_only() -> None:
    assert DB_URL is not None
    freeze_receipt = _freeze_receipt(FreezeStatus.FROZEN)
    assert freeze_receipt.status is FreezeStatus.FROZEN
    receipt = _evaluation_receipt(freeze_receipt)

    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn).record_receipt(freeze_receipt)
        repository = PostgresEvaluationRepository(conn)
        repository.record_receipt(receipt)
        assert repository.latest_evaluation_id() == receipt.evaluation_id
        retained = repository.get_receipt_json(receipt.evaluation_id)
        assert retained == receipt.to_canonical()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, candidate_freeze_receipt_id, freeze_status,
                       freeze_receipt_digest, preregistration_digest, receipt_digest
                FROM evaluation_receipts
                WHERE evaluation_id = %s
                """,
                (receipt.evaluation_id,),
            )
            row = cur.fetchone()
        assert row == (
            "INSUFFICIENT_SAMPLE",
            freeze_receipt.receipt_id,
            "FROZEN",
            str(receipt.freeze_receipt_digest),
            str(receipt.preregistration_digest),
            str(receipt.receipt_digest),
        )

        # Re-recording the identical receipt is an append-only no-op.
        repository.record_receipt(receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM evaluation_receipts WHERE evaluation_id = %s",
                (receipt.evaluation_id,),
            )
            assert cur.fetchone() == (1,)

        # Append-only guard: mutation of a durable receipt must be rejected.
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE evaluation_receipts SET status = 'COMPLETE' WHERE evaluation_id = %s",
                (receipt.evaluation_id,),
            )


def test_postgres_drifted_freeze_evaluation_is_recorded_with_drift_status() -> None:
    assert DB_URL is not None
    freeze_receipt = _freeze_receipt(FreezeStatus.DRIFTED)
    assert freeze_receipt.status is FreezeStatus.DRIFTED
    receipt = _evaluation_receipt(freeze_receipt)
    assert receipt.status is EvaluationStatus.INSUFFICIENT_SAMPLE
    assert receipt.confirmatory_evidence is False
    assert receipt.freeze_status is FreezeStatus.DRIFTED

    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn).record_receipt(freeze_receipt)
        repository = PostgresEvaluationRepository(conn)
        repository.record_receipt(receipt)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT freeze_status, status FROM evaluation_receipts WHERE evaluation_id = %s",
                (receipt.evaluation_id,),
            )
            row = cur.fetchone()
        assert row == ("DRIFTED", "INSUFFICIENT_SAMPLE")


def test_postgres_evaluation_receipt_json_round_trip_shape() -> None:
    assert DB_URL is not None
    freeze_receipt = _freeze_receipt(FreezeStatus.FROZEN)
    receipt = _evaluation_receipt(freeze_receipt)
    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn).record_receipt(freeze_receipt)
        repository = PostgresEvaluationRepository(conn)
        repository.record_receipt(receipt)
        canonical = repository.get_receipt_json(receipt.evaluation_id)
        assert canonical is not None
        assert canonical["schema_version"] == "evaluation-receipt-v0"
        assert canonical["authority_state"] == "EXPERIMENTAL_EVALUATION"
        assert canonical["status"] == "INSUFFICIENT_SAMPLE"
        assert canonical["freeze_status"] == "FROZEN"
        assert canonical["verdict"] is None
