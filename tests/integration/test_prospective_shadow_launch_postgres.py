# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.config import load_source_registry
from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresPefArtifactRepository,
)
from frontier.adapters.postgres.prospective_shadow import (
    PostgresProspectiveBaselineIntelligenceRepository,
    PostgresProspectiveShadowRunRepository,
)
from frontier.application.prospective_shadow import run_confirmatory_shadow_boundary
from frontier.domain.advanced_intelligence import PEF_CONFIGURATION_DIGEST, ShadowRunStatus
from frontier.domain.candidate_freeze import (
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

AS_OF = datetime(2035, 1, 1, 0, 0, tzinfo=UTC)
DURABLE = AS_OF - timedelta(seconds=1)
GENERATED_AT = AS_OF + timedelta(seconds=30)


def _freeze_receipt():
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
            implementation_commit="a" * 40,
            implementation_tree_digest="b" * 40,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=DURABLE - timedelta(seconds=1),
    )


def test_confirmatory_boundary_persists_freeze_candidate_and_bound_run() -> None:
    assert DB_URL is not None
    receipt = _freeze_receipt()
    assert receipt.status is FreezeStatus.FROZEN
    registry = load_source_registry(Path("."))

    with psycopg.connect(DB_URL) as conn:
        baseline = PostgresProspectiveBaselineIntelligenceRepository(conn, registry)
        pef = PostgresPefArtifactRepository(conn)
        shadow = PostgresProspectiveShadowRunRepository(conn)
        freeze = PostgresCandidateFreezeRepository(conn)

        assert baseline.list_enabled_source_ids() == sorted(registry.sources)
        result = run_confirmatory_shadow_boundary(
            baseline_repository=baseline,
            pef_repository=pef,
            shadow_repository=shadow,
            freeze_repository=freeze,
            freeze_receipt=receipt,
            durable_freeze_at=DURABLE,
            as_of=AS_OF,
            generated_at=GENERATED_AT,
            source_registry_version=registry.source_registry_version,
        )

        assert result.execution.run.status is ShadowRunStatus.RAN
        assert result.execution.run.candidate_freeze_receipt_id == receipt.receipt_id
        assert freeze.get_receipt_json(receipt.receipt_id) == receipt.to_canonical()
        assert pef.get_artifact_json(result.execution.candidate.artifact.artifact_id) == (
            result.execution.candidate.artifact.to_canonical()
        )
        assert (
            shadow.get_run_json(result.execution.run.run_id) == result.execution.run.to_canonical()
        )
        assert shadow.bound_run_boundaries(
            candidate_freeze_receipt_id=receipt.receipt_id,
            start=AS_OF,
            end=AS_OF + timedelta(minutes=5),
        ) == (AS_OF,)

        shadow.record_window_binding(
            candidate_freeze_receipt_id=receipt.receipt_id,
            durable_freeze_commit="c" * 40,
            durable_freeze_at=DURABLE,
            window_start=AS_OF,
            window_end=AS_OF + timedelta(days=28),
        )
        conn.commit()
        shadow.record_window_binding(
            candidate_freeze_receipt_id=receipt.receipt_id,
            durable_freeze_commit="c" * 40,
            durable_freeze_at=DURABLE,
            window_start=AS_OF,
            window_end=AS_OF + timedelta(days=28),
        )
        conn.commit()
        with pytest.raises(RuntimeError, match="conflicting window binding"):
            shadow.record_window_binding(
                candidate_freeze_receipt_id=receipt.receipt_id,
                durable_freeze_commit="d" * 40,
                durable_freeze_at=DURABLE,
                window_start=AS_OF,
                window_end=AS_OF + timedelta(days=28),
            )
        conn.rollback()

        conflicting_run = replace(
            result.execution.run,
            generated_at=result.execution.run.generated_at + timedelta(seconds=1),
        )
        assert conflicting_run.run_id != result.execution.run.run_id
        with pytest.raises(psycopg.errors.UniqueViolation):
            shadow.record_run(conflicting_run)

        with pytest.raises(RuntimeError, match="already exists"):
            run_confirmatory_shadow_boundary(
                baseline_repository=baseline,
                pef_repository=pef,
                shadow_repository=shadow,
                freeze_repository=freeze,
                freeze_receipt=receipt,
                durable_freeze_at=DURABLE,
                as_of=AS_OF,
                generated_at=GENERATED_AT + timedelta(seconds=1),
                source_registry_version=registry.source_registry_version,
            )
