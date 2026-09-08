# ruff: noqa: E402
"""Persisted evaluation E2E against real PostgreSQL (WP4, G2).

Persists a paired shadow run through the existing append-only repositories,
evaluates it END-TO-END from the persisted artifacts via
``evaluate_shadow_experiment_from_persisted``, and verifies the
``evaluation_receipts`` row plus idempotency. Also proves the storage layer
itself refuses artifact tampering (append-only trigger) and that a DEV run
cannot feed a confirmatory evaluation.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresEvaluationRepository,
    PostgresPefArtifactRepository,
)
from frontier.adapters.postgres.evaluation_store import (
    PostgresEvaluationArtifactStore,
)
from frontier.adapters.postgres.experiment_attempts import (
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
from frontier.adapters.postgres.intelligence import (
    PostgresBaselineIntelligenceRepository,
)
from frontier.application.advanced_intelligence import (
    PefRankingRun,
    run_pef_v0_ranking,
)
from frontier.application.evaluation import (
    PairedSnapshot,
    evaluate_shadow_experiment_from_persisted,
)
from frontier.application.evaluation_loaders import (
    PersistedEvaluationError,
    PersistedRunRef,
    load_paired_snapshot,
)
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.domain.advanced_intelligence import (
    ShadowExperimentRun,
    build_shadow_experiment_run,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import EvaluationStatus
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

# Session-unique 300s-aligned boundary so repeated sessions never collide.
_SESSION_OFFSET = (int(uuid.uuid4().hex[:8], 16) % 24_000) * 300
BOUNDARY = datetime.fromtimestamp(
    (int(datetime.now(tz=UTC).timestamp()) // 300) * 300 - _SESSION_OFFSET, tz=UTC
)
FROZEN_AT = BOUNDARY - timedelta(days=30)
REGISTRY = Digest("sha256:" + "1" * 64)

ConnectionT = Connection[tuple[object, ...]]


@pytest.fixture()
def conn() -> Iterator[ConnectionT]:
    assert DB_URL is not None
    connection = psycopg.connect(DB_URL)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _persisted_paired(
    conn: ConnectionT, *, as_of: datetime, run_class: str
) -> tuple[
    BaselineSnapshot,
    PefRankingRun,
    ShadowExperimentRun,
    CandidateFreezeReceipt,
]:
    """Build and PERSIST one complete paired snapshot through the repos."""
    live = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id="obs_" + uuid.uuid4().hex,
            source_id="pypi.updates",
            source_item_key=f"live-{uuid.uuid4().hex}",
            kind="DOCUMENT",
            observed_at=as_of - timedelta(minutes=1),
            canonical_url=f"https://example.test/live-{uuid.uuid4().hex}",
            title="Persisted evaluation live episode",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )
    dormant = replace(
        live,
        grouping=replace(
            live.grouping,
            observation_id="obs_" + uuid.uuid4().hex,
            source_item_key=f"dormant-{uuid.uuid4().hex}",
            canonical_url=f"https://example.test/dormant-{uuid.uuid4().hex}",
        ),
    )
    observations = (live, dormant)
    grouped = ((live.observation_id,), (dormant.observation_id,))
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    projection = GroupingProjection(
        as_of=as_of,
        groups=tuple(
            EpisodeGroup(group_id=f"grp_{index:064x}", observation_ids=tuple(sorted(group)))
            for index, group in enumerate(grouped, start=1)
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=tuple(
            sorted(
                item.observation_id
                for item in observations
                if item.observation_id not in grouped_ids
            )
        ),
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
    freeze = build_candidate_freeze_receipt(
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
    run = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=as_of,
        candidate_freeze_receipt_id=freeze.receipt_id,
    )
    PostgresBaselineIntelligenceRepository(conn).publish_complete_snapshot(snapshot, receipt)
    PostgresPefArtifactRepository(conn).publish_complete_artifact(
        candidate.artifact, candidate.receipt
    )
    PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(freeze)
    PostgresShadowRunPersister(conn).persist(run, run_class=run_class)
    return snapshot, candidate, run, freeze


def _publish_freeze(
    conn: ConnectionT,
    freeze: CandidateFreezeReceipt,
    *,
    publication_offset: timedelta = timedelta(seconds=1),
) -> CandidateFreezePublication:
    row = conn.execute(
        "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id=%s",
        (freeze.receipt_id,),
    ).fetchone()
    assert row is not None and row[0] is not None
    durable = cast(datetime, row[0])
    assert freeze.implementation_commit is not None
    assert freeze.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=freeze.receipt_id,
        freeze_receipt_digest=freeze.receipt_digest,
        implementation_commit=freeze.implementation_commit,
        implementation_tree_digest=freeze.implementation_tree_digest,
        publication_commit="c" * 64,
        publication_committer_at=durable + publication_offset,
    )
    PostgresCandidateFreezePublicationRepository(
        conn, persistence_authorized=True
    ).record_publication(publication)
    return publication


def _future_boundary() -> datetime:
    now = datetime.now(UTC) + timedelta(days=1)
    epoch = int(now.timestamp())
    return datetime.fromtimestamp((epoch // 300 + 1) * 300, tz=UTC)


def test_persisted_run_evaluates_end_to_end_and_appends_receipt(conn: ConnectionT) -> None:
    snapshot, candidate, run, _ = _persisted_paired(conn, as_of=BOUNDARY, run_class="DEV")
    store = PostgresEvaluationArtifactStore(conn)
    loaded = load_paired_snapshot(store, run.run_id, as_of=BOUNDARY)
    assert loaded.snapshot == PairedSnapshot(
        run=run,
        candidate_rank_by_episode={
            episode.episode_id: episode.rank for episode in candidate.artifact.episodes
        },
        episode_memberships={
            episode.episode_id: episode.observation_ids for episode in snapshot.episodes
        },
    )
    horizon = BOUNDARY + timedelta(hours=1)
    receipt = evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=(PersistedRunRef(run.run_id, BOUNDARY),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        receipt_repository=PostgresEvaluationRepository(conn),
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, freeze_status, candidate_freeze_receipt_id "
            "FROM evaluation_receipts WHERE evaluation_id = %s",
            (receipt.evaluation_id,),
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM evaluation_receipts WHERE candidate_freeze_receipt_id = %s",
            (run.candidate_freeze_receipt_id,),
        )
        count_row = cur.fetchone()
        assert count_row is not None
        count = int(cast(int, count_row[0]))
    assert row is not None
    assert row[0] == receipt.status.value == EvaluationStatus.INSUFFICIENT_SAMPLE.value
    assert row[1] == "FROZEN"
    assert row[2] == run.candidate_freeze_receipt_id
    assert count == 1
    # Idempotent re-evaluation: same content-derived receipt id, no new row.
    again = evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=(PersistedRunRef(run.run_id, BOUNDARY),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        receipt_repository=PostgresEvaluationRepository(conn),
    )
    assert again.evaluation_id == receipt.evaluation_id
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM evaluation_receipts WHERE evaluation_id = %s",
            (receipt.evaluation_id,),
        )
        count_again = cur.fetchone()
        assert count_again is not None
        assert int(cast(int, count_again[0])) == 1


def test_artifact_tampering_is_refused_and_loader_stays_intact(conn: ConnectionT) -> None:
    _, candidate, run, _ = _persisted_paired(conn, as_of=BOUNDARY, run_class="DEV")
    artifact_id = candidate.artifact.artifact_id
    with conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_json FROM pef_ranking_artifacts WHERE artifact_id = %s", (artifact_id,)
        )
        original_row = cur.fetchone()
        assert original_row is not None
        original_json = original_row[0]
    # The append-only trigger refuses ANY mutation of the stored artifact:
    # tampered artifacts can never enter the store (storage-layer refusal).
    with pytest.raises(psycopg.errors.Error), conn.cursor() as cur:
        cur.execute(
            "UPDATE pef_ranking_artifacts SET artifact_json = '{}'::jsonb WHERE artifact_id = %s",
            (artifact_id,),
        )
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_json FROM pef_ranking_artifacts WHERE artifact_id = %s",
            (artifact_id,),
        )
        intact_row = cur.fetchone()
        assert intact_row is not None
        assert intact_row[0] == original_json
    # The digest-recomputing loader accepts only the intact artifact.
    store = PostgresEvaluationArtifactStore(conn)
    loaded = load_paired_snapshot(store, run.run_id, as_of=BOUNDARY)
    assert loaded.run == run


def test_dev_run_cannot_feed_a_confirmatory_evaluation(conn: ConnectionT) -> None:
    _, _, run, _ = _persisted_paired(conn, as_of=BOUNDARY + timedelta(seconds=300), run_class="DEV")
    store = PostgresEvaluationArtifactStore(conn)
    with pytest.raises(PersistedEvaluationError, match="confirmatory"):
        load_paired_snapshot(
            store, run.run_id, as_of=BOUNDARY + timedelta(seconds=300), confirmatory=True
        )
    # The diagnostic path stays explicit and is never confirmatory-complete.
    horizon = BOUNDARY + timedelta(seconds=300) + timedelta(hours=1)
    receipt = evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=(PersistedRunRef(run.run_id, BOUNDARY + timedelta(seconds=300)),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        confirmatory=False,
        durable_freeze_at=None,
    )
    assert receipt.status is not EvaluationStatus.COMPLETE
    assert receipt.confirmatory_evidence is False


def test_persisted_confirmatory_infers_authority_when_caller_false(conn: ConnectionT) -> None:
    as_of = _future_boundary()
    _, _, run, freeze = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    publication = _publish_freeze(conn, freeze)
    assert as_of >= first_confirmatory_boundary(publication.publication_committer_at)
    horizon = as_of + timedelta(hours=1)
    receipt = evaluate_shadow_experiment_from_persisted(
        store=PostgresEvaluationArtifactStore(conn),
        runs=(PersistedRunRef(run.run_id, as_of),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        confirmatory=False,
    )
    assert receipt.status is EvaluationStatus.INSUFFICIENT_SAMPLE
    assert receipt.status is not EvaluationStatus.INVALID_DRIFT


def test_persisted_confirmatory_missing_publication_fails_closed(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=300)
    _, _, run, _ = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    with pytest.raises(PersistedEvaluationError, match="no persisted Git publication"):
        evaluate_shadow_experiment_from_persisted(
            store=PostgresEvaluationArtifactStore(conn),
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            confirmatory=False,
        )


def test_caller_cannot_escalate_dev_or_forge_authority_timestamps(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=600)
    _, _, run, _ = _persisted_paired(conn, as_of=as_of, run_class="DEV")
    store = PostgresEvaluationArtifactStore(conn)
    with pytest.raises(PersistedEvaluationError, match="cannot escalate"):
        evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            confirmatory=True,
        )
    with pytest.raises(
        PersistedEvaluationError, match="cannot accept confirmatory authority timestamps"
    ):
        evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            durable_freeze_at=as_of - timedelta(days=1),
            window_start=as_of,
        )


def test_persisted_confirmatory_rejects_forged_caller_clock_assertion(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=900)
    _, _, run, freeze = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    publication = _publish_freeze(conn, freeze)
    start = first_confirmatory_boundary(publication.publication_committer_at)
    with pytest.raises(PersistedEvaluationError, match="window_start assertion"):
        evaluate_shadow_experiment_from_persisted(
            store=PostgresEvaluationArtifactStore(conn),
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            window_start=start + timedelta(seconds=300),
        )
