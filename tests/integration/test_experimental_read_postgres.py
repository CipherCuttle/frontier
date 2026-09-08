# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.experimental_read import (
    PostgresExperimentalReadRepository,
)
from frontier.application.experimental_read import ExperimentalReadService
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import sha256_digest
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
                Jsonb(
                    {
                        "generated_at": "2026-09-05T12:00:00.000000Z",
                        "experiment_id": "advanced-ranking-pef-v0",
                        "candidate_id": "prospective-primary-emission-freshness-v0",
                        "episodes": [
                            {"episode_id": "e1", "rank": 1},
                            {"episode_id": "e2", "rank": 2},
                        ],
                    }
                ),
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
                Jsonb(
                    {
                        "generated_at": "2026-09-05T12:00:00.000000Z",
                        "candidate_freeze_receipt_id": None,
                        "control_transport_state": "OK",
                        "control_freshness_state": "OK",
                        "control_coverage_state": "OK",
                        "control_schema_state": "OK",
                    }
                ),
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
                Jsonb(["shadowrun_" + _hex("shadow-run")]),
                Jsonb({"status_reason": "sample", "verdict": None}),
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
                    Jsonb({"episode_id": f"episode_{index}", "features": []}),
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
                Jsonb({"descriptors": []}),
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
                Jsonb({"episodes": []}),
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
        # Proves the adapter reads the persisted feature_schema_version column
        # (migration 0008) while exposing the public schema_version field.
        assert batch.schema_version == "advanced-features-v0"
        assert batch.algorithm_version == "advanced-transparent-features-v0"

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


def test_overview_exposes_mixed_as_of_consistency() -> None:
    connection, repository = _connect_and_seed()
    try:
        overview = ExperimentalReadService(repository).get_overview()
        assert overview.as_of == "2099-01-01T00:05:00.000000Z"
        assert overview.as_of_consistency == "MIXED_BOUNDARIES"
        assert overview.latest_shadow_run is not None
        assert overview.latest_shadow_run.as_of == "2099-01-01T00:00:00.000000Z"
        assert (
            overview.analysis_artifacts[ExperimentalAnalysisKind.INDICATORS].as_of
            == "2099-01-01T00:05:00.000000Z"
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


# ---------------------------------------------------------------------------
# WP7 (G5): per-episode comparison, detail, history, and status reads against
# real persisted rows.
# ---------------------------------------------------------------------------

WP7_AS_OF = AS_OF - timedelta(days=1)
WP7_GENERATED_AT = WP7_AS_OF
EARLY_WP7_AS_OF = EARLY_AS_OF
CMP_EPISODE = "ep_cmp_1"
CMP_RUN_ID = "shadowrun_" + _hex("cmp-run")
CMP_ARTIFACT_ID = "artifact_" + _hex("cmp-artifact")
CMP_SNAPSHOT_ID = "snapshot_" + _hex("cmp-snapshot")
CMP_EVALUATION_ID = "evaluation_" + _hex("cmp-evaluation")
FAILED_RUN_ID = "shadowrun_" + _hex("failed-run")
FAILED_ARTIFACT_ID = "artifact_" + _hex("failed-artifact")
OTHER_SNAPSHOT_ID = "snapshot_" + _hex("other-snapshot")


def _feature_payload() -> dict[str, object]:
    return {
        "algorithm_version": "advanced-transparent-features-v0",
        "as_of": "2098-12-31T00:00:00.000000Z",
        "authority_state": "EXPERIMENTAL_SHADOW",
        "configuration_digest": "sha256:" + "f" * 64,
        "episode_id": CMP_EPISODE,
        "feature_schema_version": "advanced-features-v0",
        "features": [
            {
                "definition": "6h velocity delta of 1h mentions",
                "name": "velocity_6h_delta",
                "status": "OBSERVED",
                "unit": "mentions",
                "value": 3,
                "window_seconds": 21600,
            }
        ],
        "interpretation": "interpretable features only",
        "observation_ids": ["obs_1"],
        "observation_window_seconds": 3600,
    }


def _seed_wp7_rows(connection: ConnectionT) -> None:
    with connection.cursor() as cur:
        # The projection receipt the WP7 rows bind to (FK target).
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
                "receipt_" + _hex("cmp-receipt"),
                "projection-receipt-v1",
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "pef-ranking-artifact-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                "sha256:" + "2" * 64,
                WP7_AS_OF,
                WP7_GENERATED_AT,
                "sha256:" + "3" * 64,
                "sha256:" + "6" * 64,
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
                CMP_ARTIFACT_ID,
                "prospective-primary-emission-freshness-v0",
                "pef-ranking-artifact-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                WP7_AS_OF,
                CMP_SNAPSHOT_ID,
                "receipt_" + _hex("eval-receipt"),
                "receipt_" + _hex("cmp-receipt"),
                "sha256:" + "6" * 64,
                Jsonb(
                    {
                        "generated_at": "2098-12-31T00:00:00.000000Z",
                        "experiment_id": "advanced-ranking-pef-v0",
                        "candidate_id": "prospective-primary-emission-freshness-v0",
                        "episodes": [
                            {
                                "episode_id": CMP_EPISODE,
                                "rank": 1,
                                "velocity_6h_delta": 3,
                                "mentions_1h": 7,
                            },
                            {"episode_id": "ep_cmp_2", "rank": 2},
                        ],
                    }
                ),
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
                failure_reason, run_class, run_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_SHADOW','RAN',
                    %s,%s,%s,%s,%s,'OK',%s,%s,NULL,'DEV',%s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                CMP_RUN_ID,
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "shadow-experiment-run-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                WP7_AS_OF,
                CMP_SNAPSHOT_ID,
                "receipt_" + _hex("eval-receipt"),
                CMP_ARTIFACT_ID,
                "sha256:" + "6" * 64,
                "sha256:" + "7" * 64,
                "sha256:" + "8" * 64,
                Jsonb(
                    {
                        "generated_at": "2098-12-31T00:00:00.000000Z",
                        "candidate_freeze_receipt_id": None,
                        "control_transport_state": "OK",
                        "control_freshness_state": "OK",
                        "control_coverage_state": "OK",
                        "control_schema_state": "OK",
                        "control_ranking": [
                            {"episode_id": "ep_cmp_2", "rank": 1},
                            {"episode_id": CMP_EPISODE, "rank": 2},
                        ],
                    }
                ),
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
                failure_reason, run_class, run_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,'EXPERIMENTAL_SHADOW','FAILED',
                    %s,%s,%s,%s,%s,'OK',%s,%s,%s,'CONFIRMATORY',%s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                FAILED_RUN_ID,
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "shadow-experiment-run-v0",
                "prospective-primary-emission-freshness-lexicographic-v0",
                "sha256:" + "5" * 64,
                WP7_AS_OF,
                CMP_SNAPSHOT_ID,
                "receipt_" + _hex("eval-receipt"),
                FAILED_ARTIFACT_ID,
                "sha256:" + "6" * 64,
                "sha256:" + "b" * 64,
                "sha256:" + "c" * 64,
                "candidate artifact failed",
                Jsonb(
                    {
                        "generated_at": "2098-12-31T00:00:00.000000Z",
                        "candidate_freeze_receipt_id": None,
                        "control_transport_state": "OK",
                        "control_freshness_state": "OK",
                        "control_coverage_state": "OK",
                        "control_schema_state": "OK",
                    }
                ),
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
                    'COMPLETE',%s,%s,%s,%s,'FROZEN',%s,%s,%s,%s)
            ON CONFLICT (evaluation_id) DO NOTHING
            """,
            (
                CMP_EVALUATION_ID,
                "evaluation-receipt-v0",
                "advanced-ranking-pef-v0",
                "prospective-primary-emission-freshness-v0",
                "pef-v0-evaluation-newcombe-v0",
                "sha256:" + "5" * 64,
                "sha256:" + "9" * 64,
                WP7_AS_OF,
                WP7_GENERATED_AT,
                "freezereceipt_" + _hex("freeze"),
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                "sha256:" + "c" * 64,
                Jsonb([CMP_RUN_ID]),
                Jsonb(
                    {
                        "status_reason": "adequate",
                        "verdict": "NONINFERIOR",
                        "domains": [
                            {
                                "domain": "ML_REPOS",
                                "candidate_arm": {
                                    "precision": "0.5",
                                    "surfaced_resolved": 4,
                                    "positive_surfaced_resolved": 2,
                                },
                                "control_arm": {
                                    "precision": "0.5",
                                    "surfaced_resolved": 4,
                                    "positive_surfaced_resolved": 2,
                                },
                                "difference_lower_bound": "-0.1",
                                "noninferiority_pass": True,
                                "lead_time_median_advantage_seconds": "42",
                                "qualifies_sample_adequacy": True,
                            }
                        ],
                    }
                ),
            ),
        )
        payload = _feature_payload()
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
                "featurevector_" + _hex("cmp-vector"),
                "featurebatch_" + _hex("cmp-batch"),
                "sha256:" + "d" * 64,
                CMP_EPISODE,
                CMP_SNAPSHOT_ID,
                "receipt_" + _hex("eval-receipt"),
                "sha256:" + "e" * 64,
                WP7_AS_OF,
                WP7_GENERATED_AT,
                "advanced-features-v0",
                "advanced-transparent-features-v0",
                "sha256:" + "f" * 64,
                str(sha256_digest(canonical_json_bytes(payload))),
                Jsonb(payload),
            ),
        )


def _connect_wp7() -> tuple[ConnectionT, PostgresExperimentalReadRepository]:
    assert DB_URL is not None
    connection = psycopg.connect(DB_URL, autocommit=True)
    _seed_rows(connection)
    _seed_wp7_rows(connection)
    return connection, PostgresExperimentalReadRepository(connection)


def test_episode_comparison_ranks_and_delta_against_persisted_run() -> None:
    connection, repository = _connect_wp7()
    try:
        comparison = repository.episode_comparison(episode_id=CMP_EPISODE, run_id=CMP_RUN_ID)
        assert comparison is not None
        assert comparison.availability == "AVAILABLE"
        assert comparison.run_id == CMP_RUN_ID
        assert comparison.run_status == "RAN"
        assert comparison.control_snapshot_id == CMP_SNAPSHOT_ID
        assert comparison.candidate_freeze_receipt_id is None
        assert comparison.baseline_rank == 2
        assert comparison.baseline_rank_state == "AVAILABLE"
        assert comparison.candidate_rank == 1
        assert comparison.rank_delta == 1 - 2
        assert comparison.candidate_components is not None
        assert comparison.candidate_components["velocity_6h_delta"] == 3
        assert comparison.evaluation_receipt_id == CMP_EVALUATION_ID
        assert comparison.evaluation_state == "AVAILABLE"
        assert comparison.feature_availability == "AVAILABLE"
        assert comparison.feature_interpretation == "interpretable features only"
        assert comparison.feature_values[0]["name"] == "velocity_6h_delta"
        assert comparison.feature_values[0]["status"] == "OBSERVED"
    finally:
        connection.close()


def test_episode_comparison_absent_episode_never_renders_zero() -> None:
    connection, repository = _connect_wp7()
    try:
        comparison = repository.episode_comparison(episode_id="episode_missing", run_id=CMP_RUN_ID)
        assert comparison is not None
        assert comparison.availability == "NO_DATA"
        assert comparison.baseline_rank is None
        assert comparison.candidate_rank is None
        assert comparison.rank_delta is None
    finally:
        connection.close()


def test_failed_run_comparison_never_renders_as_empty_ranking() -> None:
    """A FAILED run stays explicit: FAILED status, reason, no fabricated ranks."""
    connection, repository = _connect_wp7()
    try:
        comparison = repository.episode_comparison(episode_id=CMP_EPISODE, run_id=FAILED_RUN_ID)
        assert comparison is not None
        assert comparison.run_status == "FAILED"
        assert comparison.run_failure_reason == "candidate artifact failed"
        assert comparison.availability == "NO_DATA"
        assert comparison.baseline_rank is None
        assert comparison.candidate_rank is None
        assert comparison.rank_delta is None
    finally:
        connection.close()


def test_episode_comparison_feature_digest_mismatch_is_unknown() -> None:
    """An unverifiable feature payload is never surfaced (R8).

    Uses a dedicated episode so the tampered row can never pollute the
    neighbouring comparison tests (append-only rows cannot be deleted).
    """
    connection = psycopg.connect(str(DB_URL), autocommit=True)
    bad_episode = "ep_digest_bad"
    try:
        with connection.cursor() as cur:
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
                    "featurevector_" + _hex("bad-vector-v2"),
                    "featurebatch_" + _hex("bad-batch-v2"),
                    "sha256:" + "d" * 64,
                    bad_episode,
                    CMP_SNAPSHOT_ID,
                    "receipt_" + _hex("eval-receipt"),
                    "sha256:" + "e" * 64,
                    WP7_AS_OF + timedelta(seconds=1),
                    WP7_GENERATED_AT,
                    "advanced-features-v0",
                    "advanced-transparent-features-v0",
                    "sha256:" + "f" * 64,
                    "sha256:" + "0" * 64,
                    Jsonb(_feature_payload()),
                ),
            )
        repository = PostgresExperimentalReadRepository(connection)
        comparison = repository.episode_comparison(episode_id=bad_episode, run_id=CMP_RUN_ID)
        assert comparison is not None
        assert comparison.feature_availability == "UNKNOWN"
        assert comparison.feature_values == []
        assert comparison.feature_interpretation_state == "UNAVAILABLE"
    finally:
        connection.close()


def test_episode_comparison_never_mixes_foreign_snapshots() -> None:
    """A feature vector bound to another snapshot is never surfaced."""
    connection = psycopg.connect(str(DB_URL), autocommit=True)
    try:
        _seed_wp7_rows(connection)
        with connection.cursor() as cur:
            # Newer bound-snapshot vector (newer than the bad-digest row the
            # earlier test left behind) so only the identity filter decides.
            fresh = dict(_feature_payload())
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
                    "featurevector_" + _hex("fresh-vector"),
                    "featurebatch_" + _hex("fresh-batch"),
                    "sha256:" + "d" * 64,
                    CMP_EPISODE,
                    CMP_SNAPSHOT_ID,
                    "receipt_" + _hex("eval-receipt"),
                    "sha256:" + "e" * 64,
                    WP7_AS_OF + timedelta(seconds=3),
                    WP7_GENERATED_AT,
                    "advanced-features-v0",
                    "advanced-transparent-features-v0",
                    "sha256:" + "f" * 64,
                    str(sha256_digest(canonical_json_bytes(fresh))),
                    Jsonb(fresh),
                ),
            )
            foreign = dict(_feature_payload())
            foreign["interpretation"] = "foreign-snapshot-payload"
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
                    "featurevector_" + _hex("foreign-vector"),
                    "featurebatch_" + _hex("foreign-batch"),
                    "sha256:" + "d" * 64,
                    CMP_EPISODE,
                    OTHER_SNAPSHOT_ID,
                    "receipt_" + _hex("eval-receipt"),
                    "sha256:" + "e" * 64,
                    # Even later as_of: if the snapshot identity filter were
                    # broken, this foreign-snapshot vector would win.
                    WP7_AS_OF + timedelta(seconds=4),
                    WP7_GENERATED_AT,
                    "advanced-features-v0",
                    "advanced-transparent-features-v0",
                    "sha256:" + "f" * 64,
                    str(sha256_digest(canonical_json_bytes(foreign))),
                    Jsonb(foreign),
                ),
            )
        repository = PostgresExperimentalReadRepository(connection)
        comparison = repository.episode_comparison(episode_id=CMP_EPISODE, run_id=CMP_RUN_ID)
        assert comparison is not None
        assert comparison.control_snapshot_id == CMP_SNAPSHOT_ID
        # The bound snapshot's vector wins; the foreign one never surfaces.
        assert comparison.feature_availability == "AVAILABLE"
        assert comparison.feature_interpretation == "interpretable features only"
    finally:
        connection.close()


def test_run_detail_round_trips_bindings_run_class_and_ranking() -> None:
    connection, repository = _connect_wp7()
    try:
        detail = repository.run_detail(run_id=CMP_RUN_ID)
        assert detail is not None
        assert detail.run_class == "DEV"
        assert detail.coverage_state == "OK"
        assert detail.candidate_artifact_id == CMP_ARTIFACT_ID
        assert detail.control_snapshot_id == CMP_SNAPSHOT_ID
        assert [(entry.episode_id, entry.rank) for entry in detail.control_ranking] == [
            ("ep_cmp_2", 1),
            (CMP_EPISODE, 2),
        ]

        failed = repository.run_detail(run_id=FAILED_RUN_ID)
        assert failed is not None
        assert failed.status == "FAILED"
        assert failed.failure_reason == "candidate artifact failed"
        assert failed.run_class == "CONFIRMATORY"
        assert failed.control_ranking == ()
    finally:
        connection.close()


def test_evaluation_detail_round_trips_domain_rows() -> None:
    connection, repository = _connect_wp7()
    try:
        detail = repository.evaluation_detail(evaluation_id=CMP_EVALUATION_ID)
        assert detail is not None
        assert detail.status == "COMPLETE"
        assert detail.verdict == "NONINFERIOR"
        assert detail.shadow_run_ids == (CMP_RUN_ID,)
        assert len(detail.domains) == 1
        row = detail.domains[0]
        assert row.domain == "ML_REPOS"
        assert row.candidate_precision == "0.5"
        assert row.candidate_surfaced_resolved == 4
        assert row.noninferiority_pass is True
        assert row.median_lead_time_advantage_seconds == "42"
    finally:
        connection.close()


def test_history_rows_are_deterministic_and_honour_horizon() -> None:
    connection, repository = _connect_wp7()
    try:
        runs = repository.experiment_history(limit=10)
        run_ids = [item.run_id for item in runs]
        assert CMP_RUN_ID in run_ids
        assert FAILED_RUN_ID in run_ids
        assert "shadowrun_" + _hex("shadow-run") in run_ids

        evaluations = repository.evaluation_history(limit=10)
        assert CMP_EVALUATION_ID in [item.evaluation_id for item in evaluations]

        early_runs = repository.experiment_history(limit=10, as_of=EARLY_WP7_AS_OF)
        assert early_runs == ()
        assert repository.evaluation_history(limit=10, as_of=EARLY_WP7_AS_OF) == ()
    finally:
        connection.close()


def test_status_inputs_gather_stored_state() -> None:
    connection, repository = _connect_wp7()
    try:
        inputs = repository.experiment_status_inputs()
        assert inputs.window is not None
        assert inputs.window.window_start is not None
        assert inputs.run is not None
        # The legacy 2099-01-01 run is the latest boundary; the WP7 rows are
        # seeded one day older so the shared-database ordering stays stable.
        assert inputs.run.run_id == "shadowrun_" + _hex("shadow-run")
        assert inputs.run.status == "RAN"
        assert inputs.coverage is not None
        assert inputs.evaluation is not None
        assert inputs.evaluation.status == "INSUFFICIENT_SAMPLE"
    finally:
        connection.close()
