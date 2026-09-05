# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.postgres.experimental_read import (
    PostgresExperimentalReadRepository,
)
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

ConnectionT = Connection[tuple[object, ...]]

# Seeded far in the future so these synthetic rows are deterministically the
# latest items regardless of other integration tests sharing the database.
AS_OF = datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC)
GENERATED_AT = AS_OF
EARLY_AS_OF = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)


def _hex(tag: str) -> str:
    return sha256(tag.encode()).hexdigest()


def _seed_rows(connection: ConnectionT) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO projection_receipts (
                receipt_id, receipt_schema_version, projection_name,
                projection_version, schema_version, algorithm_version,
                ranking_policy_version, configuration_digest,
                source_registry_version, as_of, generated_at,
                input_digest, output_digest, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'COMPLETE')
            ON CONFLICT (receipt_id) DO NOTHING
            """,
            (
                "receipt_" + _hex("eval-receipt"),
                "projection-receipt-v1",
                "baseline-intelligence",
                "baseline-intelligence-v0",
                "baseline-intelligence-snapshot-v0",
                "windowed-episode-metrics-v0",
                "naive-episode-activity-v0",
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                AS_OF,
                GENERATED_AT,
                "sha256:" + "3" * 64,
                "sha256:" + "4" * 64,
            ),
        )
        cur.execute(
            """
            INSERT INTO pef_ranking_artifacts (
                artifact_id, projection_version, schema_version,
                algorithm_version, ranking_policy_version, configuration_digest,
                authority_state, status, as_of, control_snapshot_id,
                control_receipt_id, receipt_id, output_digest, failure_reason,
                artifact_json
            ) VALUES (%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_SHADOW','RAN',%s,%s,%s,%s,%s,NULL,%s)
            ON CONFLICT (artifact_id) DO NOTHING
            """,
            (
                "artifact_" + _hex("pef-artifact"),
                "prospective-primary-emission-freshness-v0",
                "pef-ranking-artifact-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                AS_OF,
                "snapshot_" + _hex("control-snapshot"),
                "receipt_" + _hex("eval-receipt"),
                "receipt_" + _hex("eval-receipt"),
                "sha256:" + "6" * 64,
                {
                    "generated_at": "2026-09-05T12:00:00.000000Z",
                    "experiment_id": "advanced-ranking-pef-v0",
                    "candidate_id": "prospective-primary-emission-freshness-v0",
                    "episodes": [
                        {"episode_id": "e1", "rank": 1},
                        {"episode_id": "e2", "rank": 2},
                    ],
                },
            ),
        )
        cur.execute(
            """
            INSERT INTO shadow_experiment_runs (
                run_id, experiment_id, candidate_id, schema_version,
                algorithm_version, configuration_digest, authority_state,
                status, as_of, control_snapshot_id, control_receipt_id,
                candidate_artifact_id, candidate_output_digest,
                coverage_state, episode_universe_digest, run_digest,
                failure_reason, run_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_SHADOW','RAN',
                    %s,%s,%s,%s,%s,'OK',%s,%s,NULL,%s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                "shadowrun_" + _hex("shadow-run"),
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "shadow-experiment-run-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                AS_OF,
                "snapshot_" + _hex("control-snapshot"),
                "receipt_" + _hex("eval-receipt"),
                "artifact_" + _hex("pef-artifact"),
                "sha256:" + "6" * 64,
                "sha256:" + "7" * 64,
                "sha256:" + "8" * 64,
                {
                    "generated_at": "2026-09-05T12:00:00.000000Z",
                    "candidate_freeze_receipt_id": None,
                },
            ),
        )
        cur.execute(
            """
            INSERT INTO evaluation_receipts (
                evaluation_id, schema_version, experiment_id, candidate_id,
                evaluation_algorithm_version, candidate_configuration_digest,
                evaluation_configuration_digest, authority_state, status,
                as_of, generated_at, candidate_freeze_receipt_id,
                freeze_receipt_digest, freeze_status, preregistration_digest,
                receipt_digest, shadow_run_ids, receipt_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_EVALUATION',
                    'INSUFFICIENT_SAMPLE',%s,%s,%s,%s,'FROZEN',%s,%s,%s,%s)
            ON CONFLICT (evaluation_id) DO NOTHING
            """,
            (
                "evaluation_" + _hex("evaluation"),
                "evaluation-receipt-v0",
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "pef-v0-evaluation-newcombe-v0",
                "sha256:" + "5" * 64,
                "sha256:" + "9" * 64,
                AS_OF,
                GENERATED_AT,
                "freezereceipt_" + _hex("freeze"),
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                "sha256:" + "c" * 64,
                ["shadowrun_" + _hex("shadow-run")],
                {"status_reason": "sample", "verdict": None},
            ),
        )
        for index in range(2):
            cur.execute(
                """
                INSERT INTO feature_vectors (
                    feature_vector_id, batch_id, batch_digest, episode_id,
                    control_snapshot_id, control_receipt_id,
                    episode_universe_digest, as_of, generated_at,
                    feature_schema_version, algorithm_version,
                    configuration_digest, authority_state, status,
                    vector_digest, vector_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_SHADOW','RAN',%s,%s)
                ON CONFLICT (feature_vector_id) DO NOTHING
                """,
                (
                    "featurevector_" + _hex(f"vector-{index}"),
                    "featurebatch_" + _hex("batch"),
                    "sha256:" + "d" * 64,
                    f"episode_{index}",
                    "snapshot_" + _hex("control-snapshot"),
                    "receipt_" + _hex("eval-receipt"),
                    "sha256:" + "e" * 64,
                    AS_OF,
                    GENERATED_AT,
                    "advanced-features-v0",
                    "advanced-transparent-features-v0",
                    "sha256:" + "f" * 64,
                    "sha256:" + "0" * 64,
                    {"episode_id": f"episode_{index}", "features": []},
                ),
            )
        cur.execute(
            """
            INSERT INTO experimental_analysis_artifacts (
                analysis_id, artifact_kind, status, authority_state,
                as_of, generated_at, control_snapshot_id, control_receipt_id,
                source_registry_version, episode_universe_digest,
                schema_version, algorithm_version, configuration_digest,
                input_digest, output_digest, analysis_json
            )
            VALUES (%s,'CORROBORATION','DESCRIPTOR','EXPERIMENTAL_SHADOW',
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (analysis_id) DO NOTHING
            """,
            (
                "expanalysis_" + _hex("corroboration"),
                AS_OF,
                GENERATED_AT,
                "snapshot_" + _hex("control-snapshot"),
                "receipt_" + _hex("eval-receipt"),
                "sha256:" + "2" * 64,
                "sha256:" + "e" * 64,
                "experimental-analysis-v0",
                "experimental-analysis-v0",
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "sha256:" + "3" * 64,
                {"descriptors": []},
            ),
        )
        cur.execute(
            """
            INSERT INTO experimental_analysis_artifacts (
                analysis_id, artifact_kind, status, authority_state,
                as_of, generated_at, control_snapshot_id, control_receipt_id,
                source_registry_version, episode_universe_digest,
                schema_version, algorithm_version, configuration_digest,
                input_digest, output_digest, analysis_json
            )
            VALUES (%s,'INDICATORS','INDICATORS','EXPERIMENTAL_SHADOW',
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (analysis_id) DO NOTHING
            """,
            (
                "expanalysis_" + _hex("indicators"),
                AS_OF + timedelta(seconds=300),
                GENERATED_AT,
                "snapshot_" + _hex("control-snapshot"),
                "receipt_" + _hex("eval-receipt"),
                "sha256:" + "2" * 64,
                "sha256:" + "e" * 64,
                "experimental-analysis-v0",
                "experimental-analysis-v0",
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "sha256:" + "3" * 64,
                {"episodes": []},
            ),
        )


def test_latest_summaries_round_trip_identity_fields() -> None:
    connection, repository = _connect_and_seed()
    try:
        run = repository.latest_shadow_run()
        assert run is not None
        assert run.run_id == "shadowrun_" + _hex("shadow-run")
        assert run.authority_state == "EXPERIMENTAL_SHADOW"
        assert run.status == "RAN"
        assert run.control_snapshot_id == "snapshot_" + _hex("control-snapshot")
        assert run.candidate_artifact_id == "artifact_" + _hex("pef-artifact")

        artifact = repository.latest_pef_artifact()
        assert artifact is not None
        assert artifact.artifact_id == "artifact_" + _hex("pef-artifact")
        assert artifact.receipt_id == "receipt_" + _hex("eval-receipt")
        assert artifact.episode_count == 2
        assert artifact.experiment_id == "advanced-ranking-pef-v0"

        receipt = repository.latest_evaluation_receipt()
        assert receipt is not None
        assert receipt.evaluation_id == "evaluation_" + _hex("evaluation")
        assert receipt.status == "INSUFFICIENT_SAMPLE"
        assert receipt.shadow_run_ids == ("shadowrun_" + _hex("shadow-run"),)
        assert receipt.status_reason == "sample"
        assert receipt.verdict is None

        batch = repository.latest_feature_batch()
        assert batch is not None
        assert batch.batch_id == "featurebatch_" + _hex("batch")
        assert batch.vector_count == 2
        assert batch.authority_state == "EXPERIMENTAL_SHADOW"

        analyses = repository.latest_analysis_artifacts()
        assert {
            ExperimentalAnalysisKind.CORROBORATION,
            ExperimentalAnalysisKind.INDICATORS,
        } <= set(analyses)
        assert analyses[ExperimentalAnalysisKind.INDICATORS].as_of == (
            "2099-01-01T00:05:00.000000Z"
        )
        assert (
            analyses[ExperimentalAnalysisKind.CORROBORATION].output_digest == "sha256:" + "3" * 64
        )
    finally:
        connection.close()


def test_as_of_horizon_excludes_later_items() -> None:
    connection, repository = _connect_and_seed()
    try:
        assert repository.latest_shadow_run(as_of=EARLY_AS_OF) is None
        assert repository.latest_pef_artifact(as_of=EARLY_AS_OF) is None
        assert repository.latest_evaluation_receipt(as_of=EARLY_AS_OF) is None
        assert repository.latest_feature_batch(as_of=EARLY_AS_OF) is None
        assert repository.latest_analysis_artifacts(as_of=EARLY_AS_OF) == {}
    finally:
        connection.close()


def _connect_and_seed() -> tuple[ConnectionT, PostgresExperimentalReadRepository]:
    assert DB_URL is not None
    connection = psycopg.connect(DB_URL, autocommit=True)
    _seed_rows(connection)
    return connection, PostgresExperimentalReadRepository(connection)
