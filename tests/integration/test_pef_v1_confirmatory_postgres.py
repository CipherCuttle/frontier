from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
import psycopg
from psycopg.types.json import Jsonb

from frontier.adapters.postgres.advanced_intelligence import PostgresShadowRunRepository
from frontier.adapters.postgres.candidate_freeze_v1 import PostgresCandidateFreezeV1Repository
from frontier.adapters.postgres.pef_v1_confirmatory import (
    PostgresPefV1ConfirmatoryPersistence,
    PostgresPefV1FreezeBindingResolver,
)
from frontier.application.candidate_freeze_v1 import freeze_candidate_v1
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.application.pef_v1_confirmatory import (
    PefV1ConfirmatoryEvidence,
    build_pef_v1_confirmatory_evidence,
)
from frontier.domain.advanced_intelligence import (
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import FreezeStatus
from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import PEF_V1_EXPERIMENT_ID, PEF_V1_PROJECTION_VERSION
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
REGISTRY = Digest("sha256:" + "9" * 64)
ConnectionT = psycopg.Connection[tuple[object, ...]]


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


class _Repository:
    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of
        self.observations = (
            BaselineObservationInput(
                grouping=GroupingInput(
                    observation_id=_obs_id("confirmatory-package"),
                    source_id="pypi.updates",
                    source_item_key="confirmatory-package",
                    kind="DOCUMENT",
                    observed_at=as_of - timedelta(minutes=1),
                    canonical_url="https://example.test/confirmatory-package",
                    title="confirmatory package",
                    text="confirmatory package",
                    signal_roles=("PRIMARY_EMISSION",),
                ),
                first_reason="SCHEDULED",
                recovered_after_gap=False,
            ),
        )
        self.health = (
            BaselineHealthInput(
                source_id="pypi.updates",
                as_of=as_of - timedelta(seconds=1),
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
            ),
        )
        self.published: list[tuple[BaselineSnapshot, ProjectionReceipt]] = []

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]:
        return [item for item in self.observations if item.observed_at <= as_of]

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        del as_of
        return []

    def list_enabled_source_ids(self) -> list[str]:
        return ["pypi.updates"]

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        return [item for item in self.health if item.as_of <= as_of]

    def publish_complete_snapshot(
        self,
        snapshot: BaselineSnapshot,
        receipt: ProjectionReceipt,
    ) -> None:
        self.published.append((snapshot, receipt))


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
    assert receipt.status is FreezeStatus.FROZEN
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
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidate_freeze_publications (
                receipt_id, schema_version, freeze_receipt_digest,
                implementation_commit, implementation_tree_digest,
                publication_commit, publication_committer_at,
                publication_digest, publication_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (receipt_id) DO NOTHING
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


def _v0_run(as_of: datetime) -> ShadowExperimentRun:
    return ShadowExperimentRun(
        as_of=as_of,
        generated_at=as_of,
        control_snapshot_id="snapshot_" + "1" * 64,
        control_receipt_id="receipt_" + "2" * 64,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=ShadowRunStatus.RAN,
        episode_universe_digest=Digest("sha256:" + "3" * 64),
        candidate_artifact_id="artifact_" + "4" * 64,
        candidate_output_digest=Digest("sha256:" + "5" * 64),
        control_ranking=(ShadowControlArmRanking(rank=1, episode_id="episode-v0-retained"),),
    )


def test_v1_confirmatory_persistence_is_freeze_bound_and_v0_isolated() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication = _store_v1_authority(conn)
        boundary = first_confirmatory_boundary(publication.publication_committer_at)
        repository = _Repository(boundary)
        evidence = build_pef_v1_confirmatory_evidence(
            repository,
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=receipt,
        )
        assert repository.published == []

        PostgresShadowRunRepository(conn).record_run(
            _v0_run(boundary),
            run_class="CONFIRMATORY",
        )
        persistence = PostgresPefV1ConfirmatoryPersistence(conn)
        assert persistence.latest_run_id_and_class_for_as_of(boundary) is None

        forged_id = "freezereceipt_" + "f" * 64
        forged = replace(
            evidence,
            run=replace(evidence.run, candidate_freeze_receipt_id=forged_id),
        )
        with pytest.raises(RuntimeError, match="expected freeze is not latest canonical authority"):
            persistence.persist(forged, expected_freeze_receipt_id=forged_id)

        run_id = persistence.persist(
            evidence,
            expected_freeze_receipt_id=receipt.receipt_id,
        )
        assert run_id == evidence.run.run_id
        assert persistence.latest_run_id_and_class_for_as_of(boundary) == (
            run_id,
            "CONFIRMATORY",
            evidence.run.status.value,
        )

        binding = PostgresPefV1FreezeBindingResolver(conn).latest_binding()
        assert binding is not None
        assert binding.receipt == receipt
        assert binding.publication_commit == publication.publication_commit
        assert binding.publication_digest == publication.publication_digest

        rows = conn.execute(
            """
            SELECT experiment_id, run_class,
                   run_json->>'candidate_freeze_receipt_id'
            FROM shadow_experiment_runs
            WHERE as_of = %s
            ORDER BY experiment_id
            """,
            (boundary,),
        ).fetchall()
        assert any(row[0] == "advanced-ranking-pef-v0" for row in rows)
        assert any(
            row[0] == PEF_V1_EXPERIMENT_ID
            and row[1] == "CONFIRMATORY"
            and row[2] == receipt.receipt_id
            for row in rows
        )
        baseline_count = conn.execute(
            "SELECT count(*) FROM baseline_intelligence_snapshots WHERE snapshot_id = %s",
            (evidence.run.control_snapshot_id,),
        ).fetchone()
        assert baseline_count == (0,)
        artifact = conn.execute(
            """
            SELECT projection_version, configuration_digest,
                   artifact_json->>'experiment_id'
            FROM pef_ranking_artifacts WHERE artifact_id = %s
            """,
            (evidence.candidate_artifact.artifact_id,),
        ).fetchone()
        assert artifact == (
            PEF_V1_PROJECTION_VERSION,
            str(evidence.candidate_artifact.configuration_digest),
            PEF_V1_EXPERIMENT_ID,
        )


def test_v1_persistence_rejects_wrong_expected_freeze_without_partial_evidence() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication = _store_v1_authority(conn)
        boundary = first_confirmatory_boundary(publication.publication_committer_at)
        evidence = build_pef_v1_confirmatory_evidence(
            _Repository(boundary),
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=receipt,
        )
        wrong = "freezereceipt_" + "e" * 64
        forged_evidence = replace(
            evidence,
            run=replace(evidence.run, candidate_freeze_receipt_id=wrong),
        )
        with pytest.raises(RuntimeError, match="not latest canonical authority"):
            PostgresPefV1ConfirmatoryPersistence(conn).persist(
                forged_evidence,
                expected_freeze_receipt_id=wrong,
            )
        assert conn.execute(
            "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
            (forged_evidence.run.run_id,),
        ).fetchone() == (0,)


def test_newer_v1_freeze_supersedes_old_authority_before_run_commit() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        old_receipt, publication = _store_v1_authority(conn)
        boundary = first_confirmatory_boundary(publication.publication_committer_at)
        evidence = build_pef_v1_confirmatory_evidence(
            _Repository(boundary),
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=old_receipt,
        )
        newer_receipt = freeze_candidate_v1(
            REPO_ROOT,
            frozen_at=old_receipt.frozen_at + timedelta(seconds=1),
        )
        assert newer_receipt.receipt_id != old_receipt.receipt_id
        PostgresCandidateFreezeV1Repository(
            conn,
            persistence_authorized=True,
        ).record_receipt(newer_receipt)

        with pytest.raises(RuntimeError, match="not latest canonical authority"):
            PostgresPefV1ConfirmatoryPersistence(conn).persist(
                evidence,
                expected_freeze_receipt_id=old_receipt.receipt_id,
            )
        assert conn.execute(
            "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
            (evidence.run.run_id,),
        ).fetchone() == (0,)


def test_v1_persistence_rejects_candidate_receipt_status_mismatch() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication = _store_v1_authority(conn)
        boundary = first_confirmatory_boundary(publication.publication_committer_at)
        evidence = build_pef_v1_confirmatory_evidence(
            _Repository(boundary),
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=receipt,
        )
        assert evidence.candidate_receipt.status is ProjectionStatus.COMPLETE
        forged_evidence = replace(
            evidence,
            candidate_receipt=replace(
                evidence.candidate_receipt,
                status=ProjectionStatus.FAILED,
            ),
        )

        with pytest.raises(ValueError, match="status does not match candidate artifact"):
            PostgresPefV1ConfirmatoryPersistence(conn).persist(
                forged_evidence,
                expected_freeze_receipt_id=receipt.receipt_id,
            )
        assert conn.execute(
            "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
            (forged_evidence.run.run_id,),
        ).fetchone() == (0,)


def test_v1_persistence_rejects_candidate_receipt_provenance_forgery() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as conn:
        receipt, publication = _store_v1_authority(conn)
        boundary = first_confirmatory_boundary(publication.publication_committer_at)
        evidence = build_pef_v1_confirmatory_evidence(
            _Repository(boundary),
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=REGISTRY,
            freeze_receipt=receipt,
        )
        forged_receipts = (
            replace(
                evidence.candidate_receipt,
                input_digest=Digest("sha256:" + "8" * 64),
            ),
            replace(
                evidence.candidate_receipt,
                generated_at=evidence.candidate_receipt.generated_at + timedelta(seconds=1),
            ),
            replace(
                evidence.candidate_receipt,
                receipt_schema_version="projection-receipt-forged",
            ),
        )
        persistence = PostgresPefV1ConfirmatoryPersistence(conn)
        for forged_receipt in forged_receipts:
            forged_evidence = replace(evidence, candidate_receipt=forged_receipt)
            with pytest.raises(ValueError, match="full candidate input provenance"):
                persistence.persist(
                    forged_evidence,
                    expected_freeze_receipt_id=receipt.receipt_id,
                )
            assert conn.execute(
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                (forged_evidence.run.run_id,),
            ).fetchone() == (0,)
