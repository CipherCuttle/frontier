from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("psycopg")
import psycopg
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.adapters.postgres.value_observatory_internal_boundary import (
    PostgresInternalBenchmarkBoundaryResolver,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    PefArtifactStatus,
    PefEpisodeRanking,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_CONFIGURATION_DIGEST,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_RECEIPT_SCHEMA_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineEpisode,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
REGISTRY = Digest("sha256:" + "7" * 64)
ConnectionT = psycopg.Connection[tuple[object, ...]]


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def _baseline_episode(label: str, *, rank: int, observed_at: datetime) -> BaselineEpisode:
    return BaselineEpisode(
        rank=rank,
        episode_id=f"episode-{label}",
        observation_ids=(f"obs-{label}",),
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        age_seconds=60,
        evidence_count_total=1,
        prospective_evidence_count=1,
        backfill_evidence_count=0,
        recovered_backlog_evidence_count=0,
        mentions_1h=1,
        mentions_6h=1,
        mentions_24h=1,
        previous_6h=0,
        preprevious_6h=0,
        velocity_6h_delta=1,
        acceleration_6h=1,
        source_ids=("pypi.updates",),
        source_count=1,
        signal_roles=("DISCOVERY",),
        source_role_diversity=1,
    )


def _baseline_boundary(horizon: datetime, label: str) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    snapshot = BaselineSnapshot(
        as_of=horizon,
        transport_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        coverage_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        episodes=(_baseline_episode(label, rank=1, observed_at=horizon - timedelta(minutes=1)),),
    )
    receipt = ProjectionReceipt(
        receipt_schema_version=BASELINE_RECEIPT_SCHEMA_VERSION,
        projection_name=BASELINE_PROJECTION_NAME,
        projection_version=BASELINE_PROJECTION_VERSION,
        schema_version=BASELINE_SCHEMA_VERSION,
        algorithm_version=BASELINE_ALGORITHM_VERSION,
        ranking_policy_version=BASELINE_RANKING_POLICY_VERSION,
        configuration_digest=BASELINE_CONFIGURATION_DIGEST,
        source_registry_version=REGISTRY,
        as_of=horizon,
        generated_at=horizon + timedelta(seconds=1),
        input_digest=digest(label[0]),
        output_digest=sha256_digest(canonical_json_bytes(snapshot.to_canonical())),
        status=ProjectionStatus.COMPLETE,
    )
    return snapshot, receipt


def _pef_episode(label: str) -> PefEpisodeRanking:
    return PefEpisodeRanking(
        rank=1,
        episode_id=f"episode-pef-{label}",
        observation_ids=(f"obs-pef-{label}",),
        has_any_prospective_evidence=True,
        has_prospective_primary_emission=True,
        prospective_last_observed_at=None,
        prospective_age_seconds=None,
        prospective_source_role_diversity=1,
        prospective_evidence_count=1,
        mentions_1h=1,
        mentions_6h=1,
        mentions_24h=1,
        velocity_6h_delta=1,
        acceleration_6h=1,
    )


def _pef_boundary(
    horizon: datetime,
    label: str,
    *,
    failed: bool = False,
) -> tuple[PefV1Artifact, ProjectionReceipt, ShadowExperimentRun]:
    status = PefArtifactStatus.FAILED if failed else PefArtifactStatus.RAN
    failure_reason = "candidate failed" if failed else None
    artifact = PefV1Artifact(
        as_of=horizon,
        control_snapshot_id="snapshot_" + label[0] * 64,
        control_receipt_id="receipt_" + label[-1] * 64,
        source_registry_version=REGISTRY,
        generated_at=horizon + timedelta(seconds=2),
        status=status,
        failure_reason=failure_reason,
        episodes=() if failed else (_pef_episode(label),),
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        grouping_receipt_id="receipt_" + "3" * 64,
    )
    receipt = ProjectionReceipt(
        receipt_schema_version=PEF_RECEIPT_SCHEMA_VERSION,
        projection_name=PEF_V1_PROJECTION_NAME,
        projection_version=PEF_V1_PROJECTION_VERSION,
        schema_version=PEF_SCHEMA_VERSION,
        algorithm_version=PEF_ALGORITHM_VERSION,
        ranking_policy_version=PEF_RANKING_POLICY_VERSION,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        source_registry_version=REGISTRY,
        as_of=horizon,
        generated_at=artifact.generated_at,
        input_digest=digest("4"),
        output_digest=artifact.output_digest,
        status=ProjectionStatus.FAILED if failed else ProjectionStatus.COMPLETE,
    )
    run = ShadowExperimentRun(
        as_of=horizon,
        generated_at=horizon,
        control_snapshot_id=artifact.control_snapshot_id,
        control_receipt_id=artifact.control_receipt_id,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=ShadowRunStatus.FAILED if failed else ShadowRunStatus.RAN,
        episode_universe_digest=digest("6"),
        candidate_artifact_id=artifact.artifact_id,
        candidate_output_digest=artifact.output_digest,
        control_ranking=()
        if failed
        else (ShadowControlArmRanking(rank=1, episode_id=f"episode-control-{label}"),),
        failure_reason=failure_reason,
        experiment_id=PEF_V1_EXPERIMENT_ID,
        candidate_id=PEF_V1_CANDIDATE_ID,
        schema_version=SHADOW_SCHEMA_VERSION,
        algorithm_version=PEF_ALGORITHM_VERSION,
        configuration_digest=PEF_V1_CONFIGURATION_DIGEST,
        authority_state=PEF_AUTHORITY_STATE,
        candidate_freeze_receipt_id="freezereceipt_" + "8" * 64,
    )
    return artifact, receipt, run


def _persist_pef_boundary(
    conn: ConnectionT,
    artifact: PefV1Artifact,
    receipt: ProjectionReceipt,
    run: ShadowExperimentRun,
    *,
    row_candidate_id: str | None = None,
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO projection_receipts (
                receipt_id, receipt_schema_version, projection_name,
                projection_version, schema_version, algorithm_version,
                ranking_policy_version, configuration_digest,
                source_registry_version, as_of, generated_at,
                input_digest, output_digest, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
        cur.execute(
            """
            INSERT INTO pef_ranking_artifacts (
                artifact_id, projection_version, schema_version,
                algorithm_version, ranking_policy_version, configuration_digest,
                authority_state, status, as_of, control_snapshot_id,
                control_receipt_id, receipt_id, output_digest, failure_reason,
                artifact_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                artifact.artifact_id,
                PEF_V1_PROJECTION_VERSION,
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
        cur.execute(
            """
            INSERT INTO shadow_experiment_runs (
                run_id, experiment_id, candidate_id, schema_version,
                algorithm_version, configuration_digest, authority_state,
                status, as_of, control_snapshot_id, control_receipt_id,
                candidate_artifact_id, candidate_output_digest,
                coverage_state, episode_universe_digest, run_digest,
                failure_reason, run_class, run_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                run.run_id,
                run.experiment_id,
                run.candidate_id if row_candidate_id is None else row_candidate_id,
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
                "CONFIRMATORY",
                Jsonb(run.to_canonical()),
            ),
        )


def test_resolver_round_trips_exact_naive_and_pef_boundaries() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 1, 1, 0, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        snapshot, baseline_receipt = _baseline_boundary(horizon, "a")
        PostgresBaselineIntelligenceRepository(conn).publish_complete_snapshot(
            snapshot, baseline_receipt
        )
        artifact, pef_receipt, run = _pef_boundary(horizon, "bc")
        _persist_pef_boundary(conn, artifact, pef_receipt, run)

        resolver = PostgresInternalBenchmarkBoundaryResolver(conn)
        naive = resolver.resolve_naive(horizon)
        pef = resolver.resolve_pef_v1(horizon)

        assert naive is not None
        assert naive.snapshot == snapshot
        assert naive.receipt == baseline_receipt
        assert pef is not None
        assert pef.run_id == run.run_id
        assert pef.artifact == artifact
        assert pef.receipt == pef_receipt


def test_resolver_never_substitutes_prior_or_later_boundary() -> None:
    assert DB_URL is not None
    requested = datetime(2031, 2, 1, 6, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        for horizon, label in (
            (requested - timedelta(hours=6), "d"),
            (requested + timedelta(hours=6), "e"),
        ):
            snapshot, receipt = _baseline_boundary(horizon, label)
            PostgresBaselineIntelligenceRepository(conn).publish_complete_snapshot(
                snapshot, receipt
            )
            artifact, pef_receipt, run = _pef_boundary(horizon, label + "f")
            _persist_pef_boundary(conn, artifact, pef_receipt, run)

        resolver = PostgresInternalBenchmarkBoundaryResolver(conn)
        assert resolver.resolve_naive(requested) is None
        assert resolver.resolve_pef_v1(requested) is None


def test_resolver_fails_closed_on_ambiguous_exact_baseline_boundary() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 3, 1, 12, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        for label in ("a", "b"):
            snapshot, receipt = _baseline_boundary(horizon, label)
            PostgresBaselineIntelligenceRepository(conn).publish_complete_snapshot(
                snapshot, receipt
            )

        with pytest.raises(RuntimeError, match="ambiguous exact baseline"):
            PostgresInternalBenchmarkBoundaryResolver(conn).resolve_naive(horizon)


def test_resolver_fails_closed_on_ambiguous_exact_pef_v1_boundary() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 4, 1, 18, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        for label in ("ab", "cd"):
            artifact, receipt, run = _pef_boundary(horizon, label)
            _persist_pef_boundary(conn, artifact, receipt, run)

        with pytest.raises(RuntimeError, match="ambiguous exact PEF_V1"):
            PostgresInternalBenchmarkBoundaryResolver(conn).resolve_pef_v1(horizon)


def test_resolver_preserves_exact_failed_pef_boundary_instead_of_hiding_it() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 5, 1, 0, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        artifact, receipt, run = _pef_boundary(horizon, "ef", failed=True)
        _persist_pef_boundary(conn, artifact, receipt, run)

        resolved = PostgresInternalBenchmarkBoundaryResolver(conn).resolve_pef_v1(horizon)

        assert resolved is not None
        assert resolved.artifact.status is PefArtifactStatus.FAILED
        assert resolved.artifact.failure_reason == "candidate failed"
        assert resolved.receipt.status is ProjectionStatus.FAILED


def test_resolver_rejects_self_consistent_run_json_that_disagrees_with_row_identity() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 6, 1, 6, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        artifact, receipt, run = _pef_boundary(horizon, "ab")
        forged_run = replace(run, candidate_id="forged-candidate")
        _persist_pef_boundary(
            conn,
            artifact,
            receipt,
            forged_run,
            row_candidate_id=PEF_V1_CANDIDATE_ID,
        )

        with pytest.raises(RuntimeError, match="row does not bind canonical run payload"):
            PostgresInternalBenchmarkBoundaryResolver(conn).resolve_pef_v1(horizon)


def test_resolver_rejects_wrong_pef_receipt_schema_family() -> None:
    assert DB_URL is not None
    horizon = datetime(2031, 7, 1, 12, 0, tzinfo=UTC)
    with psycopg.connect(DB_URL) as conn:
        artifact, receipt, run = _pef_boundary(horizon, "cd")
        wrong_receipt = replace(receipt, receipt_schema_version="wrong-receipt-v0")
        _persist_pef_boundary(conn, artifact, wrong_receipt, run)

        with pytest.raises(RuntimeError, match="receipt frozen identity mismatch"):
            PostgresInternalBenchmarkBoundaryResolver(conn).resolve_pef_v1(horizon)
