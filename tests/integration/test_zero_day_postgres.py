# ruff: noqa: E402
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb

from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.candidate_freeze_v1 import PostgresCandidateFreezeV1Repository
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.adapters.postgres.zero_day import PostgresZeroDayAdapter
from frontier.application.candidate_freeze_v1 import freeze_candidate_v1
from frontier.application.freeze_publication import CandidateFreezePublication
from frontier.application.pef_v1_confirmatory import build_pef_v1_confirmatory_evidence
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import BaselineHealthInput, BaselineObservationInput, BaselineSnapshot
from frontier.domain.observation import DocumentPayload, ObservationCandidate, ObservationKind
from frontier.domain.pef_v1 import PEF_V1_EXPERIMENT_ID, PEF_V1_PROJECTION_VERSION
from frontier.domain.receipt import ProjectionReceipt
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
REGISTRY = Digest("sha256:" + "9" * 64)
SOURCE_ID = "fixture.zero-day.primary"
ConnectionT = psycopg.Connection[tuple[object, ...]]


def _next_zero_day_boundary(after: datetime) -> datetime:
    step = 6 * 60 * 60
    epoch = int(after.timestamp())
    return datetime.fromtimestamp(((epoch // step) + 1) * step, tz=UTC)


def _store_v1_authority(conn: ConnectionT):
    latest_row = conn.execute(
        "SELECT max(frozen_at) FROM candidate_freeze_receipts WHERE experiment_id = %s",
        (PEF_V1_EXPERIMENT_ID,),
    ).fetchone()
    frozen_at = datetime.now(UTC)
    if (
        latest_row is not None
        and isinstance(latest_row[0], datetime)
        and latest_row[0] >= frozen_at
    ):
        frozen_at = latest_row[0] + timedelta(seconds=1)

    receipt = freeze_candidate_v1(REPO_ROOT, frozen_at=frozen_at)
    repository = PostgresCandidateFreezeV1Repository(conn, persistence_authorized=True)
    repository.record_receipt(receipt)
    durable_at = repository.get_durable_freeze_at(receipt.receipt_id)
    assert durable_at is not None
    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit="c" * 40,
        publication_committer_at=max(durable_at, receipt.frozen_at) + timedelta(seconds=1),
    )
    conn.execute(
        """
        INSERT INTO candidate_freeze_publications (
            receipt_id, schema_version, freeze_receipt_digest,
            implementation_commit, implementation_tree_digest,
            publication_commit, publication_committer_at,
            publication_digest, publication_json
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            receipt.receipt_id,
            publication.schema_version,
            str(publication.freeze_receipt_digest),
            publication.implementation_commit,
            publication.implementation_tree_digest,
            publication.publication_commit,
            publication.publication_committer_at,
            str(publication.publication_digest),
            Jsonb(publication.to_canonical()),
        ),
    )
    return receipt, publication


def _source() -> SourceContract:
    return SourceContract(
        source_id=SOURCE_ID,
        display_name="ZERO-DAY primary fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def _append_document(
    store: PostgresEvidenceStore,
    *,
    source_id: str,
    key: str,
) -> str:
    run = CollectionRun(
        run_id=uuid4(),
        source_id=source_id,
        reason=CollectionReason.SCHEDULED,
        started_at=datetime.now(UTC),
    )
    store.start_collection_run(run)
    candidate = ObservationCandidate(
        source_id=source_id,
        source_item_key=key,
        kind=ObservationKind.DOCUMENT,
        payload=DocumentPayload(
            canonical_url=f"https://example.test/{key}",
            title=key,
            excerpt=key,
        ),
        retrieved_at=datetime.now(UTC),
        fetch_digest=sha256_digest(key.encode()),
    )
    observation, inserted = store.append_observation(candidate, run.run_id)
    assert inserted
    store.complete_collection_run(
        run.run_id,
        status=CollectionRunStatus.SUCCESS,
        records_received=1,
        records_accepted=1,
        records_rejected=0,
        duplicates=0,
        failure_code=None,
    )
    return observation.observation_id


class _EvidenceInputs:
    def __init__(
        self,
        repository: PostgresBaselineIntelligenceRepository,
        *,
        as_of: datetime,
    ) -> None:
        self._observations = tuple(repository.list_baseline_observations_as_of(as_of))
        self._relations = tuple(repository.list_grouping_relations_as_of(as_of))
        self._source_ids = tuple(
            sorted({item.grouping.source_id for item in self._observations})
        )
        self._health = tuple(
            BaselineHealthInput(
                source_id=source_id,
                as_of=as_of - timedelta(seconds=1),
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
            )
            for source_id in self._source_ids
        )

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]:
        return [item for item in self._observations if item.observed_at <= as_of]

    def list_grouping_relations_as_of(self, as_of: datetime):
        del as_of
        return list(self._relations)

    def list_enabled_source_ids(self) -> list[str]:
        return list(self._source_ids)

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        return [item for item in self._health if item.as_of <= as_of]

    def publish_complete_snapshot(
        self,
        snapshot: BaselineSnapshot,
        receipt: ProjectionReceipt,
    ) -> None:
        del snapshot, receipt
        raise AssertionError("PEF_V1 experiment control must not publish canonical baseline state")


def _persist_zero_day_source_rows(
    conn: ConnectionT,
    *,
    evidence,
    persisted_at: datetime,
) -> None:
    receipt = evidence.candidate_receipt
    artifact = evidence.candidate_artifact
    run = evidence.run
    conn.execute(
        """
        INSERT INTO projection_receipts (
            receipt_id, receipt_schema_version, projection_name,
            projection_version, schema_version, algorithm_version,
            ranking_policy_version, configuration_digest,
            source_registry_version, as_of, generated_at,
            input_digest, output_digest, status, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            persisted_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO pef_ranking_artifacts (
            artifact_id, projection_version, schema_version,
            algorithm_version, ranking_policy_version, configuration_digest,
            authority_state, status, as_of, control_snapshot_id,
            control_receipt_id, receipt_id, output_digest, failure_reason,
            artifact_json, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            str(artifact.output_digest),
            artifact.failure_reason,
            Jsonb(artifact.to_canonical()),
            persisted_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO shadow_experiment_runs (
            run_id, experiment_id, candidate_id, schema_version,
            algorithm_version, configuration_digest, authority_state,
            status, as_of, control_snapshot_id, control_receipt_id,
            candidate_artifact_id, candidate_output_digest,
            coverage_state, episode_universe_digest, run_digest,
            failure_reason, run_class, run_json, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            "CONFIRMATORY",
            Jsonb(run.to_canonical()),
            persisted_at,
        ),
    )


def _diagnostic_counts(conn: ConnectionT) -> tuple[int, int, int]:
    row = conn.execute(
        """
        SELECT
          (SELECT count(*) FROM projection_receipts),
          (SELECT count(*) FROM pef_ranking_artifacts),
          (SELECT count(*) FROM shadow_experiment_runs)
        """
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def test_zero_day_adapter_reconstructs_exact_persisted_v1_boundary_and_fails_on_late_input() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        store = PostgresEvidenceStore(conn)
        store.upsert_source(_source())
        first_observation_id = _append_document(
            store,
            source_id=SOURCE_ID,
            key="zero-day-first",
        )
        receipt, publication = _store_v1_authority(conn)
        boundary = _next_zero_day_boundary(publication.publication_committer_at)
        inputs = _EvidenceInputs(
            PostgresBaselineIntelligenceRepository(conn),
            as_of=boundary,
        )
        evidence = build_pef_v1_confirmatory_evidence(
            inputs,
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=receipt,
        )
        assert evidence.run.candidate_freeze_receipt_id == receipt.receipt_id
        assert first_observation_id in {
            observation_id
            for episode in evidence.candidate_artifact.episodes
            for observation_id in episode.observation_ids
        }

        persisted_at = boundary + timedelta(seconds=10)
        _persist_zero_day_source_rows(
            conn,
            evidence=evidence,
            persisted_at=persisted_at,
        )
        before = _diagnostic_counts(conn)
        adapter = PostgresZeroDayAdapter(conn)
        seal = adapter.build_seal_for_boundary(
            as_of=boundary,
            sealed_at=boundary + timedelta(minutes=1),
        )
        after = _diagnostic_counts(conn)

        assert seal is not None
        assert seal.run_id == evidence.run.run_id
        assert seal.candidate_artifact_id == evidence.candidate_artifact.artifact_id
        assert seal.candidate_receipt_id == evidence.candidate_receipt.receipt_id
        assert seal.candidate_freeze_receipt_id == receipt.receipt_id
        assert seal.run_persisted_at == persisted_at
        assert before == after

        missing = adapter.build_seal_for_boundary(
            as_of=boundary + timedelta(hours=6),
            sealed_at=boundary + timedelta(hours=6, minutes=1),
        )
        assert missing is None

        _append_document(
            store,
            source_id=SOURCE_ID,
            key="zero-day-late-historical-input",
        )
        with pytest.raises(ValueError, match="persisted PEF_V1 input digest"):
            adapter.build_seal_for_boundary(
                as_of=boundary,
                sealed_at=boundary + timedelta(minutes=2),
            )
