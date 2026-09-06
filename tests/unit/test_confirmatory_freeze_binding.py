from __future__ import annotations

from datetime import UTC, datetime, timedelta

from frontier.application.evaluation import _confirmatory_run_binding_failure
from frontier.domain.advanced_intelligence import (
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import FreezeInputs, build_candidate_freeze_receipt
from frontier.domain.digests import Digest
from frontier.domain.health import HealthValue

FROZEN_AT = datetime(2026, 9, 6, 1, 0, tzinfo=UTC)


def _freeze():
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=Digest(
                "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
            ),
            implementation_commit="a" * 64,
            implementation_tree_digest="b" * 64,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(),
        ),
        frozen_at=FROZEN_AT,
    )


def _run(*, as_of: datetime, freeze_id: str | None) -> ShadowExperimentRun:
    return ShadowExperimentRun(
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
        candidate_freeze_receipt_id=freeze_id,
    )


def test_unbound_development_run_cannot_be_confirmatory() -> None:
    freeze = _freeze()
    failure = _confirmatory_run_binding_failure(
        (_run(as_of=FROZEN_AT + timedelta(seconds=300), freeze_id=None),), freeze
    )
    assert failure is not None
    assert "does not bind" in failure


def test_mismatched_freeze_identity_cannot_be_confirmatory() -> None:
    freeze = _freeze()
    other_freeze_id = "freezereceipt_" + "f" * 64
    failure = _confirmatory_run_binding_failure(
        (_run(as_of=FROZEN_AT + timedelta(seconds=300), freeze_id=other_freeze_id),), freeze
    )
    assert failure is not None
    assert "does not bind" in failure


def test_boundary_must_be_strictly_after_freeze() -> None:
    freeze = _freeze()
    failure = _confirmatory_run_binding_failure(
        (_run(as_of=FROZEN_AT, freeze_id=freeze.receipt_id),), freeze
    )
    assert failure is not None
    assert "not strictly after" in failure


def test_exact_post_freeze_binding_is_confirmatory_eligible() -> None:
    freeze = _freeze()
    failure = _confirmatory_run_binding_failure(
        (_run(as_of=FROZEN_AT + timedelta(seconds=300), freeze_id=freeze.receipt_id),), freeze
    )
    assert failure is None
