from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus
from frontier.domain.zero_day import ZeroDayPefPersistenceBinding, build_zero_day_seal

AS_OF = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)
REGISTRY = Digest("sha256:" + "a" * 64)
FREEZE_ID = "freezereceipt_" + "b" * 64


def _pair() -> tuple[PefV1Artifact, ShadowExperimentRun]:
    artifact = PefV1Artifact(
        as_of=AS_OF,
        control_snapshot_id="snapshot_control",
        control_receipt_id="receipt_control",
        source_registry_version=REGISTRY,
        generated_at=AS_OF,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        grouping_receipt_id="receipt_grouping",
    )
    run = ShadowExperimentRun(
        as_of=AS_OF,
        generated_at=AS_OF,
        control_snapshot_id=artifact.control_snapshot_id,
        control_receipt_id=artifact.control_receipt_id,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=ShadowRunStatus.RAN,
        episode_universe_digest=REGISTRY,
        candidate_artifact_id=artifact.artifact_id,
        candidate_output_digest=artifact.output_digest,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        candidate_freeze_receipt_id=FREEZE_ID,
    )
    return artifact, run


def _persistence(artifact: PefV1Artifact) -> ZeroDayPefPersistenceBinding:
    material: dict[str, CanonicalValue] = {
        "control_snapshot_id": artifact.control_snapshot_id,
        "observations": [],
    }
    receipt = ProjectionReceipt(
        receipt_schema_version=PEF_RECEIPT_SCHEMA_VERSION,
        projection_name=PEF_V1_PROJECTION_NAME,
        projection_version=PEF_V1_PROJECTION_VERSION,
        schema_version=PEF_SCHEMA_VERSION,
        algorithm_version=PEF_ALGORITHM_VERSION,
        ranking_policy_version=PEF_RANKING_POLICY_VERSION,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        source_registry_version=artifact.source_registry_version,
        as_of=artifact.as_of,
        generated_at=artifact.generated_at,
        input_digest=sha256_digest(canonical_json_bytes(material)),
        output_digest=artifact.output_digest,
        status=ProjectionStatus.COMPLETE,
    )
    persisted_at = AS_OF + timedelta(seconds=1)
    return ZeroDayPefPersistenceBinding(
        candidate_receipt=receipt,
        artifact_receipt_id=receipt.receipt_id,
        artifact_persisted_at=persisted_at,
        candidate_receipt_persisted_at=persisted_at,
        run_persisted_at=persisted_at,
    )


def _seal(artifact: PefV1Artifact, run: ShadowExperimentRun):
    return build_zero_day_seal(
        artifact,
        run,
        (),
        _persistence(artifact),
        run_class="CONFIRMATORY",
        sealed_at=AS_OF + timedelta(minutes=1),
    )


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    (
        ("schema_version", "pef-ranking-artifact-v999"),
        ("algorithm_version", "drifted-pef-algorithm"),
        ("ranking_policy_version", "drifted-pef-ranking-policy"),
    ),
)
def test_seal_rejects_self_consistent_non_pef_candidate_identity(
    field: str,
    drifted_value: str,
) -> None:
    artifact, run = _pair()
    drifted_artifact = replace(artifact, **{field: drifted_value})
    drifted_run = replace(
        run,
        candidate_artifact_id=drifted_artifact.artifact_id,
        candidate_output_digest=drifted_artifact.output_digest,
    )

    with pytest.raises(ValueError, match="artifact version identity"):
        _seal(drifted_artifact, drifted_run)


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    (
        ("schema_version", "shadow-experiment-run-v999"),
        ("algorithm_version", "drifted-shadow-algorithm"),
    ),
)
def test_seal_rejects_self_consistent_non_pef_shadow_run_identity(
    field: str,
    drifted_value: str,
) -> None:
    artifact, run = _pair()
    drifted_run = replace(run, **{field: drifted_value})

    with pytest.raises(ValueError, match="shadow-run version identity"):
        _seal(artifact, drifted_run)


def test_fixture_uses_frozen_identity_constants() -> None:
    artifact, run = _pair()

    assert artifact.schema_version == PEF_SCHEMA_VERSION
    assert artifact.algorithm_version == PEF_ALGORITHM_VERSION
    assert artifact.ranking_policy_version == PEF_RANKING_POLICY_VERSION
    assert run.schema_version == SHADOW_SCHEMA_VERSION
    assert run.algorithm_version == PEF_ALGORITHM_VERSION
