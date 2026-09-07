# ruff: noqa: E402
"""PostgreSQL integration for the WP5 drift sentry (SKIP without a test DB).

Drift is detected against a STORED candidate freeze receipt in the canonical
PostgreSQL authority: a durable stored receipt whose bound identity differs
from the live repository state must (a) SKIP the orchestrator attempt with a
DRIFTED detail on the confirmatory path, and (b) invalidate the confirmatory
evaluation to INVALID_DRIFT under the existing semantics. Fail-closed: no
auto-repair, no re-freeze, no adoption of current state.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
)
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresFreezeBindingResolver,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.application.drift_sentry import DriftSentry
from frontier.application.evaluation import PairedSnapshot, evaluate_shadow_experiment
from frontier.application.experiment_orchestration import (
    ExperimentOrchestrator,
    FreezeBinding,
)
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.domain.advanced_intelligence import (
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import (
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import EvaluationStatus
from frontier.domain.health import HealthValue
from frontier.domain.opportunity import ExperimentAttemptStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

PEF_CONFIG_DIGEST = Digest(
    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
)


class _UnusedBaselineRepository:
    """The drift path halts before any baseline work; never called."""

    confirmatory_source_registry_version = Digest("sha256:" + "4" * 64)

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[object]:
        raise AssertionError("drift sentry must halt before the baseline repository is used")

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[object]:
        raise AssertionError("drift sentry must halt before the baseline repository is used")

    def list_enabled_source_ids(self) -> list[str]:
        raise AssertionError("drift sentry must halt before the baseline repository is used")

    def list_latest_health_as_of(self, as_of: datetime) -> list[object]:
        raise AssertionError("drift sentry must halt before the baseline repository is used")


def _stored_frozen_receipt():
    """A FROZEN receipt with fabricated digests (guaranteed drift vs live)."""
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=PEF_CONFIG_DIGEST,
            implementation_commit="a" * 64,
            implementation_tree_digest="b" * 64,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=datetime.now(UTC),
    )


def test_stored_drifted_receipt_skips_the_confirmatory_attempt_in_postgres() -> None:
    assert DB_URL is not None
    receipt = _stored_frozen_receipt()
    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        resolver = PostgresFreezeBindingResolver(conn)
        binding = resolver.latest_binding()
        assert binding is not None
        assert binding.durable_freeze_at is not None
        publication_at = binding.durable_freeze_at + timedelta(seconds=1)
        PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        ).record_publication(
            CandidateFreezePublication(
                freeze_receipt_id=receipt.receipt_id,
                freeze_receipt_digest=receipt.receipt_digest,
                implementation_commit=receipt.implementation_commit,
                implementation_tree_digest=receipt.implementation_tree_digest,
                publication_commit="c" * 64,
                publication_committer_at=publication_at,
            )
        )
        binding = resolver.latest_binding()
        assert binding is not None
        assert binding.publication_committer_at == publication_at
        boundary = first_confirmatory_boundary(publication_at)
        orchestrator = ExperimentOrchestrator(
            attempts=PostgresExperimentAttemptRepository(conn),
            baseline_repository=_UnusedBaselineRepository(),  # pyright: ignore[reportArgumentType]
            persistence=PostgresShadowRunPersister(conn),
            source_registry_version=Digest("sha256:" + "4" * 64),
            freeze_binding=_FixedBinding(resolver),
            run_class="CONFIRMATORY",
            canonical_context=True,
            drift_sentry=DriftSentry(REPO_ROOT),
            clock=lambda: boundary,
        )
        result = orchestrator.run_cycle()
    assert result.action.value == "SKIPPED_CONFIRMATORY_GATES"
    assert result.attempt is not None
    assert result.attempt.status is ExperimentAttemptStatus.SKIPPED
    assert result.detail is not None and result.detail.startswith("DRIFTED: ")
    assert "dependency_lock_digest drifted" in result.detail
    # No shadow run was launched for the skipped boundary.
    assert (
        PostgresShadowRunPersister(psycopg.connect(DB_URL)).latest_run_id_and_class_for_as_of(
            boundary
        )
        is None
    )


class _FixedBinding:
    """Resolver double pinned to one concrete PG binding (deterministic tests)."""

    def __init__(self, resolver: PostgresFreezeBindingResolver) -> None:
        self._resolver = resolver

    def latest_binding(self) -> FreezeBinding | None:
        return self._resolver.latest_binding()


def test_stored_receipt_drift_invalidates_confirmatory_evaluation() -> None:
    assert DB_URL is not None
    receipt = _stored_frozen_receipt()
    durable = datetime.now(UTC)
    as_of = durable + timedelta(seconds=300)
    horizon = as_of + timedelta(hours=1)
    sentry = DriftSentry(REPO_ROOT)
    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        stored = PostgresFreezeBindingResolver(conn).latest_binding()
    assert stored is not None and stored.durable_freeze_at is not None
    durable_freeze_at = stored.durable_freeze_at
    # Drift detected against the STORED receipt in the canonical authority.
    report = sentry.check(stored.receipt, now=horizon)
    assert report.status.value == "DRIFTED"
    verified = sentry.verify_receipt(stored.receipt, now=horizon)
    assert verified.status.value == "DRIFTED"
    run = ShadowExperimentRun(
        as_of=as_of,
        generated_at=as_of,
        control_snapshot_id="snapshot_" + "4" * 64,
        control_receipt_id="receipt_" + "5" * 64,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=ShadowRunStatus.RAN,
        episode_universe_digest=Digest("sha256:" + "6" * 64),
        candidate_artifact_id="artifact_" + "7" * 64,
        candidate_output_digest=Digest("sha256:" + "8" * 64),
        control_ranking=(ShadowControlArmRanking(rank=1, episode_id="episode-a"),),
        candidate_freeze_receipt_id=verified.receipt_id,
    )
    evaluation = evaluate_shadow_experiment(
        snapshots=(PairedSnapshot(run=run, candidate_rank_by_episode={}, episode_memberships={}),),
        opportunity_groups=(),
        freeze_receipt=verified,
        evaluation_horizon=horizon,
        generated_at=horizon,
        durable_freeze_at=durable_freeze_at,
    )
    assert evaluation.status is EvaluationStatus.INVALID_DRIFT
    assert evaluation.confirmatory_evidence is False
    assert evaluation.candidate_freeze_receipt_id == verified.receipt_id
