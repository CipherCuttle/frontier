from __future__ import annotations

from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    PEF_PROJECTION_NAME,
    PEF_PROJECTION_VERSION,
    PEF_RANKING_POLICY_VERSION,
    PEF_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    PefArtifact,
    PefArtifactStatus,
    ShadowExperimentRun,
)
from frontier.domain.candidate_freeze import (
    FREEZE_PREREGISTRATION_PATH,
    FREEZE_SCHEMA_VERSION,
    CandidateFreezeReceipt,
    FreezeStatus,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import sha256_digest
from frontier.domain.evaluation import (
    EVALUATION_ALGORITHM_VERSION,
    EVALUATION_AUTHORITY_STATE,
    EVALUATION_CONFIGURATION_DIGEST,
    EVALUATION_SCHEMA_VERSION,
    EvaluationReceipt,
)
from frontier.domain.features import (
    ADVANCED_FEATURES_CONFIGURATION_DIGEST,
    FEATURE_ALGORITHM_VERSION,
    FEATURE_SCHEMA_VERSION,
    FeatureVectorBatch,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus


class PostgresPefArtifactRepository:
    """Append-only persistence for PEF_V0 ranking artifacts and receipts."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def publish_complete_artifact(self, artifact: PefArtifact, receipt: ProjectionReceipt) -> None:
        self._publish(artifact, receipt, expected_status=PefArtifactStatus.RAN)

    def record_failed_artifact(self, artifact: PefArtifact, receipt: ProjectionReceipt) -> None:
        self._publish(artifact, receipt, expected_status=PefArtifactStatus.FAILED)

    def _publish(
        self,
        artifact: PefArtifact,
        receipt: ProjectionReceipt,
        *,
        expected_status: PefArtifactStatus,
    ) -> None:
        if artifact.status is not expected_status:
            raise ValueError(f"artifact status {artifact.status.value} does not match publish path")
        if (
            receipt.status is ProjectionStatus.COMPLETE
            and artifact.status is not PefArtifactStatus.RAN
        ):
            raise ValueError("only RAN pef artifacts may carry a COMPLETE receipt")
        if (
            receipt.status is ProjectionStatus.FAILED
            and artifact.status is not PefArtifactStatus.FAILED
        ):
            raise ValueError("only FAILED pef artifacts may carry a FAILED receipt")
        if receipt.projection_name != PEF_PROJECTION_NAME:
            raise ValueError("pef receipt projection name mismatch")
        if receipt.projection_version != PEF_PROJECTION_VERSION:
            raise ValueError("pef receipt projection version mismatch")
        if receipt.schema_version != PEF_SCHEMA_VERSION:
            raise ValueError("pef receipt schema version mismatch")
        if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("pef receipt algorithm version mismatch")
        if receipt.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
            raise ValueError("pef receipt ranking policy version mismatch")
        if receipt.configuration_digest != PEF_CONFIGURATION_DIGEST:
            raise ValueError("pef receipt configuration digest mismatch")
        output_digest = sha256_digest(canonical_json_bytes(artifact.to_canonical()))
        if output_digest != receipt.output_digest:
            raise ValueError("pef receipt output digest mismatch")

        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projection_receipts (
                    receipt_id, receipt_schema_version, projection_name,
                    projection_version, schema_version, algorithm_version,
                    ranking_policy_version, configuration_digest,
                    source_registry_version, as_of, generated_at,
                    input_digest, output_digest, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (receipt_id) DO NOTHING
                RETURNING receipt_id
                """,
                (
                    receipt.receipt_id,
                    receipt.receipt_schema_version,
                    receipt.projection_name,
                    receipt.projection_version,
                    receipt.schema_version,
                    receipt.algorithm_version,
                    receipt.ranking_policy_version,
                    str(receipt.configuration_digest),
                    str(receipt.source_registry_version),
                    receipt.as_of,
                    receipt.generated_at,
                    str(receipt.input_digest),
                    str(receipt.output_digest),
                    receipt.status.value,
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    """
                    SELECT output_digest, status FROM projection_receipts
                    WHERE receipt_id = %s
                    """,
                    (receipt.receipt_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("receipt conflict without existing row")
                if (
                    cast(str, existing[0]) != str(receipt.output_digest)
                    or cast(str, existing[1]) != receipt.status.value
                ):
                    raise RuntimeError("receipt identity conflict with different digest")

            cur.execute(
                """
                INSERT INTO pef_ranking_artifacts (
                    artifact_id, projection_version, schema_version,
                    algorithm_version, ranking_policy_version, configuration_digest,
                    authority_state, status, as_of, control_snapshot_id,
                    control_receipt_id, receipt_id, output_digest, failure_reason,
                    artifact_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (artifact_id) DO NOTHING
                RETURNING artifact_id
                """,
                (
                    artifact.artifact_id,
                    PEF_PROJECTION_VERSION,
                    artifact.schema_version,
                    artifact.algorithm_version,
                    artifact.ranking_policy_version,
                    str(artifact.configuration_digest),
                    artifact.authority_state,
                    artifact.status.value,
                    artifact.as_of,
                    artifact.control_snapshot_id,
                    artifact.control_receipt_id,
                    receipt.receipt_id,
                    str(receipt.output_digest),
                    artifact.failure_reason,
                    Jsonb(artifact.to_canonical()),
                ),
            )
            artifact_inserted = cur.fetchone()
            if artifact_inserted is None:
                cur.execute(
                    "SELECT receipt_id, output_digest FROM pef_ranking_artifacts "
                    "WHERE artifact_id = %s",
                    (artifact.artifact_id,),
                )
                existing_artifact = cur.fetchone()
                if existing_artifact is None:
                    raise RuntimeError("artifact conflict without existing row")
                if cast(str, existing_artifact[0]) != receipt.receipt_id or cast(
                    str, existing_artifact[1]
                ) != str(receipt.output_digest):
                    raise RuntimeError("artifact identity conflict with different receipt")

    def latest_artifact_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT artifact_id
                FROM pef_ranking_artifacts
                ORDER BY as_of DESC, artifact_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])

    def get_artifact_json(self, artifact_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT artifact_json FROM pef_ranking_artifacts WHERE artifact_id = %s",
                (artifact_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])


class PostgresShadowRunRepository:
    """Append-only persistence for paired shadow experiment runs."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def record_run(self, run: ShadowExperimentRun) -> None:
        if run.experiment_id != PEF_EXPERIMENT_ID:
            raise ValueError("shadow run experiment id mismatch")
        if run.candidate_id != PEF_CANDIDATE_ID:
            raise ValueError("shadow run candidate id mismatch")
        if run.schema_version != SHADOW_SCHEMA_VERSION:
            raise ValueError("shadow run schema version mismatch")
        if run.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("shadow run algorithm version mismatch")
        if run.configuration_digest != PEF_CONFIGURATION_DIGEST:
            raise ValueError("shadow run configuration digest mismatch")
        if run.authority_state != PEF_AUTHORITY_STATE:
            raise ValueError("shadow run authority state mismatch")
        if run.run_digest != sha256_digest(canonical_json_bytes(run.to_canonical())):
            raise ValueError("shadow run digest does not bind its canonical payload")

        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shadow_experiment_runs (
                    run_id, experiment_id, candidate_id, schema_version,
                    algorithm_version, configuration_digest, authority_state,
                    status, as_of, control_snapshot_id, control_receipt_id,
                    candidate_artifact_id, candidate_output_digest,
                    coverage_state, episode_universe_digest, run_digest,
                    failure_reason, run_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO NOTHING
                RETURNING run_id
                """,
                (
                    run.run_id,
                    run.experiment_id,
                    run.candidate_id,
                    run.schema_version,
                    run.algorithm_version,
                    str(run.configuration_digest),
                    run.authority_state,
                    run.status.value,
                    run.as_of,
                    run.control_snapshot_id,
                    run.control_receipt_id,
                    run.candidate_artifact_id,
                    str(run.candidate_output_digest),
                    run.coverage_state.value,
                    str(run.episode_universe_digest),
                    str(run.run_digest),
                    run.failure_reason,
                    Jsonb(run.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT run_digest, status FROM shadow_experiment_runs WHERE run_id = %s",
                    (run.run_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("shadow run conflict without existing row")
                if (
                    cast(str, existing[0]) != str(run.run_digest)
                    or cast(str, existing[1]) != run.status.value
                ):
                    raise RuntimeError("shadow run identity conflict with different digest")

    def latest_run_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT run_id
                FROM shadow_experiment_runs
                ORDER BY as_of DESC, run_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])

    def get_run_json(self, run_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT run_json FROM shadow_experiment_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])


class PostgresCandidateFreezeRepository:
    """Append-only persistence for candidate freeze receipts (R8)."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def record_receipt(self, receipt: CandidateFreezeReceipt) -> None:
        if receipt.candidate_id != PEF_CANDIDATE_ID:
            raise ValueError("candidate freeze receipt candidate id mismatch")
        if receipt.experiment_id != PEF_EXPERIMENT_ID:
            raise ValueError("candidate freeze receipt experiment id mismatch")
        if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("candidate freeze receipt algorithm version mismatch")
        if receipt.configuration_digest != PEF_CONFIGURATION_DIGEST:
            raise ValueError("candidate freeze receipt configuration digest mismatch")
        if receipt.preregistration_path != FREEZE_PREREGISTRATION_PATH:
            raise ValueError("candidate freeze receipt preregistration path mismatch")
        if receipt.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("candidate freeze receipt schema version mismatch")
        if receipt.status is FreezeStatus.DRIFTED and not receipt.drift_reasons:
            raise ValueError("DRIFTED freeze receipt requires explicit drift reasons")
        if receipt.status is FreezeStatus.FROZEN and receipt.drift_reasons:
            raise ValueError("FROZEN freeze receipt cannot carry drift reasons")
        if receipt.receipt_digest != sha256_digest(canonical_json_bytes(receipt.to_canonical())):
            raise ValueError("freeze receipt digest does not bind its canonical payload")

        entry_values: list[dict[str, str]] | None = None
        if receipt.registry_entry_digests is not None:
            entry_values = [
                {"digest": str(entry.digest), "path": entry.path}
                for entry in receipt.registry_entry_digests
            ]
        with self._connection.transaction(), self._connection.cursor() as cur:
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
                ON CONFLICT (receipt_id) DO NOTHING
                RETURNING receipt_id
                """,
                (
                    receipt.receipt_id,
                    receipt.schema_version,
                    receipt.candidate_id,
                    receipt.experiment_id,
                    receipt.algorithm_version,
                    str(receipt.configuration_digest),
                    receipt.status.value,
                    receipt.preregistration_path,
                    str(receipt.preregistration_digest),
                    (
                        None
                        if receipt.preregistration_config_digest is None
                        else str(receipt.preregistration_config_digest)
                    ),
                    receipt.implementation_commit,
                    receipt.implementation_tree_digest,
                    (
                        None
                        if receipt.dependency_lock_digest is None
                        else str(receipt.dependency_lock_digest)
                    ),
                    (
                        None
                        if receipt.source_registry_digest is None
                        else str(receipt.source_registry_digest)
                    ),
                    None if entry_values is None else Jsonb(entry_values),
                    Jsonb(list(receipt.drift_reasons)),
                    str(receipt.receipt_digest),
                    receipt.frozen_at,
                    receipt.verified_at,
                    (
                        None
                        if receipt.original_receipt_digest is None
                        else str(receipt.original_receipt_digest)
                    ),
                    Jsonb(receipt.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT receipt_digest, status FROM candidate_freeze_receipts "
                    "WHERE receipt_id = %s",
                    (receipt.receipt_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("freeze receipt conflict without existing row")
                if (
                    cast(str, existing[0]) != str(receipt.receipt_digest)
                    or cast(str, existing[1]) != receipt.status.value
                ):
                    raise RuntimeError("freeze receipt identity conflict with different digest")

    def latest_receipt_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT receipt_id
                FROM candidate_freeze_receipts
                ORDER BY frozen_at DESC, receipt_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])

    def get_receipt_json(self, receipt_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT receipt_json FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])


class PostgresEvaluationRepository:
    """Append-only persistence for preregistered evaluation receipts (R8)."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def record_receipt(self, receipt: EvaluationReceipt) -> None:
        if receipt.experiment_id != PEF_EXPERIMENT_ID:
            raise ValueError("evaluation receipt experiment id mismatch")
        if receipt.candidate_id != PEF_CANDIDATE_ID:
            raise ValueError("evaluation receipt candidate id mismatch")
        if receipt.schema_version != EVALUATION_SCHEMA_VERSION:
            raise ValueError("evaluation receipt schema version mismatch")
        if receipt.evaluation_algorithm_version != EVALUATION_ALGORITHM_VERSION:
            raise ValueError("evaluation receipt algorithm version mismatch")
        if receipt.candidate_configuration_digest != PEF_CONFIGURATION_DIGEST:
            raise ValueError("evaluation receipt candidate configuration digest mismatch")
        if receipt.evaluation_configuration_digest != EVALUATION_CONFIGURATION_DIGEST:
            raise ValueError("evaluation receipt evaluation configuration digest mismatch")
        if receipt.authority_state != EVALUATION_AUTHORITY_STATE:
            raise ValueError("evaluation receipt authority state mismatch")
        if receipt.receipt_digest != sha256_digest(canonical_json_bytes(receipt.to_canonical())):
            raise ValueError("evaluation receipt digest does not bind its canonical payload")
        if receipt.confirmatory_evidence and receipt.freeze_status is not FreezeStatus.FROZEN:
            raise ValueError("confirmatory evaluation evidence requires a FROZEN freeze receipt")

        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_receipts (
                    evaluation_id, schema_version, experiment_id, candidate_id,
                    evaluation_algorithm_version, candidate_configuration_digest,
                    evaluation_configuration_digest, authority_state, status,
                    as_of, generated_at, candidate_freeze_receipt_id,
                    freeze_receipt_digest, freeze_status, preregistration_digest,
                    receipt_digest, shadow_run_ids, receipt_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (evaluation_id) DO NOTHING
                RETURNING evaluation_id
                """,
                (
                    receipt.evaluation_id,
                    receipt.schema_version,
                    receipt.experiment_id,
                    receipt.candidate_id,
                    receipt.evaluation_algorithm_version,
                    str(receipt.candidate_configuration_digest),
                    str(receipt.evaluation_configuration_digest),
                    receipt.authority_state,
                    receipt.status.value,
                    receipt.as_of,
                    receipt.generated_at,
                    receipt.candidate_freeze_receipt_id,
                    str(receipt.freeze_receipt_digest),
                    receipt.freeze_status.value,
                    str(receipt.preregistration_digest),
                    str(receipt.receipt_digest),
                    Jsonb([binding.run_id for binding in receipt.shadow_runs]),
                    Jsonb(receipt.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT receipt_digest, status FROM evaluation_receipts "
                    "WHERE evaluation_id = %s",
                    (receipt.evaluation_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("evaluation receipt conflict without existing row")
                if (
                    cast(str, existing[0]) != str(receipt.receipt_digest)
                    or cast(str, existing[1]) != receipt.status.value
                ):
                    raise RuntimeError("evaluation receipt conflict with different digest")

    def latest_evaluation_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT evaluation_id
                FROM evaluation_receipts
                ORDER BY as_of DESC, evaluation_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])

    def get_receipt_json(self, evaluation_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT receipt_json FROM evaluation_receipts WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])


class PostgresFeatureVectorRepository:
    """Append-only persistence for EXPERIMENTAL advanced feature vectors (R8)."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def publish_batch(self, batch: FeatureVectorBatch) -> None:
        if batch.schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("feature batch schema version mismatch")
        if batch.algorithm_version != FEATURE_ALGORITHM_VERSION:
            raise ValueError("feature batch algorithm version mismatch")
        if batch.configuration_digest != ADVANCED_FEATURES_CONFIGURATION_DIGEST:
            raise ValueError("feature batch configuration digest mismatch")
        if batch.batch_digest != sha256_digest(canonical_json_bytes(batch.to_canonical())):
            raise ValueError("feature batch digest does not bind its canonical payload")
        if batch.status.value == "RAN" and not batch.vectors:
            raise ValueError("RAN feature batch requires at least one episode vector")

        with self._connection.transaction(), self._connection.cursor() as cur:
            for vector in batch.vectors:
                if vector.vector_digest != sha256_digest(
                    canonical_json_bytes(vector.to_canonical())
                ):
                    raise ValueError("feature vector digest does not bind its payload")
                cur.execute(
                    """
                    INSERT INTO feature_vectors (
                        feature_vector_id, batch_id, batch_digest, episode_id,
                        control_snapshot_id, control_receipt_id,
                        episode_universe_digest, as_of, generated_at,
                        feature_schema_version, algorithm_version,
                        configuration_digest, authority_state, status,
                        vector_digest, vector_json
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (feature_vector_id) DO NOTHING
                    RETURNING feature_vector_id
                    """,
                    (
                        vector.vector_id,
                        batch.batch_id,
                        str(batch.batch_digest),
                        vector.episode_id,
                        batch.control_snapshot_id,
                        batch.control_receipt_id,
                        str(batch.episode_universe_digest),
                        batch.as_of,
                        batch.generated_at,
                        vector.schema_version,
                        vector.algorithm_version,
                        str(vector.configuration_digest),
                        vector.authority_state,
                        batch.status.value,
                        str(vector.vector_digest),
                        Jsonb(vector.to_canonical()),
                    ),
                )
                inserted = cur.fetchone()
                if inserted is None:
                    cur.execute(
                        "SELECT vector_digest, status FROM feature_vectors "
                        "WHERE feature_vector_id = %s",
                        (vector.vector_id,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise RuntimeError("feature vector conflict without existing row")
                    if (
                        cast(str, existing[0]) != str(vector.vector_digest)
                        or cast(str, existing[1]) != batch.status.value
                    ):
                        raise RuntimeError("feature vector conflict with different digest")

    def latest_vector_id(self) -> str | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT feature_vector_id
                FROM feature_vectors
                ORDER BY as_of DESC, feature_vector_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return None if row is None else cast(str, row[0])

    def get_vector_json(self, feature_vector_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT vector_json FROM feature_vectors WHERE feature_vector_id = %s",
                (feature_vector_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])

    def count_for_batch(self, batch_id: str) -> int:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM feature_vectors WHERE batch_id = %s",
                (batch_id,),
            )
            row = cur.fetchone()
        return int(cast(int, row[0])) if row is not None else 0
