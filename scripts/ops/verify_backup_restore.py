from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg import sql

from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresEvaluationRepository,
    PostgresExperimentalAnalysisRepository,
    PostgresFeatureVectorRepository,
    PostgresPefArtifactRepository,
)
from frontier.adapters.postgres.evaluation_store import PostgresEvaluationArtifactStore
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.adapters.postgres.opportunity import PostgresOpportunityRepository
from frontier.adapters.postgres.worker_ops import PostgresWorkerHeartbeatStore
from frontier.application.advanced_features import compute_advanced_features
from frontier.application.advanced_intelligence import run_pef_v0_ranking
from frontier.application.evaluation import evaluate_shadow_experiment_from_persisted
from frontier.application.evaluation_loaders import (
    PersistedEvaluationError,
    PersistedRunRef,
    candidate_freeze_receipt_from_canonical,
    load_paired_snapshot,
)
from frontier.application.experimental_analysis import produce_experimental_analysis
from frontier.application.opportunity_outcome import (
    MembershipArm,
    OpportunityMembershipRecord,
    OpportunityOutcomeService,
)
from frontier.domain.advanced_intelligence import (
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    build_shadow_experiment_run,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.digests import Digest, sha256_digest, sha256_hex
from frontier.domain.experimental_analysis import ExperimentalAnalysisKind
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.observation import (
    DocumentPayload,
    ObservationCandidate,
    ObservationKind,
)
from frontier.domain.opportunity import (
    BlindingState,
    DomainStratum,
    ExperimentAttemptStatus,
    ExperimentRunAttempt,
    OpportunityAnchor,
    OpportunityState,
    OpportunityTransition,
    OutcomeLabel,
    OutcomeResolution,
    fold_transitions,
)
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

# Primary-key column per experiment table (SELECT * column 0 must be the key).
PRIMARY_KEY_COLUMNS: dict[str, str] = {
    "baseline_intelligence_snapshots": "snapshot_id",
    "pef_ranking_artifacts": "artifact_id",
    "shadow_experiment_runs": "run_id",
    "candidate_freeze_receipts": "receipt_id",
    "evaluation_receipts": "evaluation_id",
    "feature_vectors": "feature_vector_id",
    "experimental_analysis_artifacts": "analysis_id",
    "opportunity_anchors": "anchor_id",
    "outcome_resolutions": "anchor_id",
    "opportunity_transitions": "transition_id",
    "experiment_run_attempts": "attempt_id",
    "worker_heartbeats": "worker_id",
    "opportunity_memberships": "membership_id",
}

SOURCE_DATABASE = "frontier_recovery_source"
RESTORE_DATABASE = "frontier_recovery_restore"
POSTGRES_IMAGE = "postgres:18"
ALLOW_ENV = "FRONTIER_RECOVERY_DRILL_ALLOW"
DATABASE_URL_ENV = "FRONTIER_RECOVERY_DATABASE_URL"

RECOVERY_TIME = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
RECOVERY_RUN_ID = UUID("00000000-0000-4000-8000-000000000001")
RECOVERY_SOURCE = SourceContract(
    source_id="ops.recovery-fixture",
    display_name="Recovery fixture",
    acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
    signal_roles=(SignalRole.PRIMARY_EMISSION,),
    transport=SourceTransport.FIXTURE,
    enabled=False,
)
RECOVERY_CANDIDATE = ObservationCandidate(
    source_id=RECOVERY_SOURCE.source_id,
    source_item_key="frontier-backup-restore-probe-v1",
    kind=ObservationKind.DOCUMENT,
    payload=DocumentPayload(
        canonical_url="https://example.invalid/frontier/recovery-probe",
        title="FRONTIER backup restore recovery probe",
        excerpt=None,
        language="en",
        source_metadata={"fixture": "backup-restore-v1"},
    ),
    retrieved_at=RECOVERY_TIME,
    fetch_digest=sha256_digest(b"frontier-recovery-fetch-v1"),
)

# Experimental scientific tables (migrations 0003-0012) that the backup MUST
# carry and the restore MUST preserve byte-for-byte. ``worker_heartbeats`` and
# ``experiment_run_attempts`` are mutable operational state; they are still
# seeded, dumped and verified for exact restoration so heartbeat/attempt
# staleness can never masquerade as a scientific identity reset. Scientific
# identity (digests, run_class, durable_freeze_at) is re-derived from payloads,
# never from operational clocks, so restoring stale heartbeats/attempts cannot
# upgrade a DEV run or reset a durability timestamp.
EXPERIMENT_TABLES: tuple[str, ...] = (
    "baseline_intelligence_snapshots",
    "pef_ranking_artifacts",
    "shadow_experiment_runs",
    "candidate_freeze_receipts",
    "evaluation_receipts",
    "feature_vectors",
    "experimental_analysis_artifacts",
    "opportunity_anchors",
    "outcome_resolutions",
    "opportunity_transitions",
    "experiment_run_attempts",
    "worker_heartbeats",
    "opportunity_memberships",
)

# table -> (primary key column, canonical payload column, stored digest column)
# for digest-recomputation (payload re-digests to the stored column, always).
DIGEST_COLUMNS: dict[str, tuple[str, str]] = {
    "baseline_intelligence_snapshots": ("snapshot_json", "output_digest"),
    "pef_ranking_artifacts": ("artifact_json", "output_digest"),
    "shadow_experiment_runs": ("run_json", "run_digest"),
    "candidate_freeze_receipts": ("receipt_json", "receipt_digest"),
    "evaluation_receipts": ("receipt_json", "receipt_digest"),
    "opportunity_anchors": ("anchor_json", "anchor_digest"),
    "outcome_resolutions": ("resolution_json", "resolution_digest"),
    "opportunity_memberships": ("membership_json", "membership_digest"),
    "feature_vectors": ("vector_json", "vector_digest"),
    "experimental_analysis_artifacts": ("analysis_json", "output_digest"),
}

# Content-derived row ids re-derived after restore from the canonical payload:
# a restored payload that no longer derives its own id is corruption, even when
# the row survived byte-identically.
IDENTITY_PREFIXES: dict[str, str] = {
    "baseline_intelligence_snapshots": "snapshot_",
    "pef_ranking_artifacts": "artifact_",
    "shadow_experiment_runs": "shadowrun_",
    "evaluation_receipts": "evaluation_",
    "opportunity_anchors": "opanchor_",
    "opportunity_memberships": "opmember_",
    "feature_vectors": "featurevector_",
    "experimental_analysis_artifacts": "expanalysis_",
}

PRIMARY_KEYS: dict[str, str] = {
    "baseline_intelligence_snapshots": "snapshot_id",
    "pef_ranking_artifacts": "artifact_id",
    "shadow_experiment_runs": "run_id",
    "candidate_freeze_receipts": "receipt_id",
    "evaluation_receipts": "evaluation_id",
    "feature_vectors": "feature_vector_id",
    "experimental_analysis_artifacts": "analysis_id",
    "opportunity_anchors": "anchor_id",
    "outcome_resolutions": "anchor_id",
    "opportunity_transitions": "transition_id",
    "experiment_run_attempts": "attempt_id",
    "worker_heartbeats": "worker_id",
    "opportunity_memberships": "membership_id",
}

EXPERIMENT_ID = PEF_EXPERIMENT_ID
REGISTRY = Digest("sha256:" + "1" * 64)
DEV_AS_OF = RECOVERY_TIME
DEV_HORIZON = DEV_AS_OF + timedelta(hours=1)
FROZEN_AT = RECOVERY_TIME - timedelta(days=30)
FEATURE_AS_OF = RECOVERY_TIME - timedelta(hours=4)
ANALYSIS_AS_OF = RECOVERY_TIME - timedelta(hours=6)


def _identity_mismatch(table: str, key: str, detail: str) -> RuntimeError:
    return RuntimeError(f"restore identity mismatch [table={table} key={key}]: {detail}")


def _database_url(base_url: str, database: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise RuntimeError("recovery drill requires a PostgreSQL URL")
    if parsed.hostname is None or parsed.username is None:
        raise RuntimeError("recovery drill database URL must include host and user")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database}",
            parsed.query,
            parsed.fragment,
        )
    )


def _sqlalchemy_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = "postgresql+psycopg" if parsed.scheme in {"postgres", "postgresql"} else parsed.scheme
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _connection_parts(database_url: str) -> tuple[str, str, str, int]:
    parsed = urlsplit(database_url)
    if parsed.hostname is None or parsed.username is None:
        raise RuntimeError("recovery drill database URL must include host and user")
    return (
        parsed.hostname,
        unquote(parsed.username),
        unquote(parsed.password or ""),
        parsed.port or 5432,
    )


def _reset_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def _drop_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )


def _migrate(database_url: str) -> None:
    environment = os.environ.copy()
    environment["FRONTIER_DATABASE_URL"] = _sqlalchemy_url(database_url)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=environment)


def _base_tables(database_url: str) -> list[str]:
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
    return sorted(cast(str, row[0]) for row in rows)


# ---------------------------------------------------------------------------
# Experiment state seeding (migrations 0003-0012 covered end-to-end).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExperimentSeed:
    dev_run_id: str
    dev_as_of: datetime
    conf_run_id: str
    conf_as_of: datetime
    conf_durable_freeze_at: datetime
    freeze_receipt_id: str
    evaluation_id: str
    anchor_id: str


def _baseline_fixture(
    *, as_of: datetime, sources: tuple[str, ...], labels: tuple[str, ...]
) -> tuple[tuple[BaselineObservationInput, ...], GroupingProjection]:
    observations = tuple(
        BaselineObservationInput(
            grouping=GroupingInput(
                observation_id="obs_" + f"{label}-{as_of.strftime('%Y%m%dT%H%M%S')}",
                source_id=source,
                source_item_key=f"recovery-{label}",
                kind="DOCUMENT",
                observed_at=as_of - timedelta(minutes=1),
                canonical_url=f"https://example.invalid/recovery/{label}",
                title=f"FRONTIER recovery probe {label} episode title",
                text=None,
                signal_roles=("PRIMARY_EMISSION",),
            ),
            first_reason="SCHEDULED",
            recovered_after_gap=False,
        )
        for label, source in zip(labels, sources, strict=True)
    )
    grouped_ids = tuple(item.observation_id for item in observations)
    projection = GroupingProjection(
        as_of=as_of,
        groups=(EpisodeGroup(group_id=f"grp_{1:064x}", observation_ids=grouped_ids),),
        ambiguous_pairs=(),
        ungrouped_observation_ids=(),
    )
    return observations, projection


def _paired_fixture(
    *, as_of: datetime, source_id: str = "pypi.updates"
) -> tuple[BaselineObservationInput, BaselineObservationInput]:
    live = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=f"obs_recovery_live_{as_of.strftime('%Y%m%dT%H%M%S%f')}",
            source_id=source_id,
            source_item_key=f"recovery-live-{as_of.strftime('%Y%m%dT%H%M%S%f')}",
            kind="DOCUMENT",
            observed_at=as_of - timedelta(minutes=1),
            canonical_url=f"https://example.invalid/recovery/live-{as_of.strftime('%Y%m%dT%H%M%S%f')}",
            title="FRONTIER recovery live episode",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )
    dormant = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=f"obs_recovery_dormant_{as_of.strftime('%Y%m%dT%H%M%S%f')}",
            source_id=source_id,
            source_item_key=f"recovery-dormant-{as_of.strftime('%Y%m%dT%H%M%S%f')}",
            kind="DOCUMENT",
            observed_at=as_of - timedelta(minutes=1),
            canonical_url=(
                f"https://example.invalid/recovery/dormant-{as_of.strftime('%Y%m%dT%H%M%S%f')}"
            ),
            title="FRONTIER recovery dormant episode",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )
    return live, dormant


def _build_and_persist_paired_run(
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    as_of: datetime,
    freeze_receipt_id: str,
    run_class: str,
) -> str:
    """Build and persist one complete paired shadow run through the repos."""
    live, dormant = _paired_fixture(as_of=as_of)
    observations = (live, dormant)
    projection = GroupingProjection(
        as_of=as_of,
        groups=(
            EpisodeGroup(group_id=f"grp_{1:064x}", observation_ids=(live.observation_id,)),
            EpisodeGroup(group_id=f"grp_{2:064x}", observation_ids=(dormant.observation_id,)),
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=(),
    )
    health = BaselineHealthInput(
        source_id="pypi.updates",
        as_of=as_of - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(health,),
        as_of=as_of,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(health,),
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    candidate = run_pef_v0_ranking(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    run: ShadowExperimentRun = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=as_of,
        candidate_freeze_receipt_id=freeze_receipt_id,
    )
    PostgresBaselineIntelligenceRepository(connection).publish_complete_snapshot(snapshot, receipt)
    PostgresPefArtifactRepository(connection).publish_complete_artifact(
        candidate.artifact, candidate.receipt
    )
    PostgresShadowRunPersister(connection).persist(run, run_class=run_class)
    return run.run_id


def _seed_experiment_state(
    database_url: str, observation_id: str, observed_at: datetime
) -> ExperimentSeed:
    """Seed every experimental scientific table (migrations 0003-0012)."""
    with psycopg.connect(database_url) as connection:
        # Freeze receipt (0006): the canonical authority stamps
        # durable_freeze_at inside the insert transaction via the
        # frontier_set_durable_freeze_at BEFORE INSERT trigger.
        dev_freeze: CandidateFreezeReceipt = build_candidate_freeze_receipt(
            FreezeInputs(
                preregistration_digest=Digest("sha256:" + "2" * 64),
                preregistration_config_digest=Digest(
                    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
                ),
                implementation_commit="a" * 64,
                implementation_tree_digest="b" * 64,
                dependency_lock_digest=Digest("sha256:" + "3" * 64),
                source_registry_digest=REGISTRY,
                registry_entry_digests=(),
            ),
            frozen_at=FROZEN_AT,
        )
        conf_freeze: CandidateFreezeReceipt = build_candidate_freeze_receipt(
            FreezeInputs(
                preregistration_digest=Digest("sha256:" + "9" * 64),
                preregistration_config_digest=Digest(
                    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
                ),
                implementation_commit="a" * 64,
                implementation_tree_digest="b" * 64,
                dependency_lock_digest=Digest("sha256:" + "3" * 64),
                source_registry_digest=REGISTRY,
                registry_entry_digests=(),
            ),
            frozen_at=FROZEN_AT,
        )
        PostgresCandidateFreezeRepository(connection, persistence_authorized=True).record_receipt(
            dev_freeze
        )
        PostgresCandidateFreezeRepository(connection, persistence_authorized=True).record_receipt(
            conf_freeze
        )
        durable_row = connection.execute(
            """
            SELECT durable_freeze_at FROM candidate_freeze_receipts
            WHERE receipt_id = %s
            """,
            (conf_freeze.receipt_id,),
        ).fetchone()
        if durable_row is None or not isinstance(durable_row[0], datetime):
            raise RuntimeError("canonical freeze receipt was not stamped durable")
        durable_freeze_at = durable_row[0]

        # DEV run (0005/0004/0003 + projection receipts), fixed boundary.
        dev_run_id = _build_and_persist_paired_run(
            connection,
            as_of=DEV_AS_OF,
            freeze_receipt_id=dev_freeze.receipt_id,
            run_class="DEV",
        )
        # CONFIRMATORY run: strictly after durable_freeze_at (WP2 gate c).
        conf_as_of = durable_freeze_at + timedelta(hours=1)
        conf_run_id = _build_and_persist_paired_run(
            connection,
            as_of=conf_as_of,
            freeze_receipt_id=conf_freeze.receipt_id,
            run_class="CONFIRMATORY",
        )

        # Evaluation receipt (0007): persist the DEV-run evaluation end-to-end
        # through the append-only evaluation repository.
        store = PostgresEvaluationArtifactStore(connection)
        PostgresEvaluationRepository(connection).record_receipt(
            evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(PersistedRunRef(dev_run_id, RECOVERY_TIME),),
                opportunity_groups=(),
                evaluation_horizon=DEV_HORIZON,
                generated_at=DEV_HORIZON,
            )
        )
        evaluation_id = connection.execute(
            """
            SELECT evaluation_id FROM evaluation_receipts
            ORDER BY as_of DESC, evaluation_id DESC LIMIT 1
            """
        ).fetchone()
        if evaluation_id is None:
            raise RuntimeError("evaluation receipt was not persisted for the recovery seed")
        evaluation_id_value = cast(str, evaluation_id[0])

        # Feature vectors (0008) from an independent multi-source fixture.
        feature_observations, feature_projection = _baseline_fixture(
            as_of=FEATURE_AS_OF,
            sources=("s.a", "s.ext", "s.pri"),
            labels=("feature-a", "feature-b", "feature-c"),
        )
        feature_health = tuple(
            BaselineHealthInput(
                source_id=source_id,
                as_of=FEATURE_AS_OF - timedelta(minutes=1),
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
            )
            for source_id in ("s.a", "s.ext", "s.pri")
        )
        feature_snapshot = build_baseline_snapshot(
            feature_observations,
            grouping_projection=feature_projection,
            enabled_source_ids=("s.a", "s.ext", "s.pri"),
            health=feature_health,
            as_of=FEATURE_AS_OF,
        )
        feature_receipt = build_baseline_receipt(
            feature_snapshot,
            observations=feature_observations,
            grouping_projection=feature_projection,
            enabled_source_ids=("s.a", "s.ext", "s.pri"),
            health=feature_health,
            generated_at=FEATURE_AS_OF,
            source_registry_version=REGISTRY,
        )
        PostgresBaselineIntelligenceRepository(connection).publish_complete_snapshot(
            feature_snapshot, feature_receipt
        )
        feature_run = compute_advanced_features(
            feature_observations,
            control_snapshot=feature_snapshot,
            control_receipt=feature_receipt,
            generated_at=FEATURE_AS_OF,
            source_registry_version=REGISTRY,
        )
        PostgresFeatureVectorRepository(connection).publish_batch(feature_run.batch)

        # Experimental analysis artifact (0009), independent fixture.
        analysis_observations, analysis_projection = _baseline_fixture(
            as_of=ANALYSIS_AS_OF,
            sources=("s.pri", "s.ext"),
            labels=("analysis-a", "analysis-b"),
        )
        analysis_health = tuple(
            BaselineHealthInput(
                source_id=source_id,
                as_of=ANALYSIS_AS_OF - timedelta(minutes=1),
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
            )
            for source_id in ("s.pri", "s.ext")
        )
        analysis_snapshot = build_baseline_snapshot(
            analysis_observations,
            grouping_projection=analysis_projection,
            enabled_source_ids=("s.pri", "s.ext"),
            health=analysis_health,
            as_of=ANALYSIS_AS_OF,
        )
        analysis_receipt = build_baseline_receipt(
            analysis_snapshot,
            observations=analysis_observations,
            grouping_projection=analysis_projection,
            enabled_source_ids=("s.pri", "s.ext"),
            health=analysis_health,
            generated_at=ANALYSIS_AS_OF,
            source_registry_version=REGISTRY,
        )
        PostgresBaselineIntelligenceRepository(connection).publish_complete_snapshot(
            analysis_snapshot, analysis_receipt
        )
        analysis_run = produce_experimental_analysis(
            analysis_observations,
            kind=ExperimentalAnalysisKind.CORROBORATION,
            control_snapshot=analysis_snapshot,
            control_receipt=analysis_receipt,
            generated_at=ANALYSIS_AS_OF,
            source_registry_version=REGISTRY,
        )
        PostgresExperimentalAnalysisRepository(connection).record_artifact(
            analysis_run.artifact, input_digest=analysis_run.input_digest
        )

        # Opportunity state (0010/0012): anchor on the recovery probe
        # observation, both arms of membership evidence, and a blinded
        # RESOLVED adjudication appended as transition events.
        anchor = OpportunityAnchor(
            observation_id=observation_id,
            source_id=RECOVERY_SOURCE.source_id,
            as_of=observed_at,
            observed_at=observed_at,
            domain_stratum=DomainStratum.SOFTWARE_PACKAGES,
        )
        repository = PostgresOpportunityRepository(connection)
        service = OpportunityOutcomeService(repository)
        service.register_anchor(anchor)
        service.record_membership(
            OpportunityMembershipRecord(
                anchor_id=anchor.anchor_id,
                experiment_id=EXPERIMENT_ID,
                as_of=observed_at + timedelta(seconds=300),
                arm=MembershipArm.CANDIDATE,
                present=True,
                episode_id="ep_recovery",
                rank_position=1,
            )
        )
        service.record_membership(
            OpportunityMembershipRecord(
                anchor_id=anchor.anchor_id,
                experiment_id=EXPERIMENT_ID,
                as_of=observed_at + timedelta(seconds=300),
                arm=MembershipArm.CONTROL,
                present=False,
            )
        )
        service.resolve(
            anchor,
            OutcomeResolution(
                resolution_state=OpportunityState.RESOLVED,
                label=OutcomeLabel.POSITIVE,
                blinding_state=BlindingState.BLINDED,
                decided_at=observed_at + timedelta(seconds=86400),
                evidence_digest="sha256:" + "c" * 64,
            ),
            reason="blinded automated adjudication resolved POSITIVE",
        )

        # Experiment run attempt (0010/0011, operational) through its full
        # lifecycle, plus one worker heartbeat (mutable operational state).
        attempts = PostgresExperimentAttemptRepository(connection)
        attempt = ExperimentRunAttempt(
            experiment_id=EXPERIMENT_ID,
            as_of=RECOVERY_TIME,
            attempt_no=1,
            status=ExperimentAttemptStatus.PENDING,
        )
        attempts.record_attempt(attempt)
        attempts.claim(
            attempt.attempt_id,
            owner="ops-recovery-drill",
            lease_expires_at=RECOVERY_TIME + timedelta(minutes=10),
            now=RECOVERY_TIME,
        )
        attempts.heartbeat(
            attempt.attempt_id,
            owner="ops-recovery-drill",
            at=RECOVERY_TIME + timedelta(minutes=1),
        )
        attempts.finish(
            attempt.attempt_id,
            owner="ops-recovery-drill",
            status=ExperimentAttemptStatus.DONE,
            detail=f"shadow run {dev_run_id}",
            at=RECOVERY_TIME + timedelta(minutes=2),
        )
        PostgresWorkerHeartbeatStore(connection).upsert_heartbeat(
            worker_id="ops-recovery-drill-worker",
            role="prospective_orchestrator",
            beat_at=RECOVERY_TIME,
            metrics={"probe": "backup-restore"},
        )

        return ExperimentSeed(
            dev_run_id=dev_run_id,
            dev_as_of=RECOVERY_TIME,
            conf_run_id=conf_run_id,
            conf_as_of=conf_as_of,
            conf_durable_freeze_at=durable_freeze_at,
            freeze_receipt_id=conf_freeze.receipt_id,
            evaluation_id=evaluation_id_value,
            anchor_id=anchor.anchor_id,
        )


def _seed_probe(database_url: str) -> tuple[str, str, ExperimentSeed]:
    with psycopg.connect(database_url) as connection:
        store = PostgresEvidenceStore(connection)
        store.upsert_source(RECOVERY_SOURCE)
        run = CollectionRun(
            run_id=RECOVERY_RUN_ID,
            source_id=RECOVERY_SOURCE.source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=RECOVERY_TIME,
        )
        store.start_collection_run(run)
        observation, inserted = store.append_observation(RECOVERY_CANDIDATE, run.run_id)
        if not inserted or observation.observation_id != RECOVERY_CANDIDATE.observation_id:
            raise RuntimeError("canonical recovery probe was not inserted through evidence store")
        store.complete_collection_run(
            run.run_id,
            status=CollectionRunStatus.SUCCESS,
            records_received=1,
            records_accepted=1,
            records_rejected=0,
            duplicates=0,
            failure_code=None,
        )
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None or not isinstance(revision[0], str) or not revision[0]:
            raise RuntimeError("source database has no Alembic head")
        observed_at = connection.execute(
            "SELECT observed_at FROM observations WHERE observation_id = %s",
            (observation.observation_id,),
        ).fetchone()
        if observed_at is None:
            raise RuntimeError("recovery probe observation row vanished")
        seed = _seed_experiment_state(
            database_url,
            observation.observation_id,
            cast(datetime, observed_at[0]),
        )
        return revision[0], observation.observation_id, seed


def _postgres_client_command(
    admin_url: str,
    executable: str,
    database: str,
    *arguments: str,
    interactive: bool = False,
) -> tuple[list[str], dict[str, str]]:
    host, user, password, port = _connection_parts(admin_url)
    environment = os.environ.copy()
    environment["PGPASSWORD"] = password
    command = ["docker", "run"]
    if interactive:
        command.append("-i")
    command.extend(
        [
            "--rm",
            "--network",
            "host",
            "-e",
            "PGPASSWORD",
            POSTGRES_IMAGE,
            executable,
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            database,
            *arguments,
        ]
    )
    return command, environment


def _dump_database(admin_url: str, dump_path: Path) -> int:
    command, environment = _postgres_client_command(
        admin_url,
        "pg_dump",
        SOURCE_DATABASE,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    )
    with dump_path.open("wb") as output:
        subprocess.run(command, check=True, env=environment, stdout=output)
    size = dump_path.stat().st_size
    if size <= 0:
        raise RuntimeError("backup artifact is empty")
    return size


def _dump_table_names(admin_url: str, dump_path: Path) -> tuple[list[str], list[str]]:
    """Parse the dump TOC: (schema TABLE names, TABLE DATA names).

    TOC entries look like ``2151; 0 16444 TABLE DATA public sources frontier``
    (``<oid>; <dep-oids> <kind> <schema> <name> <owner>;``) and
    ``213; 1259 16444 TABLE public sources frontier;``.
    """
    # ``pg_restore --list`` is offline (TOC only) and must not be combined
    # with a -d/--dbname connection target, so build the command without one.
    environment = os.environ.copy()
    environment["PGPASSWORD"] = _connection_parts(admin_url)[2]
    command = [
        "docker",
        "run",
        "-i",
        "--rm",
        "--network",
        "host",
        "-e",
        "PGPASSWORD",
        POSTGRES_IMAGE,
        "pg_restore",
        "--list",
    ]
    with dump_path.open("rb") as backup:
        listing = subprocess.run(
            command, check=True, env=environment, stdin=backup, capture_output=True, text=True
        ).stdout
    schema_tables: list[str] = []
    data_tables: list[str] = []
    for line in listing.splitlines():
        body = line.split(";", 1)[-1].strip().rstrip(";").strip()
        parts = body.split()
        if len(parts) < 5:
            continue
        if parts[2:4] == ["TABLE", "DATA"] and len(parts) > 5:
            data_tables.append(parts[5])
        elif parts[2] == "TABLE":
            schema_tables.append(parts[4])
    return sorted(set(schema_tables)), sorted(set(data_tables))


def _restore_database(admin_url: str, dump_path: Path) -> None:
    """Data-only restore into the alembic-migrated (recreated) target schema."""
    command, environment = _postgres_client_command(
        admin_url,
        "pg_restore",
        RESTORE_DATABASE,
        "--exit-on-error",
        "--data-only",
        # Data-only restore into an already-migrated schema replays COPY rows
        # without the dump's dependency ordering, so referential checks run
        # through triggers must be suspended during the replay (the append-only
        # triggers are re-verified ACTIVE right after restore).
        "--disable-triggers",
        "--no-owner",
        "--no-privileges",
        interactive=True,
    )
    with dump_path.open("rb") as backup:
        subprocess.run(command, check=True, env=environment, stdin=backup)


@dataclass(frozen=True, slots=True)
class IdentityCapture:
    """PRE-backup identity expectations captured before the dump is taken."""

    rows: dict[str, list[tuple[object, ...]]]
    columns: dict[str, list[str]]
    digests: dict[str, dict[str, str]]
    durable_freeze_at: datetime


def _dump_rows(
    connection: psycopg.Connection[tuple[object, ...]], table: str
) -> tuple[list[str], list[tuple[object, ...]]]:
    """SELECT * ordered by the primary key; returns (column names, rows)."""
    query = sql.SQL("SELECT * FROM {} ORDER BY {}").format(
        sql.Identifier(table), sql.Identifier(PRIMARY_KEY_COLUMNS[table])
    )
    with connection.cursor() as cursor:
        cursor.execute(query)
        description = cursor.description
        if description is None:
            raise RuntimeError(f"{table} returned no column description")
        column_names = [column.name for column in description]
        rows = [tuple(row) for row in cursor.fetchall()]
    return column_names, rows


def _clear_alembic_version(database_url: str) -> None:
    """Make room for the dumped ``alembic_version`` row (migrations stamped
    the same head already; replaying the dump row would violate the key)."""
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("DELETE FROM alembic_version")


def _verify_restore(
    database_url: str,
    expected_revision: str,
    observation_id: str,
    seed: ExperimentSeed,
    capture: IdentityCapture,
) -> tuple[dict[str, int], OpportunityState]:
    with psycopg.connect(database_url) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision != (expected_revision,):
            raise _identity_mismatch(
                "alembic_version",
                "head",
                f"restored revision {revision!r} does not equal the backup revision "
                f"{expected_revision!r}",
            )

        restored_source = connection.execute(
            """
            SELECT contract_schema_version, contract_json, contract_digest
            FROM sources
            WHERE source_id = %s
            """,
            (RECOVERY_SOURCE.source_id,),
        ).fetchone()
        expected_source = (
            "source-contract-v1",
            RECOVERY_SOURCE.to_canonical(),
            str(RECOVERY_SOURCE.contract_digest),
        )
        if restored_source != expected_source:
            raise _identity_mismatch("sources", RECOVERY_SOURCE.source_id, "contract mismatch")

        restored = connection.execute(
            """
            SELECT schema_version, canonicalization_version, source_id, source_item_key,
                   kind, payload_json, source_published_at, effective_at,
                   content_digest, fetch_digest
            FROM observations
            WHERE observation_id = %s
            """,
            (observation_id,),
        ).fetchone()
        expected = (
            RECOVERY_CANDIDATE.schema_version,
            RECOVERY_CANDIDATE.canonicalization_version,
            RECOVERY_CANDIDATE.source_id,
            RECOVERY_CANDIDATE.source_item_key,
            RECOVERY_CANDIDATE.kind.value,
            RECOVERY_CANDIDATE.payload.to_canonical(),
            RECOVERY_CANDIDATE.source_published_at,
            RECOVERY_CANDIDATE.effective_at,
            str(RECOVERY_CANDIDATE.content_digest),
            str(RECOVERY_CANDIDATE.fetch_digest),
        )
        if restored != expected:
            raise _identity_mismatch(
                "observations", observation_id, "canonical probe does not match domain identity"
            )

        run_status = connection.execute(
            "SELECT status FROM collection_runs WHERE run_id = %s", (RECOVERY_RUN_ID,)
        ).fetchone()
        if run_status != (CollectionRunStatus.SUCCESS.value,):
            raise _identity_mismatch(
                "collection_runs", str(RECOVERY_RUN_ID), "restored run is not complete"
            )

        # --- Experimental scientific identity (WP10, G9) ----------------------
        row_counts: dict[str, int] = {}
        opportunity_fold: OpportunityState | None = None
        for table in EXPERIMENT_TABLES:
            pre_rows = capture.rows[table]
            post_columns, post_rows = _dump_rows(connection, table)
            if pre_rows != post_rows:
                for pre_row, post_row in zip(pre_rows, post_rows, strict=False):
                    if pre_row != post_row:
                        raise _identity_mismatch(
                            table, str(pre_row[0]), f"row differs after restore: {post_row!r}"
                        )
                raise _identity_mismatch(
                    table,
                    "row-set",
                    f"row count differs: pre={len(pre_rows)} post={len(post_rows)}",
                )
            row_counts[table] = len(post_rows)
            digest_column = DIGEST_COLUMNS.get(table)
            if digest_column is None:
                continue
            payload_name, digest_name = digest_column
            payload_index = post_columns.index(payload_name)
            digest_index = post_columns.index(digest_name)
            for row in post_rows:
                key = str(row[0])
                payload = cast("dict[str, object]", row[payload_index])
                recomputed = "sha256:" + sha256_hex(canonical_json_bytes(payload))
                if recomputed != row[digest_index]:
                    raise _identity_mismatch(
                        table,
                        key,
                        f"payload does not re-digest to stored {digest_name}",
                    )
                if str(row[digest_index]) != capture.digests[table][key]:
                    raise _identity_mismatch(
                        table,
                        key,
                        "restored digest differs from the pre-backup captured digest",
                    )
            prefix = IDENTITY_PREFIXES.get(table)
            if prefix is not None:
                for row in post_rows:
                    payload = cast("dict[str, object]", row[payload_index])
                    derived = prefix + sha256_hex(canonical_json_bytes(payload))
                    if derived != row[0]:
                        raise _identity_mismatch(
                            table, str(row[0]), "payload no longer re-derives the row identity"
                        )

        # Freeze receipts: re-derive receipt_id + receipt_digest from canonical
        # content and compare durable_freeze_at byte-identically (never a
        # restore-time clock value).
        freeze_columns, freeze_rows = _dump_rows(connection, "candidate_freeze_receipts")
        durable_freeze_at: datetime | None = None
        receipt_id_index = freeze_columns.index("receipt_id")
        durable_index = freeze_columns.index("durable_freeze_at")
        json_index = freeze_columns.index("receipt_json")
        for row in freeze_rows:
            key = str(row[receipt_id_index])
            payload = cast("dict[str, object]", row[json_index])
            receipt = candidate_freeze_receipt_from_canonical(payload)
            if receipt.receipt_id != key:
                raise _identity_mismatch(
                    "candidate_freeze_receipts", key, "canonical payload re-derives another id"
                )
            if key == seed.freeze_receipt_id:
                durable_freeze_at = cast("datetime | None", row[durable_index])
        if durable_freeze_at != capture.durable_freeze_at:
            raise _identity_mismatch(
                "candidate_freeze_receipts",
                seed.freeze_receipt_id,
                "durable_freeze_at changed during recovery (scientific clock reset)",
            )

        # Opportunity transitions: recompute each event digest from the stored
        # transition fields (append-only log identity).
        _, transition_rows = _dump_rows(connection, "opportunity_transitions")
        for row in transition_rows:
            transition = OpportunityTransition(
                anchor_id=cast(str, row[1]),
                from_state=None if row[2] is None else OpportunityState(cast(str, row[2])),
                to_state=OpportunityState(cast(str, row[3])),
                reason=cast(str, row[4]),
                occurred_at=cast(datetime, row[5]),
            )
            derived_transition_id = "optrans_" + sha256_hex(
                canonical_json_bytes(transition.to_canonical())
            )
            derived_event_digest = "sha256:" + transition.event_digest_hex
            if derived_transition_id != row[0] or derived_event_digest != row[6]:
                raise _identity_mismatch(
                    "opportunity_transitions",
                    str(row[0]),
                    "event digest does not re-derive from canonical transition content",
                )

        # Scientific identity must not be resettable through operational state:
        # the DEV run stays DEV (a restore-time upgrade to CONFIRMATORY is
        # fatal), the CONFIRMATORY run stays CONFIRMATORY.
        run_class_rows = cast(
            "list[tuple[object, ...]]",
            connection.execute("SELECT run_id, run_class FROM shadow_experiment_runs").fetchall(),
        )
        run_class_by_id = {
            cast(str, run_id): cast(str, run_class) for run_id, run_class in run_class_rows
        }
        if run_class_by_id.get(seed.dev_run_id) != "DEV":
            raise _identity_mismatch(
                "shadow_experiment_runs", seed.dev_run_id, "DEV run did not stay DEV after restore"
            )
        if run_class_by_id.get(seed.conf_run_id) != "CONFIRMATORY":
            raise _identity_mismatch(
                "shadow_experiment_runs",
                seed.conf_run_id,
                "CONFIRMATORY run_class changed during recovery",
            )

        # WP4 persisted loader against the restored DB: reloaded artifacts must
        # reconstruct both run classes (and refuse the DEV run on the
        # confirmatory path).
        store = PostgresEvaluationArtifactStore(connection)
        loaded_dev = load_paired_snapshot(store, seed.dev_run_id, as_of=seed.dev_as_of)
        if loaded_dev.run_class != "DEV":
            raise _identity_mismatch(
                "shadow_experiment_runs", seed.dev_run_id, "loader sees a non-DEV run_class"
            )
        loaded_conf = load_paired_snapshot(
            store, seed.conf_run_id, as_of=seed.conf_as_of, confirmatory=True
        )
        if loaded_conf.run_class != "CONFIRMATORY":
            raise _identity_mismatch(
                "shadow_experiment_runs", seed.conf_run_id, "loader lost the confirmatory class"
            )
        try:
            load_paired_snapshot(store, seed.dev_run_id, as_of=seed.dev_as_of, confirmatory=True)
        except PersistedEvaluationError:
            pass
        else:
            raise _identity_mismatch(
                "shadow_experiment_runs",
                seed.dev_run_id,
                "restored DEV run was accepted on the confirmatory path",
            )

        # Evaluation reconstructibility (dry: no new persistence): re-running
        # the persisted evaluation against the restored artifacts must produce
        # the identical content-derived receipt identity.
        receipt = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(seed.dev_run_id, seed.dev_as_of),),
            opportunity_groups=(),
            evaluation_horizon=DEV_HORIZON,
            generated_at=DEV_HORIZON,
        )
        if receipt.evaluation_id != seed.evaluation_id:
            raise _identity_mismatch(
                "evaluation_receipts",
                seed.evaluation_id,
                "re-evaluated receipt identity differs from the restored receipt",
            )
        evaluation_digest = connection.execute(
            "SELECT receipt_digest FROM evaluation_receipts WHERE evaluation_id = %s",
            (seed.evaluation_id,),
        ).fetchone()
        if evaluation_digest is None or str(receipt.receipt_digest) != cast(
            str, evaluation_digest[0]
        ):
            raise _identity_mismatch(
                "evaluation_receipts",
                seed.evaluation_id,
                "re-evaluated receipt digest differs from the restored row",
            )

        # Fold-projection of the opportunity transitions is identical after
        # restore (fold-from-log, never from mutable columns).
        opportunity_repository = PostgresOpportunityRepository(connection)
        folded = fold_transitions(opportunity_repository.list_transitions(seed.anchor_id))
        if folded is not OpportunityState.RESOLVED:
            raise _identity_mismatch(
                "opportunity_transitions",
                seed.anchor_id,
                f"restored fold is {folded}, not RESOLVED",
            )
        opportunity_fold = folded

        try:
            with connection.transaction():
                connection.execute(
                    "UPDATE observations SET source_item_key = 'mutated' WHERE observation_id = %s",
                    (observation_id,),
                )
        except psycopg.Error as exc:
            if exc.sqlstate != "55000":
                raise RuntimeError(
                    "restored append-only trigger failed with wrong SQLSTATE"
                ) from exc
        else:
            raise RuntimeError("restored canonical observation unexpectedly accepted mutation")

    return row_counts, opportunity_fold


def _capture_identity(database_url: str, seed: ExperimentSeed) -> IdentityCapture:
    """Capture PRE-backup digests and full rows for every experiment table."""
    rows_by_table: dict[str, list[tuple[object, ...]]] = {}
    columns_by_table: dict[str, list[str]] = {}
    digests_by_table: dict[str, dict[str, str]] = {}
    with psycopg.connect(database_url) as connection:
        for table in EXPERIMENT_TABLES:
            column_names, rows = _dump_rows(connection, table)
            rows_by_table[table] = rows
            columns_by_table[table] = column_names
            digest_column = DIGEST_COLUMNS.get(table)
            if digest_column is None:
                continue
            payload_name, digest_name = digest_column
            if payload_name not in column_names or digest_name not in column_names:
                raise RuntimeError(f"{table} is missing its identity columns")
            digest_index = column_names.index(digest_name)
            digests_by_table[table] = {str(row[0]): str(row[digest_index]) for row in rows}
        durable_row = connection.execute(
            "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id = %s",
            (seed.freeze_receipt_id,),
        ).fetchone()
        if durable_row is None or not isinstance(durable_row[0], datetime):
            raise RuntimeError("seed freeze receipt lost its durability stamp before backup")
        durable_freeze_at = durable_row[0]
    return IdentityCapture(
        rows=rows_by_table,
        columns=columns_by_table,
        digests=digests_by_table,
        durable_freeze_at=durable_freeze_at,
    )


def main() -> int:
    if os.environ.get(ALLOW_ENV) != "1":
        raise RuntimeError(f"set {ALLOW_ENV}=1 to run the destructive scratch-database drill")
    admin_url = os.environ.get(DATABASE_URL_ENV)
    if admin_url is None or not admin_url.strip():
        raise RuntimeError(f"{DATABASE_URL_ENV} is required")

    source_url = _database_url(admin_url, SOURCE_DATABASE)
    restore_url = _database_url(admin_url, RESTORE_DATABASE)
    _drop_database(admin_url, RESTORE_DATABASE)
    _drop_database(admin_url, SOURCE_DATABASE)
    try:
        _reset_database(admin_url, SOURCE_DATABASE)
        _migrate(source_url)
        revision, observation_id, seed = _seed_probe(source_url)
        with tempfile.TemporaryDirectory(prefix="frontier-recovery-") as directory:
            dump_path = Path(directory) / "frontier.dump"
            backup_bytes = _dump_database(admin_url, dump_path)
            dump_schema_tables, dump_data_tables = _dump_table_names(admin_url, dump_path)
            missing = sorted(set(EXPERIMENT_TABLES) - set(dump_data_tables))
            if missing:
                raise RuntimeError(
                    "backup artifact is missing experiment tables: " + ", ".join(missing)
                )
            capture = _capture_identity(source_url, seed)
            _reset_database(admin_url, RESTORE_DATABASE)
            _migrate(restore_url)
            migrated_tables = _base_tables(restore_url)
            _clear_alembic_version(restore_url)
            if set(dump_schema_tables) != set(migrated_tables):
                raise RuntimeError(
                    "alembic-migrated schema differs from the backed-up schema: "
                    f"dump-only={sorted(set(dump_schema_tables) - set(migrated_tables))} "
                    f"migration-only={sorted(set(migrated_tables) - set(dump_schema_tables))}"
                )
            _restore_database(admin_url, dump_path)
            row_counts, opportunity_fold = _verify_restore(
                restore_url, revision, observation_id, seed, capture
            )
        print(
            json.dumps(
                {
                    "backup_bytes": backup_bytes,
                    "migration_revision": revision,
                    "observation_id": observation_id,
                    "restore_verified": True,
                    "experiment_tables_present_in_dump": True,
                    "experiment_tables": {
                        table: row_counts.get(table, 0) for table in EXPERIMENT_TABLES
                    },
                    "dev_run_id": seed.dev_run_id,
                    "dev_run_class_after_restore": "DEV",
                    "conf_run_id": seed.conf_run_id,
                    "conf_run_class_after_restore": "CONFIRMATORY",
                    "durable_freeze_at_preserved": True,
                    "evaluation_id": seed.evaluation_id,
                    "anchor_id": seed.anchor_id,
                    "opportunity_fold_after_restore": opportunity_fold.value,
                },
                sort_keys=True,
            )
        )
    finally:
        _drop_database(admin_url, RESTORE_DATABASE)
        _drop_database(admin_url, SOURCE_DATABASE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
