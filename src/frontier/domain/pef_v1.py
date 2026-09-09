from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CONFIGURATION,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    PefArtifact,
    PefArtifactStatus,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_pef_ranking,
    canonical_freeze_components,
    pef_input_digest,
    shadow_universe_digest,
)
from .canonical_json import CanonicalValue, canonical_json_bytes
from .digests import Digest, sha256_digest
from .intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_CONFIGURATION_DIGEST,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineObservationInput,
    BaselineSnapshot,
)
from .receipt import ProjectionReceipt, ProjectionStatus

PEF_V1_EXPERIMENT_ID = "advanced-ranking-pef-v1"
PEF_V1_CANDIDATE_ID = "prospective-primary-emission-freshness-v1"
PEF_V1_PROJECTION_NAME = PEF_V1_EXPERIMENT_ID
PEF_V1_PROJECTION_VERSION = PEF_V1_CANDIDATE_ID
PEF_V1_PREREGISTRATION_PATH = "experiments/advanced_intelligence/pef_v1/preregistration.json"
PEF_V1_GROUPING_CONTRACT = (
    "candidate and control use the exact grouping-scalable-v1 projection at each as_of; "
    "candidate never regroups observations; grouping identity is bound by this successor "
    "preregistration"
)

PEF_V1_CONFIGURATION: dict[str, CanonicalValue] = dict(PEF_CONFIGURATION)
PEF_V1_CONFIGURATION["grouping_contract"] = PEF_V1_GROUPING_CONTRACT
PEF_V1_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(PEF_V1_CONFIGURATION))
PEF_V1_PREREGISTERED_CONFIG_DIGEST = Digest(
    "sha256:db2305ee0d89ee56b4c0a2837fd7034dad899ec5fc41acc710358b434a52fd67"
)


def require_pef_v1_configuration_identity() -> None:
    if PEF_V1_CONFIGURATION_DIGEST != PEF_V1_PREREGISTERED_CONFIG_DIGEST:
        raise RuntimeError("PEF_V1 configuration digest drifted from preregistration")


def require_pef_v1_control_identity(
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
) -> None:
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("PEF_V1 requires a COMPLETE control snapshot")
    if (
        control_receipt.output_digest.value.removeprefix("sha256:")
        != control_snapshot.snapshot_id.removeprefix("snapshot_")
    ):
        raise ValueError("control receipt does not bind the given control snapshot")
    if control_receipt.projection_name != BASELINE_PROJECTION_NAME:
        raise ValueError("control receipt projection name mismatch")
    if control_receipt.projection_version != BASELINE_PROJECTION_VERSION:
        raise ValueError("control receipt projection version mismatch")
    if control_receipt.schema_version != BASELINE_SCHEMA_VERSION:
        raise ValueError("control receipt schema version mismatch")
    if control_receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise ValueError("control receipt algorithm version mismatch")
    if control_receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise ValueError("control receipt ranking policy version mismatch")
    if control_receipt.configuration_digest != BASELINE_CONFIGURATION_DIGEST:
        raise ValueError("control receipt configuration digest mismatch")


def build_pef_v1_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> PefArtifact:
    require_pef_v1_configuration_identity()
    require_pef_v1_control_identity(control_snapshot, control_receipt)
    ranking = build_pef_ranking(observations, control_snapshot=control_snapshot, as_of=as_of)
    return PefArtifact(
        as_of=as_of,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        generated_at=generated_at,
        episodes=ranking,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
    )


def failed_pef_v1_artifact(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
    failure_reason: str,
) -> PefArtifact:
    require_pef_v1_configuration_identity()
    require_pef_v1_control_identity(control_snapshot, control_receipt)
    return PefArtifact(
        as_of=as_of,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        generated_at=generated_at,
        status=PefArtifactStatus.FAILED,
        failure_reason=failure_reason,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
    )


def build_pef_v1_receipt(
    artifact: PefArtifact,
    *,
    observations: Iterable[BaselineObservationInput],
    control_snapshot: BaselineSnapshot,
) -> ProjectionReceipt:
    require_pef_v1_configuration_identity()
    if artifact.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("PEF_V1 artifact experiment id mismatch")
    if artifact.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("PEF_V1 artifact candidate id mismatch")
    if artifact.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 artifact configuration digest mismatch")
    if artifact.status is PefArtifactStatus.RAN:
        status = ProjectionStatus.COMPLETE
    elif artifact.status is PefArtifactStatus.FAILED:
        status = ProjectionStatus.FAILED
    else:
        raise ValueError("NOT_RUN PEF_V1 artifacts cannot produce receipts")
    return ProjectionReceipt(
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
        input_digest=pef_input_digest(observations, control_snapshot=control_snapshot),
        output_digest=artifact.output_digest,
        status=status,
    )


def _require_v1_candidate_identity(
    artifact: PefArtifact,
    receipt: ProjectionReceipt,
) -> None:
    if artifact.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("candidate artifact experiment id mismatch")
    if artifact.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("candidate artifact candidate id mismatch")
    if artifact.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("candidate artifact schema version mismatch")
    if artifact.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("candidate artifact algorithm version mismatch")
    if artifact.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("candidate artifact ranking policy version mismatch")
    if artifact.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("candidate artifact configuration digest mismatch")
    if artifact.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("candidate artifact authority state mismatch")
    if receipt.projection_name != PEF_V1_PROJECTION_NAME:
        raise ValueError("candidate receipt projection name mismatch")
    if receipt.projection_version != PEF_V1_PROJECTION_VERSION:
        raise ValueError("candidate receipt projection version mismatch")
    if receipt.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("candidate receipt schema version mismatch")
    if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("candidate receipt algorithm version mismatch")
    if receipt.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("candidate receipt ranking policy version mismatch")
    if receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("candidate receipt configuration digest mismatch")
    if receipt.output_digest != artifact.output_digest:
        raise ValueError("candidate receipt does not bind the candidate artifact")
    expected_status = (
        ProjectionStatus.COMPLETE
        if artifact.status is PefArtifactStatus.RAN
        else ProjectionStatus.FAILED
    )
    if receipt.status is not expected_status:
        raise ValueError("candidate receipt status does not match candidate artifact")


def _require_paired_universe(
    control_snapshot: BaselineSnapshot,
    candidate_artifact: PefArtifact,
) -> None:
    control_universe = {
        episode.episode_id: tuple(episode.observation_ids) for episode in control_snapshot.episodes
    }
    candidate_universe = {
        episode.episode_id: tuple(episode.observation_ids) for episode in candidate_artifact.episodes
    }
    if len(candidate_universe) != len(candidate_artifact.episodes):
        raise ValueError("candidate ranking contains duplicate episode ids")
    if control_universe != candidate_universe:
        raise ValueError("PEF_V1 requires an identical episode universe for both arms")


def _control_ranking(control_snapshot: BaselineSnapshot) -> tuple[ShadowControlArmRanking, ...]:
    return tuple(
        ShadowControlArmRanking(rank=episode.rank, episode_id=episode.episode_id)
        for episode in sorted(control_snapshot.episodes, key=lambda item: item.rank)
    )


def build_shadow_experiment_run_v1(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    candidate_artifact: PefArtifact,
    candidate_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
    candidate_freeze_receipt_id: str | None = None,
) -> ShadowExperimentRun:
    require_pef_v1_configuration_identity()
    require_pef_v1_control_identity(control_snapshot, control_receipt)
    _require_v1_candidate_identity(candidate_artifact, candidate_receipt)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("PEF_V1 shadow run as_of must be timezone-aware")
    if as_of != control_snapshot.as_of or candidate_artifact.as_of != as_of:
        raise ValueError("PEF_V1 requires identical as_of for both arms")
    if candidate_artifact.control_snapshot_id != control_snapshot.snapshot_id:
        raise ValueError("candidate artifact must bind the control snapshot")
    if candidate_artifact.control_receipt_id != control_receipt.receipt_id:
        raise ValueError("candidate artifact must bind the control receipt")
    if candidate_artifact.source_registry_version != control_receipt.source_registry_version:
        raise ValueError("candidate and control source registry versions differ")
    if candidate_receipt.source_registry_version != control_receipt.source_registry_version:
        raise ValueError("candidate receipt and control source registry versions differ")

    freeze_id = canonical_freeze_components(candidate_freeze_receipt_id)
    common = dict(
        as_of=as_of,
        generated_at=generated_at,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        coverage_state=control_snapshot.coverage_state,
        freshness_state=control_snapshot.freshness_state,
        transport_state=control_snapshot.transport_state,
        schema_state=control_snapshot.schema_state,
        episode_universe_digest=shadow_universe_digest(control_snapshot),
        candidate_artifact_id=candidate_artifact.artifact_id,
        candidate_output_digest=candidate_artifact.output_digest,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        candidate_freeze_receipt_id=freeze_id,
    )
    if candidate_artifact.status is PefArtifactStatus.RAN:
        _require_paired_universe(control_snapshot, candidate_artifact)
        return ShadowExperimentRun(
            **common,
            status=ShadowRunStatus.RAN,
            control_ranking=_control_ranking(control_snapshot),
        )
    return ShadowExperimentRun(
        **common,
        status=ShadowRunStatus.FAILED,
        failure_reason=candidate_artifact.failure_reason,
    )
